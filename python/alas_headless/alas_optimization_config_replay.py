"""Deterministic replay of pinned ALAS global optimization decisions."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import MethodType, ModuleType, SimpleNamespace
from typing import Any, Callable

from .alas_optimization_config_contract import (
    WHEN_TASK_QUEUE_EMPTY,
    validate_alas_screenshot_interval_config,
    validate_alas_when_task_queue_empty,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.optimization-config-replay/v1"
INVALID_NUMBERS = (True, False, "0.3", None, math.nan, math.inf, -math.inf, [], {})
INVALID_IDLE_MODES = ("", "invalid", None, 0, True, [], {})


class _Logger:
    def __getattr__(self, _name: str) -> Callable[..., None]:
        return lambda *_args, **_kwargs: None


class _ScriptError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, owner: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == owner:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
    raise AssertionError(f"missing {owner}.{name} in {path.name}")


def _compile_method(node: ast.FunctionDef, globals_: dict[str, Any]):
    namespace = dict(globals_)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, "<alas-optimization-replay>", "exec"), namespace)
    return namespace[node.name]


def _verify_args(args_path: Path) -> None:
    document = json.loads(args_path.read_text(encoding="utf-8"))
    optimization = document.get("Alas", {}).get("Optimization")
    if not isinstance(optimization, dict) or set(optimization) != {
        "ScreenshotInterval",
        "CombatScreenshotInterval",
        "TaskHoardingDuration",
        "WhenTaskQueueEmpty",
    }:
        raise AssertionError("Optimization field surface drifted")
    for field, default in {
        "ScreenshotInterval": 0.3,
        "CombatScreenshotInterval": 1.0,
    }.items():
        declaration = optimization[field]
        if declaration.get("type") != "input" or declaration.get("value") != default:
            raise AssertionError(f"Optimization.{field} declaration drifted")
    idle = optimization["WhenTaskQueueEmpty"]
    if (
        idle.get("type") != "select"
        or idle.get("value") != "goto_main"
        or tuple(idle.get("option", ())) != WHEN_TASK_QUEUE_EMPTY
    ):
        raise AssertionError("Optimization.WhenTaskQueueEmpty declaration drifted")


def _consumer_methods(path: Path, owner: str, fields: tuple[str, ...]) -> dict[str, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    target = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == owner
    )
    result: dict[str, list[str]] = {}
    for field in fields:
        methods = []
        for child in target.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            if any(
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and node.attr == field
                for node in ast.walk(child)
            ):
                methods.append(child.name)
        result[field] = methods
    return result


def _guard_present(node: ast.FunctionDef, name: str) -> bool:
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == name
        for item in ast.walk(node)
    )


def _limit_in(value: int | float, lower: float, upper: float) -> int | float:
    return max(min(value, upper), lower)


class _Timer:
    def __init__(self):
        self.limit = 99.0


def _interval_case(
    method,
    *,
    screenshot: object = 0.3,
    combat: object = 1.0,
    screenshot_method: str = "ADB",
    requested: object = None,
) -> dict[str, Any]:
    config = SimpleNamespace(
        Optimization_ScreenshotInterval=screenshot,
        Optimization_CombatScreenshotInterval=combat,
        Emulator_ScreenshotMethod=screenshot_method,
    )
    timer = _Timer()
    host = SimpleNamespace(config=config, _screenshot_interval=timer)
    MethodType(method, host)(requested)
    return {
        "timer": timer.limit,
        "screenshot": config.Optimization_ScreenshotInterval,
        "combat": config.Optimization_CombatScreenshotInterval,
    }


def _verify_interval_replay(method) -> dict[str, Any]:
    cases = {
        "default_low_clamp": _interval_case(method, screenshot=-1),
        "default_high_clamp": _interval_case(method, screenshot=2),
        "default_exact": _interval_case(method, screenshot=0.2),
        "nemu_lower_cap": _interval_case(
            method, screenshot=0.3, screenshot_method="nemu_ipc"
        ),
        "ldopengl_lower_cap": _interval_case(
            method, screenshot=0.3, screenshot_method="ldopengl"
        ),
        "combat_low_clamp": _interval_case(method, combat=-1, requested="combat"),
        "combat_high_clamp": _interval_case(method, combat=2, requested="combat"),
        "combat_exact": _interval_case(method, combat=0.6, requested="combat"),
        "manual": _interval_case(method, requested=0.35),
        "scrcpy": _interval_case(
            method, screenshot=0.3, screenshot_method="scrcpy"
        ),
    }
    expected_timers = {
        "default_low_clamp": 0.1,
        "default_high_clamp": 0.3,
        "default_exact": 0.2,
        "nemu_lower_cap": 0.2,
        "ldopengl_lower_cap": 0.2,
        "combat_low_clamp": 0.3,
        "combat_high_clamp": 1.0,
        "combat_exact": 0.6,
        "manual": 0.35,
        "scrcpy": 0.1,
    }
    if {name: case["timer"] for name, case in cases.items()} != expected_timers:
        raise AssertionError("original screenshot interval decisions drifted")
    if cases["default_low_clamp"]["screenshot"] != 0.1:
        raise AssertionError("default low clamp writeback drifted")
    if cases["default_high_clamp"]["screenshot"] != 0.3:
        raise AssertionError("default high clamp writeback drifted")
    if cases["combat_low_clamp"]["combat"] != 0.3:
        raise AssertionError("combat low clamp writeback drifted")
    if cases["combat_high_clamp"]["combat"] != 1.0:
        raise AssertionError("combat high clamp writeback drifted")
    return cases


class _FixedDateTime(datetime):
    now_value = datetime(2026, 8, 15, 8, 0, 0)

    @classmethod
    def now(cls, _tz=None):
        return cls.now_value


def _queue_case(method, *, mode: object, future: bool = True) -> dict[str, Any]:
    events: list[Any] = []
    task = SimpleNamespace(
        command="Restart",
        next_run=_FixedDateTime.now_value
        + (timedelta(minutes=5) if future else -timedelta(minutes=1)),
    )

    class Config:
        Optimization_WhenTaskQueueEmpty = mode
        get_next_calls = 0

        def get_next(self):
            self.get_next_calls += 1
            events.append("get_next")
            return task

        def bind(self, actual):
            events.append(["bind", actual.command])

        def task_call(self, command):
            events.append(["task_call", command])

    config = Config()
    device = SimpleNamespace(
        app_stop=lambda: events.append("app_stop"),
        release_during_wait=lambda: events.append("release_during_wait"),
    )
    host = SimpleNamespace(
        config=config,
        device=device,
        is_first_task=True,
        run=lambda name: events.append(["run", name]),
        wait_until=lambda value: events.append(
            ["wait_until", value.isoformat(sep=" ")]
        )
        or True,
    )
    saved = {name: sys.modules.get(name) for name in (
        "module",
        "module.base",
        "module.base.resource",
    )}
    package = ModuleType("module")
    package.__path__ = []  # type: ignore[attr-defined]
    base = ModuleType("module.base")
    base.__path__ = []  # type: ignore[attr-defined]
    resource = ModuleType("module.base.resource")
    resource.release_resources = lambda **kwargs: events.append(  # type: ignore[attr-defined]
        ["release_resources", kwargs]
    )
    sys.modules["module"] = package
    sys.modules["module.base"] = base
    sys.modules["module.base.resource"] = resource
    rejected = False
    try:
        try:
            result = MethodType(method, host)()
        except SemanticGateClosed:
            result = None
            rejected = True
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return {
        "result": result,
        "events": events,
        "get_next_calls": config.get_next_calls,
        "rejected": rejected,
    }


def _verify_queue_replay(method) -> dict[str, Any]:
    cases = {
        mode: _queue_case(method, mode=mode)
        for mode in WHEN_TASK_QUEUE_EMPTY
    }
    cases["due"] = _queue_case(method, mode="goto_main", future=False)
    if "app_stop" not in cases["close_game"]["events"]:
        raise AssertionError("close_game idle branch drifted")
    if ["run", "goto_main"] not in cases["goto_main"]["events"]:
        raise AssertionError("goto_main idle branch drifted")
    if any(
        event == "app_stop" or event == ["run", "goto_main"]
        for event in cases["stay_there"]["events"]
    ):
        raise AssertionError("stay_there idle branch drifted")
    if any(
        event == "app_stop" or event == ["run", "goto_main"]
        for event in cases["due"]["events"]
    ):
        raise AssertionError("due task touched idle action")
    return cases


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    for value in (-1, 0, 0.1, 0.3, 1, 2):
        validate_alas_screenshot_interval_config(
            screenshot_interval=value,
            combat_screenshot_interval=value,
        )
        accepted += 1
    for value in WHEN_TASK_QUEUE_EMPTY:
        validate_alas_when_task_queue_empty(value)
        accepted += 1
    invalid = 0
    for field in ("screenshot_interval", "combat_screenshot_interval"):
        for value in INVALID_NUMBERS:
            case = {"screenshot_interval": 0.3, "combat_screenshot_interval": 1.0}
            case[field] = value
            try:
                validate_alas_screenshot_interval_config(**case)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid {field} was admitted")
    for value in INVALID_IDLE_MODES:
        try:
            validate_alas_when_task_queue_empty(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid WhenTaskQueueEmpty was admitted")
    return accepted, invalid


def _dedithering_bypassed_in_semantic_mode(screenshot_path: Path) -> bool:
    node = _method(screenshot_path, "Screenshot", "screenshot")
    semantic_returns = [
        item.lineno
        for item in ast.walk(node)
        if isinstance(item, ast.Return)
        and isinstance(item.value, ast.Attribute)
        and item.value.attr == "image"
    ]
    dedithering_operations = [
        item.lineno
        for item in ast.walk(node)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and item.func.attr == "fastNlMeansDenoising"
    ]
    return bool(
        semantic_returns
        and dedithering_operations
        and min(semantic_returns) < min(dedithering_operations)
    )


def verify_optimization_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    screenshot_path = alas_root / "module/device/screenshot.py"
    alas_path = alas_root / "alas.py"
    args_path = alas_root / "module/config/argument/args.json"
    _verify_args(args_path)
    interval_node = _method(screenshot_path, "Screenshot", "screenshot_interval_set")
    queue_node = _method(alas_path, "AzurLaneAutoScript", "get_next_task")
    consumers = {
        **_consumer_methods(
            screenshot_path,
            "Screenshot",
            (
                "Optimization_ScreenshotInterval",
                "Optimization_CombatScreenshotInterval",
            ),
        ),
        **_consumer_methods(
            alas_path,
            "AzurLaneAutoScript",
            ("Optimization_WhenTaskQueueEmpty",),
        ),
    }
    expected_consumers = {
        "Optimization_ScreenshotInterval": ["screenshot_interval_set"],
        "Optimization_CombatScreenshotInterval": ["screenshot_interval_set"],
        "Optimization_WhenTaskQueueEmpty": ["get_next_task"],
    }
    if consumers != expected_consumers:
        raise AssertionError("Optimization consumer surface drifted")
    interval_guard = _guard_present(
        interval_node, "validate_alas_screenshot_interval_config"
    )
    queue_guard = _guard_present(queue_node, "validate_alas_when_task_queue_empty")
    interval_method = _compile_method(
        interval_node,
        {
            "validate_alas_screenshot_interval_config": validate_alas_screenshot_interval_config,
            "limit_in": _limit_in,
            "logger": _Logger(),
            "ScriptError": _ScriptError,
        },
    )
    queue_method = _compile_method(
        queue_node,
        {
            "validate_alas_when_task_queue_empty": validate_alas_when_task_queue_empty,
            "datetime": _FixedDateTime,
            "logger": _Logger(),
            "AzurLaneConfig": type("AzurLaneConfig", (), {"is_hoarding_task": True}),
            "del_cached_property": lambda *_args: None,
        },
    )
    interval_cases = _verify_interval_replay(interval_method)
    queue_cases = _verify_queue_replay(queue_method)
    accepted, invalid = _verify_contract()
    invalid_entry_events = {}
    if interval_guard:
        timer = _Timer()
        host = SimpleNamespace(
            config=SimpleNamespace(
                Optimization_ScreenshotInterval=math.nan,
                Optimization_CombatScreenshotInterval=1.0,
                Emulator_ScreenshotMethod="ADB",
            ),
            _screenshot_interval=timer,
        )
        try:
            MethodType(interval_method, host)()
        except SemanticGateClosed:
            invalid_entry_events["screenshot_interval"] = []
        else:
            raise AssertionError("patched interval entry admitted NaN")
        if timer.limit != 99.0:
            raise AssertionError("invalid interval mutated timer before rejection")
    if queue_guard:
        rejected = _queue_case(queue_method, mode="invalid")
        if not rejected["rejected"] or rejected["get_next_calls"]:
            raise AssertionError("invalid idle mode dequeued a task")
        invalid_entry_events["when_task_queue_empty"] = rejected["events"]
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "patched_guards_present": interval_guard and queue_guard,
        "interval_cases": interval_cases,
        "queue_cases": queue_cases,
        "invalid_entry_events": invalid_entry_events,
        "screenshot_dedithering_semantic_bypass": _dedithering_bypassed_in_semantic_mode(
            screenshot_path
        ),
        "mutation_budget": 0,
        "real_screenshot_performed": False,
        "real_idle_action_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(args_path),
            "screenshot": _sha256(screenshot_path),
            "alas": _sha256(alas_path),
        },
    }
