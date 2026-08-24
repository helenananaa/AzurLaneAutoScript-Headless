#!/usr/bin/env python3
"""Collect one repeatable non-combat ALAS workload on the live semantic client.

Profiles use original ALAS task code where a task is involved.  The collector
only supplies a shared measurement envelope and explicit zero-resource
postconditions; it never creates a replacement scheduler or navigation flow.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless import AlasSemanticSession, RuntimeTraceRecorder  # noqa: E402
from alas_headless.adb_device import resolve_adb_serial  # noqa: E402
from alas_headless.workload_capture import (  # noqa: E402
    build_baseline_summary,
    build_resource_receipt,
    capture_live_workload,
    write_json,
)


PROFILE_DEFINITIONS: Mapping[str, Mapping[str, Any]] = {
    "semantic-io": {
        "class": "semantic-observation-control",
        "description": "Original ALAS Benchmark observation and reversible control loops.",
        "account_state_mutation": "reversible-settings-round-trip",
        "in_game_resource_mutation_expected": False,
        "process_restart_expected": False,
        "recommended_frequency": "every-runtime-candidate",
    },
    "reward-readonly": {
        "class": "original-alas-task-readonly",
        "description": "Original Reward daily and weekly branches with every claim disabled.",
        "account_state_mutation": "none",
        "in_game_resource_mutation_expected": False,
        "process_restart_expected": False,
        "recommended_frequency": "every-runtime-candidate",
    },
    "restart-warm": {
        "class": "lifecycle-recovery",
        "description": "One original ALAS Restart task with running-PID turnover and recovery.",
        "account_state_mutation": "none",
        "in_game_resource_mutation_expected": False,
        "process_restart_expected": True,
        "recommended_frequency": "image-or-runtime-milestone",
    },
    "idle-soak": {
        "class": "passive-stability",
        "description": "Passive main-page residence with typed start/end postconditions.",
        "account_state_mutation": "none",
        "in_game_resource_mutation_expected": False,
        "process_restart_expected": False,
        "recommended_frequency": "release-candidate",
    },
}


def _load_script(name: str, filename: str) -> ModuleType:
    path = ROOT / "scripts" / "python" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("live runner could not be loaded: " + filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document is not an object: " + str(path))
    return value


def _seed_identity(alas_root: Path, seed_config: str) -> tuple[str, str]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    if not seed_path.is_file():
        raise FileNotFoundError("seed config does not exist: " + str(seed_path))
    seed = _read_json(seed_path)
    emulator = seed.get("Alas", {}).get("Emulator", {})
    serial = emulator.get("Serial")
    package = emulator.get("PackageName")
    if not isinstance(serial, str) or not serial:
        raise ValueError("seed config has no concrete emulator serial")
    if not isinstance(package, str) or not package or package == "auto":
        raise ValueError("seed config has no concrete game package")
    return serial, package


def prepare_unobstructed_main(args: argparse.Namespace) -> Mapping[str, Any]:
    """Use original ALAS UI handlers before, and outside, timed measurement."""

    original_cwd = Path.cwd()
    benchmark = _load_script(
        "alas_workload_preflight_benchmark",
        "run_alas_benchmark_live_validation.py",
    )
    modules = benchmark._load_modules(args.alas_root, args.driver_revision)
    instance = modules.AzurLaneAutoScript(args.seed_config)
    bulletin_closed = False
    try:
        instance.config.bind("Benchmark")
        task = modules.Benchmark(
            instance.config,
            device=instance.device,
            task="Benchmark",
        )
        task.device.screenshot()
        oracle = task.device.semantic_adapter.open().oracle
        if oracle.enabled("overlay/bulletin/close"):
            if not task.ui_additional(get_ship=False):
                raise AssertionError(
                    "original ALAS did not close the proven bulletin blocker"
                )
            bulletin_closed = True
            time.sleep(0.5)
        task.semantic_ensure_main()
    finally:
        benchmark._close(instance)
        os.chdir(original_cwd)

    verify = AlasSemanticSession(
        serial=args.serial,
        driver_revision=args.driver_revision,
    )
    try:
        oracle = verify.open().oracle
        if not oracle.main_page_visible() or not oracle.enabled("main/settings"):
            raise AssertionError("ALAS preflight did not reach unobstructed main")
    finally:
        verify.close()
    return {
        "performed": True,
        "measurement_included": False,
        "owner": "original ALAS Benchmark.semantic_ensure_main and UI.ui_additional",
        "bulletin_closed": bulletin_closed,
        "postcondition": "unobstructed-typed-main",
    }


def _semantic_io_runner(args: argparse.Namespace) -> Callable[[RuntimeTraceRecorder], Mapping[str, Any]]:
    def run(trace: RuntimeTraceRecorder) -> Mapping[str, Any]:
        benchmark = _load_script(
            "alas_workload_benchmark", "run_alas_benchmark_live_validation.py"
        )
        seed_path = args.alas_root / "config" / (args.seed_config + ".json")
        seed = benchmark._read_json(seed_path)
        modules = benchmark._load_modules(args.alas_root, args.driver_revision)
        cases = []
        for scene in benchmark.TEST_SCENES:
            trace.emit(
                "workload.case",
                fields={"phase": "start", "case": scene, "profile": args.profile},
            )
            case = benchmark._case(
                modules=modules,
                alas_root=args.alas_root,
                seed=seed,
                device_type="emulator",
                test_scene=scene,
            )
            cases.append(case)
            trace.emit(
                "workload.case",
                outcome="ok" if case.get("passed") else "error",
                fields={"phase": "finish", "case": scene, "profile": args.profile},
            )
            if not case.get("passed"):
                raise RuntimeError("semantic Benchmark case failed: " + str(case))
            postcondition_session = AlasSemanticSession(
                serial=args.serial,
                driver_revision=args.driver_revision,
                trace=trace,
            )
            try:
                if not postcondition_session.open().oracle.main_page_visible():
                    raise AssertionError("semantic Benchmark did not return to main")
            finally:
                postcondition_session.close()
        return {
            "schema": "alas-headless.semantic-io-workload/v1",
            "passed": True,
            "device_type": "emulator",
            "test_scenes": list(benchmark.TEST_SCENES),
            "original_samples_per_scene": 15,
            "cases": cases,
            "postcondition": {"main_page_visible_after_every_case": True},
        }

    return run


def _reward_readonly_runner(args: argparse.Namespace) -> Callable[[RuntimeTraceRecorder], Mapping[str, Any]]:
    def run(trace: RuntimeTraceRecorder) -> Mapping[str, Any]:
        reward = _load_script(
            "alas_workload_reward", "run_alas_reward_mission_live_validation.py"
        )
        cases = []
        for mode in ("daily", "weekly"):
            trace.emit(
                "workload.case",
                fields={"phase": "start", "case": mode, "profile": args.profile},
            )
            case = reward.validate(
                alas_root=args.alas_root,
                seed_config=args.seed_config,
                driver_revision=args.driver_revision,
                mode=mode,
                mission_claim_enabled=False,
            )
            cases.append(case)
            trace.emit(
                "workload.case",
                outcome="ok" if case.get("passed") else "error",
                fields={"phase": "finish", "case": mode, "profile": args.profile},
            )
            if not case.get("passed"):
                raise RuntimeError("read-only Reward case failed: " + str(case))
            if case.get("dispatches"):
                raise AssertionError("read-only Reward emitted a mutation dispatch")
            if not case.get("main_page_visible_after_cleanup"):
                raise AssertionError("read-only Reward did not return to main")
        return {
            "schema": "alas-headless.reward-readonly-workload/v1",
            "passed": True,
            "cases": cases,
            "mutation_dispatches": 0,
            "postcondition": {"main_page_visible_after_every_case": True},
        }

    return run


def _restart_warm_runner(args: argparse.Namespace) -> Callable[[RuntimeTraceRecorder], Mapping[str, Any]]:
    def run(trace: RuntimeTraceRecorder) -> Mapping[str, Any]:
        restart = _load_script(
            "alas_workload_restart", "run_alas_restart_live_validation.py"
        )
        modules = restart._load_live_modules(args.alas_root, args.driver_revision)
        seed_path = args.alas_root / "config" / (args.seed_config + ".json")
        seed = restart._json_read(seed_path)
        config_args = restart._json_read(
            args.alas_root / "module" / "config" / "argument" / "args.json"
        )
        panels = restart._scheduler_panels(config_args)
        config_name = "codex_restart_workload_" + uuid.uuid4().hex
        config_path = restart._config_path(args.alas_root, config_name)
        try:
            if restart._pid(args.serial, args.package) is None:
                raise RuntimeError("restart-warm requires a running game process")
            starting_forwards = tuple(sorted(restart._observer_forwards(args.serial)))
            trace.emit(
                "workload.case",
                fields={"phase": "start", "case": "warm-pid-turnover"},
            )
            case = restart._run_restart_once(
                modules,
                args.alas_root,
                config_name,
                seed,
                panels,
                args.serial,
                args.package,
            )
            trace.emit(
                "workload.case",
                outcome="ok" if case.get("exit_code") == 0 else "error",
                fields={"phase": "finish", "case": "warm-pid-turnover"},
            )
            if case.get("exit_code") != 0 or case.get("run_commands") != ["restart"]:
                raise AssertionError("original ALAS Restart did not complete")
            if not isinstance(case.get("before_pid"), int) or not isinstance(
                case.get("after_pid"), int
            ):
                raise AssertionError("Restart did not retain both PID observations")
            if case["before_pid"] == case["after_pid"]:
                raise AssertionError("Restart did not turn over the game PID")
            ending_forwards = tuple(sorted(restart._observer_forwards(args.serial)))
            owned_forward_delta = tuple(
                item for item in ending_forwards if item not in starting_forwards
            )
            case["starting_observer_forwards"] = list(starting_forwards)
            case["ending_observer_forwards"] = list(ending_forwards)
            case["owned_observer_forward_delta"] = list(owned_forward_delta)
            if owned_forward_delta:
                raise AssertionError("Restart left a new observer forward behind")
            return {
                "schema": "alas-headless.restart-warm-workload/v1",
                "passed": True,
                "case": case,
                "postcondition": {
                    "game_process_running": True,
                    "pid_turned_over": True,
                    "owned_observer_forward_delta": 0,
                    "preexisting_observer_forwards": len(starting_forwards),
                },
            }
        finally:
            config_path.unlink(missing_ok=True)

    return run


def _idle_soak_runner(args: argparse.Namespace) -> Callable[[RuntimeTraceRecorder], Mapping[str, Any]]:
    def run(trace: RuntimeTraceRecorder) -> Mapping[str, Any]:
        os.environ["ALAS_SEMANTIC_MODE"] = "1"
        os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = args.driver_revision
        os.environ["ALAS_SEMANTIC_ADB"] = args.adb
        session = AlasSemanticSession.from_environment(serial=args.serial)
        try:
            adapter = session.open()
            initial = session.refresh_frame(include_ui=True)
            if not adapter.oracle.main_page_visible() or not adapter.oracle.enabled(
                "main/settings"
            ):
                raise AssertionError(
                    "idle-soak must start on the unobstructed typed main page"
                )
            trace.emit(
                "workload.case",
                fields={
                    "phase": "idle-start",
                    "generation": initial.generation,
                    "pid": initial.pid,
                    "duration_seconds": args.idle_duration_seconds,
                },
            )
            threading.Event().wait(args.idle_duration_seconds)
            final = session.refresh_frame(include_ui=True)
            if not adapter.oracle.main_page_visible() or not adapter.oracle.enabled(
                "main/settings"
            ):
                raise AssertionError(
                    "idle-soak did not finish on the unobstructed typed main page"
                )
            if final.pid != initial.pid:
                raise AssertionError("game PID changed during idle-soak")
            if final.generation < initial.generation:
                raise AssertionError("observer generation moved backwards during idle-soak")
            trace.emit(
                "workload.case",
                fields={
                    "phase": "idle-finish",
                    "generation": final.generation,
                    "pid": final.pid,
                },
            )
            return {
                "schema": "alas-headless.idle-soak-workload/v1",
                "passed": True,
                "duration_seconds": args.idle_duration_seconds,
                "initial": {
                    "pid": initial.pid,
                    "generation": initial.generation,
                    "scene_handle": initial.scene_handle,
                },
                "final": {
                    "pid": final.pid,
                    "generation": final.generation,
                    "scene_handle": final.scene_handle,
                },
                "postcondition": {
                    "main_page_visible": True,
                    "same_game_pid": True,
                },
            }
        finally:
            session.close()

    return run


RUNNER_FACTORIES: Mapping[
    str, Callable[[argparse.Namespace], Callable[[RuntimeTraceRecorder], Mapping[str, Any]]]
] = {
    "semantic-io": _semantic_io_runner,
    "reward-readonly": _reward_readonly_runner,
    "restart-warm": _restart_warm_runner,
    "idle-soak": _idle_soak_runner,
}


def workload_metadata(args: argparse.Namespace) -> Mapping[str, Any]:
    definition = PROFILE_DEFINITIONS[args.profile]
    metadata: dict[str, Any] = {
        "id": args.profile,
        "version": 1,
        "class": definition["class"],
        "description": definition["description"],
        "recommended_frequency": definition["recommended_frequency"],
    }
    if args.profile == "idle-soak":
        metadata["duration_seconds"] = args.idle_duration_seconds
    if args.profile == "semantic-io":
        metadata.update(
            {
                "device_type": "emulator",
                "test_scenes": ["screenshot_click", "screenshot", "click"],
                "original_samples_per_scene": 15,
            }
        )
    if getattr(args, "preflight", None) is not None:
        metadata["preflight"] = args.preflight
    return metadata


def safety_metadata(args: argparse.Namespace) -> Mapping[str, Any]:
    definition = PROFILE_DEFINITIONS[args.profile]
    return {
        "typed_semantic_only": True,
        "screenshots_allowed": False,
        "raw_input_allowed": False,
        "observer_sidecar_allowed": False,
        "account_state_mutation": definition["account_state_mutation"],
        "in_game_resource_mutation_expected": definition[
            "in_game_resource_mutation_expected"
        ],
        "process_restart_expected": definition["process_restart_expected"],
        "transient_process_unavailability_expected": args.profile == "restart-warm",
        "premium_currency_budget": 0,
        "purchase_budget": 0,
    }


def resource_receipt_for(
    args: argparse.Namespace, result: Mapping[str, Any]
) -> Mapping[str, Any]:
    if args.profile == "reward-readonly":
        dispatches = sum(
            len(case.get("dispatches", ()))
            for case in (result.get("runner_result") or {}).get("cases", ())
        )
        return build_resource_receipt(
            result,
            evidence_basis="original Reward dispatch receipts with every claim disabled",
            observed_mutation_dispatches=dispatches,
            notes=(
                "Both original Reward branches returned to main.",
                "No resource counter value is manufactured when it was not observed.",
            ),
        )
    basis = {
        "semantic-io": "original Benchmark observation and reversible settings action surface",
        "restart-warm": "original Restart lifecycle path has no in-game resource operation",
        "idle-soak": "passive typed observation with no input operation",
    }[args.profile]
    return build_resource_receipt(
        result,
        evidence_basis=basis,
        observed_mutation_dispatches=None,
        notes=(
            "The profile contains no in-game resource mutation capability.",
            "Resource counters are reported as unobserved rather than synthetic zeroes.",
        ),
    )


def collect(args: argparse.Namespace) -> Mapping[str, Any]:
    args.preflight = (
        prepare_unobstructed_main(args)
        if args.profile in ("semantic-io", "idle-soak")
        else None
    )
    result = capture_live_workload(
        root=ROOT,
        output_directory=args.output_directory,
        serial=args.serial,
        adb=args.adb,
        package=args.package,
        driver_revision=args.driver_revision,
        sample_interval_seconds=args.sample_interval_seconds,
        workload=workload_metadata(args),
        safety=safety_metadata(args),
        runner=RUNNER_FACTORIES[args.profile](args),
    )
    output = args.output_directory.resolve()
    receipt = resource_receipt_for(args, result)
    receipt_path = output / "resource-receipt.json"
    write_json(receipt_path, receipt)
    baseline = build_baseline_summary(result, receipt_path)
    write_json(output / "baseline-summary.json", baseline)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILE_DEFINITIONS), required=True)
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--sample-interval-seconds", type=float, default=1.0)
    parser.add_argument("--idle-duration-seconds", type=float, default=1800.0)
    args = parser.parse_args()
    args.alas_root = args.alas_root.resolve()
    if not (args.alas_root / "alas.py").is_file():
        parser.error("ALAS root is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", args.driver_revision) is None:
        parser.error("driver revision must be a 40-character lowercase SHA-1")
    if not 0.5 <= args.sample_interval_seconds <= 10.0:
        parser.error("sample interval must be in [0.5, 10]")
    if not 30.0 <= args.idle_duration_seconds <= 7200.0:
        parser.error("idle duration must be in [30, 7200] seconds")
    try:
        seed_serial, args.package = _seed_identity(args.alas_root, args.seed_config)
        args.serial = resolve_adb_serial(args.adb, args.serial)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    if seed_serial != args.serial:
        parser.error(
            "seed config serial does not match the explicitly selected online device"
        )
    return args


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    result = collect(args)
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "profile": args.profile,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "output_directory": str(args.output_directory.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
