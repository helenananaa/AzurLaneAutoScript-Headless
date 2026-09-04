#!/usr/bin/env python3
"""Qualify OpsiAshAssist.Tier without starting or confirming a sortie."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import SemanticGateClosed  # noqa: E402


from alas_headless.semantic_sources import semantic_source_hashes


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(value: Any) -> Any:
    return dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value


def _wait(call: Callable[[], Any], label: str, timeout: float = 15.0) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return call()
        except SemanticGateClosed as exc:
            last_error = exc
            time.sleep(0.25)
    detail = "" if last_error is None else ": " + str(last_error)
    raise RuntimeError(label + " did not settle" + detail)


def validate(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / f"{seed_config}.json"
    seed = _read(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    pid = subprocess.run(
        ("adb", "-s", serial, "shell", "pidof", package),
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    ).stdout.strip()
    if not pid:
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    for group in payload.values():
        if not isinstance(group, dict):
            continue
        scheduler = group.get("Scheduler")
        if isinstance(scheduler, dict) and "Enable" in scheduler:
            scheduler["Enable"] = False
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["OpsiAshAssist"]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    config_name = "codex_opsi_ash_assist_tier_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.opsi-ash-assist-tier-live-qualification/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha(seed_path),
        "cases": [],
        "input_semantic_ids": [],
        "final_action_semantic_ids": [],
        "sortie_started": False,
        "account_resource_mutations": [],
    }
    instance = None
    original_click = None
    previous_cwd = Path.cwd()
    previous_path = tuple(sys.path)
    previous_env = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ADB",
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
            "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
            "ALAS_SEMANTIC_META_ASSIST_BUDGET",
        )
    }
    try:
        os.environ.update(
            {
                "ALAS_SEMANTIC_MODE": "1",
                "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
                "ALAS_SEMANTIC_ADB": "adb",
                "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
                "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS": "60000",
                # Candidate selection is permitted, but the sortie gate is closed.
                "ALAS_SEMANTIC_META_ASSIST_BUDGET": "0",
            }
        )
        sys.path.insert(0, str(alas_root))
        os.chdir(alas_root)

        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function
        from module.os_ash.meta import AshBeaconAssist
        from module.ui.page import page_reward

        instance = AzurLaneAutoScript(config_name)
        task_name = name_to_function("OpsiAshAssist")
        instance.config.task = task_name
        instance.config.bind(task_name)
        task = AshBeaconAssist(instance.config, instance.device)
        session = instance.device.semantic_adapter
        adapter = session.open()
        oracle = adapter.oracle

        navigation = []
        try:
            _wait(oracle.meta_assist_state, "existing META assist list", timeout=2.0)
        except RuntimeError:
            task.ui_ensure(page_reward)
            try:
                oracle.meta_entrance_state()
            except SemanticGateClosed:
                navigation.append(_json(oracle.click_meta_entrance()))
                _wait(oracle.meta_entrance_state, "META landing")
            navigation.append(_json(oracle.click_meta_card(dossier=False)))
            try:
                _wait(
                    oracle.meta_current_detail_state,
                    "META current page",
                    timeout=4.0,
                )
                navigation.append(_json(oracle.click_meta_current_detail_list()))
            except RuntimeError:
                _wait(oracle.meta_current_empty_points, "META empty current page")
                navigation.append(_json(oracle.click_meta_current_list()))
            _wait(oracle.meta_assist_state, "META assist list")
        result["navigation"] = navigation

        original_click = session.click_meta_assist_next_candidate

        def observed_click(*, expected_index: int, expected_level: int):
            receipt = original_click(
                expected_index=expected_index,
                expected_level=expected_level,
            )
            result["input_semantic_ids"].append(receipt.semantic_id)
            return receipt

        session.click_meta_assist_next_candidate = observed_click
        initial = session.meta_assist_state()
        result["initial_state"] = _json(initial)
        expected_clicks = {-1: 0, 0: 0, 15: 0, 16: 5}
        errors = []
        for tier in (-1, 0, 15, 16):
            instance.config.override(OpsiAshAssist_Tier=tier)
            before = session.meta_assist_state()
            click_offset = len(result["input_semantic_ids"])
            started = time.monotonic()
            task._ensure_meta_level()
            after = session.meta_assist_state()
            case_clicks = result["input_semantic_ids"][click_offset:]
            case = {
                "tier": tier,
                "before": _json(before),
                "after": _json(after),
                "input_semantic_ids": case_clicks,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
            result["cases"].append(case)
            if len(case_clicks) != expected_clicks[tier]:
                errors.append(
                    f"Tier {tier} emitted {len(case_clicks)} candidate inputs; "
                    f"expected {expected_clicks[tier]}"
                )
            if (
                after.remaining_attempts != before.remaining_attempts
                or after.attempt_capacity != before.attempt_capacity
            ):
                errors.append(f"Tier {tier} changed META assist attempts")
            if after.selected_hp != before.selected_hp:
                errors.append(f"Tier {tier} changed selected beacon HP")

        final = session.meta_assist_state()
        result["final_state"] = _json(final)
        if final.remaining_attempts != initial.remaining_attempts:
            errors.append("META assist attempts changed across validation")
        result["validation_errors"] = errors
        result["passed"] = not errors
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["passed"] = False
    finally:
        if instance is not None:
            device = instance.__dict__.get("device")
            session = getattr(device, "semantic_adapter", None)
            if session is not None:
                if original_click is not None:
                    session.click_meta_assist_next_candidate = original_click
                session.close()
        os.chdir(previous_cwd)
        sys.path[:] = previous_path
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    result["source_sha256"] = {
        **semantic_source_hashes(ROOT),
        "meta_task": _sha(alas_root / "module" / "os_ash" / "meta.py"),
        "adapter": _sha(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        "oracle": _sha(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
    )
    _write(args.output.resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
