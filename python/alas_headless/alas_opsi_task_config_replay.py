"""Input-free replay for selected pinned ALAS Operation Siren task settings."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Callable

import numpy as np

from .alas_opsi_task_config_contract import (
    OPSI_MONTH_BOSS_MODES,
    validate_alas_opsi_month_boss_config,
    validate_alas_opsi_obscure_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.opsi-task-config-replay/v1"
INVALID_BOOLEANS = (0, 1, "true", None, [], {})
INVALID_MODES = ("", "hard", None, 0, True, [], {})
DEAD_FIELDS = (
    "OpsiExplore_ForceRun",
    "OpsiAbyssal_ForceRun",
    "OpsiMonthBoss_ForceRun",
)


class _Logger:
    def __getattr__(self, _name: str) -> Callable[..., None]:
        return lambda *_args, **_kwargs: None


class _TaskStop(RuntimeError):
    pass


class _Switch(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _method(path: Path, owner: str, name: str) -> ast.FunctionDef:
    for node in _tree(path).body:
        if isinstance(node, ast.ClassDef) and node.name == owner:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
    raise AssertionError(f"missing {owner}.{name} in {path.name}")


def _compile(node: ast.FunctionDef, globals_: dict[str, Any]):
    namespace = dict(globals_)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, "<alas-opsi-task-config-replay>", "exec"), namespace)
    return namespace[node.name]


def _verify_args(args_path: Path) -> None:
    document = json.loads(args_path.read_text(encoding="utf-8"))
    month = document.get("OpsiMonthBoss", {}).get("OpsiMonthBoss")
    expected_month = {
        "Mode": ("select", "normal", list(OPSI_MONTH_BOSS_MODES)),
        "CheckAdaptability": ("checkbox", True, None),
        "ForceRun": ("checkbox", False, None),
    }
    if not isinstance(month, dict) or set(month) != set(expected_month):
        raise AssertionError("OpsiMonthBoss field surface drifted")
    for field, (type_, default, options) in expected_month.items():
        declaration = month[field]
        if declaration.get("type") != type_ or declaration.get("value") != default:
            raise AssertionError(f"OpsiMonthBoss.{field} declaration drifted")
        if options is not None and declaration.get("option") != options:
            raise AssertionError(f"OpsiMonthBoss.{field} options drifted")
    obscure = document.get("OpsiObscure", {}).get("OpsiObscure", {}).get("ForceRun")
    if (
        not isinstance(obscure, dict)
        or obscure.get("type") != "checkbox"
        or obscure.get("value") is not False
    ):
        raise AssertionError("OpsiObscure.ForceRun declaration drifted")


def _consumer_methods(path: Path, owner: str, fields: tuple[str, ...]):
    tree = _tree(path)
    target = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == owner
    )
    result = {}
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


def _dead_field_loads(alas_root: Path) -> dict[str, list[str]]:
    result = {field: [] for field in DEAD_FIELDS}
    for path in alas_root.rglob("*.py"):
        if path.name == "config_generated.py":
            continue
        try:
            tree = _tree(path)
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and node.attr in result
            ):
                continue
            result[node.attr].append(path.relative_to(alas_root).as_posix())
    return result


class _Config(SimpleNamespace):
    def __init__(self, *, mode: object, check: object, force: object = False):
        super().__init__(
            OpsiMonthBoss_Mode=mode,
            OpsiMonthBoss_CheckAdaptability=check,
            OpsiMonthBoss_ForceRun=False,
            OpsiObscure_ForceRun=force,
            OpsiGeneral_UseLogger=False,
            OpsiFleet_Fleet=1,
            OpsiFleet_Submarine=False,
        )
        self.events: list[Any] = []

    def task_delay(self, **kwargs):
        self.events.append(["task_delay", kwargs])

    def opsi_task_delay(self, **kwargs):
        self.events.append(["opsi_task_delay", kwargs])

    def task_stop(self):
        self.events.append("task_stop")
        raise _TaskStop

    def check_task_switch(self):
        self.events.append("check_task_switch")
        raise _Switch


def _month_clear_case(
    method,
    *,
    mode: object,
    check: object,
    difficulty: str = "normal",
    adaptability: tuple[int, int, int] = (203, 203, 156),
) -> dict[str, Any]:
    config = _Config(mode=mode, check=check)
    events = config.events
    host = SimpleNamespace(config=config)
    host.is_in_opsi_explore = lambda: events.append("explore_probe") or False
    host.os_mission_enter = lambda: events.append("mission_enter")
    host.os_mission_quit = lambda: events.append("mission_quit")
    host.appear = lambda button, **_kwargs: events.append(["appear", button]) or (
        button == difficulty
    )
    host.month_boss_delay = lambda **kwargs: events.append(["month_boss_delay", kwargs])
    host.os_map_goto_globe = lambda **kwargs: events.append(["goto_globe", kwargs])
    host.get_adaptability = lambda: events.append("adaptability") or adaptability
    host.globe_goto = lambda zone: events.append(["globe_goto", zone])
    host.go_month_boss_room = lambda **kwargs: events.append(["boss_room", kwargs])
    host.boss_clear = lambda **kwargs: events.append(["boss_clear", kwargs]) or True
    host.fleet_repair = lambda **kwargs: events.append(["fleet_repair", kwargs])
    host.handle_fleet_resolve = lambda **kwargs: events.append(["fleet_resolve", kwargs])
    stopped = False
    rejected = False
    try:
        result = MethodType(method, host)()
    except SemanticGateClosed:
        result = None
        rejected = True
    except _TaskStop:
        result = None
        stopped = True
    return {
        "result": result,
        "stopped": stopped,
        "rejected": rejected,
        "events": events,
    }


def _month_delay_case(method, *, mode: str, is_normal: bool, result: bool):
    config = _Config(mode=mode, check=False)
    events = config.events
    config.task_stop = lambda: events.append("task_stop")
    host = SimpleNamespace(config=config)
    MethodType(method, host)(is_normal=is_normal, result=result)
    return events


def _verify_month(method, delay_method) -> dict[str, Any]:
    cases = {
        "normal": _month_clear_case(method, mode="normal", check=False),
        "normal_hard": _month_clear_case(
            method, mode="normal_hard", check=False
        ),
        "hard_skipped": _month_clear_case(
            method, mode="normal", check=False, difficulty="hard"
        ),
        "adaptability_high": _month_clear_case(
            method, mode="normal", check=True
        ),
        "adaptability_low": _month_clear_case(
            method,
            mode="normal",
            check=True,
            adaptability=(202, 203, 156),
        ),
        "absent": _month_clear_case(
            method, mode="normal", check=False, difficulty="absent"
        ),
    }
    if ["boss_clear", {"has_fleet_step": True, "is_month": True}] not in cases[
        "normal"
    ]["events"]:
        raise AssertionError("normal month boss dispatch drifted")
    if ["boss_clear", {"has_fleet_step": True, "is_month": True}] in cases[
        "hard_skipped"
    ]["events"]:
        raise AssertionError("normal-only mode attacked hard boss")
    if "adaptability" in cases["normal"]["events"]:
        raise AssertionError("disabled adaptability check was executed")
    if "adaptability" not in cases["adaptability_high"]["events"]:
        raise AssertionError("enabled adaptability check was skipped")
    if ["boss_clear", {"has_fleet_step": True, "is_month": True}] in cases[
        "adaptability_low"
    ]["events"]:
        raise AssertionError("low adaptability reached combat")
    delays = {
        f"{mode}:{int(normal)}:{int(result)}": _month_delay_case(
            delay_method,
            mode=mode,
            is_normal=normal,
            result=result,
        )
        for mode in OPSI_MONTH_BOSS_MODES
        for normal, result in ((True, True), (True, False), (False, True), (False, False))
    }
    return {"clear_cases": cases, "delay_cases": delays}


def _verify_obscure(clear_method, run_method) -> dict[str, Any]:
    cases = {}
    for force in (False, True):
        config = _Config(mode="normal", check=False, force=force)
        events = config.events
        host = SimpleNamespace(
            config=config,
            clear_obscure=lambda: events.append("clear_obscure"),
        )
        stopped = False
        try:
            MethodType(run_method, host)()
        except _Switch:
            stopped = True
        cases[str(force).lower()] = {"events": events, "switch_stop": stopped}
    if cases["false"] != {"events": ["clear_obscure"], "switch_stop": False}:
        raise AssertionError("disabled obscure force-run drifted")
    if cases["true"] != {
        "events": ["clear_obscure", "check_task_switch"],
        "switch_stop": True,
    }:
        raise AssertionError("enabled obscure force-run drifted")
    config = _Config(mode="normal", check=False, force=None)
    host = SimpleNamespace(config=config)
    try:
        MethodType(clear_method, host)()
    except SemanticGateClosed:
        invalid_events: list[Any] = []
    else:
        raise AssertionError("invalid OpsiObscure.ForceRun reached clear state")
    return {"cases": cases, "invalid_entry_events": invalid_events}


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    for mode in OPSI_MONTH_BOSS_MODES:
        for check in (False, True):
            validate_alas_opsi_month_boss_config(
                mode=mode, check_adaptability=check
            )
            accepted += 1
    for force in (False, True):
        validate_alas_opsi_obscure_config(force_run=force)
        accepted += 1
    invalid = 0
    for value in INVALID_MODES:
        try:
            validate_alas_opsi_month_boss_config(
                mode=value, check_adaptability=True
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiMonthBoss.Mode was admitted")
    for value in INVALID_BOOLEANS:
        for field in ("month", "obscure"):
            try:
                if field == "month":
                    validate_alas_opsi_month_boss_config(
                        mode="normal", check_adaptability=value
                    )
                else:
                    validate_alas_opsi_obscure_config(force_run=value)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid {field} boolean was admitted")
    return accepted, invalid


def verify_opsi_task_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    args_path = alas_root / "module/config/argument/args.json"
    month_path = alas_root / "module/os/tasks/month_boss.py"
    obscure_path = alas_root / "module/os/tasks/obscure.py"
    _verify_args(args_path)
    month_consumers = _consumer_methods(
        month_path,
        "OpsiMonthBoss",
        ("OpsiMonthBoss_Mode", "OpsiMonthBoss_CheckAdaptability"),
    )
    obscure_consumers = _consumer_methods(
        obscure_path,
        "OpsiObscure",
        ("OpsiObscure_ForceRun",),
    )
    consumers = {**month_consumers, **obscure_consumers}
    expected = {
        "OpsiMonthBoss_Mode": ["clear_month_boss", "month_boss_delay"],
        "OpsiMonthBoss_CheckAdaptability": ["clear_month_boss", "month_boss_delay"],
        "OpsiObscure_ForceRun": ["clear_obscure", "os_obscure"],
    }
    if consumers != expected:
        raise AssertionError("selected Opsi task consumer surface drifted")
    dead_loads = _dead_field_loads(alas_root)
    if any(dead_loads.values()):
        raise AssertionError("declared zero-read ForceRun field gained a consumer")
    globals_ = {
        "np": np,
        "logger": _Logger(),
        "OS_MONTHBOSS_NORMAL": "normal",
        "OS_MONTHBOSS_HARD": "hard",
        "get_os_next_reset": lambda: "next-reset",
        "validate_alas_opsi_month_boss_config": validate_alas_opsi_month_boss_config,
        "validate_alas_opsi_obscure_config": validate_alas_opsi_obscure_config,
    }
    month_node = _method(month_path, "OpsiMonthBoss", "clear_month_boss")
    delay_node = _method(month_path, "OpsiMonthBoss", "month_boss_delay")
    obscure_clear_node = _method(obscure_path, "OpsiObscure", "clear_obscure")
    obscure_run_node = _method(obscure_path, "OpsiObscure", "os_obscure")
    month_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_month_boss_config"
        for node in ast.walk(month_node)
    )
    obscure_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_obscure_config"
        for node in ast.walk(obscure_clear_node)
    )
    month = _verify_month(
        _compile(month_node, globals_),
        _compile(delay_node, globals_),
    )
    obscure = _verify_obscure(
        _compile(obscure_clear_node, globals_),
        _compile(obscure_run_node, globals_),
    )
    invalid_month_events = {}
    if month_guard:
        invalid = _month_clear_case(
            _compile(month_node, globals_),
            mode="invalid",
            check=True,
        )
        if not invalid["rejected"]:
            raise AssertionError("invalid month boss config was not rejected")
        if invalid["events"]:
            raise AssertionError("invalid month boss config touched task state")
        invalid_month_events = invalid
    accepted, invalid = _verify_contract()
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "zero_runtime_consumers": dead_loads,
        "patched_guards_present": month_guard and obscure_guard,
        "month_boss": month,
        "obscure": obscure,
        "invalid_month_entry": invalid_month_events,
        "mutation_budget": 0,
        "real_combat_performed": False,
        "real_storage_item_consumed": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(args_path),
            "month_boss": _sha256(month_path),
            "obscure": _sha256(obscure_path),
        },
    }
