#!/usr/bin/env python3
"""Run original-ALAS handle_fleet_resolve after Month Boss dock repair."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate(alas_root: Path, seed_config: str, driver_revision: str) -> dict[str, Any]:
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
    config_name = "codex_opsi_fleet_resolve_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-fleet-resolve-live/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "fleet_selections": [],
        "resolve_returned": None,
    }
    instance = None
    previous = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
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
            }
        )
        sys.path.insert(0, str(alas_root))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function
        from module.os.map import OSMap
        from module.os.tasks.month_boss import OpsiMonthBoss

        original_fleet_set = OSMap.fleet_set

        def observed_fleet(task, value, *args, **kwargs):
            returned = original_fleet_set(task, value, *args, **kwargs)
            result["fleet_selections"].append(
                {"requested": value, "returned": returned}
            )
            return returned

        OSMap.fleet_set = observed_fleet
        instance = AzurLaneAutoScript(config_name)
        task_name = name_to_function("OpsiMonthBoss")
        instance.config.task = task_name
        instance.config.bind(task_name)
        task = OpsiMonthBoss(config=instance.config, device=instance.device)
        started = time.monotonic()
        task.os_init()
        result["resolve_returned"] = task.handle_fleet_resolve(revert=False)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["passed"] = True
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["passed"] = False
    finally:
        if instance is not None:
            try:
                instance.device.semantic_adapter.close()
            except Exception:
                pass
        if config_path.exists():
            config_path.unlink()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
    )
    if args.output is not None:
        _write((ROOT / args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
