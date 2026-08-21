#!/usr/bin/env python3
"""Run one bounded, instrumented original-ALAS OpsiMonthBoss task."""

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
sys.path.insert(0, str(ROOT / "python"))


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=_json_safe,
        )
        + "\n",
        encoding="utf-8",
    )


def _json_safe(value: Any) -> Any:
    """Preserve typed ALAS return evidence without leaking Python objects."""

    try:
        json.dumps(value)
        return value
    except TypeError:
        return {
            "type": type(value).__name__,
            "zone_id": getattr(value, "zone_id", None),
            "name": getattr(value, "name", str(value)),
        }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    *,
    mode: str,
    check_adaptability: bool,
    force_run: bool,
    exit_after_room_entry: bool = False,
    skip_recovery: bool = False,
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
    payload["OpsiMonthBoss"]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    payload["OpsiMonthBoss"]["OpsiMonthBoss"].update(
        {
            "Mode": mode,
            "CheckAdaptability": check_adaptability,
            "ForceRun": force_run,
            "ExitAfterRoomEntry": exit_after_room_entry,
            "SkipRecovery": skip_recovery,
        }
    )
    config_name = "codex_opsi_month_boss_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-month-boss-live-qualification/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha(seed_path),
        "configured": {
            "Mode": mode,
            "CheckAdaptability": check_adaptability,
            "ForceRun": force_run,
            "Filter": payload["OpsiMonthBoss"]["OpsiFleetFilter"]["Filter"],
        },
        "mission_difficulties": [],
        "adaptability": [],
        "globe_targets": [],
        "room_entries": [],
        "fleet_selections": [],
        "boss_clear_results": [],
        "repair_results": [],
        "resolve_results": [],
        "delay_calls": [],
    }
    instance = None
    originals: dict[str, Any] = {}
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

        for owner, name in (
            (OpsiMonthBoss, "os_mission_enter"),
            (OpsiMonthBoss, "get_adaptability"),
            (OpsiMonthBoss, "globe_goto"),
            (OpsiMonthBoss, "go_month_boss_room"),
            (OpsiMonthBoss, "boss_clear"),
            (OpsiMonthBoss, "fleet_repair"),
            (OpsiMonthBoss, "handle_fleet_resolve"),
            (OpsiMonthBoss, "month_boss_delay"),
            (OSMap, "fleet_set"),
        ):
            originals[name] = getattr(owner, name)

        def observed_mission_enter(task, *args, **kwargs):
            returned = originals["os_mission_enter"](task, *args, **kwargs)
            task.device.semantic_adapter.refresh_frame()
            difficulty = (
                task.device.semantic_adapter
                .open().oracle.operation_siren_month_boss_difficulty()
            )
            result["mission_difficulties"].append(difficulty)
            return returned

        def observed_adaptability(task, *args, **kwargs):
            returned = originals["get_adaptability"](task, *args, **kwargs)
            result["adaptability"].append(list(returned))
            return returned

        def observed_globe_goto(task, zone, *args, **kwargs):
            returned = originals["globe_goto"](task, zone, *args, **kwargs)
            returned_evidence = _json_safe(returned)
            result["globe_targets"].append(
                {"zone": _json_safe(zone), "returned": returned_evidence}
            )
            return returned

        def observed_room(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["go_month_boss_room"](task, *args, **kwargs)
            result["room_entries"].append(
                {
                    "is_normal": kwargs.get("is_normal"),
                    "returned": returned,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            return returned

        def observed_fleet(task, value, *args, **kwargs):
            returned = originals["fleet_set"](task, value, *args, **kwargs)
            result["fleet_selections"].append(
                {"requested": value, "returned": returned}
            )
            return returned

        def observed_boss_clear(task, *args, **kwargs):
            started = time.monotonic()
            observation = {
                "returned": None,
                "kwargs": dict(kwargs),
            }
            try:
                if exit_after_room_entry:
                    task.map_exit()
                    returned = False
                else:
                    returned = originals["boss_clear"](task, *args, **kwargs)
                observation["returned"] = _json_safe(returned)
                return returned
            except BaseException as exc:
                observation["raised"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                observation["elapsed_seconds"] = round(
                    time.monotonic() - started, 3
                )
                result["boss_clear_results"].append(observation)

        def observed_repair(task, *args, **kwargs):
            returned = (
                None
                if skip_recovery
                else originals["fleet_repair"](task, *args, **kwargs)
            )
            result["repair_results"].append(
                {"returned": _json_safe(returned)}
            )
            return returned

        def observed_resolve(task, *args, **kwargs):
            returned = (
                None
                if skip_recovery
                else originals["handle_fleet_resolve"](task, *args, **kwargs)
            )
            result["resolve_results"].append(
                {"returned": _json_safe(returned)}
            )
            return returned

        def observed_delay(task, *args, **kwargs):
            result["delay_calls"].append(
                {"args": list(args), "kwargs": dict(kwargs)}
            )
            return originals["month_boss_delay"](task, *args, **kwargs)

        OpsiMonthBoss.os_mission_enter = observed_mission_enter
        OpsiMonthBoss.get_adaptability = observed_adaptability
        OpsiMonthBoss.globe_goto = observed_globe_goto
        OpsiMonthBoss.go_month_boss_room = observed_room
        OpsiMonthBoss.boss_clear = observed_boss_clear
        OpsiMonthBoss.fleet_repair = observed_repair
        OpsiMonthBoss.handle_fleet_resolve = observed_resolve
        OpsiMonthBoss.month_boss_delay = observed_delay
        OSMap.fleet_set = observed_fleet

        instance = AzurLaneAutoScript(config_name)
        task_name = name_to_function("OpsiMonthBoss")
        instance.config.task = task_name
        instance.config.bind(task_name)
        started = time.monotonic()
        result["task_result"] = instance.run("opsi_month_boss")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["final_config"] = {
            "NextRun": str(instance.config.Scheduler_NextRun)
        }
        errors = []
        if not result["mission_difficulties"]:
            errors.append("monthly boss mission difficulty was not observed")
        if result["mission_difficulties"] and not result["boss_clear_results"]:
            errors.append("monthly boss combat result was not observed")
        result["validation_errors"] = errors
        result["passed"] = not errors and result["task_result"] is True
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
        result["temporary_config_removed"] = not config_path.exists()
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
    parser.add_argument("--mode", choices=("normal", "normal_hard"), default="normal")
    parser.add_argument(
        "--check-adaptability",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--force-run", action="store_true")
    parser.add_argument("--exit-after-room-entry", action="store_true")
    parser.add_argument("--skip-recovery", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
        mode=args.mode,
        check_adaptability=args.check_adaptability,
        force_run=args.force_run,
        exit_after_room_entry=args.exit_after_room_entry,
        skip_recovery=args.skip_recovery,
    )
    if args.output is not None:
        _write((ROOT / args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
