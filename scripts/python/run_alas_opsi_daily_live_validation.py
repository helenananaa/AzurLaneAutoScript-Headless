#!/usr/bin/env python3
"""Run a bounded, instrumented original-ALAS OpsiDaily task."""

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
    serial: str,
    package: str,
    adb: str,
    do_mission: bool,
    use_tuning_sample: bool,
    fleet: int,
    submarine: bool,
    expect_min_finished: int,
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / f"{seed_config}.json"
    seed = _read(seed_path)
    pid = subprocess.run(
        (adb, "-s", serial, "shell", "pidof", package),
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    ).stdout.strip()
    if not pid:
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Emulator"].update(
        {
            "Serial": serial,
            "PackageName": package,
            "ScreenshotMethod": "ADB",
        }
    )
    for group in payload.values():
        if not isinstance(group, dict):
            continue
        scheduler = group.get("Scheduler")
        if isinstance(scheduler, dict) and "Enable" in scheduler:
            scheduler["Enable"] = False
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["OpsiDaily"]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    payload["OpsiDaily"]["OpsiDaily"].update(
        {"DoMission": do_mission, "UseTuningSample": use_tuning_sample}
    )
    payload["OpsiDaily"]["OpsiFleet"].update(
        {"Fleet": fleet, "Submarine": submarine}
    )
    config_name = "codex_opsi_daily_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-daily-live-qualification/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha(seed_path),
        "configured": {
            "DoMission": do_mission,
            "UseTuningSample": use_tuning_sample,
            "Fleet": fleet,
            "Submarine": submarine,
            "ExpectMinFinished": expect_min_finished,
        },
        "tuning_sample_calls": [],
        "overview_accepts": [],
        "mission_finish_counts": [],
        "fleet_actions": [],
        "order_actions": [],
        "auto_searches": [],
        "login_recovered": False,
        "runtime_preflight": {},
    }
    instance = None
    originals: dict[str, Any] = {}
    prior_cwd = Path.cwd()
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
                "ALAS_SEMANTIC_ADB": adb,
                "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
                "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS": "60000",
            }
        )
        sys.path.insert(0, str(alas_root))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.config.config import AzurLaneConfig, name_to_function
        from module.handler.login import LoginHandler
        from module.os.map import OSMap
        from module.os.tasks.daily import OpsiDaily

        for owner, name in (
            (OpsiDaily, "tuning_sample_use"),
            (OpsiDaily, "os_mission_overview_accept"),
            (OpsiDaily, "os_finish_daily_mission"),
            (OSMap, "fleet_set"),
            (OSMap, "os_order_execute"),
            (OSMap, "run_auto_search"),
        ):
            originals[name] = getattr(owner, name)
        originals["check_task_switch"] = AzurLaneConfig.check_task_switch

        def observed_tuning_sample(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["tuning_sample_use"](task, *args, **kwargs)
            result["tuning_sample_calls"].append(
                {"returned": returned, "elapsed_seconds": round(time.monotonic() - started, 3)}
            )
            return returned

        def observed_overview(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["os_mission_overview_accept"](task, *args, **kwargs)
            result["overview_accepts"].append(
                {"returned": returned, "elapsed_seconds": round(time.monotonic() - started, 3)}
            )
            return returned

        def observed_finish(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["os_finish_daily_mission"](task, *args, **kwargs)
            result["mission_finish_counts"].append(
                {"count": returned, "elapsed_seconds": round(time.monotonic() - started, 3)}
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
            return returned

        def observed_auto_search(task, *args, **kwargs):
            started = time.monotonic()
            returned = originals["run_auto_search"](task, *args, **kwargs)
            result["auto_searches"].append(
                {"finished_combat": returned, "elapsed_seconds": round(time.monotonic() - started, 3)}
            )
            return returned

        OpsiDaily.tuning_sample_use = observed_tuning_sample
        OpsiDaily.os_mission_overview_accept = observed_overview
        OpsiDaily.os_finish_daily_mission = observed_finish
        OSMap.fleet_set = observed_fleet
        OSMap.os_order_execute = observed_order
        OSMap.run_auto_search = observed_auto_search
        AzurLaneConfig.check_task_switch = lambda self, message="": None

        instance = AzurLaneAutoScript(config_name)
        session = instance.device.semantic_adapter
        adapter = session.open()
        oracle = adapter.oracle
        # The task owns startup recovery before any runner-level login/main
        # navigation. This is the same bounded passive owner that OSMap.os_init
        # declares; it never authorizes an input by itself.
        session.begin_operation_siren_startup_recovery()
        observed = oracle.read_state()
        result["runtime_preflight"] = {
            "package": observed.snapshot.get("package"),
            "pid": observed.snapshot.get("pid"),
            "generation": observed.generation,
            "scene_handle": observed.scene_handle,
            "status": observed.snapshot.get("status"),
            "age_ms": observed.snapshot.get("age_ms"),
            "main_thread": observed.snapshot.get("main_thread"),
            "driver_revision": observed.snapshot.get("driver_revision"),
        }
        if oracle.enabled("login/enter"):
            LoginHandler(instance.config, device=instance.device).handle_app_login()
            result["login_recovered"] = True
            instance.goto_main()
        task = name_to_function("OpsiDaily")
        instance.config.task = task
        instance.config.bind(task)
        started = time.monotonic()
        result["task_result"] = instance.run("opsi_daily")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["final_config"] = {"NextRun": str(instance.config.Scheduler_NextRun)}
        errors = []
        if use_tuning_sample and len(result["tuning_sample_calls"]) != 1:
            errors.append("tuning sample branch did not execute exactly once")
        if not use_tuning_sample and result["tuning_sample_calls"]:
            errors.append("disabled tuning sample branch executed")
        if do_mission and not result["overview_accepts"]:
            errors.append("daily mission overview was not visited")
        if not do_mission and result["overview_accepts"]:
            errors.append("disabled daily mission branch visited overview")
        finished_total = sum(
            int(item["count"])
            for item in result["mission_finish_counts"]
            if isinstance(item.get("count"), int)
        )
        result["finished_total"] = finished_total
        if do_mission and finished_total < expect_min_finished:
            errors.append(
                "daily mission completion count was below the live expectation: "
                f"{finished_total} < {expect_min_finished}"
            )
        if result.get("task_result") is not True:
            errors.append("original OpsiDaily task did not return success")
        result["validation_errors"] = errors
        result["passed"] = not errors
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["passed"] = False
    finally:
        if originals:
            from module.config.config import AzurLaneConfig
            from module.os.map import OSMap
            from module.os.tasks.daily import OpsiDaily

            for name in (
                "tuning_sample_use",
                "os_mission_overview_accept",
                "os_finish_daily_mission",
            ):
                setattr(OpsiDaily, name, originals[name])
            for name in ("fleet_set", "os_order_execute", "run_auto_search"):
                setattr(OSMap, name, originals[name])
            AzurLaneConfig.check_task_switch = originals["check_task_switch"]
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
        os.chdir(prior_cwd)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    result["source_sha256"] = {
        **semantic_source_hashes(ROOT),
        "daily_task": _sha(alas_root / "module" / "os" / "tasks" / "daily.py"),
        "mission_handler": _sha(alas_root / "module" / "os_handler" / "mission.py"),
        "storage_handler": _sha(alas_root / "module" / "os_handler" / "storage.py"),
        "adapter": _sha(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        "oracle": _sha(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--do-mission", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--use-tuning-sample", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fleet", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--submarine", action="store_true")
    parser.add_argument("--expect-min-finished", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.expect_min_finished < 0:
        parser.error("--expect-min-finished must be non-negative")
    if not args.do_mission and args.expect_min_finished:
        parser.error("--expect-min-finished requires --do-mission")
    result = validate(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
        serial=args.serial,
        package=args.package,
        adb=args.adb,
        do_mission=args.do_mission,
        use_tuning_sample=args.use_tuning_sample,
        fleet=args.fleet,
        submarine=args.submarine,
        expect_min_finished=args.expect_min_finished,
    )
    _write(args.output.resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
