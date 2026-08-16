#!/usr/bin/env python3
"""Run every declared ALAS Benchmark setting on the live semantic client.

The semantic implementation deliberately treats the legacy DeviceType selector
as configuration provenance: all five admitted values share the same observer
transport.  TestScene remains behavior-bearing and selects observation, the
reviewed settings round trip, or both.  Each original Benchmark invocation
uses its unmodified 15-sample timing loop.
"""

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
from types import SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEVICE_TYPES = (
    "emulator",
    "plone_cloud_with_adb",
    "phone_cloud_without_adb",
    "android_phone",
    "android_phone_vmos",
)
TEST_SCENES = ("screenshot_click", "screenshot", "click")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _adb(serial: str, *arguments: str) -> str:
    completed = subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    return completed.stdout.strip()


def _load_modules(alas_root: Path, driver_revision: str) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.daemon.benchmark import Benchmark

    return SimpleNamespace(AzurLaneAutoScript=AzurLaneAutoScript, Benchmark=Benchmark)


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _main_visible(serial: str, driver_revision: str) -> bool:
    from alas_headless import AlasSemanticSession

    session = AlasSemanticSession(serial=serial, driver_revision=driver_revision)
    try:
        return session.open().oracle.main_page_visible()
    finally:
        session.close()


def _case(
    *,
    modules: SimpleNamespace,
    alas_root: Path,
    seed: Mapping[str, Any],
    device_type: str,
    test_scene: str,
) -> dict[str, Any]:
    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Benchmark"]["Benchmark"].update(
        {"DeviceType": device_type, "TestScene": test_scene}
    )
    config_name = "codex_benchmark_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    instance: object | None = None
    result: dict[str, Any] = {
        "device_type": device_type,
        "test_scene": test_scene,
        "temporary_config": config_path.name,
    }
    try:
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Benchmark")
        task = modules.Benchmark(instance.config, device=instance.device, task="Benchmark")
        started = time.monotonic()
        observe, control = task.run()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["observe"] = observe
        result["control"] = control
        expected_observe = 1 if "screenshot" in test_scene else 0
        expected_control = 1 if "click" in test_scene else 0
        if len(observe) != expected_observe or len(control) != expected_control:
            raise AssertionError("Benchmark scene did not select the expected methods")
        for _, duration in (*observe, *control):
            if not isinstance(duration, float) or duration < 0:
                raise AssertionError("Benchmark did not return a timing measurement")
        result["passed"] = True
    except BaseException as exc:
        result["passed"] = False
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
    return result


def validate(
    *, alas_root: Path, seed_config: str, driver_revision: str
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not isinstance(serial, str) or not serial:
        raise AssertionError("seed config has no emulator serial")
    if not isinstance(package, str) or not package:
        raise AssertionError("seed config has no package")
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    modules = _load_modules(alas_root, driver_revision)
    cases = []
    for device_type in DEVICE_TYPES:
        for test_scene in TEST_SCENES:
            cases.append(
                _case(
                    modules=modules,
                    alas_root=alas_root,
                    seed=seed,
                    device_type=device_type,
                    test_scene=test_scene,
                )
            )
            if not cases[-1]["passed"]:
                raise RuntimeError("live Benchmark case failed: " + str(cases[-1]))
            if not _main_visible(serial, driver_revision):
                raise AssertionError("Benchmark did not return to the main page")

    expected = {(device_type, scene) for device_type in DEVICE_TYPES for scene in TEST_SCENES}
    observed = {(case["device_type"], case["test_scene"]) for case in cases}
    if observed != expected:
        raise AssertionError("Benchmark case matrix is incomplete")
    return {
        "schema": "alas-headless.benchmark-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "source_sha256": {
            "benchmark": _sha256(alas_root / "module" / "daemon" / "benchmark.py"),
            "args": _sha256(alas_root / "module" / "config" / "argument" / "args.json"),
        },
        "configured_device_types": list(DEVICE_TYPES),
        "test_scenes": list(TEST_SCENES),
        "case_count": len(cases),
        "cases": cases,
        "postcondition": {"main_page_visible_after_every_case": True},
        "passed": True,
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
        print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")


if __name__ == "__main__":
    raise SystemExit(main())
