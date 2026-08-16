"""Deterministic replay of pinned ALAS Benchmark configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_benchmark_config_contract import (
    BENCHMARK_DEVICE_TYPES,
    BENCHMARK_TEST_SCENES,
    validate_alas_benchmark_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.benchmark-config-replay/v1"
INVALID_VALUES = (None, True, 1, "", "unknown", [])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    group = document.get("Benchmark", {}).get("Benchmark")
    expected = {
        "DeviceType": ("emulator", BENCHMARK_DEVICE_TYPES),
        "TestScene": ("screenshot_click", BENCHMARK_TEST_SCENES),
    }
    for field, (default, options) in expected.items():
        declaration = group.get(field) if isinstance(group, dict) else None
        if not isinstance(declaration, dict) or declaration.get("type") != "select":
            raise AssertionError(f"Benchmark.{field} declaration drifted")
        if declaration.get("value") != default or tuple(declaration.get("option", ())) != options:
            raise AssertionError(f"Benchmark.{field} values drifted")


def _source_flags(path: Path) -> tuple[bool, bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    run = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Benchmark":
            run = next((child for child in node.body if isinstance(child, ast.FunctionDef) and child.name == "run"), None)
    if run is None:
        raise AssertionError("Benchmark.run is missing")
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_benchmark_config"
        for node in ast.walk(run)
    )
    semantic_path_present = any(
        isinstance(node, ast.Attribute) and node.attr == "run_semantic"
        for node in ast.walk(run)
    )
    if guard_present:
        executable = [s for s in run.body if not isinstance(s, (ast.Import, ast.ImportFrom))]
        first = executable[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "validate_alas_benchmark_config"
        ):
            raise AssertionError("Benchmark config guard is not first in run")
    return guard_present, semantic_path_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.daemon.benchmark")
        return module, module.Benchmark
    finally:
        sys.path.remove(root)


def _device():
    return SimpleNamespace(
        sdk_ver=30,
        nemu_ipc_available=lambda: False,
        ldopengl_available=lambda: False,
        is_bluestacks_air=False,
    )


def _method_case(benchmark_type: type[Any], device_type: str, test_scene: str):
    host = object.__new__(benchmark_type)
    host.config = SimpleNamespace(
        Benchmark_DeviceType=device_type,
        Benchmark_TestScene=test_scene,
    )
    host.device = _device()
    screenshot, click = benchmark_type.get_test_methods(host)
    return {"screenshot": list(screenshot), "click": list(click)}


def _verify_methods(benchmark_type: type[Any]) -> dict[str, Any]:
    cases = {}
    for device_type, test_scene in itertools.product(BENCHMARK_DEVICE_TYPES, BENCHMARK_TEST_SCENES):
        key = f"{device_type}:{test_scene}"
        case = _method_case(benchmark_type, device_type, test_scene)
        base_screenshot = ["ADB", "ADB_nc", "uiautomator2", "DroidCast", "DroidCast_raw"]
        base_click = ["ADB", "uiautomator2", "minitouch", "MaaTouch"]
        if device_type == "plone_cloud_with_adb":
            base_screenshot.remove("ADB_nc")
        if device_type == "android_phone_vmos":
            base_screenshot = ["ADB", "aScreenCap", "DroidCast", "DroidCast_raw"]
            base_click = ["ADB", "Hermit", "MaaTouch"]
        expected = {
            "screenshot": base_screenshot if "screenshot" in test_scene else [],
            "click": base_click if "click" in test_scene else [],
        }
        if case != expected:
            raise AssertionError("original Benchmark method selection drifted")
        cases[key] = case
    return cases


def _semantic_cases(
    benchmark_type: type[Any], *, guard_present: bool, semantic_path_present: bool
):
    if not semantic_path_present:
        return {}
    result = {}
    for device_type, scene in itertools.product(
        BENCHMARK_DEVICE_TYPES, BENCHMARK_TEST_SCENES
    ):
        events = []
        host = object.__new__(benchmark_type)
        host.config = SimpleNamespace(
            Benchmark_DeviceType=device_type,
            Benchmark_TestScene=scene,
        )
        host.device = SimpleNamespace(semantic_adapter=object())
        host.semantic_ensure_main = MethodType(lambda self: events.append("ensure_main"), host)
        host.benchmark_test = MethodType(lambda self, method: events.append(method.__name__) or 1.0, host)
        host.semantic_observe = MethodType(lambda self: None, host)
        host.semantic_reversible_input = MethodType(lambda self: None, host)
        host.show = MethodType(lambda self, **kwargs: events.append(kwargs["test"]), host)
        if guard_present:
            observe, control = benchmark_type.run(host)
        else:
            observe, control = benchmark_type.run_semantic(host)
        expected = ["ensure_main"]
        if "screenshot" in scene:
            expected.append("<lambda>")
        if "click" in scene:
            expected.append("<lambda>")
        if "screenshot" in scene:
            expected.append("Semantic observation")
        if "click" in scene:
            expected.append("Semantic UI round trip")
        expected.append("ensure_main")
        if events != expected:
            raise AssertionError("semantic Benchmark scene decision drifted")
        result[f"{device_type}:{scene}"] = {
            "observe": len(observe),
            "control": len(control),
            "events": events,
        }
    return result


def _verify_contract() -> int:
    for device_type, test_scene in itertools.product(BENCHMARK_DEVICE_TYPES, BENCHMARK_TEST_SCENES):
        validate_alas_benchmark_config(device_type=device_type, test_scene=test_scene)
    invalid_count = 0
    for field in ("device_type", "test_scene"):
        for value in INVALID_VALUES:
            case = {"device_type": "emulator", "test_scene": "screenshot_click"}
            case[field] = value
            try:
                validate_alas_benchmark_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Benchmark.{field} was admitted")
    return invalid_count


def _verify_invalid_entry(benchmark_type: type[Any], guard_present: bool):
    if not guard_present:
        return {}
    result = {}
    for field in ("Benchmark_DeviceType", "Benchmark_TestScene"):
        host = object.__new__(benchmark_type)
        host.config = SimpleNamespace(Benchmark_DeviceType="emulator", Benchmark_TestScene="screenshot_click")
        setattr(host.config, field, None)
        host.device = SimpleNamespace(semantic_adapter=object())
        try:
            benchmark_type.run(host)
        except SemanticGateClosed:
            result[field] = []
        else:
            raise AssertionError(f"patched Benchmark admitted invalid {field}")
    return result


def verify_benchmark_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    source = alas_root / "module/daemon/benchmark.py"
    guard_present, semantic_path_present = _source_flags(source)
    module, benchmark_type = _load_original(alas_root)
    methods = _verify_methods(benchmark_type)
    semantic = _semantic_cases(
        benchmark_type,
        guard_present=guard_present,
        semantic_path_present=semantic_path_present,
    )
    invalid_count = _verify_contract()
    invalid_events = _verify_invalid_entry(benchmark_type, guard_present)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "accepted_case_count": len(methods),
        "invalid_case_count": invalid_count,
        "patched_guard_present": guard_present,
        "semantic_path_present": semantic_path_present,
        "original_method_decisions": methods,
        "semantic_scene_decisions": semantic,
        "invalid_entry_events": invalid_events,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_benchmark_method_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "benchmark": _sha256(source),
        },
    }
