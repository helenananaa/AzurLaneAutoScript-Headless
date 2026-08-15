"""Deterministic replay for ALAS screenshot error-capture configuration."""

from __future__ import annotations

import ast
import hashlib
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from .alas_screenshot_error_config_contract import (
    validate_alas_error_screenshot_length,
    validate_alas_screenshot_capture_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.screenshot-error-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Screenshot"
    )
    return next(
        node for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _assignment_values(path: Path) -> dict[str, object]:
    expected = {
        "Emulator_ScreenshotDedithering": False,
        "Error_SaveError": True,
        "Error_ScreenshotLength": 1,
    }
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in expected:
                value = ast.literal_eval(node.value)
                if type(value) is not type(expected[target.id]) or value != expected[target.id]:
                    raise AssertionError(f"{target.id} generated default drifted")
                values[target.id] = value
    if values != expected:
        raise AssertionError("screenshot error configuration surface drifted")
    return values


def _verify_argument_schema(path: Path, defaults: dict[str, object]) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError("ALAS argument schema is unavailable")
    emulator = document.get("Emulator")
    error = document.get("Error")
    if not isinstance(emulator, dict) or not isinstance(error, dict):
        raise AssertionError("screenshot error configuration groups are unavailable")
    if emulator.get("ScreenshotDedithering") is not defaults["Emulator_ScreenshotDedithering"]:
        raise AssertionError("Emulator.ScreenshotDedithering default drifted")
    if error.get("SaveError") is not defaults["Error_SaveError"]:
        raise AssertionError("Error.SaveError default drifted")
    if error.get("ScreenshotLength") != defaults["Error_ScreenshotLength"]:
        raise AssertionError("Error.ScreenshotLength default drifted")


def _compile(method: ast.FunctionDef, globals_: dict[str, Any]):
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_)
    exec(compile(module, "<alas-screenshot-error-replay>", "exec"), namespace)
    return namespace[method.name]


def _capture_kwargs(
    *, dedithering: object = False, save_error: object = True, length: object = 1
) -> dict[str, object]:
    return {
        "screenshot_dedithering": dedithering,
        "save_error": save_error,
        "screenshot_length": length,
    }


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for value in (False, True):
        validate_alas_screenshot_capture_config(**_capture_kwargs(dedithering=value))
        accepted += 1
    for value in (False, True):
        validate_alas_screenshot_capture_config(**_capture_kwargs(save_error=value))
        accepted += 1
    expected_lengths = (
        (1, 1),
        ("1", 1),
        (0, 1),
        (-50, 1),
        (300, 300),
        (301, 300),
        (1.8, 1),
        (True, 1),
    )
    for value, expected in expected_lengths:
        if validate_alas_error_screenshot_length(screenshot_length=value) != expected:
            raise AssertionError("Error.ScreenshotLength coercion drifted")
        accepted += 1
    for field, values in {
        "screenshot_dedithering": (0, "true", None),
        "save_error": (0, "true", None),
    }.items():
        for value in values:
            kwargs = _capture_kwargs()
            kwargs[field] = value
            try:
                validate_alas_screenshot_capture_config(**kwargs)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid screenshot {field} was admitted")
    for value in ("", "invalid", None, [], {}):
        try:
            validate_alas_error_screenshot_length(screenshot_length=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Error.ScreenshotLength was admitted")
    return accepted, invalid


def _run_case(method, **values: object) -> dict[str, object]:
    events: list[str] = []

    class Timer:
        def wait(self) -> None:
            events.append("timer.wait")

        def reset(self) -> None:
            events.append("timer.reset")

    class Session:
        def refresh_frame(self) -> str:
            events.append("frame.refresh")
            return "frame-1"

        def pixel_guard(self, frame: str) -> str:
            events.append("frame.pixel_guard")
            return f"guarded-{frame}"

    config = SimpleNamespace(
        Emulator_ScreenshotDedithering=values.get("dedithering", False),
        Error_SaveError=values.get("save_error", True),
        Error_ScreenshotLength=values.get("length", 1),
    )
    host = SimpleNamespace(
        _screenshot_interval=Timer(),
        config=config,
        semantic_adapter=Session(),
    )
    try:
        result = method(host)
    except SemanticGateClosed:
        return {"rejected": True, "result": None, "events": events}
    return {"rejected": False, "result": result, "events": events}


def _verify_screenshot(method) -> dict[str, object]:
    valid = _run_case(method, dedithering=True, save_error=False, length="301")
    if valid != {
        "rejected": False,
        "result": "guarded-frame-1",
        "events": [
            "timer.wait",
            "timer.reset",
            "frame.refresh",
            "frame.pixel_guard",
        ],
    }:
        raise AssertionError("semantic screenshot capture branch drifted")
    invalid = {
        field: _run_case(method, **{field: value})
        for field, value in {
            "dedithering": "true",
            "save_error": "false",
            "length": "invalid",
        }.items()
    }
    if any(
        not case["rejected"]
        or case["events"] != ["timer.wait", "timer.reset"]
        for case in invalid.values()
    ):
        raise AssertionError("invalid capture configuration reached a frame request")
    return {"valid": valid, "invalid_entries": invalid}


def _deque_case(method, value: object) -> dict[str, object]:
    host = SimpleNamespace(config=SimpleNamespace(Error_ScreenshotLength=value))
    try:
        result = method(host)
    except SemanticGateClosed:
        return {"rejected": True, "maxlen": None}
    return {"rejected": False, "maxlen": result.maxlen}


def _verify_deque(method) -> dict[str, object]:
    cases = {repr(value): _deque_case(method, value) for value in (0, "1", 301)}
    if [case["maxlen"] for case in cases.values()] != [1, 1, 300]:
        raise AssertionError("screenshot deque bound drifted")
    invalid = {
        repr(value): _deque_case(method, value)
        for value in ("invalid", None)
    }
    if any(not case["rejected"] for case in invalid.values()):
        raise AssertionError("invalid screenshot deque length was admitted")
    return {"cases": cases, "invalid_entries": invalid}


def verify_screenshot_error_config(alas_root: Path) -> dict[str, object]:
    root = alas_root.resolve()
    screenshot_path = root / "module" / "device" / "screenshot.py"
    config_path = root / "module" / "config" / "config_generated.py"
    argument_path = root / "module" / "config" / "argument" / "argument.yaml"
    if not all(path.is_file() for path in (screenshot_path, config_path, argument_path)):
        raise FileNotFoundError("ALAS screenshot error source is incomplete")
    defaults = _assignment_values(config_path)
    _verify_argument_schema(argument_path, defaults)
    screenshot = _method(screenshot_path, "screenshot")
    screenshot_deque = _method(screenshot_path, "screenshot_deque")
    capture_calls = {
        node.func.id for node in ast.walk(screenshot)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    deque_calls = {
        node.func.id for node in ast.walk(screenshot_deque)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_screenshot_capture_config" not in capture_calls:
        raise AssertionError("screenshot capture guard is absent")
    if "validate_alas_error_screenshot_length" not in deque_calls:
        raise AssertionError("screenshot deque guard is absent")
    capture_assignment = next(
        node for node in screenshot.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "capture" for target in node.targets)
    )
    semantic_assignment = next(
        node for node in screenshot.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "semantic_session" for target in node.targets)
    )
    if screenshot.body.index(capture_assignment) >= screenshot.body.index(semantic_assignment):
        raise AssertionError("screenshot capture guard runs after the frame request gate")
    accepted, invalid = _verify_contract()
    screenshot_result = _verify_screenshot(
        _compile(
            screenshot,
            {"validate_alas_screenshot_capture_config": validate_alas_screenshot_capture_config},
        )
    )
    deque_result = _verify_deque(
        _compile(
            screenshot_deque,
            {
                "cached_property": lambda method: method,
                "deque": deque,
                "validate_alas_error_screenshot_length": validate_alas_error_screenshot_length,
            },
        )
    )
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_defaults": defaults,
        "runtime_consumers": {
            "Emulator.ScreenshotDedithering": "Screenshot.screenshot",
            "Error.SaveError": "Screenshot.screenshot",
            "Error.ScreenshotLength": "Screenshot.screenshot -> Screenshot.screenshot_deque",
        },
        "original_decisions": {
            "screenshot": screenshot_result,
            "screenshot_deque": deque_result,
        },
        "mutation_budget": 0,
        "real_screenshot_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "screenshot": _sha256(screenshot_path),
            "config_generated": _sha256(config_path),
            "argument_schema": _sha256(argument_path),
        },
    }
