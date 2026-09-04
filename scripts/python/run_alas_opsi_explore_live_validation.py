#!/usr/bin/env python3
"""Run a bounded, instrumented original-ALAS OpsiExplore traversal."""

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


def validate(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    *,
    last_zone: int | str,
    special_radar: bool,
    fleet: int,
    submarine: bool,
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
    payload["OpsiExplore"]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    payload["OpsiExplore"]["OpsiExplore"].update(
        {
            "ForceRun": False,
            "LastZone": last_zone,
            "SpecialRadar": special_radar,
        }
    )
    payload["OpsiExplore"]["OpsiFleet"].update(
        {"Fleet": fleet, "Submarine": submarine}
    )
    config_name = "codex_opsi_explore_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-explore-live-qualification/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha(seed_path),
        "configured": {
            "ForceRun": False,
            "LastZone": last_zone,
            "SpecialRadar": special_radar,
            "Fleet": fleet,
            "Submarine": submarine,
        },
        "zone_visits": [],
        "zone_failures": [],
        "fleet_actions": [],
        "order_actions": [],
        "auto_searches": [],
        "preflight_auto_searches": [],
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
        from module.config.config import AzurLaneConfig, name_to_function
        from module.os.map import OSMap
        from module.os.tasks.explore import OpsiExplore

        for name in (
            "globe_goto",
            "fleet_set",
            "os_order_execute",
            "run_auto_search",
        ):
            originals[name] = getattr(OSMap, name)
        originals["check_task_switch"] = AzurLaneConfig.check_task_switch
        originals["_os_explore"] = OpsiExplore._os_explore
        inside_explore = False

        def observed_os_explore(task, *args, **kwargs):
            nonlocal inside_explore
            inside_explore = True
            try:
                return originals["_os_explore"](task, *args, **kwargs)
            finally:
                inside_explore = False

        def observed_globe_goto(task, zone, *args, **kwargs):
            started = time.monotonic()
            resolved = task.name_to_zone(zone)
            try:
                returned = originals["globe_goto"](
                    task, zone, *args, **kwargs
                )
            except BaseException as exc:
                result["zone_failures"].append(
                    {
                        "requested": getattr(resolved, "zone_id", zone),
                        "name": str(resolved),
                        "error": type(exc).__name__ + ": " + str(exc),
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    }
                )
                raise
            result["zone_visits"].append(
                {
                    "requested": getattr(resolved, "zone_id", zone),
                    "name": str(resolved),
                    "stop_if_safe": bool(kwargs.get("stop_if_safe", False)),
                    "entered_dangerous_zone": bool(returned),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            return returned

        def observed_fleet_set(task, value, *args, **kwargs):
            returned = originals["fleet_set"](task, value, *args, **kwargs)
            result["fleet_actions"].append({"requested": value, "returned": returned})
            return returned

        def observed_os_order_execute(task, *args, **kwargs):
            returned = originals["os_order_execute"](task, *args, **kwargs)
            result["order_actions"].append(
                {
                    "recon_scan": kwargs.get("recon_scan"),
                    "submarine_call": kwargs.get("submarine_call"),
                    "returned": returned,
                }
            )
            return returned

        def observed_run_auto_search(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["run_auto_search"](task, *args, **kwargs)
            key = "auto_searches" if inside_explore else "preflight_auto_searches"
            result[key].append(
                {
                    "finished_combat": returned,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            return returned

        OSMap.globe_goto = observed_globe_goto
        OSMap.fleet_set = observed_fleet_set
        OSMap.os_order_execute = observed_os_order_execute
        OSMap.run_auto_search = observed_run_auto_search
        OpsiExplore._os_explore = observed_os_explore
        AzurLaneConfig.check_task_switch = lambda self, message="": None

        instance = AzurLaneAutoScript(config_name)
        task = name_to_function("OpsiExplore")
        instance.config.task = task
        instance.config.bind(task)
        result["explore_order"] = [
            int(value.strip())
            for value in instance.config.OS_EXPLORE_FILTER.split(">")
        ]
        started = time.monotonic()
        result["task_result"] = instance.run("opsi_explore")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["final_config"] = {
            "LastZone": instance.config.OpsiExplore_LastZone,
            "SpecialRadar": instance.config.OpsiExplore_SpecialRadar,
            "NextRun": str(instance.config.Scheduler_NextRun),
        }

        expected = result["explore_order"]
        if last_zone in expected:
            expected = expected[expected.index(last_zone) + 1 :]
        visited = [visit["requested"] for visit in result["zone_visits"]]
        validation_errors = []
        if visited != expected:
            validation_errors.append("visited zone sequence differs from original explore order")
        if result["final_config"]["LastZone"] != 0:
            validation_errors.append("completed traversal did not reset LastZone")
        if result["final_config"]["SpecialRadar"] is not False:
            validation_errors.append("completed traversal did not reset SpecialRadar")
        if len(result["fleet_actions"]) != len(result["auto_searches"]):
            validation_errors.append("dangerous-zone fleet and auto-search counts differ")
        if len(result["order_actions"]) != len(result["auto_searches"]):
            validation_errors.append("dangerous-zone order and auto-search counts differ")
        result["validation_errors"] = validation_errors
        result["passed"] = not validation_errors
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["passed"] = False
    finally:
        if originals:
            from module.config.config import AzurLaneConfig
            from module.os.map import OSMap
            from module.os.tasks.explore import OpsiExplore

            for name in (
                "globe_goto",
                "fleet_set",
                "os_order_execute",
                "run_auto_search",
            ):
                setattr(OSMap, name, originals[name])
            AzurLaneConfig.check_task_switch = originals["check_task_switch"]
            OpsiExplore._os_explore = originals["_os_explore"]
        if instance is not None:
            device = instance.__dict__.get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    result["source_sha256"] = {
        **semantic_source_hashes(ROOT),
        "explore_task": _sha(alas_root / "module" / "os" / "tasks" / "explore.py"),
        "globe_camera": _sha(alas_root / "module" / "os" / "globe_camera.py"),
        "globe_operation": _sha(alas_root / "module" / "os" / "globe_operation.py"),
        "map_event": _sha(alas_root / "module" / "os_handler" / "map_event.py"),
        "adapter": _sha(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        "oracle": _sha(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--last-zone", default="0")
    parser.add_argument("--special-radar", action="store_true")
    parser.add_argument("--fleet", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--submarine", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        last_zone: int | str = int(args.last_zone)
    except ValueError:
        last_zone = args.last_zone
    result = validate(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
        last_zone=last_zone,
        special_radar=args.special_radar,
        fleet=args.fleet,
        submarine=args.submarine,
    )
    _write(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
