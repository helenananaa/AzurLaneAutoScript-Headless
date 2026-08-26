#!/usr/bin/env python3
"""Run the real ALAS Meowfficer task at a typed training boundary."""

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
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
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


def _wait_dock_state(adapter: object, timeout: float = 12.0) -> object:
    from alas_headless import SemanticGateClosed

    deadline = time.monotonic() + timeout
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            return adapter.oracle.meowfficer_dock_state()
        except SemanticGateClosed as exc:
            last_error = exc
            time.sleep(0.25)
    raise AssertionError("Meowfficer dock did not stabilize after closing") from last_error


def _ensure_dock(adapter: object) -> object:
    from alas_headless import SemanticGateClosed

    try:
        return adapter.oracle.meowfficer_dock_state()
    except SemanticGateClosed:
        # Recover only from the exact training overlay left by an interrupted
        # validation. Any other page remains a hard failure.
        adapter.oracle.meowfficer_training_state()
        adapter.oracle.click("meowfficer/train/close")
        return _wait_dock_state(adapter)


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
        {"BuyAmount": 0, "FortChoreMeowfficer": False, "OverflowCoins": -1}
    )
    payload["Meowfficer"]["MeowfficerTrain"].update(
        {"Enable": True, "Mode": "once_a_day"}
    )
    config_name = "codex_meowfficer_train_full_live_" + uuid.uuid4().hex
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
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function
        from module.handler.login import LoginHandler
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
        LoginHandler(config=instance.config, device=instance.device).handle_app_login()
        meowfficer.ui_ensure(page_meowfficer)
        meowfficer.wait_meowfficer_buttons()
        before = _ensure_dock(adapter)

        dispatches: list[str] = []
        taps: list[tuple[int, int]] = []
        actions: list[dict[str, Any]] = []
        original_dispatch = adapter._dispatch_mutation
        original_tap = adapter.oracle._tap
        original_click = adapter.oracle.click

        def record_dispatch(capability: str, operation: object) -> object:
            dispatches.append(capability)
            return original_dispatch(capability, operation)

        def record_tap(x: int, y: int) -> None:
            taps.append((x, y))
            original_tap(x, y)

        def record_click(semantic_id: str) -> object:
            receipt = original_click(semantic_id)
            actions.append(
                {
                    "semantic_id": receipt.semantic_id,
                    "generation": receipt.generation,
                    "path": receipt.path,
                }
            )
            return receipt

        adapter._dispatch_mutation = record_dispatch
        adapter.oracle._tap = record_tap
        adapter.oracle.click = record_click
        before_next_run = instance.config.Scheduler_NextRun
        started = time.monotonic()
        instance.meowfficer()
        elapsed = round(time.monotonic() - started, 3)
        after = _wait_dock_state(adapter)
        persisted = _read_json(config_path)
        after_next_run = persisted["Meowfficer"]["Scheduler"]["NextRun"]

        if dispatches:
            raise AssertionError("Meowfficer run unexpectedly used raw mutation dispatch")
        if before.training_finished == 0:
            validation_branch = "full-queue-no-op"
            if [item["semantic_id"] for item in actions] != [
                "meowfficer/train/enter",
                "meowfficer/train/close",
            ]:
                raise AssertionError("full-queue run used unexpected semantic actions")
            if after != before:
                raise AssertionError("full-queue run changed the typed dock state")
        else:
            validation_branch = "collect-one-and-requeue"
            if before.capacity_used >= before.capacity_total:
                raise AssertionError("positive run requires one free dock slot")
            semantic_actions = [item["semantic_id"] for item in actions]
            required = {
                "meowfficer/train/enter",
                "meowfficer/train/complete/first",
                "meowfficer/get/continue",
                "meowfficer/train/start",
                "meowfficer/queue/auto",
                "meowfficer/queue/start",
                "meowfficer/queue/confirm",
                "meowfficer/train/close",
            }
            if not required.issubset(semantic_actions):
                raise AssertionError("positive run missed required semantic actions")
            if after.capacity_used != before.capacity_used + 1:
                raise AssertionError("positive run did not collect exactly one cat")
            if after.training_finished != before.training_finished - 1:
                raise AssertionError("positive run did not consume one completed slot")
            if sum(after.box_counts) != sum(before.box_counts) - 1:
                raise AssertionError("positive run did not enqueue exactly one box")
            if (
                after.purchased != before.purchased
                or after.purchase_total != before.purchase_total
                or after.coins != before.coins
                or after.fort_current != before.fort_current
            ):
                raise AssertionError("positive run changed an unrelated dock resource")
        if after_next_run <= before_next_run.isoformat(sep=" "):
            raise AssertionError("Meowfficer scheduler delay was not committed")
        result.update(
            {
                "passed": True,
                "validation_branch": validation_branch,
                "elapsed_seconds": elapsed,
                "before": before.__dict__,
                "after": after.__dict__,
                "navigation_taps": taps,
                "actions": actions,
                "android_mutation_dispatched": False,
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
        "schema": "alas-headless.meowfficer-train-full-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "Meowfficer.BuyAmount": 0,
            "Meowfficer.FortChoreMeowfficer": False,
            "Meowfficer.OverflowCoins": -1,
            "MeowfficerTrain.Enable": True,
            "MeowfficerTrain.Mode": "once_a_day",
        },
        "source_sha256": {
            "train": _sha256(alas_root / "module" / "meowfficer" / "train.py"),
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
