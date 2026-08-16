#!/usr/bin/env python3
"""Run bounded live qualification for ALAS's ``Restart`` scheduler task.

This runner intentionally uses a disposable ALAS config.  It drives the
unchanged scheduler and LoginHandler code in a patched ALAS checkout, records
the durable Scheduler writes for every declared scheduler instance, then
executes one disabled-package failure followed by one real recovery restart.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_COMPONENT_SUFFIX = "com.manjuu.azurlane.MainActivity"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _local_now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise AssertionError(f"Scheduler.NextRun is not a string: {value!r}")
    return datetime.fromisoformat(value).replace(tzinfo=None)


def _interval_bounds(value: object) -> tuple[int, int]:
    if isinstance(value, bool):
        raise AssertionError(f"boolean Scheduler interval: {value!r}")
    if isinstance(value, int):
        return value, value
    if isinstance(value, str):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", value)
        if match is not None:
            low = int(match.group(1))
            high = int(match.group(2) or low)
            if low <= high:
                return low, high
    raise AssertionError(f"unsupported Scheduler interval: {value!r}")


def _adb(serial: str, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    if check and completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def _pid(serial: str, package: str) -> int | None:
    raw = _adb(serial, "shell", "pidof", package, check=False).strip()
    for token in raw.split():
        if token.isdigit():
            return int(token)
    return None


def _observer_forwards(serial: str) -> list[str]:
    raw = _adb(serial, "forward", "--list", check=False)
    return [line for line in raw.splitlines() if line.split(maxsplit=1)[0:1] == [serial]]


def _top_resumed_component(serial: str) -> str | None:
    raw = _adb(serial, "shell", "dumpsys", "activity", "activities", check=False)
    match = re.search(r"topResumedActivity=.*? ([\w.$]+/[\w.$]+)", raw)
    if match is not None:
        return match.group(1)
    match = re.search(r"mResumedActivity:.*? ([\w.$]+/[\w.$]+)", raw)
    return match.group(1) if match is not None else None


def _package_enabled(serial: str, package: str) -> bool:
    return bool(_adb(serial, "shell", "pm", "path", package, check=False).strip())


def _close_semantic_session(instance: object) -> None:
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _load_live_modules(alas_root: Path, driver_revision: str) -> SimpleNamespace:
    if re.fullmatch(r"[0-9a-f]{40}", driver_revision) is None:
        raise ValueError("driver revision must be a 40-character lowercase SHA-1")
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ.setdefault("ALAS_SEMANTIC_ADB", "adb")
    python_root = ROOT / "python"
    if str(python_root) not in sys.path:
        sys.path.insert(0, str(python_root))
    if str(alas_root) not in sys.path:
        sys.path.insert(0, str(alas_root))
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import AzurLaneConfig

    return SimpleNamespace(AzurLaneAutoScript=AzurLaneAutoScript, AzurLaneConfig=AzurLaneConfig)


def _scheduler_panels(args: Mapping[str, Any]) -> list[str]:
    panels = []
    for panel, panel_data in args.items():
        scheduler = panel_data.get("Scheduler")
        if isinstance(scheduler, Mapping):
            required = {
                "Enable",
                "NextRun",
                "Command",
                "SuccessInterval",
                "FailureInterval",
                "ServerUpdate",
            }
            if set(scheduler) != required:
                raise AssertionError(f"{panel} has a non-standard Scheduler surface")
            panels.append(panel)
    if len(panels) != 50:
        raise AssertionError(f"expected 50 Scheduler panels, got {len(panels)}")
    return panels


def _scheduler_classes(args: Mapping[str, Any], panels: list[str]) -> int:
    signatures = {
        json.dumps(
            {
                field: args[panel]["Scheduler"][field]["value"]
                for field in ("Enable", "SuccessInterval", "FailureInterval", "ServerUpdate")
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for panel in panels
    }
    if len(signatures) != 15:
        raise AssertionError(f"expected 15 Scheduler equivalence classes, got {len(signatures)}")
    return len(signatures)


def _targeted_config(
    seed: Mapping[str, Any],
    panels: list[str],
    target: str,
    *,
    enabled: bool,
    due_at: datetime,
) -> dict[str, Any]:
    payload = copy.deepcopy(seed)
    for panel in panels:
        payload[panel]["Scheduler"]["Enable"] = False
    scheduler = payload[target]["Scheduler"]
    scheduler["Enable"] = enabled
    scheduler["NextRun"] = _format_time(due_at)
    scheduler["Command"] = target
    payload["Alas"]["Optimization"]["TaskHoardingDuration"] = 0
    payload["Alas"]["Optimization"]["WhenTaskQueueEmpty"] = "stay_there"
    return payload


def _config_path(alas_root: Path, config_name: str) -> Path:
    return alas_root / "config" / f"{config_name}.json"


def _write_targeted_config(
    alas_root: Path,
    config_name: str,
    seed: Mapping[str, Any],
    panels: list[str],
    target: str,
    *,
    enabled: bool,
    due_at: datetime,
) -> None:
    _json_write(
        _config_path(alas_root, config_name),
        _targeted_config(seed, panels, target, enabled=enabled, due_at=due_at),
    )


def _assert_interval_result(
    label: str,
    result: datetime,
    started: datetime,
    completed: datetime,
    value: object,
) -> None:
    low, high = _interval_bounds(value)
    earliest = started + timedelta(minutes=low, seconds=-2)
    latest = completed + timedelta(minutes=high, seconds=2)
    if not earliest <= result <= latest:
        raise AssertionError(
            f"{label} next run {result} outside [{earliest}, {latest}] for {value!r}"
        )


def _exercise_scheduler_instances(
    modules: SimpleNamespace,
    alas_root: Path,
    config_name: str,
    seed: Mapping[str, Any],
    args: Mapping[str, Any],
    panels: list[str],
) -> Mapping[str, Any]:
    """Use original config queueing and durable updates for every Scheduler instance."""

    cases: list[dict[str, Any]] = []
    for panel in panels:
        started = _local_now().replace(tzinfo=None)
        _write_targeted_config(
            alas_root,
            config_name,
            seed,
            panels,
            panel,
            enabled=True,
            due_at=started - timedelta(minutes=1),
        )
        config = modules.AzurLaneConfig(config_name)
        config.get_next_task()
        pending = [item.command for item in config.pending_task]
        if panel not in pending:
            raise AssertionError(f"{panel} was absent from due queue {pending!r}")
        config.task = next(item for item in config.pending_task if item.command == panel)
        config.bind(config.task)
        if config.Scheduler_Command != panel:
            raise AssertionError(f"{panel} Scheduler.Command changed identity")

        success_interval = config.Scheduler_SuccessInterval
        failure_interval = config.Scheduler_FailureInterval
        write_results: dict[str, str] = {}
        started_success = datetime.now().replace(microsecond=0)
        config.task_delay(success=True)
        completed_success = datetime.now().replace(microsecond=0)
        persisted = _json_read(_config_path(alas_root, config_name))
        next_run = _parse_time(persisted[panel]["Scheduler"]["NextRun"])
        _assert_interval_result(
            f"{panel}.Scheduler.SuccessInterval",
            next_run,
            started_success,
            completed_success,
            success_interval,
        )
        write_results["success"] = _format_time(next_run)

        config = modules.AzurLaneConfig(config_name)
        config.get_next_task()
        config.task = next(
            item
            for item in config.pending_task + config.waiting_task
            if item.command == panel
        )
        config.bind(config.task)
        started_failure = datetime.now().replace(microsecond=0)
        config.task_delay(success=False)
        completed_failure = datetime.now().replace(microsecond=0)
        persisted = _json_read(_config_path(alas_root, config_name))
        next_run = _parse_time(persisted[panel]["Scheduler"]["NextRun"])
        _assert_interval_result(
            f"{panel}.Scheduler.FailureInterval",
            next_run,
            started_failure,
            completed_failure,
            failure_interval,
        )
        write_results["failure"] = _format_time(next_run)

        config = modules.AzurLaneConfig(config_name)
        config.get_next_task()
        config.task = next(
            item
            for item in config.pending_task + config.waiting_task
            if item.command == panel
        )
        config.bind(config.task)
        before_update = datetime.now().replace(microsecond=0)
        config.task_delay(server_update=True)
        persisted = _json_read(_config_path(alas_root, config_name))
        next_run = _parse_time(persisted[panel]["Scheduler"]["NextRun"])
        if not before_update - timedelta(seconds=2) <= next_run <= before_update + timedelta(days=2):
            raise AssertionError(f"{panel}.Scheduler.ServerUpdate produced {next_run}")
        write_results["server_update"] = _format_time(next_run)
        cases.append(
            {
                "panel": panel,
                "due_queue": pending,
                "writes": write_results,
            }
        )

    # Restart is a pinned ``state`` control in upstream args and is therefore
    # deliberately restored to true by ConfigUpdater.  Main is the ordinary
    # user-toggleable Scheduler.Enable instance that exercises false.
    disabled = "Main"
    if disabled not in panels:
        raise AssertionError("Main Scheduler panel disappeared")
    _write_targeted_config(
        alas_root,
        config_name,
        seed,
        panels,
        disabled,
        enabled=False,
        due_at=_local_now().replace(tzinfo=None) - timedelta(minutes=1),
    )
    config = modules.AzurLaneConfig(config_name)
    config.get_next_task()
    if any(item.command == disabled for item in config.pending_task + config.waiting_task):
        raise AssertionError(f"disabled Scheduler.Enable still queued {disabled}")

    return {
        "scheduler_instances": len(cases),
        "disabled_panel": disabled,
        "disabled_not_queued": True,
        "durable_writes": cases,
    }


class _AvailableChecker:
    def wait_until_available(self) -> None:
        return None

    def is_recovered(self) -> bool:
        return False

    def check_now(self) -> None:
        return None


def _run_initial_skip(
    modules: SimpleNamespace,
    alas_root: Path,
    config_name: str,
    seed: Mapping[str, Any],
    panels: list[str],
) -> Mapping[str, Any]:
    started = _local_now().replace(tzinfo=None)
    _write_targeted_config(
        alas_root,
        config_name,
        seed,
        panels,
        "Restart",
        enabled=True,
        due_at=started - timedelta(minutes=1),
    )
    instance = modules.AzurLaneAutoScript(config_name)
    instance.stop_event = threading.Event()
    instance.checker = _AvailableChecker()
    original_delay = instance.config.task_delay
    calls: list[dict[str, Any]] = []

    def delay(*args: Any, **kwargs: Any) -> Any:
        result = original_delay(*args, **kwargs)
        calls.append({"args": list(args), "kwargs": kwargs})
        instance.stop_event.set()
        return result

    instance.config.task_delay = delay
    try:
        instance.loop()
    finally:
        _close_semantic_session(instance)
    persisted = _json_read(_config_path(alas_root, config_name))
    next_run = _parse_time(persisted["Restart"]["Scheduler"]["NextRun"])
    if calls != [{"args": [], "kwargs": {"server_update": True}}]:
        raise AssertionError(f"initial Restart did not use exact server update: {calls!r}")
    if next_run <= started - timedelta(seconds=2):
        raise AssertionError("initial Restart skip did not move NextRun into the future")
    return {
        "name": "initial_restart_skip",
        "next_run": _format_time(next_run),
        "exact_server_update_call": True,
        "app_restart_executed": False,
    }


def _run_restart_once(
    modules: SimpleNamespace,
    alas_root: Path,
    config_name: str,
    seed: Mapping[str, Any],
    panels: list[str],
    serial: str,
    package: str,
) -> Mapping[str, Any]:
    _write_targeted_config(
        alas_root,
        config_name,
        seed,
        panels,
        "Restart",
        enabled=True,
        due_at=_local_now().replace(tzinfo=None) - timedelta(minutes=1),
    )
    base = modules.AzurLaneAutoScript

    class OneShotRestart(base):
        def run(self, command: str, *args: Any, **kwargs: Any) -> bool:
            self.run_commands.append(command)
            result = super().run(command, *args, **kwargs)
            self.stop_event.set()
            return result

    instance = OneShotRestart(config_name)
    instance.is_first_task = False
    instance.stop_event = threading.Event()
    instance.checker = _AvailableChecker()
    instance.run_commands = []
    before_pid = _pid(serial, package)
    started_at = _local_now()
    wall_started = time.monotonic()
    exit_code = 0
    failure: str | None = None
    try:
        instance.loop()
    except SystemExit as exc:
        exit_code = int(exc.code) if isinstance(exc.code, int) else 1
        failure = f"SystemExit: {exc.code!r}"
    except BaseException as exc:  # The evidence must retain unexpected failures.
        exit_code = 1
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        _close_semantic_session(instance)
    elapsed = round(time.monotonic() - wall_started, 3)
    after_pid = _pid(serial, package)
    persisted = _json_read(_config_path(alas_root, config_name))
    next_run = _parse_time(persisted["Restart"]["Scheduler"]["NextRun"])
    return {
        "started_at": started_at.isoformat(),
        "elapsed_seconds": elapsed,
        "exit_code": exit_code,
        "failure": failure,
        "run_commands": instance.run_commands,
        "before_pid": before_pid,
        "after_pid": after_pid,
        "next_run": _format_time(next_run),
        "remaining_observer_forwards": len(_observer_forwards(serial)),
    }


def _validate_live(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    output: Path,
) -> Mapping[str, Any]:
    live_config = _config_path(alas_root, seed_config)
    if not live_config.is_file():
        raise FileNotFoundError(f"seed config does not exist: {live_config}")
    modules = _load_live_modules(alas_root, driver_revision)
    seed = _json_read(live_config)
    args = _json_read(alas_root / "module" / "config" / "argument" / "args.json")
    panels = _scheduler_panels(args)
    class_count = _scheduler_classes(args, panels)
    restart = seed.get("Restart", {}).get("Scheduler", {})
    serial = seed.get("Alas", {}).get("Emulator", {}).get("Serial")
    package = seed.get("Alas", {}).get("Emulator", {}).get("PackageName")
    if not isinstance(serial, str) or not serial:
        raise AssertionError("seed config does not select an emulator serial")
    if not isinstance(package, str) or not package or package == "auto":
        raise AssertionError("seed config does not select a concrete package")
    if restart.get("Command") != "Restart":
        raise AssertionError("seed config Restart command drifted")
    if not _package_enabled(serial, package):
        raise RuntimeError(f"target package is not enabled: {package}")

    config_name = f"codex_restart_live_{uuid.uuid4().hex}"
    temporary_config = _config_path(alas_root, config_name)
    result: dict[str, Any] = {
        "schema": "alas-headless.restart-live-validation/v1",
        "validated_at": _local_now().isoformat(),
        "serial": serial,
        "package": package,
        "component": f"{package}/{PACKAGE_COMPONENT_SUFFIX}",
        "semantic_mode": True,
        "observer_driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(live_config),
        "source_sha256": {
            "alas.py": _sha256(alas_root / "alas.py"),
            "config.py": _sha256(alas_root / "module" / "config" / "config.py"),
            "login.py": _sha256(alas_root / "module" / "handler" / "login.py"),
            "args.json": _sha256(alas_root / "module" / "config" / "argument" / "args.json"),
        },
        "scheduler": {"equivalence_classes": class_count},
        "cases": [],
    }
    package_disabled = False
    try:
        result["scheduler"].update(
            _exercise_scheduler_instances(
                modules, alas_root, config_name, seed, args, panels
            )
        )
        result["cases"].append(
            _run_initial_skip(modules, alas_root, config_name, seed, panels)
        )

        _write_targeted_config(
            alas_root,
            config_name,
            seed,
            panels,
            "Restart",
            enabled=True,
            due_at=_local_now().replace(tzinfo=None) - timedelta(minutes=1),
        )
        _adb(serial, "shell", "pm", "disable-user", "--user", "0", package)
        package_disabled = True
        failed = _run_restart_once(
            modules, alas_root, config_name, seed, panels, serial, package
        )
        failed["name"] = "disabled_package_restart_failure"
        if failed["exit_code"] == 0:
            raise AssertionError("disabled package Restart unexpectedly succeeded")
        if failed["remaining_observer_forwards"] != 0:
            raise AssertionError("disabled package Restart leaked observer forwards")
        result["cases"].append(failed)

        _adb(serial, "shell", "pm", "enable", package)
        package_disabled = False
        recovered = _run_restart_once(
            modules, alas_root, config_name, seed, panels, serial, package
        )
        recovered["name"] = "restart_recovery_cold_start"
        if recovered["exit_code"] != 0 or recovered["run_commands"] != ["restart"]:
            raise AssertionError(f"Restart recovery did not complete: {recovered!r}")
        if recovered["after_pid"] is None:
            raise AssertionError("Restart recovery did not leave a running game process")
        if recovered["remaining_observer_forwards"] != 0:
            raise AssertionError("Restart recovery leaked observer forwards")
        result["cases"].append(recovered)

        turnover = _run_restart_once(
            modules, alas_root, config_name, seed, panels, serial, package
        )
        turnover["name"] = "restart_running_pid_turnover"
        if turnover["exit_code"] != 0 or turnover["run_commands"] != ["restart"]:
            raise AssertionError(f"running Restart did not complete: {turnover!r}")
        if turnover["before_pid"] is None or turnover["after_pid"] is None:
            raise AssertionError("running Restart did not retain a game process")
        if turnover["before_pid"] == turnover["after_pid"]:
            raise AssertionError("running Restart did not turn over the game PID")
        if turnover["remaining_observer_forwards"] != 0:
            raise AssertionError("running Restart leaked observer forwards")
        result["cases"].append(turnover)

        persisted = _json_read(temporary_config)
        next_run = _parse_time(persisted["Restart"]["Scheduler"]["NextRun"])
        if next_run <= datetime.now() - timedelta(seconds=2):
            raise AssertionError("successful Restart did not durably defer to ServerUpdate")
        top = _top_resumed_component(serial)
        result["final_state"] = {
            "package_enabled": _package_enabled(serial, package),
            "pid": _pid(serial, package),
            "top_resumed_component": top,
            "restart_next_run": _format_time(next_run),
            "remaining_observer_forwards": len(_observer_forwards(serial)),
        }
        if result["final_state"]["remaining_observer_forwards"] != 0:
            raise AssertionError("final Restart state leaked observer forwards")
        if result["final_state"]["pid"] is None:
            raise AssertionError("final Restart state has no game process")
        result["passed"] = True
        return result
    finally:
        if package_disabled:
            _adb(serial, "shell", "pm", "enable", package, check=False)
        temporary_config.unlink(missing_ok=True)
        result["temporary_config_removed"] = not temporary_config.exists()
        if result.get("passed") is not True:
            result["passed"] = False
        output.parent.mkdir(parents=True, exist_ok=True)
        _json_write(output, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "integration" / "alas" / "restart-live-validation-receipt.json",
    )
    args = parser.parse_args()
    result = _validate_live(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
        args.output.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
