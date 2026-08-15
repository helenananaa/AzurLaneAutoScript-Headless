"""Input-free replay for selected pinned ALAS Operation Siren task settings."""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Callable

import numpy as np

from .alas_opsi_task_config_contract import (
    OPSI_HAZARD1_TARGET_ZONES,
    OPSI_FLEET_INDEXES,
    OPSI_MEOWFFICER_HAZARD_LEVELS,
    OPSI_MONTH_BOSS_MODES,
    validate_alas_opsi_daily_config,
    validate_alas_opsi_delay_task_config,
    validate_alas_opsi_explore_config,
    validate_alas_opsi_fleet_selection,
    validate_alas_opsi_hazard1_config,
    validate_alas_opsi_meowfficer_config,
    validate_alas_opsi_month_boss_config,
    validate_alas_opsi_order,
    validate_alas_opsi_obscure_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.opsi-task-config-replay/v1"
INVALID_BOOLEANS = (0, 1, "true", None, [], {})
INVALID_MODES = ("", "hard", None, 0, True, [], {})
DEAD_FIELDS = (
    "OpsiMonthBoss_ForceRun",
    "OpsiDaily_DoMission",
)

DYNAMIC_DELAY_FIELDS = (
    "OpsiExplore_ForceRun",
    "OpsiObscure_ForceRun",
    "OpsiAbyssal_ForceRun",
    "OpsiStronghold_ForceRun",
    "OpsiExplore_SpecialRadar",
)


class _Logger:
    def __getattr__(self, _name: str) -> Callable[..., None]:
        return lambda *_args, **_kwargs: None


class _TaskStop(RuntimeError):
    pass


class _Switch(RuntimeError):
    pass


class _ZoneList:
    def __init__(self, zone_id: int):
        self.zone = SimpleNamespace(zone_id=zone_id)

    def delete(self, _value):
        return self

    def sort_by_clock_degree(self, **_kwargs):
        return self

    def __getitem__(self, index: int):
        if index != 0:
            raise IndexError(index)
        return self.zone


class _TaskList:
    def __init__(self, values):
        self.values = list(values)

    def __iter__(self):
        return iter(self.values)

    def filter(self, predicate):
        return _TaskList(value for value in self.values if predicate(value))

    def delete(self, other):
        removed = set(other.values)
        return _TaskList(value for value in self.values if value not in removed)


def _deep_get(data: dict[str, Any], *, keys: str, default=None):
    value: Any = data
    for key in keys.split("."):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


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
    for panel in (
        "OpsiExplore",
        "OpsiDaily",
        "OpsiObscure",
        "OpsiArchive",
        "OpsiMeowfficerFarming",
        "OpsiHazard1Leveling",
    ):
        fleet = document.get(panel, {}).get("OpsiFleet")
        if not isinstance(fleet, dict) or set(fleet) != {"Fleet", "Submarine"}:
            raise AssertionError(f"{panel}.OpsiFleet field surface drifted")
        fleet_index = fleet["Fleet"]
        if (
            fleet_index.get("type") != "select"
            or fleet_index.get("value") != 1
            or fleet_index.get("option") != list(OPSI_FLEET_INDEXES)
        ):
            raise AssertionError(f"{panel}.OpsiFleet.Fleet declaration drifted")
        submarine = fleet["Submarine"]
        if submarine.get("type") != "checkbox" or submarine.get("value") is not False:
            raise AssertionError(f"{panel}.OpsiFleet.Submarine declaration drifted")
    explore = document.get("OpsiExplore", {}).get("OpsiExplore")
    if not isinstance(explore, dict) or set(explore) != {
        "SpecialRadar",
        "ForceRun",
        "LastZone",
    }:
        raise AssertionError("OpsiExplore field surface drifted")
    for field in ("SpecialRadar", "ForceRun"):
        declaration = explore[field]
        if declaration.get("type") != "checkbox" or declaration.get("value") is not False:
            raise AssertionError(f"OpsiExplore.{field} declaration drifted")
    last_zone = explore["LastZone"]
    if last_zone.get("type") != "input" or last_zone.get("value") != 0:
        raise AssertionError("OpsiExplore.LastZone declaration drifted")
    for task in ("OpsiAbyssal", "OpsiStronghold"):
        declaration = document.get(task, {}).get(task, {}).get("ForceRun")
        if (
            not isinstance(declaration, dict)
            or declaration.get("type") != "checkbox"
            or declaration.get("value") is not False
        ):
            raise AssertionError(f"{task}.ForceRun declaration drifted")
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
    daily = document.get("OpsiDaily", {}).get("OpsiDaily")
    if not isinstance(daily, dict) or set(daily) != {
        "DoMission",
        "UseTuningSample",
    }:
        raise AssertionError("OpsiDaily field surface drifted")
    for field, default in (("DoMission", True), ("UseTuningSample", True)):
        declaration = daily[field]
        if declaration.get("type") != "checkbox" or declaration.get("value") is not default:
            raise AssertionError(f"OpsiDaily.{field} declaration drifted")
    hazard = document.get("OpsiHazard1Leveling", {}).get(
        "OpsiHazard1Leveling", {}
    ).get("TargetZone")
    if (
        not isinstance(hazard, dict)
        or hazard.get("type") != "select"
        or hazard.get("value") != 0
        or hazard.get("option") != list(OPSI_HAZARD1_TARGET_ZONES)
    ):
        raise AssertionError("OpsiHazard1Leveling.TargetZone declaration drifted")
    meowfficer = document.get("OpsiMeowfficerFarming", {}).get(
        "OpsiMeowfficerFarming"
    )
    if not isinstance(meowfficer, dict) or set(meowfficer) != {
        "ActionPointPreserve",
        "HazardLevel",
        "TargetZone",
    }:
        raise AssertionError("OpsiMeowfficerFarming field surface drifted")
    hazard_level = meowfficer["HazardLevel"]
    if (
        hazard_level.get("type") != "select"
        or hazard_level.get("value") != 5
        or hazard_level.get("option") != list(OPSI_MEOWFFICER_HAZARD_LEVELS)
    ):
        raise AssertionError("OpsiMeowfficerFarming.HazardLevel declaration drifted")
    action_point_preserve = meowfficer["ActionPointPreserve"]
    if (
        action_point_preserve.get("type") != "input"
        or action_point_preserve.get("value") != 1000
    ):
        raise AssertionError(
            "OpsiMeowfficerFarming.ActionPointPreserve declaration drifted"
        )


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


def _dynamic_delay_consumers(config_path: Path) -> dict[str, list[str]]:
    method = _method(config_path, "AzurLaneConfig", "opsi_task_delay")
    source = ast.unparse(method)
    result = {}
    for field in DYNAMIC_DELAY_FIELDS:
        dotted = field.replace("_", ".", 1)
        result[field] = (
            ["AzurLaneConfig.opsi_task_delay"] if dotted in source else []
        )
    return result


class _Config(SimpleNamespace):
    def __init__(
        self,
        *,
        mode: object,
        check: object,
        force: object = False,
        use_tuning_sample: object = True,
        hazard_target_zone: object = 0,
        meowfficer_action_point_preserve: object = 1000,
        meowfficer_hazard_level: object = 5,
        special_radar: object = False,
    ):
        super().__init__(
            OpsiMonthBoss_Mode=mode,
            OpsiMonthBoss_CheckAdaptability=check,
            OpsiMonthBoss_ForceRun=False,
            OpsiObscure_ForceRun=force,
            OpsiDaily_UseTuningSample=use_tuning_sample,
            OpsiHazard1Leveling_TargetZone=hazard_target_zone,
            OpsiMeowfficerFarming_HazardLevel=meowfficer_hazard_level,
            OpsiExplore_SpecialRadar=special_radar,
            OpsiExplore_LastZone=0,
            OS_EXPLORE_FILTER="22",
            OpsiMeowfficerFarming_ActionPointPreserve=meowfficer_action_point_preserve,
            OpsiMeowfficerFarming_TargetZone=0,
            OpsiGeneral_UseLogger=False,
            OpsiGeneral_BuyActionPointLimit=0,
            OpsiAshBeacon_EnsureFullyCollected=False,
            OpsiFleet_Fleet=1,
            OpsiFleet_Submarine=False,
            OS_CL1_YELLOW_COINS_PRESERVE=100,
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

    def override(self, **kwargs):
        self.events.append(["override", kwargs])

    def is_task_enabled(self, task):
        self.events.append(["is_task_enabled", task])
        return False

    def cross_set(self, **kwargs):
        self.events.append(["cross_set", kwargs])


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


def _daily_case(method, *, use_tuning_sample: object) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
        use_tuning_sample=use_tuning_sample,
    )
    events = config.events
    host = SimpleNamespace(config=config)
    host.tuning_sample_use = lambda: events.append("tuning_sample_use")
    host.os_mission_overview_accept = lambda: events.append("mission_accept") or True
    host.zone_init = lambda: events.append("zone_init")
    host.os_finish_daily_mission = lambda: events.append("finish_daily")
    host.is_in_opsi_explore = lambda: events.append("explore_probe") or False
    rejected = False
    try:
        MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
    return {"rejected": rejected, "events": events}


def _verify_daily(method) -> dict[str, Any]:
    cases = {
        str(value).lower(): _daily_case(method, use_tuning_sample=value)
        for value in (False, True)
    }
    suffix = [
        "mission_accept",
        "zone_init",
        "finish_daily",
        "explore_probe",
        ["task_delay", {"server_update": True}],
    ]
    if cases["false"] != {"rejected": False, "events": suffix}:
        raise AssertionError("disabled daily tuning-sample branch drifted")
    if cases["true"] != {
        "rejected": False,
        "events": ["tuning_sample_use", *suffix],
    }:
        raise AssertionError("enabled daily tuning-sample branch drifted")
    invalid = _daily_case(method, use_tuning_sample=None)
    if invalid != {"rejected": True, "events": []}:
        raise AssertionError("invalid daily tuning-sample config touched task state")
    return {"cases": cases, "invalid_entry": invalid}


def _hazard_case(method, *, target_zone: object) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
        hazard_target_zone=target_zone,
    )
    events = config.events
    host = SimpleNamespace(
        config=config,
        device=SimpleNamespace(semantic_adapter=None),
        _ash_fully_collected=True,
        _action_point_total=0,
        zone=SimpleNamespace(zone_id=99),
        is_zone_name_hidden=True,
    )
    host.get_yellow_coins = lambda: events.append("yellow_coins") or 9999
    host.get_current_zone = lambda: events.append("current_zone")
    host.action_point_set = lambda **kwargs: events.append(["action_point_set", kwargs])
    host.name_to_zone = lambda zone: SimpleNamespace(zone_id=zone)
    host.globe_goto = lambda zone, **kwargs: events.append(
        ["globe_goto", zone.zone_id, kwargs]
    )
    host.fleet_set = lambda fleet: events.append(["fleet_set", fleet])
    host.run_strategic_search = lambda: events.append("strategic_search")
    host.handle_after_auto_search = lambda: events.append("after_auto_search")
    rejected = False
    switched = False
    try:
        MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
    except _Switch:
        switched = True
    return {"rejected": rejected, "switched": switched, "events": events}


def _verify_hazard(method) -> dict[str, Any]:
    cases = {
        str(target): _hazard_case(method, target_zone=target)
        for target in OPSI_HAZARD1_TARGET_ZONES
    }
    expected_zone = {"0": 22, "44": 44, "22": 22}
    for target, zone in expected_zone.items():
        case = cases[target]
        if case["rejected"] or not case["switched"]:
            raise AssertionError("hazard target-zone task boundary drifted")
        globe_events = [event for event in case["events"] if event[0] == "globe_goto"]
        if globe_events != [["globe_goto", zone, {"types": "SAFE", "refresh": True}]]:
            raise AssertionError("hazard target-zone selection drifted")
    invalid = _hazard_case(method, target_zone=23)
    if invalid != {"rejected": True, "switched": False, "events": []}:
        raise AssertionError("invalid hazard target zone touched task state")
    return {"cases": cases, "invalid_entry": invalid}


def _meowfficer_case(
    method, *, hazard_level: object, action_point_preserve: object = 1000
) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
        meowfficer_action_point_preserve=action_point_preserve,
        meowfficer_hazard_level=hazard_level,
    )
    events = config.events
    host = SimpleNamespace(
        config=config,
        device=SimpleNamespace(semantic_adapter=None),
        is_cl1_enabled=False,
        _ash_fully_collected=True,
        zone=SimpleNamespace(zone_id=1, location=(0, 0)),
        zones=SimpleNamespace(select=lambda **_kwargs: []),
    )
    host.get_action_point_limit = lambda: events.append("ap_limit") or 2000
    host.is_in_opsi_explore = lambda: events.append("explore_probe") or False
    host.action_point_set = lambda **kwargs: events.append(["action_point_set", kwargs])
    host.zone_select = lambda **kwargs: events.append(
        ["zone_select", kwargs]
    ) or _ZoneList(44)
    host.globe_goto = lambda zone, **kwargs: events.append(
        ["globe_goto", zone.zone_id, kwargs]
    )
    host.fleet_set = lambda fleet: events.append(["fleet_set", fleet])
    host.os_order_execute = lambda **kwargs: events.append(["os_order_execute", kwargs])
    host.run_auto_search = lambda: events.append("auto_search")
    host.handle_after_auto_search = lambda: events.append("after_auto_search")
    rejected = False
    switched = False
    try:
        MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
    except _Switch:
        switched = True
    return {
        "rejected": rejected,
        "switched": switched,
        "effective_preserve": getattr(config, "OS_ACTION_POINT_PRESERVE", None),
        "events": events,
    }


def _verify_meowfficer(method) -> dict[str, Any]:
    cases = {
        str(level): _meowfficer_case(method, hazard_level=level)
        for level in OPSI_MEOWFFICER_HAZARD_LEVELS
    }
    for level, case in cases.items():
        if case["rejected"] or not case["switched"]:
            raise AssertionError("meowfficer hazard-level task boundary drifted")
        selected = [event for event in case["events"] if event[0] == "zone_select"]
        if selected != [["zone_select", {"hazard_level": int(level)}]]:
            raise AssertionError("meowfficer hazard-level selection drifted")
    preserve_cases = {
        str(preserve): _meowfficer_case(
            method,
            hazard_level=5,
            action_point_preserve=preserve,
        )
        for preserve in (0, 1000, 2500)
    }
    for preserve, expected in (("0", 0), ("1000", 1000), ("2500", 2000)):
        case = preserve_cases[preserve]
        if case["rejected"] or not case["switched"]:
            raise AssertionError("meowfficer AP-preserve task boundary drifted")
        if case["effective_preserve"] != expected:
            raise AssertionError("meowfficer AP-preserve clamping drifted")
    invalid = _meowfficer_case(method, hazard_level=7)
    if invalid != {
        "rejected": True,
        "switched": False,
        "effective_preserve": None,
        "events": [],
    }:
        raise AssertionError("invalid meowfficer hazard level touched task state")
    invalid_preserve = _meowfficer_case(
        method,
        hazard_level=5,
        action_point_preserve=-1,
    )
    if invalid_preserve != {
        "rejected": True,
        "switched": False,
        "effective_preserve": None,
        "events": [],
    }:
        raise AssertionError("invalid meowfficer AP preserve touched task state")
    return {
        "cases": cases,
        "preserve_cases": preserve_cases,
        "invalid_entry": invalid,
        "invalid_preserve_entry": invalid_preserve,
    }


_DELAY_TASKS = (
    "OpsiExplore",
    "OpsiDaily",
    "OpsiObscure",
    "OpsiAbyssal",
    "OpsiArchive",
    "OpsiStronghold",
    "OpsiMeowfficerFarming",
    "OpsiMonthBoss",
)


def _delay_data(overrides: dict[str, object] | None = None) -> dict[str, Any]:
    data = {
        task: {
            "Scheduler": {"NextRun": datetime(1970, 1, 1)},
            "OpsiExplore": {"ForceRun": False, "SpecialRadar": False},
            "OpsiObscure": {"ForceRun": False},
            "OpsiAbyssal": {"ForceRun": False},
            "OpsiStronghold": {"ForceRun": False},
            "OpsiFleet": {"Submarine": False},
            "OpsiFleetFilter": {"Filter": ""},
        }
        for task in _DELAY_TASKS
    }
    for path, value in (overrides or {}).items():
        task, group, field = path.split(".")
        data[task][group][field] = value
    return data


def _delay_case(method, *, overrides=None, recon_scan=False, submarine_call=False):
    data = _delay_data(overrides)
    modified: dict[str, Any] = {}
    updates: list[str] = []
    host = SimpleNamespace(
        data=data,
        modified=modified,
        update=lambda: updates.append("update"),
    )
    rejected = False
    try:
        MethodType(method, host)(
            recon_scan=recon_scan,
            submarine_call=submarine_call,
        )
    except SemanticGateClosed:
        rejected = True
    return {
        "rejected": rejected,
        "modified": sorted(modified),
        "updates": updates,
    }


def _verify_delay(method) -> dict[str, Any]:
    expected_recon = [
        "OpsiExplore.Scheduler.NextRun",
        "OpsiObscure.Scheduler.NextRun",
        "OpsiStronghold.Scheduler.NextRun",
    ]
    cases = {"recon_default": _delay_case(method, recon_scan=True)}
    if cases["recon_default"] != {
        "rejected": False,
        "modified": expected_recon,
        "updates": ["update"],
    }:
        raise AssertionError("default recon-scan delay drifted")
    for task, group in (
        ("OpsiExplore", "OpsiExplore"),
        ("OpsiObscure", "OpsiObscure"),
        ("OpsiStronghold", "OpsiStronghold"),
    ):
        name = f"{task}_force"
        cases[name] = _delay_case(
            method,
            recon_scan=True,
            overrides={f"{task}.{group}.ForceRun": True},
        )
        expected = [key for key in expected_recon if not key.startswith(task + ".")]
        if cases[name]["modified"] != expected or cases[name]["rejected"]:
            raise AssertionError(f"{task}.ForceRun delay exclusion drifted")
    cases["explore_special_radar"] = _delay_case(
        method,
        recon_scan=True,
        overrides={"OpsiExplore.OpsiExplore.SpecialRadar": True},
    )
    if (
        cases["explore_special_radar"]["modified"]
        != expected_recon[1:]
        or cases["explore_special_radar"]["rejected"]
    ):
        raise AssertionError("OpsiExplore.SpecialRadar delay exclusion drifted")
    cases["abyssal_submarine"] = _delay_case(
        method,
        submarine_call=True,
        overrides={"OpsiAbyssal.OpsiFleet.Submarine": True},
    )
    if cases["abyssal_submarine"]["modified"] != [
        "OpsiAbyssal.Scheduler.NextRun"
    ]:
        raise AssertionError("Abyssal submarine delay drifted")
    cases["abyssal_force"] = _delay_case(
        method,
        submarine_call=True,
        overrides={
            "OpsiAbyssal.OpsiFleet.Submarine": True,
            "OpsiAbyssal.OpsiAbyssal.ForceRun": True,
        },
    )
    if cases["abyssal_force"]["modified"] or cases["abyssal_force"]["rejected"]:
        raise AssertionError("OpsiAbyssal.ForceRun delay exclusion drifted")

    invalid_cases = {}
    invalid_paths = (
        ("OpsiExplore.OpsiExplore.ForceRun", True, False),
        ("OpsiObscure.OpsiObscure.ForceRun", True, False),
        ("OpsiAbyssal.OpsiAbyssal.ForceRun", False, True),
        ("OpsiStronghold.OpsiStronghold.ForceRun", True, False),
        ("OpsiExplore.OpsiExplore.SpecialRadar", True, False),
    )
    for path, recon, submarine in invalid_paths:
        overrides = {path: None}
        if submarine:
            overrides["OpsiAbyssal.OpsiFleet.Submarine"] = True
        case = _delay_case(
            method,
            overrides=overrides,
            recon_scan=recon,
            submarine_call=submarine,
        )
        if case != {"rejected": True, "modified": [], "updates": []}:
            raise AssertionError(f"invalid {path} touched scheduler state")
        invalid_cases[path] = case
    return {"cases": cases, "invalid_entries": invalid_cases}


def _explore_case(method, *, special_radar: object) -> dict[str, Any]:
    config = _Config(mode="normal", check=False, special_radar=special_radar)
    events = config.events
    host = SimpleNamespace(
        config=config,
        _solved_map_event=set(),
        _os_explore_failed_zone=[],
    )
    host.name_to_zone = lambda zone: events.append(["name_to_zone", zone]) or SimpleNamespace(
        zone_id=int(zone)
    )
    host.globe_goto = lambda zone, **kwargs: events.append(
        ["globe_goto", zone, kwargs]
    ) or True
    host.tuning_sample_use = lambda: events.append("tuning_sample_use")
    host.fleet_set = lambda fleet: events.append(["fleet_set", fleet])
    host.os_order_execute = lambda **kwargs: events.append(
        ["os_order_execute", kwargs]
    )
    host._os_explore_task_delay = lambda: events.append("explore_task_delay")
    host.run_auto_search = lambda: events.append("auto_search") or 1
    host.handle_after_auto_search = lambda: events.append("after_auto_search")
    rejected = False
    switched = False
    try:
        MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
    except _Switch:
        switched = True
    return {"rejected": rejected, "switched": switched, "events": events}


def _verify_explore(method) -> dict[str, Any]:
    cases = {
        str(value).lower(): _explore_case(method, special_radar=value)
        for value in (False, True)
    }
    for value, recon_scan in ((False, True), (True, False)):
        case = cases[str(value).lower()]
        if case["rejected"] or not case["switched"]:
            raise AssertionError("OpsiExplore.SpecialRadar task boundary drifted")
        orders = [event for event in case["events"] if event[0] == "os_order_execute"]
        if orders != [["os_order_execute", {"recon_scan": recon_scan, "submarine_call": False}]]:
            raise AssertionError("OpsiExplore.SpecialRadar recon decision drifted")
        used_tuning = "tuning_sample_use" in case["events"]
        if used_tuning is not (not value):
            raise AssertionError("OpsiExplore.SpecialRadar tuning decision drifted")
    invalid = _explore_case(method, special_radar=None)
    if invalid != {"rejected": True, "switched": False, "events": []}:
        raise AssertionError("invalid OpsiExplore.SpecialRadar touched task state")
    return {"cases": cases, "invalid_entry": invalid}


def _fleet_selection_case(method, *, fleet: object) -> dict[str, Any]:
    events: list[Any] = []
    selector = SimpleNamespace(
        ensure_to_be=lambda index: events.append(["ensure_to_be", index]) or True
    )
    host = SimpleNamespace(fleet_selector=selector)
    host.wait_until_camera_stable = lambda: events.append("camera_stable")
    rejected = False
    try:
        result = MethodType(method, host)(fleet)
    except SemanticGateClosed:
        result = None
        rejected = True
    return {"rejected": rejected, "result": result, "events": events}


def _verify_fleet_selection(method) -> dict[str, Any]:
    cases = {
        str(fleet): _fleet_selection_case(method, fleet=fleet)
        for fleet in OPSI_FLEET_INDEXES
    }
    for fleet, case in cases.items():
        if case != {
            "rejected": False,
            "result": True,
            "events": [["ensure_to_be", int(fleet)], "camera_stable"],
        }:
            raise AssertionError("OpsiFleet.Fleet selection boundary drifted")
    invalid = _fleet_selection_case(method, fleet=0)
    if invalid != {"rejected": True, "result": None, "events": []}:
        raise AssertionError("invalid OpsiFleet.Fleet touched selector state")
    return {"cases": cases, "invalid_entry": invalid}


def _order_case(method, *, recon_scan: object, submarine_call: object):
    events: list[Any] = []
    config = SimpleNamespace(
        opsi_task_delay=lambda **kwargs: events.append(["opsi_task_delay", kwargs])
    )
    host = SimpleNamespace(config=config)
    host.order_execute = lambda order: events.append(["order_execute", order]) or True
    host.wait_until_order_finished = lambda: events.append("order_finished")
    rejected = False
    try:
        MethodType(method, host)(
            recon_scan=recon_scan,
            submarine_call=submarine_call,
        )
    except SemanticGateClosed:
        rejected = True
    return {"rejected": rejected, "events": events}


def _verify_order(method) -> dict[str, Any]:
    cases = {}
    for recon_scan, submarine_call in product((False, True), repeat=2):
        name = f"{int(recon_scan)}:{int(submarine_call)}"
        case = _order_case(
            method,
            recon_scan=recon_scan,
            submarine_call=submarine_call,
        )
        expected = []
        if recon_scan:
            expected.append(["order_execute", "scan"])
        if submarine_call:
            expected.extend(
                (["order_execute", "submarine"], "order_finished")
            )
        expected.append(
            [
                "opsi_task_delay",
                {
                    "recon_scan": recon_scan,
                    "submarine_call": submarine_call,
                },
            ]
        )
        if case != {"rejected": False, "events": expected}:
            raise AssertionError("OpsiFleet.Submarine order boundary drifted")
        cases[name] = case
    invalid = _order_case(method, recon_scan=False, submarine_call=None)
    if invalid != {"rejected": True, "events": []}:
        raise AssertionError("invalid OpsiFleet.Submarine touched order state")
    return {"cases": cases, "invalid_entry": invalid}


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
    for use_tuning_sample in (False, True):
        validate_alas_opsi_daily_config(use_tuning_sample=use_tuning_sample)
        accepted += 1
    for target_zone in OPSI_HAZARD1_TARGET_ZONES:
        validate_alas_opsi_hazard1_config(target_zone=target_zone)
        accepted += 1
    for hazard_level in OPSI_MEOWFFICER_HAZARD_LEVELS:
        validate_alas_opsi_meowfficer_config(
            action_point_preserve=1000,
            hazard_level=hazard_level,
        )
        accepted += 1
    for action_point_preserve in (0, 1000, 2500):
        validate_alas_opsi_meowfficer_config(
            action_point_preserve=action_point_preserve,
            hazard_level=5,
        )
        accepted += 1
    for values in product((False, True), repeat=5):
        validate_alas_opsi_delay_task_config(
            explore_force_run=values[0],
            obscure_force_run=values[1],
            abyssal_force_run=values[2],
            stronghold_force_run=values[3],
            special_radar=values[4],
        )
        validate_alas_opsi_explore_config(special_radar=values[4])
        accepted += 1
    for fleet in OPSI_FLEET_INDEXES:
        validate_alas_opsi_fleet_selection(fleet=fleet)
        accepted += 1
    for recon_scan, submarine_call in product((False, True), repeat=2):
        validate_alas_opsi_order(
            recon_scan=recon_scan,
            submarine_call=submarine_call,
        )
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
        for field in ("month", "obscure", "daily"):
            try:
                if field == "month":
                    validate_alas_opsi_month_boss_config(
                        mode="normal", check_adaptability=value
                    )
                elif field == "obscure":
                    validate_alas_opsi_obscure_config(force_run=value)
                else:
                    validate_alas_opsi_daily_config(use_tuning_sample=value)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid {field} boolean was admitted")
    for value in (-1, 1, 23, 45, None, True, "22", 22.0, [], {}):
        try:
            validate_alas_opsi_hazard1_config(target_zone=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiHazard1Leveling.TargetZone was admitted")
    for value in (0, 1, 2, 7, 9, 11, None, True, "5", 5.0, [], {}):
        try:
            validate_alas_opsi_meowfficer_config(
                action_point_preserve=1000,
                hazard_level=value,
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiMeowfficerFarming.HazardLevel was admitted")
    for value in (-1, None, True, False, "1000", 1000.0, [], {}):
        try:
            validate_alas_opsi_meowfficer_config(
                action_point_preserve=value,
                hazard_level=5,
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError(
                "invalid OpsiMeowfficerFarming.ActionPointPreserve was admitted"
            )
    delay_fields = (
        "explore_force_run",
        "obscure_force_run",
        "abyssal_force_run",
        "stronghold_force_run",
        "special_radar",
    )
    for value in INVALID_BOOLEANS:
        for field in delay_fields:
            kwargs = {name: False for name in delay_fields}
            kwargs[field] = value
            try:
                validate_alas_opsi_delay_task_config(**kwargs)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid delay boolean {field} was admitted")
    for value in (-1, 0, 5, None, True, False, "1", 1.0, [], {}):
        try:
            validate_alas_opsi_fleet_selection(fleet=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiFleet.Fleet was admitted")
    for value in INVALID_BOOLEANS:
        for field in ("recon_scan", "submarine_call"):
            kwargs = {"recon_scan": False, "submarine_call": False}
            kwargs[field] = value
            try:
                validate_alas_opsi_order(**kwargs)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid Opsi order boolean {field} was admitted")
    return accepted, invalid


def verify_opsi_task_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    args_path = alas_root / "module/config/argument/args.json"
    config_path = alas_root / "module/config/config.py"
    fleet_path = alas_root / "module/os/fleet.py"
    explore_path = alas_root / "module/os/tasks/explore.py"
    order_path = alas_root / "module/os_handler/map_order.py"
    month_path = alas_root / "module/os/tasks/month_boss.py"
    obscure_path = alas_root / "module/os/tasks/obscure.py"
    daily_path = alas_root / "module/os/tasks/daily.py"
    hazard_path = alas_root / "module/os/tasks/hazard_leveling.py"
    meowfficer_path = alas_root / "module/os/tasks/meowfficer_farming.py"
    _verify_args(args_path)
    explore_consumers = _consumer_methods(
        explore_path,
        "OpsiExplore",
        ("OpsiExplore_SpecialRadar",),
    )
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
    daily_consumers = _consumer_methods(
        daily_path,
        "OpsiDaily",
        ("OpsiDaily_UseTuningSample",),
    )
    hazard_consumers = _consumer_methods(
        hazard_path,
        "OpsiHazard1Leveling",
        ("OpsiHazard1Leveling_TargetZone",),
    )
    meowfficer_consumers = _consumer_methods(
        meowfficer_path,
        "OpsiMeowfficerFarming",
        (
            "OpsiMeowfficerFarming_ActionPointPreserve",
            "OpsiMeowfficerFarming_HazardLevel",
        ),
    )
    consumers = {
        **explore_consumers,
        **month_consumers,
        **obscure_consumers,
        **daily_consumers,
        **hazard_consumers,
        **meowfficer_consumers,
    }
    for field, methods in _dynamic_delay_consumers(config_path).items():
        consumers.setdefault(field, []).extend(methods)
    expected = {
        "OpsiExplore_SpecialRadar": [
            "_os_explore",
            "AzurLaneConfig.opsi_task_delay",
        ],
        "OpsiExplore_ForceRun": ["AzurLaneConfig.opsi_task_delay"],
        "OpsiMonthBoss_Mode": ["clear_month_boss", "month_boss_delay"],
        "OpsiMonthBoss_CheckAdaptability": ["clear_month_boss", "month_boss_delay"],
        "OpsiObscure_ForceRun": [
            "clear_obscure",
            "os_obscure",
            "AzurLaneConfig.opsi_task_delay",
        ],
        "OpsiAbyssal_ForceRun": ["AzurLaneConfig.opsi_task_delay"],
        "OpsiStronghold_ForceRun": ["AzurLaneConfig.opsi_task_delay"],
        "OpsiDaily_UseTuningSample": ["os_daily"],
        "OpsiHazard1Leveling_TargetZone": ["os_hazard1_leveling"],
        "OpsiMeowfficerFarming_ActionPointPreserve": ["os_meowfficer_farming"],
        "OpsiMeowfficerFarming_HazardLevel": ["os_meowfficer_farming"],
    }
    if consumers != expected:
        raise AssertionError("selected Opsi task consumer surface drifted")
    dead_loads = _dead_field_loads(alas_root)
    if any(dead_loads.values()):
        raise AssertionError("declared zero-read Opsi field gained a consumer")
    globals_ = {
        "np": np,
        "logger": _Logger(),
        "OS_MONTHBOSS_NORMAL": "normal",
        "OS_MONTHBOSS_HARD": "hard",
        "get_os_next_reset": lambda: "next-reset",
        "validate_alas_opsi_month_boss_config": validate_alas_opsi_month_boss_config,
        "validate_alas_opsi_obscure_config": validate_alas_opsi_obscure_config,
        "validate_alas_opsi_daily_config": validate_alas_opsi_daily_config,
        "validate_alas_opsi_hazard1_config": validate_alas_opsi_hazard1_config,
        "validate_alas_opsi_meowfficer_config": validate_alas_opsi_meowfficer_config,
        "SelectedGrids": _TaskList,
        "get_os_reset_remain": lambda: 1,
        "datetime": datetime,
        "timedelta": timedelta,
        "DEFAULT_TIME": datetime(1970, 1, 1),
        "dict_to_kv": lambda values: str(values),
        "deep_get": _deep_get,
        "ORDER_SCAN": "scan",
        "ORDER_SUBMARINE": "submarine",
    }
    fleet_node = _method(fleet_path, "OSFleet", "fleet_set")
    explore_node = _method(explore_path, "OpsiExplore", "_os_explore")
    order_node = _method(order_path, "MapOrderHandler", "os_order_execute")
    delay_task_node = _method(config_path, "AzurLaneConfig", "opsi_task_delay")
    month_node = _method(month_path, "OpsiMonthBoss", "clear_month_boss")
    delay_node = _method(month_path, "OpsiMonthBoss", "month_boss_delay")
    obscure_clear_node = _method(obscure_path, "OpsiObscure", "clear_obscure")
    obscure_run_node = _method(obscure_path, "OpsiObscure", "os_obscure")
    daily_node = _method(daily_path, "OpsiDaily", "os_daily")
    hazard_node = _method(
        hazard_path,
        "OpsiHazard1Leveling",
        "os_hazard1_leveling",
    )
    meowfficer_node = _method(
        meowfficer_path,
        "OpsiMeowfficerFarming",
        "os_meowfficer_farming",
    )
    explore_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_explore_config"
        for node in ast.walk(explore_node)
    )
    delay_task_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_delay_task_config"
        for node in ast.walk(delay_task_node)
    )
    fleet_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_fleet_selection"
        for node in ast.walk(fleet_node)
    )
    order_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_order"
        for node in ast.walk(order_node)
    )
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
    daily_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_daily_config"
        for node in ast.walk(daily_node)
    )
    hazard_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_hazard1_config"
        for node in ast.walk(hazard_node)
    )
    meowfficer_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_meowfficer_config"
        for node in ast.walk(meowfficer_node)
    )
    month = _verify_month(
        _compile(month_node, globals_),
        _compile(delay_node, globals_),
    )
    obscure = _verify_obscure(
        _compile(obscure_clear_node, globals_),
        _compile(obscure_run_node, globals_),
    )
    daily = _verify_daily(_compile(daily_node, globals_))
    hazard = _verify_hazard(_compile(hazard_node, globals_))
    meowfficer = _verify_meowfficer(_compile(meowfficer_node, globals_))
    explore_globals = {**globals_, "ScriptError": RuntimeError}
    explore = _verify_explore(_compile(explore_node, explore_globals))
    delay = _verify_delay(_compile(delay_task_node, globals_))
    fleet_selection = _verify_fleet_selection(_compile(fleet_node, globals_))
    order = _verify_order(_compile(order_node, globals_))
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
        "field_count": 13,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "zero_runtime_consumers": dead_loads,
        "patched_guards_present": (
            month_guard
            and obscure_guard
            and daily_guard
            and hazard_guard
            and meowfficer_guard
            and explore_guard
            and delay_task_guard
            and fleet_guard
            and order_guard
        ),
        "validated_runtime_boundaries": {
            "OpsiFleet.Fleet": "OSFleet.fleet_set",
            "OpsiFleet.Submarine": "MapOrderHandler.os_order_execute",
            "OpsiMeowfficerFarming.ActionPointPreserve": (
                "OpsiMeowfficerFarming.os_meowfficer_farming"
            ),
        },
        "fleet_selection": fleet_selection,
        "order": order,
        "explore": explore,
        "task_delay": delay,
        "month_boss": month,
        "obscure": obscure,
        "daily": daily,
        "hazard1_leveling": hazard,
        "meowfficer_farming": meowfficer,
        "invalid_month_entry": invalid_month_events,
        "mutation_budget": 0,
        "real_combat_performed": False,
        "real_storage_item_consumed": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(args_path),
            "config": _sha256(config_path),
            "fleet": _sha256(fleet_path),
            "explore": _sha256(explore_path),
            "map_order": _sha256(order_path),
            "month_boss": _sha256(month_path),
            "obscure": _sha256(obscure_path),
            "daily": _sha256(daily_path),
            "hazard1_leveling": _sha256(hazard_path),
            "meowfficer_farming": _sha256(meowfficer_path),
        },
    }
