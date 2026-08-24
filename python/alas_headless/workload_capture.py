"""Shared live-workload capture primitives for semantic ALAS profiles.

The capture envelope observes one already-selected Android device.  It records
host/runtime, game, controller, and observer activity without screenshots or a
second observer sidecar.  Workload runners remain responsible for their own
typed postconditions and mutation policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import psutil

from .alas_adapter import AlasSemanticSession
from .runtime_trace import (
    RuntimeProcessSample,
    RuntimeTraceRecorder,
    summarize_runtime_trace,
)
from .semantic_oracle import SemanticOracle


LIVE_WORKLOAD_CAPTURE_SCHEMA = "alas-headless.live-workload-capture/v1"
LIVE_WORKLOAD_BASELINE_SCHEMA = "alas-headless.live-workload-baseline/v1"
LIVE_WORKLOAD_RESOURCE_RECEIPT_SCHEMA = (
    "alas-headless.live-workload-resource-receipt/v1"
)
AUTO_COMBAT_WORKLOAD_CAPTURE_SCHEMA = (
    "alas-headless.auto-combat-workload-capture/v1"
)
AUTO_COMBAT_WORKLOAD_BASELINE_SCHEMA = (
    "alas-headless.auto-combat-workload-baseline/v1"
)
AUTO_COMBAT_RESOURCE_RECEIPT_SCHEMA = (
    "alas-headless.auto-combat-resource-receipt/v1"
)
WORKLOAD_VERIFICATION_MANIFEST_SCHEMA = (
    "alas-headless.workload-verification-manifest/v1"
)
LIVE_WORKLOAD_VERIFICATION_SCHEMA = "alas-headless.live-workload-verification/v1"
DEFAULT_TRACED_ACTION_METHODS = (
    "click",
    "click_toggle",
    "click_campaign_mode_switch",
    "click_campaign_chapter",
    "click_campaign_map_preparation",
    "cancel_campaign_map_preparation",
    "click_campaign_hard_recommend",
    "cancel_campaign_fleet_preparation",
    "click_campaign_sortie",
    "click_campaign_auto_search_sortie",
    "click_campaign_stage",
)
_SERIAL_PORT = re.compile(r"^emulator-([1-9][0-9]*)$")
_MEMINFO_TOTAL = re.compile(
    r"TOTAL PSS:\s*([0-9]+)\s+TOTAL RSS:\s*([0-9]+)\s+TOTAL SWAP PSS:\s*([0-9]+)"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_command(
    command: Sequence[str], *, timeout_seconds: float = 5.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def git_identity(root: Path) -> Mapping[str, Any]:
    commit = run_command(("git", "rev-parse", "HEAD"))
    status = run_command(("git", "status", "--porcelain"))
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "root": str(root.resolve()),
    }


def emulator_port(serial: str) -> Optional[int]:
    match = _SERIAL_PORT.fullmatch(serial)
    return int(match.group(1)) if match is not None else None


def discover_host_runtime_pid(serial: str) -> Optional[int]:
    """Find the one QEMU process that owns the explicitly selected port."""

    port = emulator_port(serial)
    if port is None:
        return None
    matches = []
    for process in psutil.process_iter(("pid", "name", "cmdline")):
        try:
            name = (process.info.get("name") or "").lower()
            arguments = tuple(process.info.get("cmdline") or ())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if not name.startswith("qemu-system-"):
            continue
        for index, argument in enumerate(arguments[:-1]):
            if argument == "-port" and arguments[index + 1] == str(port):
                matches.append(int(process.info["pid"]))
                break
    return matches[0] if len(matches) == 1 else None


def parse_guest_process_sample(
    output: str, *, clock_ticks: int, page_size: int
) -> tuple[int, RuntimeProcessSample, Mapping[str, int]]:
    """Parse one bounded Android ``/proc`` process sample."""

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) < 2 or not lines[0].startswith("PID:"):
        raise ValueError("guest process sample has no PID")
    pid_text = lines[0][4:].strip()
    if not pid_text.isdigit():
        raise ValueError("guest process sample PID is malformed")
    stat_line = lines[1]
    close = stat_line.rfind(")")
    if close < 0:
        raise ValueError("guest process stat is malformed")
    fields = stat_line[close + 2 :].split()
    if len(fields) < 22:
        raise ValueError("guest process stat is truncated")
    user_ticks = int(fields[11])
    system_ticks = int(fields[12])
    rss_pages = int(fields[21])
    details: dict[str, int] = {}
    for line in lines[2:]:
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        token = raw.strip().split()[0]
        if token.isdigit():
            details[key] = int(token)
    rss_bytes = details.get("VmRSS", rss_pages * page_size // 1024) * 1024
    cpu_time_ns = (user_ticks + system_ticks) * 1_000_000_000 // clock_ticks
    return (
        int(pid_text),
        RuntimeProcessSample(
            scope="game",
            cpu_time_ns=cpu_time_ns,
            rss_bytes=rss_bytes,
        ),
        details,
    )


def parse_meminfo_totals(output: str) -> Mapping[str, int]:
    match = _MEMINFO_TOTAL.search(output)
    if match is None:
        raise ValueError("game meminfo totals are unavailable")
    pss_kib, rss_kib, swap_pss_kib = (int(item) for item in match.groups())
    return {
        "pss_bytes": pss_kib * 1024,
        "rss_bytes": rss_kib * 1024,
        "swap_pss_bytes": swap_pss_kib * 1024,
    }


@dataclass
class ProcessSamplerSummary:
    host_runtime_pid: Optional[int]
    samples: int = 0
    guest_failures: int = 0
    host_failures: int = 0
    controller_failures: int = 0

    def fields(self) -> Mapping[str, Any]:
        return {
            "host_runtime_pid": self.host_runtime_pid,
            "samples": self.samples,
            "guest_failures": self.guest_failures,
            "host_failures": self.host_failures,
            "controller_failures": self.controller_failures,
        }


class ProcessSampler:
    """Low-frequency host and guest sampler shared by every live profile."""

    def __init__(
        self,
        *,
        trace: RuntimeTraceRecorder,
        serial: str,
        adb: str,
        package: str,
        interval_seconds: float,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
    ) -> None:
        self.trace = trace
        self.serial = serial
        self.adb = adb
        self.package = package
        self.interval_seconds = interval_seconds
        self.command_runner = command_runner
        self.summary = ProcessSamplerSummary(discover_host_runtime_pid(serial))
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="alas-workload-process-sampler", daemon=True
        )
        self._clock_ticks = self._guest_constant("CLK_TCK")
        self._page_size = self._guest_constant("PAGESIZE")
        self._host_process = (
            psutil.Process(self.summary.host_runtime_pid)
            if self.summary.host_runtime_pid is not None
            else None
        )
        self._controller_process = psutil.Process(os.getpid())

    def _guest_constant(self, name: str) -> int:
        completed = self.command_runner(
            (self.adb, "-s", self.serial, "shell", "getconf", name),
            timeout_seconds=5.0,
        )
        value = completed.stdout.strip()
        if completed.returncode != 0 or not value.isdigit() or int(value) <= 0:
            raise RuntimeError("guest process constant is unavailable: " + name)
        return int(value)

    @staticmethod
    def _psutil_fields(process: psutil.Process) -> Mapping[str, int]:
        cpu = process.cpu_times()
        memory = process.memory_info()
        fields: dict[str, int] = {
            "cpu_time_ns": int((cpu.user + cpu.system) * 1_000_000_000),
            "rss_bytes": int(memory.rss),
        }
        try:
            io = process.io_counters()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return fields
        fields["read_bytes"] = int(io.read_bytes)
        fields["write_bytes"] = int(io.write_bytes)
        return fields

    def _sample_host(self) -> None:
        if self._host_process is None:
            return
        self.trace.process_sample(
            RuntimeProcessSample(
                scope="host-runtime", **self._psutil_fields(self._host_process)
            )
        )

    def _sample_controller(self) -> None:
        self.trace.emit(
            "runtime.controller.process.sample",
            fields=self._psutil_fields(self._controller_process),
        )

    def _sample_guest(self) -> None:
        shell_command = (
            "p=$(pidof "
            + self.package
            + "); test -n \"$p\" || exit 3; "
            + "echo PID:$p; cat /proc/$p/stat; "
            + "grep -E '^(VmRSS|VmHWM|Threads):' /proc/$p/status"
        )
        completed = self.command_runner(
            (self.adb, "-s", self.serial, "shell", shell_command),
            timeout_seconds=min(10.0, max(3.0, self.interval_seconds * 2.0)),
        )
        if completed.returncode != 0:
            raise RuntimeError("guest process sample command failed")
        pid, sample, details = parse_guest_process_sample(
            completed.stdout,
            clock_ticks=self._clock_ticks,
            page_size=self._page_size,
        )
        self.trace.process_sample(sample)
        self.trace.emit(
            "runtime.game.process.identity",
            fields={
                "pid": pid,
                "threads": details.get("Threads"),
                "vm_hwm_bytes": (
                    details["VmHWM"] * 1024 if "VmHWM" in details else None
                ),
            },
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._sample_host()
            except (psutil.Error, OSError, ValueError):
                self.summary.host_failures += 1
            try:
                self._sample_controller()
            except (psutil.Error, OSError, ValueError):
                self.summary.controller_failures += 1
            try:
                self._sample_guest()
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                self.summary.guest_failures += 1
            self.summary.samples += 1
            remaining = self.interval_seconds - (time.monotonic() - started)
            self._stop.wait(max(0.0, remaining))

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> Mapping[str, Any]:
        self._stop.set()
        self._thread.join(max(5.0, self.interval_seconds * 3.0))
        return self.summary.fields()

    def capture_meminfo(self, phase: str) -> Optional[Mapping[str, Any]]:
        pid = self.command_runner(
            (self.adb, "-s", self.serial, "shell", "pidof", self.package),
            timeout_seconds=5.0,
        ).stdout.strip()
        if not pid.isdigit():
            return None
        completed = self.command_runner(
            (self.adb, "-s", self.serial, "shell", "dumpsys", "meminfo", pid),
            timeout_seconds=30.0,
        )
        if completed.returncode != 0:
            return None
        try:
            fields: dict[str, Any] = dict(parse_meminfo_totals(completed.stdout))
        except ValueError:
            return None
        fields.update({"pid": int(pid), "phase": phase})
        self.trace.emit("runtime.game.meminfo", fields=fields)
        return fields


def install_semantic_trace_hooks(
    trace: RuntimeTraceRecorder,
    *,
    action_methods: Sequence[str] = DEFAULT_TRACED_ACTION_METHODS,
    campaign_auto_phases: bool = False,
) -> Callable[[], None]:
    """Attach one trace to semantic sessions created by an original ALAS run."""

    original_from_environment = AlasSemanticSession.__dict__["from_environment"]
    original_factory = original_from_environment.__func__
    original_action_methods = {
        name: getattr(SemanticOracle, name)
        for name in action_methods
        if hasattr(SemanticOracle, name)
    }
    original_auto_start = AlasSemanticSession.confirm_campaign_auto_search_started
    original_auto_completion = AlasSemanticSession.wait_campaign_auto_search_completion

    def traced_from_environment(
        cls: type[AlasSemanticSession], serial: str, *args: Any, **kwargs: Any
    ) -> AlasSemanticSession:
        kwargs["trace"] = trace
        return original_factory(cls, serial, *args, **kwargs)

    def action_wrapper(
        method_name: str, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @wraps(original)
        def traced_action(oracle: SemanticOracle, *args: Any, **kwargs: Any) -> Any:
            started = time.monotonic_ns()
            try:
                receipt = original(oracle, *args, **kwargs)
            except BaseException as exc:
                fields = {
                    "method": "SemanticOracle." + method_name,
                    "exception_type": type(exc).__name__,
                }
                if method_name in ("click", "click_toggle") and args:
                    fields["requested_semantic_id"] = str(args[0])
                trace.emit(
                    "alas.action",
                    outcome="error",
                    duration_ns=max(0, time.monotonic_ns() - started),
                    fields=fields,
                )
                raise
            trace.emit(
                "alas.action",
                duration_ns=max(0, time.monotonic_ns() - started),
                fields={
                    "method": "SemanticOracle." + method_name,
                    "semantic_id": getattr(receipt, "semantic_id", None),
                    "receipt_generation": getattr(receipt, "generation", None),
                },
            )
            return receipt

        return traced_action

    @wraps(original_auto_start)
    def traced_auto_start(session: AlasSemanticSession, *args: Any, **kwargs: Any) -> Any:
        proof = original_auto_start(session, *args, **kwargs)
        trace.emit(
            "alas.phase",
            fields={
                "phase": "official-auto-start",
                "stage_code": proof.stage_code,
                "sortie_generation": proof.sortie_generation,
                "map_generation": proof.map_generation,
                "map_root_path": proof.map_root_path,
            },
        )
        return proof

    @wraps(original_auto_completion)
    def traced_auto_completion(
        session: AlasSemanticSession, *args: Any, **kwargs: Any
    ) -> Any:
        proof = original_auto_completion(session, *args, **kwargs)
        trace.emit(
            "alas.phase",
            fields={
                "phase": "official-auto-complete",
                "stage_code": proof.stage_code,
                "result_generation": proof.result_generation,
                "result_path": proof.result_path,
                "waited_seconds": proof.waited_seconds,
            },
        )
        return proof

    AlasSemanticSession.from_environment = classmethod(traced_from_environment)
    for method_name, original in original_action_methods.items():
        setattr(SemanticOracle, method_name, action_wrapper(method_name, original))
    if campaign_auto_phases:
        AlasSemanticSession.confirm_campaign_auto_search_started = traced_auto_start
        AlasSemanticSession.wait_campaign_auto_search_completion = (
            traced_auto_completion
        )

    def restore() -> None:
        AlasSemanticSession.from_environment = original_from_environment
        for method_name, original in original_action_methods.items():
            setattr(SemanticOracle, method_name, original)
        AlasSemanticSession.confirm_campaign_auto_search_started = original_auto_start
        AlasSemanticSession.wait_campaign_auto_search_completion = (
            original_auto_completion
        )

    return restore


def capture_live_workload(
    *,
    root: Path,
    output_directory: Path,
    serial: str,
    adb: str,
    package: str,
    driver_revision: str,
    sample_interval_seconds: float,
    workload: Mapping[str, Any],
    safety: Mapping[str, Any],
    runner: Callable[[RuntimeTraceRecorder], Mapping[str, Any]],
    campaign_auto_phases: bool = False,
    raise_runner_failure: bool = False,
) -> Mapping[str, Any]:
    """Run one profile inside a uniform measurement and trace envelope."""

    if not 0.5 <= sample_interval_seconds <= 10.0:
        raise ValueError("sample interval must be in [0.5, 10]")
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex
    trace_path = output / "runtime-trace.jsonl"
    trace = RuntimeTraceRecorder(trace_path, enabled=True, run_id=run_id)
    sampler = ProcessSampler(
        trace=trace,
        serial=serial,
        adb=adb,
        package=package,
        interval_seconds=sample_interval_seconds,
    )
    restore_hooks = install_semantic_trace_hooks(
        trace, campaign_auto_phases=campaign_auto_phases
    )
    original_cwd = Path.cwd()
    started_at = utc_now()
    started_monotonic_ns = time.monotonic_ns()
    pre_meminfo = sampler.capture_meminfo("before")
    sampler.start()
    runner_result: Optional[Mapping[str, Any]] = None
    failure: Optional[BaseException] = None
    sampler_summary: Mapping[str, Any] = {}
    trace.emit("workload.phase", fields={"phase": "start", "profile": workload["id"]})
    try:
        runner_result = runner(trace)
        trace.emit(
            "workload.phase",
            outcome="ok" if runner_result.get("passed") else "error",
            fields={"phase": "finish", "profile": workload["id"]},
        )
    except BaseException as exc:
        failure = exc
        trace.emit(
            "workload.phase",
            outcome="error",
            fields={
                "phase": "finish",
                "profile": workload["id"],
                "exception_type": type(exc).__name__,
            },
        )
    finally:
        os.chdir(original_cwd)
        sampler_summary = sampler.stop()
        post_meminfo = sampler.capture_meminfo("after")
        restore_hooks()
        trace_summary_before_close = trace.summary()
        trace_close = trace.close()

    result = {
        "schema": LIVE_WORKLOAD_CAPTURE_SCHEMA,
        "passed": bool(runner_result and runner_result.get("passed"))
        and failure is None,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_ns": max(0, time.monotonic_ns() - started_monotonic_ns),
        "source": git_identity(root),
        "workload": dict(workload),
        "safety": dict(safety),
        "device": {
            "serial": serial,
            "package": package,
            "driver_revision": driver_revision,
        },
        "sampling": {
            "interval_seconds": sample_interval_seconds,
            "observer_sidecar_used": False,
            "screenshots_captured": False,
            "pre_meminfo": pre_meminfo,
            "post_meminfo": post_meminfo,
            "process_sampler": sampler_summary,
        },
        "runner_result": runner_result,
        "failure": (
            {"type": type(failure).__name__, "message": str(failure)[:500]}
            if failure is not None
            else None
        ),
        "trace": {
            "path": str(trace_path),
            "before_close": trace_summary_before_close,
            "after_close": trace_close,
            "summary": summarize_runtime_trace(trace_path),
        },
        "raw_input_fallback_used": False,
    }
    write_json(output / "result.json", result)
    if failure is not None and raise_runner_failure:
        raise failure
    return result


def load_trace_records(path: Path) -> tuple[Mapping[str, Any], ...]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("runtime trace record is not an object")
        records.append(value)
    return tuple(records)


def _percentile(values: Sequence[int], percentile: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.5)))
    return int(ordered[index])


def _counter_delta(values: Sequence[int]) -> int:
    total = 0
    for previous, current in zip(values, values[1:]):
        total += current - previous if current >= previous else current
    return total


def _process_summary(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not records:
        return {"samples": 0}
    fields = [record.get("fields", {}) for record in records]
    monotonic = [int(record["monotonic_ns"]) for record in records]
    cpu = [int(item["cpu_time_ns"]) for item in fields if "cpu_time_ns" in item]
    rss = [int(item["rss_bytes"]) for item in fields if "rss_bytes" in item]
    read = [int(item["read_bytes"]) for item in fields if "read_bytes" in item]
    write = [int(item["write_bytes"]) for item in fields if "write_bytes" in item]
    elapsed_ns = max(0, monotonic[-1] - monotonic[0])
    output: dict[str, Any] = {
        "samples": len(records),
        "average_cpu_cores": (
            round(_counter_delta(cpu) / elapsed_ns, 6)
            if len(cpu) >= 2 and elapsed_ns > 0
            else None
        ),
        "rss_bytes_p50": _percentile(rss, 0.50),
        "rss_bytes_p95": _percentile(rss, 0.95),
        "rss_bytes_max": max(rss) if rss else None,
    }
    if len(read) >= 2:
        output["read_bytes_delta"] = _counter_delta(read)
    if len(write) >= 2:
        output["write_bytes_delta"] = _counter_delta(write)
    return output


def summarize_workload_records(
    records: Sequence[Mapping[str, Any]], *, duration_ns: int
) -> Mapping[str, Any]:
    scopes: dict[str, list[Mapping[str, Any]]] = {
        "host-runtime": [],
        "game": [],
        "controller": [],
    }
    observer = []
    game_identity = []
    for record in records:
        event = record.get("event")
        fields = record.get("fields")
        if not isinstance(fields, dict):
            continue
        if event == "runtime.process.sample" and fields.get("scope") in scopes:
            scopes[str(fields["scope"])].append(record)
        elif event == "runtime.controller.process.sample":
            scopes["controller"].append(record)
        elif event == "observer.request":
            observer.append(record)
        elif event == "runtime.game.process.identity":
            game_identity.append(record)

    observer_durations = [
        int(record["duration_ns"])
        for record in observer
        if isinstance(record.get("duration_ns"), int)
    ]
    response_bytes = [
        int(record["fields"]["response_bytes"])
        for record in observer
        if isinstance(record.get("fields", {}).get("response_bytes"), int)
    ]
    endpoints: dict[str, int] = {}
    for record in observer:
        endpoint = str(record.get("fields", {}).get("endpoint", "unknown"))
        endpoints[endpoint] = endpoints.get(endpoint, 0) + 1
    threads = [
        int(record["fields"]["threads"])
        for record in game_identity
        if isinstance(record.get("fields", {}).get("threads"), int)
    ]
    elapsed_seconds = duration_ns / 1_000_000_000
    game_summary = dict(_process_summary(scopes["game"]))
    game_summary.update(
        {
            "threads_p50": _percentile(threads, 0.50),
            "threads_p95": _percentile(threads, 0.95),
        }
    )
    return {
        "elapsed_seconds": round(elapsed_seconds, 6),
        "host_runtime": _process_summary(scopes["host-runtime"]),
        "game": game_summary,
        "controller": _process_summary(scopes["controller"]),
        "observer": {
            "requests": len(observer),
            "requests_per_second": (
                round(len(observer) / elapsed_seconds, 6)
                if elapsed_seconds > 0
                else None
            ),
            "errors": sum(1 for record in observer if record.get("outcome") != "ok"),
            "endpoints": dict(sorted(endpoints.items())),
            "duration_ms_p50": (
                _percentile(observer_durations, 0.50) // 1_000_000
                if observer_durations
                else None
            ),
            "duration_ms_p95": (
                _percentile(observer_durations, 0.95) // 1_000_000
                if observer_durations
                else None
            ),
            "duration_ms_max": (
                max(observer_durations) // 1_000_000 if observer_durations else None
            ),
            "response_bytes_p50": _percentile(response_bytes, 0.50),
            "response_bytes_p95": _percentile(response_bytes, 0.95),
            "response_bytes_max": max(response_bytes) if response_bytes else None,
        },
    }


def build_resource_receipt(
    result: Mapping[str, Any],
    *,
    evidence_basis: str,
    observed_mutation_dispatches: Optional[int],
    notes: Sequence[str] = (),
) -> Mapping[str, Any]:
    expected_zero = not bool(
        result.get("safety", {}).get("in_game_resource_mutation_expected")
    )
    return {
        "schema": LIVE_WORKLOAD_RESOURCE_RECEIPT_SCHEMA,
        "run_id": result["run_id"],
        "profile": result["workload"]["id"],
        "device": result["device"],
        "expected_in_game_resource_delta": 0 if expected_zero else None,
        "resource_counters_directly_observed": False,
        "observed_mutation_dispatches": observed_mutation_dispatches,
        "evidence_basis": evidence_basis,
        "zero_resource_contract_passed": bool(result.get("passed"))
        and expected_zero
        and observed_mutation_dispatches in (None, 0),
        "notes": list(notes),
    }


def build_baseline_summary(
    result: Mapping[str, Any], resource_receipt_path: Path
) -> Mapping[str, Any]:
    trace_path = Path(str(result["trace"]["path"]))
    records = load_trace_records(trace_path)
    sampler = result.get("sampling", {}).get("process_sampler", {})
    trace_close = result.get("trace", {}).get("after_close", {})
    result_path = trace_path.parent / "result.json"
    return {
        "schema": LIVE_WORKLOAD_BASELINE_SCHEMA,
        "derived_at": utc_now(),
        "run_id": result["run_id"],
        "capture_passed": bool(result.get("passed")),
        "workload": result["workload"],
        "source": {
            "result_sha256": sha256_file(result_path),
            "runtime_trace_sha256": sha256_file(trace_path),
            "resource_receipt_sha256": sha256_file(resource_receipt_path),
        },
        "integrity": {
            "trace_records": trace_close.get("recorded"),
            "trace_dropped": trace_close.get("dropped"),
            "trace_invalid": trace_close.get("invalid"),
            "trace_writer_error": trace_close.get("writer_error"),
            "process_samples": sampler.get("samples"),
            "guest_sample_failures": sampler.get("guest_failures"),
            "host_sample_failures": sampler.get("host_failures"),
            "controller_sample_failures": sampler.get("controller_failures"),
            "screenshots_captured": result.get("sampling", {}).get(
                "screenshots_captured"
            ),
            "observer_sidecar_used": result.get("sampling", {}).get(
                "observer_sidecar_used"
            ),
            "raw_input_fallback_used": result.get("raw_input_fallback_used"),
        },
        "whole_capture": summarize_workload_records(
            records, duration_ns=int(result["duration_ns"])
        ),
    }


def build_auto_combat_resource_receipt(
    result: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Record one bounded official-auto sortie without inventing counters."""

    runner_result = result.get("runner_result")
    if not isinstance(runner_result, Mapping):
        runner_result = {}
    completion = runner_result.get("auto_search_completion")
    if not isinstance(completion, Mapping):
        completion = {}
    successful_sorties = int(
        bool(result.get("passed"))
        and bool(completion.get("combat_auto_proven"))
        and bool(completion.get("passive_after_sortie"))
    )
    device = result.get("device")
    if not isinstance(device, Mapping):
        device = {}
    return {
        "schema": AUTO_COMBAT_RESOURCE_RECEIPT_SCHEMA,
        "run_id": result["run_id"],
        "serial": device.get("serial"),
        "package": device.get("package"),
        "driver_revision": device.get("driver_revision"),
        "before": {
            "oil": None,
            "evidence_basis": "no typed pre-sortie oil counter was captured",
        },
        "after": {
            "oil": None,
            "evidence_basis": "no typed post-sortie oil counter was captured",
        },
        "delta": {
            "oil": None,
            "successful_sorties": successful_sorties,
            "premium_currency_consumed": 0,
            "purchases": 0,
        },
        "notes": [
            "The original Main runner authorized at most one sortie.",
            "Oil is reported as unobserved rather than a synthetic value.",
            "Combat and viewport input budgets remained zero after sortie.",
        ],
    }


def build_auto_combat_baseline_summary(
    result: Mapping[str, Any], resource_receipt_path: Path
) -> Mapping[str, Any]:
    """Build the hash-bound baseline envelope for official-auto capture."""

    baseline = dict(build_baseline_summary(result, resource_receipt_path))
    baseline["schema"] = AUTO_COMBAT_WORKLOAD_BASELINE_SCHEMA
    return baseline


def build_workload_verification_manifest(
    output_directory: Path,
) -> Mapping[str, Any]:
    """Seal retained legacy capture files without rewriting their contents."""

    output = output_directory.resolve()
    paths = {
        name: output / name
        for name in (
            "result.json",
            "runtime-trace.jsonl",
            "resource-receipt.json",
            "baseline-summary.json",
        )
    }
    missing = tuple(name for name, path in paths.items() if not path.is_file())
    if missing:
        raise ValueError(
            "cannot seal incomplete workload capture: " + ", ".join(missing)
        )
    result = _read_json_object(paths["result.json"])
    run_id = result.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("cannot seal workload capture without a run_id")
    return {
        "schema": WORKLOAD_VERIFICATION_MANIFEST_SCHEMA,
        "created_at": utc_now(),
        "run_id": run_id,
        "artifacts": {
            name: sha256_file(path) for name, path in sorted(paths.items())
        },
    }


def _read_json_object(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("workload artifact is not a JSON object: " + path.name)
    return value


def verify_workload_capture(output_directory: Path) -> Mapping[str, Any]:
    """Verify correlation, hashes, and non-pixel integrity for one capture."""

    output = output_directory.resolve()
    result_path = output / "result.json"
    trace_path = output / "runtime-trace.jsonl"
    receipt_path = output / "resource-receipt.json"
    baseline_path = output / "baseline-summary.json"
    verification_manifest_path = output / "verification-manifest.json"
    missing = tuple(
        path.name
        for path in (result_path, trace_path, receipt_path, baseline_path)
        if not path.is_file()
    )
    if missing:
        return {
            "schema": LIVE_WORKLOAD_VERIFICATION_SCHEMA,
            "passed": False,
            "directory": str(output),
            "errors": ["missing artifact: " + name for name in missing],
        }

    try:
        result = _read_json_object(result_path)
        receipt = _read_json_object(receipt_path)
        baseline = _read_json_object(baseline_path)
        records = load_trace_records(trace_path)
        verification_manifest = (
            _read_json_object(verification_manifest_path)
            if verification_manifest_path.is_file()
            else None
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema": LIVE_WORKLOAD_VERIFICATION_SCHEMA,
            "passed": False,
            "directory": str(output),
            "errors": ["artifact parse failed: " + str(exc)],
        }
    errors = []
    result_schema = result.get("schema")
    schema_contracts = {
        LIVE_WORKLOAD_CAPTURE_SCHEMA: (
            LIVE_WORKLOAD_RESOURCE_RECEIPT_SCHEMA,
            LIVE_WORKLOAD_BASELINE_SCHEMA,
        ),
        AUTO_COMBAT_WORKLOAD_CAPTURE_SCHEMA: (
            AUTO_COMBAT_RESOURCE_RECEIPT_SCHEMA,
            AUTO_COMBAT_WORKLOAD_BASELINE_SCHEMA,
        ),
    }
    contract = schema_contracts.get(result_schema)
    if contract is None:
        errors.append("result schema is unsupported")
    else:
        expected_receipt_schema, expected_baseline_schema = contract
        if receipt.get("schema") != expected_receipt_schema:
            errors.append("resource receipt schema changed")
        if baseline.get("schema") != expected_baseline_schema:
            errors.append("baseline schema changed")
    run_ids = {result.get("run_id"), receipt.get("run_id"), baseline.get("run_id")}
    if None in run_ids or len(run_ids) != 1:
        errors.append("artifact run_id correlation failed")
    source = baseline.get("source")
    if not isinstance(source, dict):
        errors.append("baseline source hashes are absent")
    else:
        expected_hashes = {
            "result_sha256": sha256_file(result_path),
            "runtime_trace_sha256": sha256_file(trace_path),
        }
        for field, actual in expected_hashes.items():
            if source.get(field) != actual:
                errors.append(field + " mismatch")
        receipt_sha256 = sha256_file(receipt_path)
        if "resource_receipt_sha256" in source:
            if source.get("resource_receipt_sha256") != receipt_sha256:
                errors.append("resource_receipt_sha256 mismatch")
        elif verification_manifest is None:
            errors.append("resource receipt is not hash-bound")

    if verification_manifest is not None:
        if (
            verification_manifest.get("schema")
            != WORKLOAD_VERIFICATION_MANIFEST_SCHEMA
        ):
            errors.append("verification manifest schema changed")
        if verification_manifest.get("run_id") != result.get("run_id"):
            errors.append("verification manifest run_id correlation failed")
        manifest_artifacts = verification_manifest.get("artifacts")
        expected_manifest_artifacts = {
            "baseline-summary.json": sha256_file(baseline_path),
            "resource-receipt.json": sha256_file(receipt_path),
            "result.json": sha256_file(result_path),
            "runtime-trace.jsonl": sha256_file(trace_path),
        }
        if manifest_artifacts != expected_manifest_artifacts:
            errors.append("verification manifest artifact hashes changed")

    trace_close = result.get("trace", {}).get("after_close", {})
    integrity = baseline.get("integrity", {})
    if trace_close.get("recorded") != len(records):
        errors.append("trace record count changed")
    if integrity.get("trace_records") != len(records):
        errors.append("baseline trace record count changed")
    for field in ("trace_dropped", "trace_invalid"):
        if integrity.get(field) != 0:
            errors.append(field + " is nonzero")
    if integrity.get("trace_writer_error") is not None:
        errors.append("trace writer reported an error")
    for field in (
        "screenshots_captured",
        "observer_sidecar_used",
        "raw_input_fallback_used",
    ):
        if integrity.get(field) is not False:
            errors.append(field + " is not false")
    if bool(result.get("passed")) != bool(baseline.get("capture_passed")):
        errors.append("capture pass status is inconsistent")
    if not result.get("passed"):
        errors.append("capture itself failed")
    expected_zero = receipt.get("expected_in_game_resource_delta") == 0
    if result.get("passed") and expected_zero and not receipt.get(
        "zero_resource_contract_passed"
    ):
        errors.append("zero-resource contract did not pass")
    if result_schema == AUTO_COMBAT_WORKLOAD_CAPTURE_SCHEMA:
        runner_result = result.get("runner_result")
        if not isinstance(runner_result, Mapping):
            runner_result = {}
        budgets = runner_result.get("budgets")
        if not isinstance(budgets, Mapping):
            budgets = {}
        completion = runner_result.get("auto_search_completion")
        if not isinstance(completion, Mapping):
            completion = {}
        delta = receipt.get("delta")
        if not isinstance(delta, Mapping):
            delta = {}
        if budgets.get("sortie") != 1:
            errors.append("official-auto sortie budget is not one")
        if budgets.get("combat") != 0 or budgets.get("viewport_swipe") != 0:
            errors.append("official-auto post-sortie input budget is not zero")
        if not completion.get("combat_auto_proven") or not completion.get(
            "passive_after_sortie"
        ):
            errors.append("official-auto passive completion is unproven")
        if delta.get("successful_sorties") != 1:
            errors.append("resource receipt does not record one successful sortie")
        if delta.get("premium_currency_consumed") != 0:
            errors.append("premium currency consumption is nonzero or unknown")
        if delta.get("purchases") != 0:
            errors.append("purchase count is nonzero or unknown")
        device = result.get("device")
        if not isinstance(device, Mapping):
            device = {}
        for field in ("serial", "package", "driver_revision"):
            if receipt.get(field) != device.get(field):
                errors.append("resource receipt device identity differs: " + field)
        if result.get("raw_input_fallback_used") is not False:
            errors.append("auto-combat raw input fallback is not false")
    return {
        "schema": LIVE_WORKLOAD_VERIFICATION_SCHEMA,
        "passed": not errors,
        "directory": str(output),
        "profile": (
            result.get("workload", {}).get("id")
            if result_schema == LIVE_WORKLOAD_CAPTURE_SCHEMA
            else "main-12-4-official-auto"
        ),
        "run_id": result.get("run_id"),
        "capture_passed": bool(result.get("passed")),
        "trace_records": len(records),
        "errors": errors,
    }


__all__ = (
    "AUTO_COMBAT_RESOURCE_RECEIPT_SCHEMA",
    "AUTO_COMBAT_WORKLOAD_BASELINE_SCHEMA",
    "AUTO_COMBAT_WORKLOAD_CAPTURE_SCHEMA",
    "DEFAULT_TRACED_ACTION_METHODS",
    "LIVE_WORKLOAD_BASELINE_SCHEMA",
    "LIVE_WORKLOAD_CAPTURE_SCHEMA",
    "LIVE_WORKLOAD_RESOURCE_RECEIPT_SCHEMA",
    "LIVE_WORKLOAD_VERIFICATION_SCHEMA",
    "ProcessSampler",
    "ProcessSamplerSummary",
    "build_baseline_summary",
    "build_auto_combat_baseline_summary",
    "build_auto_combat_resource_receipt",
    "build_resource_receipt",
    "build_workload_verification_manifest",
    "capture_live_workload",
    "discover_host_runtime_pid",
    "emulator_port",
    "git_identity",
    "install_semantic_trace_hooks",
    "load_trace_records",
    "parse_guest_process_sample",
    "parse_meminfo_totals",
    "run_command",
    "sha256_file",
    "summarize_workload_records",
    "utc_now",
    "verify_workload_capture",
    "WORKLOAD_VERIFICATION_MANIFEST_SCHEMA",
    "write_json",
)
