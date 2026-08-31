"""Account-free battle-shaped W0 workload capsules.

A capsule binds a verified live workload's resource shape to an offline
semantic combat replay. It never launches Android, injects input, or claims
live-device qualification.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from .workload_capture import (
    AUTO_COMBAT_WORKLOAD_BASELINE_SCHEMA,
    sha256_file,
    verify_workload_capture,
)

BATTLE_CAPSULE_SCHEMA = "alas-headless.battle-capsule/v1"
BATTLE_CAPSULE_RUN_SCHEMA = "alas-headless.battle-capsule-run/v1"
BATTLE_CAPSULE_ALAS_REPLAY_SCHEMA = (
    "alas-headless.battle-capsule-alas-replay/v1"
)


class BattleCapsuleError(ValueError):
    """Capsule provenance or execution contract failure."""


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise BattleCapsuleError(f"JSON root must be an object: {path}")
    return value


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1)
    return float(ordered[max(0, index)])


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BattleCapsuleError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise BattleCapsuleError(f"{field} must be finite and nonnegative")
    return result


def _sha256_json(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_trace(path: Path) -> list[Mapping[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BattleCapsuleError(
                    f"runtime trace line {line_number} is malformed: {exc}"
                ) from exc
            if not isinstance(value, Mapping):
                raise BattleCapsuleError(
                    f"runtime trace line {line_number} is not an object"
                )
            records.append(value)
    return records


def _build_steps(
    records: Sequence[Mapping[str, Any]], duration: float, bucket_size: float
) -> list[MutableMapping[str, Any]]:
    count = max(1, math.ceil(duration / bucket_size))
    steps: list[MutableMapping[str, Any]] = []
    for index in range(count):
        steps.append(
            {
                "offset_seconds": round(index * bucket_size, 6),
                "duration_seconds": round(
                    max(0.0, min(bucket_size, duration - index * bucket_size)), 6
                ),
                "host_runtime": {
                    "cpu_cores": 0.0,
                    "rss_bytes": 0,
                    "read_bytes": 0,
                    "write_bytes": 0,
                },
                "game": {"cpu_cores": 0.0, "rss_bytes": 0, "threads": 0},
                "controller": {"cpu_cores": 0.0, "rss_bytes": 0},
                "observer": {
                    "requests": 0,
                    "state_requests": 0,
                    "ui_requests": 0,
                    "duration_ms_p95": 0.0,
                    "response_bytes_p95": 0.0,
                },
            }
        )
    start_ns = int(records[0]["monotonic_ns"])
    samples: dict[str, list[Mapping[str, Any]]] = {
        "host_runtime": [],
        "game": [],
        "controller": [],
    }
    observer: dict[int, dict[str, list[float]]] = {}
    for record in records:
        elapsed = max(0.0, (int(record["monotonic_ns"]) - start_ns) / 1e9)
        bucket = min(count - 1, int(elapsed / bucket_size))
        event = record.get("event")
        fields = record.get("fields")
        if not isinstance(fields, Mapping):
            continue
        if event == "runtime.process.sample":
            scope = fields.get("scope")
            if scope == "host-runtime":
                samples["host_runtime"].append(record)
            elif scope == "game":
                samples["game"].append(record)
        elif event == "runtime.controller.process.sample":
            samples["controller"].append(record)
        elif event == "runtime.game.process.identity":
            steps[bucket]["game"]["threads"] = int(fields.get("threads", 0) or 0)
        elif event == "observer.request":
            values = observer.setdefault(bucket, {"duration": [], "bytes": []})
            target = steps[bucket]["observer"]
            target["requests"] += 1
            if fields.get("endpoint") == "/v1/state":
                target["state_requests"] += 1
            elif fields.get("endpoint") == "/v1/ui":
                target["ui_requests"] += 1
            values["duration"].append(float(record.get("duration_ns") or 0) / 1e6)
            values["bytes"].append(float(fields.get("response_bytes") or 0))

    for scope, scope_samples in samples.items():
        previous: Mapping[str, Any] | None = None
        for record in scope_samples:
            fields = record["fields"]
            elapsed = max(0.0, (int(record["monotonic_ns"]) - start_ns) / 1e9)
            target = steps[min(count - 1, int(elapsed / bucket_size))][scope]
            target["rss_bytes"] = int(fields.get("rss_bytes", 0) or 0)
            if previous is not None:
                prior = previous["fields"]
                delta_ns = int(record["monotonic_ns"]) - int(previous["monotonic_ns"])
                if delta_ns > 0:
                    cpu_delta = max(
                        0,
                        int(fields.get("cpu_time_ns", 0))
                        - int(prior.get("cpu_time_ns", 0)),
                    )
                    target["cpu_cores"] = round(cpu_delta / delta_ns, 6)
                if scope == "host_runtime":
                    target["read_bytes"] += max(
                        0,
                        int(fields.get("read_bytes", 0))
                        - int(prior.get("read_bytes", 0)),
                    )
                    target["write_bytes"] += max(
                        0,
                        int(fields.get("write_bytes", 0))
                        - int(prior.get("write_bytes", 0)),
                    )
            previous = record

    carry_rss = {"host_runtime": 0, "game": 0, "controller": 0}
    carry_threads = 0
    for index, step in enumerate(steps):
        for scope in carry_rss:
            current = int(step[scope]["rss_bytes"])
            if current:
                carry_rss[scope] = current
            else:
                step[scope]["rss_bytes"] = carry_rss[scope]
        if step["game"]["threads"]:
            carry_threads = int(step["game"]["threads"])
        else:
            step["game"]["threads"] = carry_threads
        values = observer.get(index, {"duration": [], "bytes": []})
        step["observer"]["duration_ms_p95"] = round(
            _percentile(values["duration"], 0.95), 3
        )
        step["observer"]["response_bytes_p95"] = round(
            _percentile(values["bytes"], 0.95), 3
        )
    rss_floor = min(
        (int(step["game"]["rss_bytes"]) for step in steps if step["game"]["rss_bytes"]),
        default=0,
    )
    for step in steps:
        step["game"]["working_set_delta_bytes"] = max(
            0, int(step["game"]["rss_bytes"]) - rss_floor
        )
    return steps


def compile_battle_capsule(
    capture_directory: Path, replay_path: Path, *, bucket_seconds: float = 1.0
) -> Mapping[str, Any]:
    capture_directory = capture_directory.resolve()
    replay_path = replay_path.resolve()
    bucket_seconds = _number(bucket_seconds, "bucket_seconds")
    if bucket_seconds <= 0:
        raise BattleCapsuleError("bucket_seconds must be greater than zero")
    verification = verify_workload_capture(capture_directory)
    if verification.get("passed") is not True:
        raise BattleCapsuleError(
            "source workload capture did not verify: "
            + "; ".join(str(item) for item in verification.get("errors", []))
        )

    baseline_path = capture_directory / "baseline-summary.json"
    result_path = capture_directory / "result.json"
    trace_path = capture_directory / "runtime-trace.jsonl"
    receipt_path = capture_directory / "resource-receipt.json"
    baseline = _read_json(baseline_path)
    result = _read_json(result_path)
    replay = _read_json(replay_path)
    if baseline.get("schema") != AUTO_COMBAT_WORKLOAD_BASELINE_SCHEMA:
        raise BattleCapsuleError("source is not an official-auto combat baseline")
    if replay.get("passed") is not True or replay.get("semantic_combat_flow") is not True:
        raise BattleCapsuleError("semantic replay did not pass its combat-flow contract")
    if replay.get("input_injected") is not False:
        raise BattleCapsuleError("semantic replay injected input")
    if replay.get("production_ready") is not False:
        raise BattleCapsuleError("semantic replay readiness classification changed")
    if replay.get("pixel_accesses") not in (None, []):
        raise BattleCapsuleError("semantic replay used pixel access")

    phase = baseline.get("official_auto_phase")
    if not isinstance(phase, Mapping):
        raise BattleCapsuleError("official-auto phase is absent")
    start, end = phase.get("start"), phase.get("result")
    if not isinstance(start, Mapping) or not isinstance(end, Mapping):
        raise BattleCapsuleError("official-auto phase boundaries are absent")
    start_sequence = int(start.get("trace_sequence", 0))
    end_sequence = int(end.get("trace_sequence", 0))
    if start_sequence <= 0 or end_sequence < start_sequence:
        raise BattleCapsuleError("official-auto trace sequence is invalid")
    duration = _number(phase.get("elapsed_seconds"), "official_auto_phase.elapsed_seconds")
    if duration <= 0:
        raise BattleCapsuleError("official-auto phase duration must be positive")
    records = [
        record
        for record in _read_trace(trace_path)
        if start_sequence <= int(record.get("sequence", 0)) <= end_sequence
    ]
    if not records:
        raise BattleCapsuleError("official-auto trace interval is empty")

    capsule: Mapping[str, Any] = {
        "schema": BATTLE_CAPSULE_SCHEMA,
        "qualification_scope": "W0-account-free-harness-only",
        "account_required": False,
        "android_input_injected": False,
        "synthetic_pressure": True,
        "duration_seconds": round(duration, 6),
        "bucket_seconds": round(bucket_seconds, 6),
        "source": {
            "run_id": baseline.get("run_id"),
            "workload": baseline.get("workload"),
            "trace_sequence": {"start": start_sequence, "end": end_sequence},
            "artifacts": {
                "baseline-summary.json": sha256_file(baseline_path),
                "result.json": sha256_file(result_path),
                "runtime-trace.jsonl": sha256_file(trace_path),
                "resource-receipt.json": sha256_file(receipt_path),
            },
            "historical_resource_observation": baseline.get("resource_observation"),
            "source_dirty": result.get("source", {}).get("dirty"),
        },
        "semantic_replay": {
            "schema": replay.get("schema"),
            "sha256": sha256_file(replay_path),
            "profile_id": replay.get("profile_id"),
            "upstream_alas_commit": replay.get("upstream_alas_commit"),
            "task_config_sha256": replay.get("task_config_sha256"),
            "observer_fixture_sha256": replay.get(
                "observer_fixture_sha256"
            ),
            "stage": replay.get("stage"),
            "target": replay.get("target"),
            "phases": replay.get("phases"),
            "virtual_actions": replay.get("virtual_actions"),
            "input_injected": False,
            "production_ready": False,
            "call_plan": {
                "device_methods": replay.get("device_methods", []),
                "observation_requests": replay.get("observation_requests", []),
                "direct_typed_state_reads": replay.get(
                    "direct_typed_state_reads", []
                ),
                "resource_query_count": replay.get("resource_query_count", 0),
                "resource_query_names": replay.get("resource_query_names", []),
                "virtual_sleeps": replay.get("virtual_sleeps", []),
            },
        },
        "aggregate": {
            name: phase.get(name, {})
            for name in ("host_runtime", "game", "controller", "observer")
        },
        "steps": _build_steps(records, duration, bucket_seconds),
        "known_limitations": [
            "The source resource curve was recorded during one real account battle; replaying it uses no account.",
            "Host-proxy pressure does not reproduce Android guest scheduling, GPU/driver behavior, PSI, zram, or major faults.",
            "This W0 capsule validates workload shape and harness behavior only; it cannot promote W1 live battle support.",
        ],
    }
    validate_battle_capsule(capsule)
    return capsule


def validate_battle_capsule(capsule: Mapping[str, Any]) -> None:
    expected = {
        "schema": BATTLE_CAPSULE_SCHEMA,
        "qualification_scope": "W0-account-free-harness-only",
        "account_required": False,
        "android_input_injected": False,
        "synthetic_pressure": True,
    }
    for field, value in expected.items():
        if capsule.get(field) != value:
            raise BattleCapsuleError(f"battle capsule {field} changed")
    if _number(capsule.get("duration_seconds"), "duration_seconds") <= 0:
        raise BattleCapsuleError("duration_seconds must be positive")
    source, replay, steps = capsule.get("source"), capsule.get("semantic_replay"), capsule.get("steps")
    if not isinstance(source, Mapping) or not isinstance(replay, Mapping):
        raise BattleCapsuleError("capsule provenance is absent")
    if replay.get("input_injected") is not False or replay.get("production_ready") is not False:
        raise BattleCapsuleError("semantic replay boundary changed")
    call_plan = replay.get("call_plan")
    if not isinstance(call_plan, Mapping):
        raise BattleCapsuleError("semantic replay call plan is absent")
    for field in ("device_methods", "observation_requests", "direct_typed_state_reads"):
        if not isinstance(call_plan.get(field), list):
            raise BattleCapsuleError(f"semantic replay {field} is malformed")
    artifacts = source.get("artifacts")
    if not isinstance(artifacts, Mapping) or len(artifacts) < 4:
        raise BattleCapsuleError("source artifact hashes are absent")
    for digest in artifacts.values():
        if not isinstance(digest, str) or len(digest) != 64:
            raise BattleCapsuleError("source artifact hash is malformed")
    if not isinstance(steps, list) or not steps:
        raise BattleCapsuleError("capsule steps are absent")
    previous = -1.0
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise BattleCapsuleError(f"step {index} is not an object")
        offset = _number(step.get("offset_seconds"), f"step {index} offset")
        _number(step.get("duration_seconds"), f"step {index} duration")
        if offset <= previous:
            raise BattleCapsuleError("capsule step offsets are not increasing")
        previous = offset


def load_battle_capsule(path: Path) -> Mapping[str, Any]:
    capsule = _read_json(path.resolve())
    validate_battle_capsule(capsule)
    return capsule


def plan_battle_capsule(capsule: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_battle_capsule(capsule)
    steps = capsule["steps"]
    return {
        "schema": BATTLE_CAPSULE_RUN_SCHEMA,
        "mode": "plan",
        "passed": True,
        "account_used": False,
        "android_input_injected": False,
        "qualification_scope": "W0-account-free-harness-only",
        "capsule_sha256": _sha256_json(capsule),
        "planned_duration_seconds": capsule["duration_seconds"],
        "steps": len(steps),
        "peaks": {
            "host_cpu_cores": max(float(s["host_runtime"]["cpu_cores"]) for s in steps),
            "game_rss_bytes": max(int(s["game"]["rss_bytes"]) for s in steps),
            "working_set_delta_bytes": max(int(s["game"]["working_set_delta_bytes"]) for s in steps),
        },
        "semantic_call_plan": {
            "device_methods": len(capsule["semantic_replay"]["call_plan"]["device_methods"]),
            "observation_requests": len(
                capsule["semantic_replay"]["call_plan"]["observation_requests"]
            ),
            "direct_typed_state_reads": len(
                capsule["semantic_replay"]["call_plan"]["direct_typed_state_reads"]
            ),
            "resource_queries": capsule["semantic_replay"]["call_plan"].get(
                "resource_query_count", 0
            ),
        },
        "claim": "schedule verified; no pressure executed",
    }


def run_host_proxy(
    capsule: Mapping[str, Any], *, time_scale: float, max_memory_mib: int,
    max_cpu_core: float, max_write_mib: int
) -> Mapping[str, Any]:
    """Execute a bounded single-process proxy; never touch Android."""
    validate_battle_capsule(capsule)
    time_scale = _number(time_scale, "time_scale")
    max_cpu_core = _number(max_cpu_core, "max_cpu_core")
    if not 0 < time_scale <= 1:
        raise BattleCapsuleError("time_scale must be in (0, 1]")
    if max_cpu_core > 1:
        raise BattleCapsuleError("host proxy supports at most one CPU core")
    if max_memory_mib < 0 or max_write_mib < 0:
        raise BattleCapsuleError("host proxy resource caps must be nonnegative")
    memory_cap, write_cap = max_memory_mib * 1024 * 1024, max_write_mib * 1024 * 1024
    memory, bytes_written = bytearray(), 0
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="alas-battle-capsule-") as temporary:
        with (Path(temporary) / "pressure.bin").open("wb") as scratch:
            for step in capsule["steps"]:
                target = min(memory_cap, int(step["game"]["working_set_delta_bytes"]))
                if target > len(memory):
                    memory.extend(b"\0" * (target - len(memory)))
                    for offset in range(0, len(memory), 4096):
                        memory[offset] = (memory[offset] + 1) % 256
                elif target < len(memory):
                    del memory[target:]
                allowed = min(
                    int(step["host_runtime"].get("write_bytes", 0)),
                    max(0, write_cap - bytes_written),
                )
                chunk = b"\0" * min(1024 * 1024, allowed)
                remaining = allowed
                while remaining:
                    count = min(remaining, len(chunk))
                    scratch.write(chunk[:count])
                    remaining -= count
                bytes_written += allowed
                scaled = float(step["duration_seconds"]) * time_scale
                duty = min(max_cpu_core, float(step["host_runtime"]["cpu_cores"]))
                step_start = time.perf_counter()
                busy_until = step_start + scaled * duty
                step_end = step_start + scaled
                payload = b"alas-headless-battle-capsule"
                while time.perf_counter() < busy_until:
                    payload = hashlib.sha256(payload).digest()
                if step_end > time.perf_counter():
                    time.sleep(step_end - time.perf_counter())
    return {
        "schema": BATTLE_CAPSULE_RUN_SCHEMA,
        "mode": "host-proxy",
        "passed": True,
        "account_used": False,
        "android_input_injected": False,
        "qualification_scope": "W0-account-free-harness-only",
        "capsule_sha256": _sha256_json(capsule),
        "planned_duration_seconds": capsule["duration_seconds"],
        "executed_elapsed_seconds": round(time.perf_counter() - started, 6),
        "steps": len(capsule["steps"]),
        "caps": {"time_scale": time_scale, "max_memory_mib": max_memory_mib,
                 "max_cpu_core": max_cpu_core, "max_write_mib": max_write_mib},
        "observed": {"scratch_bytes_written": bytes_written},
        "claim": "bounded host proxy executed; Android guest and W1 remain unqualified",
    }


def verify_offline_alas_replay(
    capsule: Mapping[str, Any],
    replay_result: Mapping[str, Any],
    defensive_preflight: Mapping[str, Any],
    *,
    replay_sha256: str,
) -> Mapping[str, Any]:
    """Bind a fresh original-ALAS replay to one verified battle capsule.

    The caller owns construction of the disposable patched ALAS checkout.
    This function validates the replay result and reports the remaining live
    re-entry blockers. It never treats a passing offline replay as authority
    to use an account or dispatch Android input.
    """

    validate_battle_capsule(capsule)
    source = capsule["source"]
    stored = capsule["semantic_replay"]
    workload = source.get("workload")
    if not isinstance(workload, Mapping):
        raise BattleCapsuleError("capsule workload identity is absent")
    if (
        workload.get("task") != "Main"
        or workload.get("mode") != "normal"
        or workload.get("stage") != replay_result.get("stage")
    ):
        raise BattleCapsuleError(
            "source workload and ALAS replay identity differ"
        )

    identity_fields = (
        "schema",
        "profile_id",
        "upstream_alas_commit",
        "task_config_sha256",
        "observer_fixture_sha256",
        "stage",
        "target",
    )
    for field in identity_fields:
        if not stored.get(field) or stored.get(field) != replay_result.get(field):
            raise BattleCapsuleError(
                f"semantic replay identity changed: {field}"
            )
    if (
        not isinstance(replay_sha256, str)
        or len(replay_sha256) != 64
        or replay_sha256 != stored.get("sha256")
    ):
        raise BattleCapsuleError("semantic replay artifact hash changed")
    if (
        replay_result.get("schema")
        != "alas-headless.g36-normal-observer-replay/v1"
        or replay_result.get("passed") is not True
        or replay_result.get("semantic_combat_flow") is not True
        or replay_result.get("input_injected") is not False
        or replay_result.get("capability_promotion") is not False
        or replay_result.get("production_ready") is not False
        or replay_result.get("pixel_accesses") != []
        or replay_result.get("source_restored") is not True
        or replay_result.get("projected_map_unchanged") is not True
    ):
        raise BattleCapsuleError("fresh original-ALAS replay boundary changed")

    for field in ("phases", "virtual_actions"):
        if replay_result.get(field) != stored.get(field):
            raise BattleCapsuleError(f"semantic replay {field} changed")
    call_plan = stored["call_plan"]
    for field in (
        "device_methods",
        "observation_requests",
        "direct_typed_state_reads",
        "resource_query_count",
        "resource_query_names",
        "virtual_sleeps",
    ):
        if replay_result.get(field) != call_plan.get(field):
            raise BattleCapsuleError(
                f"semantic replay call plan changed: {field}"
            )
    battle = replay_result.get("battle")
    ammo = replay_result.get("ammo")
    if (
        not isinstance(battle, list)
        or len(battle) != 2
        or battle[1] != battle[0] + 1
        or not isinstance(ammo, list)
        or len(ammo) != 2
        or ammo[1] != ammo[0] - 1
    ):
        raise BattleCapsuleError("original ALAS replay post-state changed")

    if (
        defensive_preflight.get("schema")
        != "alas-headless.g36-defensive-preflight/v1"
        or defensive_preflight.get("profile_id")
        != replay_result.get("profile_id")
        or defensive_preflight.get("upstream_alas_commit")
        != replay_result.get("upstream_alas_commit")
        or defensive_preflight.get("task_config_sha256")
        != replay_result.get("task_config_sha256")
        or defensive_preflight.get("normal_replay_sha256")
        != _sha256_json(replay_result)
        or defensive_preflight.get("closure_complete") is not True
        or defensive_preflight.get("input_injected") is not False
        or defensive_preflight.get("capability_promotion") is not False
        or defensive_preflight.get("production_ready") is not False
    ):
        raise BattleCapsuleError("defensive preflight boundary changed")
    rows = defensive_preflight.get("rows")
    if not isinstance(rows, list) or not rows:
        raise BattleCapsuleError("defensive preflight rows are absent")
    blocked_roots = []
    roots = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or row.get("implicit_unknown") is not False:
            raise BattleCapsuleError(
                f"defensive preflight row {index} is not explicit"
            )
        root = row.get("root")
        if not isinstance(root, str) or not root:
            raise BattleCapsuleError(
                f"defensive preflight row {index} root is absent"
            )
        roots.append(root)
        resolution = row.get("resolution")
        if resolution == "qualification-stop":
            if row.get("recovery_before_grid") is not True:
                raise BattleCapsuleError(
                    "defensive qualification stop moved past the grid click"
                )
            blocked_roots.append(
                {
                    "root": root,
                    "missing_resources": list(row.get("missing_resources", ())),
                    "missing_actions": list(row.get("missing_actions", ())),
                }
            )
        elif resolution != "qualified-evidence":
            raise BattleCapsuleError("defensive preflight resolution changed")

    if len(roots) != len(set(roots)):
        raise BattleCapsuleError("defensive preflight roots are duplicated")
    grid_click_allowed = defensive_preflight.get("grid_click_allowed") is True
    if grid_click_allowed != (not blocked_roots):
        raise BattleCapsuleError(
            "defensive grid-click decision disagrees with its rows"
        )
    return {
        "schema": BATTLE_CAPSULE_ALAS_REPLAY_SCHEMA,
        "mode": "alas-replay",
        "passed": True,
        "account_used": False,
        "android_input_injected": False,
        "qualification_scope": "W1-offline-rehearsal-only",
        "capsule_sha256": _sha256_json(capsule),
        "source_workload": {
            "task": workload.get("task"),
            "stage": workload.get("stage"),
            "mode": workload.get("mode"),
            "official_auto_search": workload.get("official_auto_search"),
        },
        "original_alas": {
            "upstream_commit": replay_result["upstream_alas_commit"],
            "profile_id": replay_result["profile_id"],
            "stage": replay_result["stage"],
            "target": replay_result["target"],
            "battle": battle,
            "ammo": ammo,
            "phases": replay_result["phases"],
            "virtual_actions": replay_result["virtual_actions"],
            "resource_query_count": replay_result["resource_query_count"],
            "pixel_accesses": [],
            "source_restored": True,
            "projected_map_unchanged": True,
        },
        "defensive_preflight": {
            "closure_complete": True,
            "grid_click_allowed": grid_click_allowed,
            "stop_boundary": defensive_preflight.get("stop_boundary"),
            "recovery_policy": defensive_preflight.get("recovery_policy"),
            "blocked_roots": blocked_roots,
        },
        "live_reentry": {
            "ready_for_current_live_preflight": grid_click_allowed,
            "account_execution_authorized": False,
            "requires": [
                "all defensive roots qualified before the original grid click",
                "fresh typed live preflight on the selected runtime",
                "explicit one-battle resource budget and user authorization",
            ],
        },
        "claim": (
            "original ALAS completed one Device-free typed combat replay; "
            "live W1 remains unqualified"
        ),
    }
