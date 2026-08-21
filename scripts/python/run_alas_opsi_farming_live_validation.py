#!/usr/bin/env python3
"""Run one bounded, instrumented original-ALAS OpSi farming cycle."""

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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    *,
    task_name: str,
    target_zone: int,
    fleet: int,
    submarine: bool,
    action_point_preserve: int,
    hazard_level: int,
    stop_after_submarine_order: bool,
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
        if isinstance(group, dict):
            scheduler = group.get("Scheduler")
            if isinstance(scheduler, dict) and "Enable" in scheduler:
                scheduler["Enable"] = False
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload[task_name]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    payload[task_name]["OpsiFleet"].update({"Fleet": fleet, "Submarine": submarine})
    if task_name == "OpsiMeowfficerFarming":
        payload[task_name][task_name].update(
            {
                "ActionPointPreserve": action_point_preserve,
                "HazardLevel": hazard_level,
                "TargetZone": str(target_zone),
            }
        )
    else:
        payload[task_name][task_name].update({"TargetZone": target_zone})

    config_name = "codex_opsi_farming_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)
    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-farming-live-qualification/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha(seed_path),
        "configured": {
            "task": task_name,
            "TargetZone": target_zone,
            "Fleet": fleet,
            "Submarine": submarine,
            "ActionPointPreserve": action_point_preserve,
            "HazardLevel": hazard_level,
            "StopAfterSubmarineOrder": stop_after_submarine_order,
        },
        "action_point_calls": [],
        "zone_visits": [],
        "fleet_actions": [],
        "order_actions": [],
        "searches": [],
        "preflight_searches": [],
        "post_search_calls": [],
    }

    def collect_validation_errors() -> list[str]:
        errors: list[str] = []
        if not result.get("bounded_stop"):
            errors.append("original task did not complete one bounded cycle")
        if not result["action_point_calls"]:
            errors.append("action-point gate was not exercised")
        if not result["fleet_actions"]:
            errors.append("fleet selection was not exercised")
        if target_zone and not result["zone_visits"] and task_name == "OpsiMeowfficerFarming":
            errors.append("explicit target zone was not visited")
        if (
            target_zone
            and task_name == "OpsiMeowfficerFarming"
            and result["zone_visits"]
            and result["zone_visits"][-1]["requested"] != target_zone
        ):
            errors.append("final visited zone differs from explicit target zone")
        if stop_after_submarine_order:
            submarine_orders = [
                item for item in result["order_actions"]
                if item["submarine_call"] is True
            ]
            if len(submarine_orders) != 1:
                errors.append("expected exactly one submarine order execution")
            return errors
        expected_search = (
            "run_auto_search"
            if task_name == "OpsiMeowfficerFarming"
            else "run_strategic_search"
        )
        if [item["kind"] for item in result["searches"]] != [expected_search]:
            errors.append("expected exactly one original search execution")
        associated_post_search = sum(
            bool(item["associated_with_search"])
            for item in result["post_search_calls"]
        )
        if associated_post_search != 1:
            errors.append("expected exactly one post-search handling pass")
        return errors
    instance = None
    originals: dict[str, Any] = {}
    previous_cwd = Path.cwd()
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
        from module.os.tasks.hazard_leveling import OpsiHazard1Leveling
        from module.os.tasks.meowfficer_farming import OpsiMeowfficerFarming

        for name in (
            "action_point_set",
            "globe_goto",
            "fleet_set",
            "os_order_execute",
            "run_auto_search",
            "run_strategic_search",
            "handle_after_auto_search",
        ):
            originals[name] = getattr(OSMap, name)
        originals["check_task_switch"] = AzurLaneConfig.check_task_switch
        originals["task_switched"] = AzurLaneConfig.task_switched
        task_class = (
            OpsiMeowfficerFarming
            if task_name == "OpsiMeowfficerFarming"
            else OpsiHazard1Leveling
        )
        task_method_name = (
            "os_meowfficer_farming"
            if task_name == "OpsiMeowfficerFarming"
            else "os_hazard1_leveling"
        )
        originals["task_method"] = getattr(task_class, task_method_name)
        inside_task = False

        def observed_task_method(task, *args, **kwargs):
            nonlocal inside_task
            inside_task = True
            try:
                if task_name == "OpsiMeowfficerFarming":
                    object.__setattr__(
                        task.config,
                        "OpsiMeowfficerFarming_ActionPointPreserve",
                        action_point_preserve,
                    )
                    object.__setattr__(
                        task.config, "OpsiMeowfficerFarming_HazardLevel", hazard_level
                    )
                    object.__setattr__(
                        task.config, "OpsiMeowfficerFarming_TargetZone", str(target_zone)
                    )
                else:
                    object.__setattr__(
                        task.config, "OpsiHazard1Leveling_TargetZone", target_zone
                    )
                object.__setattr__(task.config, "OpsiFleet_Fleet", fleet)
                object.__setattr__(task.config, "OpsiFleet_Submarine", submarine)
                result["effective_task_config"] = {
                    "TargetZone": getattr(
                        task.config,
                        "OpsiMeowfficerFarming_TargetZone"
                        if task_name == "OpsiMeowfficerFarming"
                        else "OpsiHazard1Leveling_TargetZone",
                    ),
                    "Fleet": task.config.OpsiFleet_Fleet,
                    "Submarine": task.config.OpsiFleet_Submarine,
                }
                return originals["task_method"](task, *args, **kwargs)
            finally:
                inside_task = False

        def observed_action_point(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["action_point_set"](task, *args, **kwargs)
            result["action_point_calls"].append(
                {
                    "cost": kwargs.get("cost"),
                    "keep_current_ap": kwargs.get("keep_current_ap"),
                    "check_rest_ap": kwargs.get("check_rest_ap"),
                    "total": getattr(task, "_action_point_total", None),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            return returned

        def observed_globe(task, zone, *args, **kwargs):
            started = time.monotonic()
            resolved = task.name_to_zone(zone)
            returned = originals["globe_goto"](task, zone, *args, **kwargs)
            result["zone_visits"].append(
                {
                    "requested": getattr(resolved, "zone_id", zone),
                    "name": str(resolved),
                    "types": kwargs.get("types"),
                    "refresh": kwargs.get("refresh"),
                    "entered_dangerous_zone": bool(returned),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            return returned

        def observed_fleet(task, value, *args, **kwargs):
            returned = originals["fleet_set"](task, value, *args, **kwargs)
            result["fleet_actions"].append({"requested": value, "returned": returned})
            return returned

        def observed_order(task, *args, **kwargs):
            returned = originals["os_order_execute"](task, *args, **kwargs)
            result["order_actions"].append(
                {
                    "recon_scan": kwargs.get("recon_scan"),
                    "submarine_call": kwargs.get("submarine_call"),
                    "returned": returned,
                }
            )
            if stop_after_submarine_order and kwargs.get("submarine_call") is True:
                result["bounded_stop"] = (
                    "one original submarine order execution completed"
                )
                task.config.task_stop()
            return returned

        def observed_search(kind):
            def wrapper(task, *args, **kwargs):
                started = time.monotonic()
                returned = originals[kind](task, *args, **kwargs)
                destination = "searches" if inside_task else "preflight_searches"
                result[destination].append(
                    {
                        "kind": kind,
                        "returned": returned,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    }
                )
                return returned
            return wrapper

        def observed_post_search(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["handle_after_auto_search"](task, *args, **kwargs)
            result["post_search_calls"].append(
                {
                    "returned": returned,
                    "associated_with_search": bool(result["searches"]),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            return returned

        def bounded_switch(_config, message=""):
            if result["searches"] and any(
                item["associated_with_search"] for item in result["post_search_calls"]
            ):
                result["bounded_stop"] = message or "one original task cycle completed"
                _config.task_stop()
            return originals["check_task_switch"](_config, message)

        def isolated_task_switched(_config):
            # The qualification owns exactly one bounded task cycle. Seed
            # scheduler timestamps must not interrupt the original search
            # before its post-search boundary is observed.
            return False

        OSMap.action_point_set = observed_action_point
        OSMap.globe_goto = observed_globe
        OSMap.fleet_set = observed_fleet
        OSMap.os_order_execute = observed_order
        OSMap.run_auto_search = observed_search("run_auto_search")
        OSMap.run_strategic_search = observed_search("run_strategic_search")
        OSMap.handle_after_auto_search = observed_post_search
        setattr(task_class, task_method_name, observed_task_method)
        AzurLaneConfig.check_task_switch = bounded_switch
        AzurLaneConfig.task_switched = isolated_task_switched

        instance = AzurLaneAutoScript(config_name)
        task = name_to_function(task_name)
        instance.config.task = task
        instance.config.bind(task)
        # ALAS' config updater preserves defaults for some disabled task input
        # fields. Pin the same validated temporary values on the bound in-memory
        # config so the live task exercises the requested branch.
        instance.config.OpsiFleet_Fleet = fleet
        instance.config.OpsiFleet_Submarine = submarine
        if task_name == "OpsiMeowfficerFarming":
            instance.config.OpsiMeowfficerFarming_ActionPointPreserve = action_point_preserve
            instance.config.OpsiMeowfficerFarming_HazardLevel = hazard_level
            instance.config.OpsiMeowfficerFarming_TargetZone = str(target_zone)
            instance.config.override(
                OpsiMeowfficerFarming_ActionPointPreserve=action_point_preserve,
                OpsiMeowfficerFarming_HazardLevel=hazard_level,
                OpsiMeowfficerFarming_TargetZone=str(target_zone),
                OpsiFleet_Fleet=fleet,
                OpsiFleet_Submarine=submarine,
            )
        else:
            instance.config.OpsiHazard1Leveling_TargetZone = target_zone
            instance.config.override(
                OpsiHazard1Leveling_TargetZone=target_zone,
                OpsiFleet_Fleet=fleet,
                OpsiFleet_Submarine=submarine,
            )
        command = (
            "opsi_meowfficer_farming"
            if task_name == "OpsiMeowfficerFarming"
            else "opsi_hazard1_leveling"
        )
        started = time.monotonic()
        result["task_result"] = instance.run(command)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["final_config"] = {
            "OS_ACTION_POINT_PRESERVE": getattr(instance.config, "OS_ACTION_POINT_PRESERVE", None),
            "NextRun": str(instance.config.Scheduler_NextRun),
        }
        errors = collect_validation_errors()
        result["validation_errors"] = errors
        result["passed"] = not errors
    except BaseException as exc:
        if isinstance(exc, SystemExit) and result.get("bounded_stop"):
            result["bounded_exit_code"] = exc.code
            errors = collect_validation_errors()
            result["validation_errors"] = errors
            result["passed"] = not errors
        else:
            result["error"] = type(exc).__name__ + ": " + str(exc)
            result["passed"] = False
    finally:
        if originals:
            from module.config.config import AzurLaneConfig
            from module.os.map import OSMap
            from module.os.tasks.hazard_leveling import OpsiHazard1Leveling
            from module.os.tasks.meowfficer_farming import OpsiMeowfficerFarming

            for name in (
                "action_point_set",
                "globe_goto",
                "fleet_set",
                "os_order_execute",
                "run_auto_search",
                "run_strategic_search",
                "handle_after_auto_search",
            ):
                setattr(OSMap, name, originals[name])
            AzurLaneConfig.check_task_switch = originals["check_task_switch"]
            AzurLaneConfig.task_switched = originals["task_switched"]
            task_class = (
                OpsiMeowfficerFarming
                if task_name == "OpsiMeowfficerFarming"
                else OpsiHazard1Leveling
            )
            task_method_name = (
                "os_meowfficer_farming"
                if task_name == "OpsiMeowfficerFarming"
                else "os_hazard1_leveling"
            )
            setattr(task_class, task_method_name, originals["task_method"])
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
        os.chdir(previous_cwd)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    result["source_sha256"] = {
        "task": _sha(
            alas_root
            / "module"
            / "os"
            / "tasks"
            / ("meowfficer_farming.py" if task_name == "OpsiMeowfficerFarming" else "hazard_leveling.py")
        ),
        "map": _sha(alas_root / "module" / "os" / "map.py"),
        "adapter": _sha(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        "oracle": _sha(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument(
        "--task",
        choices=("OpsiMeowfficerFarming", "OpsiHazard1Leveling"),
        default="OpsiMeowfficerFarming",
    )
    parser.add_argument("--target-zone", type=int, default=22)
    parser.add_argument("--fleet", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--submarine", action="store_true")
    parser.add_argument("--stop-after-submarine-order", action="store_true")
    parser.add_argument("--action-point-preserve", type=int, default=1)
    parser.add_argument("--hazard-level", type=int, choices=(3, 4, 5), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.stop_after_submarine_order and not args.submarine:
        parser.error("--stop-after-submarine-order requires --submarine")
    result = validate(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
        task_name=args.task,
        target_zone=args.target_zone,
        fleet=args.fleet,
        submarine=args.submarine,
        action_point_preserve=args.action_point_preserve,
        hazard_level=args.hazard_level,
        stop_after_submarine_order=args.stop_after_submarine_order,
    )
    _write(args.output.resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
