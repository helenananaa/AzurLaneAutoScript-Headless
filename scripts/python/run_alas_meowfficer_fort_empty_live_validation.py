#!/usr/bin/env python3
"""Run the real ALAS Meowfficer task at an empty-Fort no-op boundary."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _adb(serial: str, *arguments: str) -> str:
    return subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    ).stdout.strip()


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def validate(*, alas_root: Path, seed_config: str, driver_revision: str) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Meowfficer"]["Scheduler"].update(
        {"Enable": True, "NextRun": "2020-01-01 00:00:00"}
    )
    payload["Meowfficer"]["Meowfficer"].update(
        {"BuyAmount": 0, "FortChoreMeowfficer": True, "OverflowCoins": -1}
    )
    payload["Meowfficer"]["MeowfficerTrain"]["Enable"] = False
    config_name = "codex_meowfficer_fort_empty_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    instance: object | None = None
    result: dict[str, Any] = {"passed": False, "temporary_config": config_path.name}
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
            "ALAS_SEMANTIC_ADB": "adb",
        }
    )
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.chdir(alas_root)
    try:
        from alas_headless import SemanticGateClosed
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function
        from module.meowfficer.meowfficer import RewardMeowfficer
        from module.ui.page import page_meowfficer

        instance = AzurLaneAutoScript(config_name)
        task = name_to_function("Meowfficer")
        instance.config.task = task
        instance.config.bind(task)
        adapter = instance.device.semantic_adapter.open()
        instance.config.task = task
        instance.config.bind(task)
        meowfficer = RewardMeowfficer(config=instance.config, device=instance.device)
        meowfficer.ui_ensure(page_meowfficer)
        meowfficer.wait_meowfficer_buttons()
        try:
            before = adapter.oracle.meowfficer_dock_state()
        except SemanticGateClosed:
            if not adapter.oracle.enabled("meowfficer/fort/close"):
                raise
            adapter.oracle.click("meowfficer/fort/close")
            before = adapter.oracle._retry_transition_read(
                adapter.oracle.meowfficer_dock_state,
                attempts=20,
                interval_seconds=0.25,
            )
        if before.fort_current != 0 or before.fort_total <= 0:
            raise AssertionError("live validation requires an exact empty Fort")

        dispatches: list[str] = []
        taps: list[tuple[int, int]] = []
        original_dispatch = adapter._dispatch_mutation
        original_tap = adapter.oracle._tap

        def record_dispatch(capability: str, operation: object) -> object:
            dispatches.append(capability)
            return original_dispatch(capability, operation)

        def record_tap(x: int, y: int) -> None:
            taps.append((x, y))
            original_tap(x, y)

        adapter._dispatch_mutation = record_dispatch
        adapter.oracle._tap = record_tap
        before_next_run = instance.config.Scheduler_NextRun
        started = time.monotonic()
        instance.meowfficer()
        elapsed = round(time.monotonic() - started, 3)
        after = adapter.oracle.meowfficer_dock_state()
        persisted = _read_json(config_path)
        after_next_run = persisted["Meowfficer"]["Scheduler"]["NextRun"]

        if taps or dispatches:
            raise AssertionError("empty-Fort run unexpectedly injected input")
        if after != before:
            raise AssertionError("empty-Fort run changed the typed dock state")
        if after_next_run <= before_next_run.isoformat(sep=" "):
            raise AssertionError("Meowfficer scheduler delay was not committed")
        result.update(
            {
                "passed": True,
                "elapsed_seconds": elapsed,
                "before": before.__dict__,
                "after": after.__dict__,
                "android_input_injected": False,
                "mutation_dispatches": dispatches,
                "before_next_run": before_next_run.isoformat(),
                "after_next_run": after_next_run,
            }
        )
    finally:
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    return {
        "schema": "alas-headless.meowfficer-fort-empty-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "Meowfficer.BuyAmount": 0,
            "Meowfficer.FortChoreMeowfficer": True,
            "MeowfficerTrain.Enable": False,
        },
        "source_sha256": {
            "fort": _sha256(alas_root / "module" / "meowfficer" / "fort.py"),
            "task": _sha256(alas_root / "module" / "meowfficer" / "meowfficer.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = validate(
            alas_root=args.alas_root.resolve(),
            seed_config=args.seed_config,
            driver_revision=args.driver_revision,
        )
        return 0
    except BaseException as exc:
        result = {"passed": False, "error": type(exc).__name__ + ": " + str(exc)}
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
