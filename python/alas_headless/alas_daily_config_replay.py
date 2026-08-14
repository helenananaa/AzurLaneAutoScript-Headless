"""Deterministic replay of the pinned ALAS Daily configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_daily_config_contract import validate_alas_daily_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.daily-config-replay/v1"
STAGE_FIELDS = (
    "EscortMission",
    "AdvanceMission",
    "FierceAssault",
    "TacticalTraining",
    "SupplyLineDisruption",
)
TWO_STAGE_FIELDS = ("ModuleDevelopment", "EmergencyModuleDevelopment")
FLEET_FIELDS = (
    "EscortMissionFleet",
    "AdvanceMissionFleet",
    "FierceAssaultFleet",
    "TacticalTrainingFleet",
    "ModuleDevelopmentFleet",
    "EmergencyModuleDevelopmentFleet",
)
ALL_FIELDS = ("UseDailySkip",) + STAGE_FIELDS + TWO_STAGE_FIELDS + FLEET_FIELDS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "use_daily_skip": True,
        "escort_mission": "first",
        "escort_mission_fleet": 1,
        "advance_mission": "second",
        "advance_mission_fleet": 2,
        "fierce_assault": "third",
        "fierce_assault_fleet": 6,
        "tactical_training": "second",
        "tactical_training_fleet": 4,
        "supply_line_disruption": "third",
        "module_development": "second",
        "module_development_fleet": 3,
        "emergency_module_development": "second",
        "emergency_module_development_fleet": 5,
    }
    values.update(overrides)
    return values


def _config(**overrides: object) -> SimpleNamespace:
    values = _values(**overrides)
    return SimpleNamespace(
        **{
            "Daily_UseDailySkip": values["use_daily_skip"],
            "Daily_EscortMission": values["escort_mission"],
            "Daily_EscortMissionFleet": values["escort_mission_fleet"],
            "Daily_AdvanceMission": values["advance_mission"],
            "Daily_AdvanceMissionFleet": values["advance_mission_fleet"],
            "Daily_FierceAssault": values["fierce_assault"],
            "Daily_FierceAssaultFleet": values["fierce_assault_fleet"],
            "Daily_TacticalTraining": values["tactical_training"],
            "Daily_TacticalTrainingFleet": values["tactical_training_fleet"],
            "Daily_SupplyLineDisruption": values["supply_line_disruption"],
            "Daily_ModuleDevelopment": values["module_development"],
            "Daily_ModuleDevelopmentFleet": values["module_development_fleet"],
            "Daily_EmergencyModuleDevelopment": values[
                "emergency_module_development"
            ],
            "Daily_EmergencyModuleDevelopmentFleet": values[
                "emergency_module_development_fleet"
            ],
        }
    )


def _verify_args(alas_root: Path) -> dict[str, object]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panel = document.get("Daily")
    group = panel.get("Daily") if isinstance(panel, dict) else None
    if not isinstance(group, dict) or set(group) != set(ALL_FIELDS):
        raise AssertionError("Daily field surface drifted")
    expected_three = ["skip", "first", "second", "third"]
    expected_two = ["skip", "first", "second"]
    expected_fleets = [1, 2, 3, 4, 5, 6]
    for field in STAGE_FIELDS:
        if group[field].get("type") != "select" or group[field].get(
            "option"
        ) != expected_three:
            raise AssertionError(f"Daily.{field} choices drifted")
    for field in TWO_STAGE_FIELDS:
        if group[field].get("type") != "select" or group[field].get(
            "option"
        ) != expected_two:
            raise AssertionError(f"Daily.{field} choices drifted")
    for field in FLEET_FIELDS:
        if group[field].get("type") != "select" or group[field].get(
            "option"
        ) != expected_fleets:
            raise AssertionError(f"Daily.{field} choices drifted")
    if group["UseDailySkip"].get("type") != "checkbox":
        raise AssertionError("Daily.UseDailySkip type drifted")
    return {field: group[field].get("value") for field in ALL_FIELDS}


def _verify_consumers(path: Path) -> dict[str, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    daily = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Daily"
    )
    functions = {
        node.name: node
        for node in daily.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    mapping = functions.get("get_daily_stage_and_fleet")
    enter = functions.get("daily_enter")
    run_one = functions.get("daily_run_one")
    run = functions.get("run")
    if None in (mapping, enter, run_one, run):
        raise AssertionError("Daily consumer methods drifted")
    mapping_attributes = {
        node.attr for node in ast.walk(mapping) if isinstance(node, ast.Attribute)
    }
    for field in STAGE_FIELDS + TWO_STAGE_FIELDS + FLEET_FIELDS:
        if f"Daily_{field}" not in mapping_attributes:
            raise AssertionError(f"Daily.{field} mapping consumer drifted")
    use_skip_consumers = []
    for name, function in (("daily_enter", enter), ("daily_run_one", run_one)):
        attributes = {
            node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)
        }
        if "Daily_UseDailySkip" not in attributes:
            raise AssertionError(f"Daily.UseDailySkip {name} consumer drifted")
        use_skip_consumers.append(name)
    run_calls = {
        node.func.attr
        for node in ast.walk(run)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    return {
        "Daily.stage_and_fleet": ["Daily.get_daily_stage_and_fleet"],
        "Daily.UseDailySkip": use_skip_consumers,
        "patched_guards": sorted(run_calls & {"_validate_daily_config"}),
    }


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.daily.daily")
        return module, module.Daily
    finally:
        sys.path.remove(root)


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for field in STAGE_FIELDS:
        key = field[0].lower() + field[1:]
        snake = "".join(
            ("_" + char.lower()) if char.isupper() else char for char in field
        ).lstrip("_")
        for value in ("skip", "first", "second", "third"):
            validate_alas_daily_config(**_values(**{snake: value}))
            accepted += 1
        for value in ("", " first", "FIRST", "fourth", 1, None):
            try:
                validate_alas_daily_config(**_values(**{snake: value}))
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid Daily.{key} was admitted")
    for field in TWO_STAGE_FIELDS:
        key = field[0].lower() + field[1:]
        snake = "".join(
            ("_" + char.lower()) if char.isupper() else char for char in field
        ).lstrip("_")
        for value in ("skip", "first", "second"):
            validate_alas_daily_config(**_values(**{snake: value}))
            accepted += 1
        for value in ("", "third", "FIRST", 1, None):
            try:
                validate_alas_daily_config(**_values(**{snake: value}))
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid Daily.{key} was admitted")
    for field in FLEET_FIELDS:
        key = field[0].lower() + field[1:]
        snake = "".join(
            ("_" + char.lower()) if char.isupper() else char for char in field
        ).lstrip("_")
        for value in range(1, 7):
            validate_alas_daily_config(**_values(**{snake: value}))
            accepted += 1
        for value in (0, 7, -1, True, "1", 1.0):
            try:
                validate_alas_daily_config(**_values(**{snake: value}))
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid Daily.{key} was admitted")
    for value in (True, False):
        validate_alas_daily_config(**_values(use_daily_skip=value))
        accepted += 1
    for value in (0, 1, "true", None):
        try:
            validate_alas_daily_config(**_values(use_daily_skip=value))
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Daily.UseDailySkip was admitted")
    return accepted, invalid


def _mapping_case(daily_type: type[Any], *, emergency: bool) -> list[tuple[int, int]]:
    host = object.__new__(daily_type)
    host.config = _config()
    host.emergency_module_development = emergency
    daily_type._validate_daily_config(host)
    results = []
    for current in range(1, 8):
        host.daily_current = current
        results.append(daily_type.get_daily_stage_and_fleet(host))
    return results


def _daily_enter_case(module: Any, daily_type: type[Any], *, use_skip: bool) -> str:
    host = object.__new__(daily_type)
    host.config = _config(use_daily_skip=use_skip)
    host.device = SimpleNamespace(screenshot=lambda: None)
    clicked = []
    host.appear = lambda *args, **kwargs: False
    host.handle_get_items = lambda: False
    host.appear_then_click = lambda button, **kwargs: clicked.append(button) or False
    host.handle_combat_automation_confirm = lambda: False
    host.handle_daily_additional = lambda: False
    host.handle_popup_confirm = lambda name: False
    host.info_bar_count = lambda: 0
    host.combat_appear = lambda: True
    result = daily_type.daily_enter(host, object())
    if result is not True or len(clicked) != 1:
        raise AssertionError("Daily.daily_enter branch fixture drifted")
    expected = module.DAILY_SKIP if use_skip else module.DAILY_NORMAL_RUN
    if clicked[0] is not expected:
        raise AssertionError("Daily.UseDailySkip selected the wrong original control")
    return "daily_skip" if use_skip else "normal_run"


def _daily_run_one_case(
    module: Any,
    daily_type: type[Any],
    *,
    target: int,
    use_skip: bool,
    active: bool = True,
    remain: int = 2,
) -> dict[str, Any]:
    overrides = {
        "use_daily_skip": use_skip,
        "escort_mission": "skip",
        "advance_mission": "skip",
        "fierce_assault": "skip",
        "tactical_training": "skip",
        "supply_line_disruption": "skip",
        "module_development": "skip",
        "emergency_module_development": "skip",
    }
    field = {
        1: "tactical_training",
        2: "supply_line_disruption",
        3: "module_development",
        5: "escort_mission",
        6: "advance_mission",
        7: "fierce_assault",
    }[target]
    overrides[field] = "second"
    host = object.__new__(daily_type)
    host.config = _config(**overrides)
    daily_type._validate_daily_config(host)
    host.daily_checked = [0]
    host.device = SimpleNamespace(
        semantic_adapter=None,
        image=None,
        sleep=lambda *args, **kwargs: None,
        screenshot=lambda: None,
    )
    events: list[tuple[Any, ...]] = []
    host.ui_ensure = lambda page: events.append(("ui_ensure",))
    host.appear = lambda *args, **kwargs: False
    host.next = lambda: (
        events.append(("next", host.daily_current)),
        setattr(host, "daily_current", host.daily_current + 1),
    )[-1]
    host.daily_check = lambda n=None: host.daily_checked.append(
        host.daily_current if n is None else n
    )
    host.is_active = lambda: active
    host.daily_execute = lambda **kwargs: events.append(("execute", kwargs)) or True
    host.ui_goto = lambda page: events.append(("ui_goto",))
    old_ocr = module.OCR_REMAIN
    module.OCR_REMAIN = SimpleNamespace(ocr=lambda image: remain)
    try:
        daily_type.daily_run_one(host)
    finally:
        module.OCR_REMAIN = old_ocr
    return {
        "events": events,
        "checked": host.daily_checked,
        "executions": [event[1] for event in events if event[0] == "execute"],
    }


def _verify_run_gate(daily_type: type[Any]) -> dict[str, Any]:
    valid = object.__new__(daily_type)
    valid.config = _config()
    valid_events = []
    valid.daily_run = lambda: valid_events.append("daily_run")
    valid.config.task_delay = lambda **kwargs: valid_events.append(("delay", kwargs))
    daily_type.run(valid)
    if valid_events != ["daily_run", ("delay", {"server_update": True})]:
        raise AssertionError("valid Daily.run ordering drifted")
    invalid = object.__new__(daily_type)
    invalid.config = _config(tactical_training="fourth")
    invalid_events = []
    invalid.daily_run = lambda: invalid_events.append("daily_run")
    invalid.config.task_delay = lambda **kwargs: invalid_events.append("delay")
    try:
        daily_type.run(invalid)
    except SemanticGateClosed:
        pass
    else:
        raise AssertionError("Daily.run admitted invalid configuration")
    if invalid_events:
        raise AssertionError("invalid Daily configuration entered the state machine")
    return {"valid_events": valid_events, "invalid_events": invalid_events}


def _verify_original(module: Any, daily_type: type[Any]) -> dict[str, Any]:
    standard = _mapping_case(daily_type, emergency=False)
    emergency = _mapping_case(daily_type, emergency=True)
    if standard != [(2, 4), (3, 0), (2, 3), (0, 0), (1, 1), (2, 2), (3, 6)]:
        raise AssertionError("standard Daily stage/fleet mapping drifted")
    if emergency != [(2, 5), (1, 1), (2, 2), (3, 6), (2, 4), (3, 0), (2, 3)]:
        raise AssertionError("emergency Daily stage/fleet mapping drifted")
    cases = {
        "daily_skip_control": _daily_enter_case(module, daily_type, use_skip=True),
        "normal_run_control": _daily_enter_case(module, daily_type, use_skip=False),
        "tactical_execute": _daily_run_one_case(
            module, daily_type, target=1, use_skip=True
        ),
        "supply_skip_disabled": _daily_run_one_case(
            module, daily_type, target=2, use_skip=False
        ),
        "supply_skip_enabled": _daily_run_one_case(
            module, daily_type, target=2, use_skip=True
        ),
        "inactive": _daily_run_one_case(
            module, daily_type, target=1, use_skip=True, active=False
        ),
        "zero_remain": _daily_run_one_case(
            module, daily_type, target=1, use_skip=True, remain=0
        ),
    }
    if cases["tactical_execute"]["executions"] != [
        {"remain": 2, "stage": 2, "fleet": 4}
    ]:
        raise AssertionError("Tactical Training execution parameters drifted")
    if cases["supply_skip_disabled"]["executions"]:
        raise AssertionError("disabled Daily skip entered Supply Line Disruption")
    if cases["supply_skip_enabled"]["executions"] != [
        {"remain": 2, "stage": 2, "fleet": 0}
    ]:
        raise AssertionError("enabled Daily skip did not preserve fleet-zero semantics")
    if cases["inactive"]["executions"] or cases["zero_remain"]["executions"]:
        raise AssertionError("inactive or exhausted Daily unexpectedly executed")
    return {
        "standard_mapping": standard,
        "emergency_mapping": emergency,
        "cases": cases,
        "run_gate": _verify_run_gate(daily_type),
    }


def verify_daily_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    defaults = _verify_args(alas_root)
    source = alas_root / "module" / "daily" / "daily.py"
    consumers = _verify_consumers(source)
    module, daily_type = _load_original(alas_root)
    accepted, invalid = _verify_contract()
    original = _verify_original(module, daily_type)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 14,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "defaults": defaults,
        "runtime_consumers": consumers,
        "original_decisions": original,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module" / "config" / "argument" / "args.json"),
            "daily": _sha256(source),
        },
    }
