"""Input-free replay for selected pinned ALAS Operation Siren task settings."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import datetime, timedelta
from functools import reduce
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
    validate_alas_opsi_action_point_purchase,
    validate_alas_opsi_akashi_filter,
    validate_alas_opsi_shop_custom_filter,
    validate_alas_opsi_shop_filter,
    validate_alas_opsi_shop_preset,
    validate_alas_opsi_voucher_filter,
    validate_alas_opsi_delay_task_config,
    validate_alas_opsi_explore_config,
    validate_alas_opsi_explore_last_zone,
    validate_alas_opsi_fleet_selection,
    validate_alas_opsi_hazard1_config,
    validate_alas_opsi_meowfficer_config,
    validate_alas_opsi_month_boss_config,
    validate_alas_opsi_order,
    validate_alas_opsi_obscure_config,
    validate_alas_opsi_repair_config,
    validate_alas_opsi_rescan_config,
    validate_alas_opsi_storage_config,
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


class _ScriptError(RuntimeError):
    pass


class _HumanTakeover(RuntimeError):
    pass


class _ResolverZone(SimpleNamespace):
    pass


class _ResolverZones:
    def __init__(self, values):
        self.values = list(values)

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def select(self, **kwargs):
        return _ResolverZones(
            value
            for value in self.values
            if all(getattr(value, key) == expected for key, expected in kwargs.items())
        )


class _DropRecorder:
    def __init__(self, events):
        self.events = events
        self.count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def add(self, _image):
        self.count += 1
        self.events.append("drop_add")

    def clear(self):
        self.events.append("drop_clear")


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


def _function(path: Path, name: str) -> ast.FunctionDef:
    for node in _tree(path).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function {name} in {path.name}")


def _class(path: Path, name: str) -> ast.ClassDef:
    for node in _tree(path).body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"missing class {name} in {path.name}")


def _assignment(path: Path, name: str, globals_: dict[str, Any]):
    for node in _tree(path).body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
        ):
            expression = ast.fix_missing_locations(ast.Expression(node.value))
            return eval(compile(expression, str(path), "eval"), dict(globals_))
    raise AssertionError(f"missing assignment {name} in {path.name}")


def _zone_fixtures(map_data_path: Path) -> _ResolverZones:
    for node in _tree(map_data_path).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "DIC_OS_MAP" for target in node.targets)
        ):
            document = ast.literal_eval(node.value)
            return _ResolverZones(
                _ResolverZone(
                    zone_id=zone_id,
                    is_port=zone_id in (0, 1, 2, 3, 4, 5, 6, 7, 154),
                    **data,
                )
                for zone_id, data in document.items()
            )
    raise AssertionError("missing DIC_OS_MAP in map_data.py")


def _compile(node: ast.FunctionDef, globals_: dict[str, Any]):
    namespace = dict(globals_)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, "<alas-opsi-task-config-replay>", "exec"), namespace)
    return namespace[node.name]


def _compile_class(node: ast.ClassDef, globals_: dict[str, Any]):
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
    general = document.get("OpsiGeneral", {}).get("OpsiGeneral")
    expected_general = {
        "UseLogger": ("checkbox", True, None),
        "BuyActionPointLimit": ("select", 0, list(range(6))),
        "OilLimit": ("input", 1000, None),
        "RepairThreshold": ("input", 0.4, None),
        "DoRandomMapEvent": ("checkbox", True, None),
        "AkashiShopFilter": ("textarea", "ActionPoint > PurpleCoins", None),
    }
    if not isinstance(general, dict) or set(general) != set(expected_general):
        raise AssertionError("OpsiGeneral field surface drifted")
    for field, (type_, default, options) in expected_general.items():
        declaration = general[field]
        if declaration.get("type") != type_ or declaration.get("value") != default:
            raise AssertionError(f"OpsiGeneral.{field} declaration drifted")
        if options is not None and declaration.get("option") != options:
            raise AssertionError(f"OpsiGeneral.{field} options drifted")
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
        meowfficer_target_zone: object = 0,
        opsi_buy_limit: object = 0,
        opsi_oil_limit: object = 1000,
        opsi_repair_threshold: object = 0.4,
        opsi_do_random_map_event: object = True,
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
            OpsiMeowfficerFarming_TargetZone=meowfficer_target_zone,
            OpsiGeneral_UseLogger=False,
            OpsiGeneral_BuyActionPointLimit=opsi_buy_limit,
            OpsiGeneral_OilLimit=opsi_oil_limit,
            OpsiGeneral_RepairThreshold=opsi_repair_threshold,
            OpsiGeneral_DoRandomMapEvent=opsi_do_random_map_event,
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
    method,
    resolver_method,
    zone_fixtures,
    *,
    hazard_level: object,
    action_point_preserve: object = 1000,
    target_zone: object = 0,
) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
        meowfficer_action_point_preserve=action_point_preserve,
        meowfficer_hazard_level=hazard_level,
        meowfficer_target_zone=target_zone,
    )
    events = config.events
    host = SimpleNamespace(
        config=config,
        device=SimpleNamespace(semantic_adapter=None),
        is_cl1_enabled=False,
        _ash_fully_collected=True,
        zone=SimpleNamespace(zone_id=1, location=(0, 0)),
        zones=zone_fixtures,
    )
    host.name_to_zone = MethodType(resolver_method, host)
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
    takeover = False
    try:
        MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
    except _Switch:
        switched = True
    except _HumanTakeover:
        takeover = True
    return {
        "rejected": rejected,
        "switched": switched,
        "takeover": takeover,
        "effective_preserve": getattr(config, "OS_ACTION_POINT_PRESERVE", None),
        "events": events,
    }


def _verify_meowfficer(method, resolver_method, zone_fixtures) -> dict[str, Any]:
    cases = {
        str(level): _meowfficer_case(
            method,
            resolver_method,
            zone_fixtures,
            hazard_level=level,
        )
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
            resolver_method,
            zone_fixtures,
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
    target_inputs = (
        ("int:51", 51),
        ("str:51", "51"),
        ("cn", "东南洋脊A"),
        ("en", "Southeast Ocean Ridge A"),
        ("jp", "南東海嶺A"),
        ("tw", "東南洋脊A"),
    )
    target_cases = {
        label: _meowfficer_case(
            method,
            resolver_method,
            zone_fixtures,
            hazard_level=5,
            target_zone=target,
        )
        for label, target in target_inputs
    }
    for case in target_cases.values():
        if case["rejected"] or case["takeover"] or not case["switched"]:
            raise AssertionError("meowfficer target-zone task boundary drifted")
        globe = [event for event in case["events"] if event[0] == "globe_goto"]
        if globe != [["globe_goto", 51, {"refresh": True}]]:
            raise AssertionError("meowfficer multilingual target resolution drifted")
        if any(event[0] == "zone_select" for event in case["events"]):
            raise AssertionError("explicit meowfficer target used hazard selection")
    invalid = _meowfficer_case(
        method,
        resolver_method,
        zone_fixtures,
        hazard_level=7,
    )
    if invalid != {
        "rejected": True,
        "switched": False,
        "takeover": False,
        "effective_preserve": None,
        "events": [],
    }:
        raise AssertionError("invalid meowfficer hazard level touched task state")
    invalid_preserve = _meowfficer_case(
        method,
        resolver_method,
        zone_fixtures,
        hazard_level=5,
        action_point_preserve=-1,
    )
    if invalid_preserve != {
        "rejected": True,
        "switched": False,
        "takeover": False,
        "effective_preserve": None,
        "events": [],
    }:
        raise AssertionError("invalid meowfficer AP preserve touched task state")
    invalid_target_type = _meowfficer_case(
        method,
        resolver_method,
        zone_fixtures,
        hazard_level=5,
        target_zone=None,
    )
    if invalid_target_type != {
        "rejected": True,
        "switched": False,
        "takeover": False,
        "effective_preserve": None,
        "events": [],
    }:
        raise AssertionError("invalid meowfficer target type touched task state")
    unknown_target = _meowfficer_case(
        method,
        resolver_method,
        zone_fixtures,
        hazard_level=5,
        target_zone="missing zone",
    )
    if unknown_target != {
        "rejected": False,
        "switched": False,
        "takeover": True,
        "effective_preserve": None,
        "events": [],
    }:
        raise AssertionError("unknown meowfficer target touched task state")
    return {
        "cases": cases,
        "preserve_cases": preserve_cases,
        "target_cases": target_cases,
        "invalid_entry": invalid,
        "invalid_preserve_entry": invalid_preserve,
        "invalid_target_type": invalid_target_type,
        "unknown_target": unknown_target,
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


def _explore_case(
    method,
    resolver_method,
    zone_fixtures,
    *,
    special_radar: object,
    last_zone: object = 0,
    order: str = "22",
) -> dict[str, Any]:
    config = _Config(mode="normal", check=False, special_radar=special_radar)
    config.OpsiExplore_LastZone = last_zone
    config.OS_EXPLORE_FILTER = order
    events = config.events
    host = SimpleNamespace(
        config=config,
        _solved_map_event=set(),
        _os_explore_failed_zone=[],
    )
    resolver_host = SimpleNamespace(zones=zone_fixtures)
    resolver = MethodType(resolver_method, resolver_host)
    host.name_to_zone = lambda zone: (
        events.append(["name_to_zone", zone]) or resolver(zone)
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
    stopped = False
    try:
        MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
    except _Switch:
        switched = True
    except _TaskStop:
        stopped = True
    return {
        "rejected": rejected,
        "switched": switched,
        "stopped": stopped,
        "events": events,
    }


def _verify_explore(method, resolver_method, zone_fixtures) -> dict[str, Any]:
    cases = {
        str(value).lower(): _explore_case(
            method,
            resolver_method,
            zone_fixtures,
            special_radar=value,
        )
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
    invalid = _explore_case(
        method,
        resolver_method,
        zone_fixtures,
        special_radar=None,
    )
    if invalid != {
        "rejected": True,
        "switched": False,
        "stopped": False,
        "events": [],
    }:
        raise AssertionError("invalid OpsiExplore.SpecialRadar touched task state")
    resume = _explore_case(
        method,
        resolver_method,
        zone_fixtures,
        special_radar=False,
        last_zone=22,
        order="22 > 51",
    )
    resumed_globe = [
        event for event in resume["events"] if event[0] == "globe_goto"
    ]
    if resume["rejected"] or not resume["switched"] or resumed_globe[:1] != [
        ["globe_goto", 51, {"stop_if_safe": True}]
    ]:
        raise AssertionError("OpsiExplore.LastZone resume boundary drifted")
    named_resume = _explore_case(
        method,
        resolver_method,
        zone_fixtures,
        special_radar=False,
        last_zone="NA Ocean SW Sector B",
        order="22 > 51",
    )
    named_globe = [
        event for event in named_resume["events"] if event[0] == "globe_goto"
    ]
    if (
        named_resume["rejected"]
        or not named_resume["switched"]
        or named_globe[:1] != [["globe_goto", 51, {"stop_if_safe": True}]]
    ):
        raise AssertionError("named OpsiExplore.LastZone resolution drifted")
    invalid_last_zone = {
        repr(value): _explore_case(
            method,
            resolver_method,
            zone_fixtures,
            special_radar=False,
            last_zone=value,
            order="22 > 51",
        )
        for value in (None, True, "missing zone", 44)
    }
    if any(
        not case["rejected"]
        or case["switched"]
        or case["stopped"]
        or any(event[0] == "globe_goto" for event in case["events"])
        for case in invalid_last_zone.values()
    ):
        raise AssertionError("invalid OpsiExplore.LastZone reached map state")
    return {
        "cases": cases,
        "invalid_entry": invalid,
        "last_zone_resume": resume,
        "last_zone_named_resume": named_resume,
        "invalid_last_zone": invalid_last_zone,
    }


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


def _storage_case(method, *, use_logger: object) -> dict[str, Any]:
    events: list[Any] = []
    host = SimpleNamespace()
    host.storage_enter = lambda: events.append("storage_enter")
    host.storage_logger_use_all = lambda: events.append("storage_logger_use_all")
    host.storage_checkout_item = lambda item: events.append(
        ["storage_checkout_item", item]
    ) or True
    rejected = False
    try:
        result = MethodType(method, host)("OBSCURE", use_logger=use_logger)
    except SemanticGateClosed:
        rejected = True
        result = None
    return {"rejected": rejected, "result": result, "events": events}


def _verify_storage(method) -> dict[str, Any]:
    cases = {
        str(value).lower(): _storage_case(method, use_logger=value)
        for value in (False, True)
    }
    if cases["false"] != {
        "rejected": False,
        "result": True,
        "events": ["storage_enter", ["storage_checkout_item", "OBSCURE"]],
    }:
        raise AssertionError("disabled OpsiGeneral.UseLogger branch drifted")
    if cases["true"] != {
        "rejected": False,
        "result": True,
        "events": [
            "storage_enter",
            "storage_logger_use_all",
            ["storage_checkout_item", "OBSCURE"],
        ],
    }:
        raise AssertionError("enabled OpsiGeneral.UseLogger branch drifted")
    invalid = _storage_case(method, use_logger=None)
    if invalid != {"rejected": True, "result": None, "events": []}:
        raise AssertionError("invalid OpsiGeneral.UseLogger touched storage state")
    return {"cases": cases, "invalid_entry": invalid}


def _purchase_case(
    method,
    *,
    buy_limit: object,
    oil_limit: object,
    current: int = 5,
    oil: int = 100_000,
) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
        opsi_buy_limit=buy_limit,
        opsi_oil_limit=oil_limit,
    )
    events = config.events
    host = SimpleNamespace(config=config, _action_point_box=[oil, 0, 0, 0])
    host.action_point_set_button = lambda index: events.append(
        ["action_point_set_button", index]
    )
    host.action_point_get_buy_remain = lambda: events.append(
        "action_point_get_buy_remain"
    ) or current
    host.action_point_use = lambda: events.append("action_point_use")
    rejected = False
    try:
        result = MethodType(method, host)(preserve=oil_limit)
    except SemanticGateClosed:
        rejected = True
        result = None
    return {"rejected": rejected, "result": result, "events": events}


def _verify_purchase(method) -> dict[str, Any]:
    limit_cases = {}
    for buy_limit in range(6):
        reached = _purchase_case(
            method,
            buy_limit=buy_limit,
            oil_limit=1000,
            current=5 - buy_limit,
        )
        if reached["rejected"] or reached["result"] is not False:
            raise AssertionError("OpsiGeneral buy-limit boundary drifted")
        if "action_point_use" in reached["events"]:
            raise AssertionError("reached OpsiGeneral buy limit purchased AP")
        limit_cases[f"reached:{buy_limit}"] = reached
        if buy_limit:
            allowed = _purchase_case(
                method,
                buy_limit=buy_limit,
                oil_limit=1000,
                current=6 - buy_limit,
            )
            if allowed["rejected"] or allowed["result"] is not True:
                raise AssertionError("allowed OpsiGeneral AP purchase drifted")
            if allowed["events"][-1] != "action_point_use":
                raise AssertionError("allowed OpsiGeneral AP purchase skipped input boundary")
            limit_cases[f"allowed:{buy_limit}"] = allowed
    oil_cases = {
        "exact": _purchase_case(
            method,
            buy_limit=1,
            oil_limit=1000,
            current=5,
            oil=2000,
        ),
        "below": _purchase_case(
            method,
            buy_limit=1,
            oil_limit=1000,
            current=5,
            oil=1999,
        ),
    }
    if oil_cases["exact"]["result"] is not True:
        raise AssertionError("exact OpsiGeneral oil preserve boundary drifted")
    if oil_cases["below"]["result"] is not False:
        raise AssertionError("below OpsiGeneral oil preserve boundary purchased AP")
    invalid_limit = _purchase_case(
        method,
        buy_limit=6,
        oil_limit=1000,
    )
    invalid_oil = _purchase_case(
        method,
        buy_limit=1,
        oil_limit=-1,
    )
    for invalid in (invalid_limit, invalid_oil):
        if invalid != {"rejected": True, "result": None, "events": []}:
            raise AssertionError("invalid OpsiGeneral purchase config touched input state")
    return {
        "limit_cases": limit_cases,
        "oil_cases": oil_cases,
        "invalid_limit": invalid_limit,
        "invalid_oil": invalid_oil,
    }


def _repair_case(method, *, threshold: object, hp: float = 0.4) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
        opsi_repair_threshold=threshold,
    )
    events = config.events
    host = SimpleNamespace(
        config=config,
        hp=[hp],
        hp_has_ship=[True],
    )
    host.is_in_special_zone = lambda: events.append("special_zone") or False
    host.hp_get = lambda: events.append("hp_get")
    host.fleet_repair = lambda **kwargs: events.append(["fleet_repair", kwargs])
    host.hp_reset = lambda: events.append("hp_reset")
    rejected = False
    try:
        result = MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
        result = None
    return {"rejected": rejected, "result": result, "events": events}


def _verify_repair(method) -> dict[str, Any]:
    cases = {
        "disabled": _repair_case(method, threshold=-1),
        "zero": _repair_case(method, threshold=0, hp=0),
        "above": _repair_case(method, threshold=0.4, hp=0.41),
        "boundary": _repair_case(method, threshold=0.4, hp=0.4),
        "one": _repair_case(method, threshold=1, hp=1),
    }
    if cases["disabled"] != {"rejected": False, "result": False, "events": []}:
        raise AssertionError("disabled OpsiGeneral repair threshold drifted")
    if cases["above"]["result"] is not False or any(
        event[0] == "fleet_repair" for event in cases["above"]["events"]
    ):
        raise AssertionError("above-threshold OpsiGeneral repair branch drifted")
    for name in ("zero", "boundary", "one"):
        if cases[name]["result"] is not True or not any(
            event[0] == "fleet_repair" for event in cases[name]["events"]
        ):
            raise AssertionError("triggered OpsiGeneral repair branch drifted")
    invalid = _repair_case(method, threshold=1.1)
    if invalid != {"rejected": True, "result": None, "events": []}:
        raise AssertionError("invalid OpsiGeneral repair config touched map state")
    return {"cases": cases, "invalid_entry": invalid}


def _rescan_case(
    method, *, do_random_map_event: object, explicit_rescan=None
) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
        opsi_do_random_map_event=do_random_map_event,
    )
    config.task = SimpleNamespace(command="OpsiMeowfficerFarming")
    config.DropRecord_OpsiRecord = False
    events = config.events
    drop = _DropRecorder(events)
    host = SimpleNamespace(
        config=config,
        stat=SimpleNamespace(new=lambda **_kwargs: drop),
        device=SimpleNamespace(image="frame"),
    )
    host.handle_ash_beacon_attack = lambda: events.append("ash_beacon")
    host.os_auto_search_run = lambda _drop: events.append("auto_search") or 0
    host.hp_reset = lambda: events.append("hp_reset")
    host.hp_get = lambda: events.append("hp_get")
    host.map_rescan = lambda **kwargs: events.append(["map_rescan", kwargs])
    rejected = False
    try:
        result = MethodType(method, host)(
            question=False,
            rescan=explicit_rescan,
            after_auto_search=False,
        )
    except SemanticGateClosed:
        rejected = True
        result = None
    return {"rejected": rejected, "result": result, "events": events}


def _verify_rescan(method) -> dict[str, Any]:
    cases = {
        str(value).lower(): _rescan_case(
            method,
            do_random_map_event=value,
        )
        for value in (False, True)
    }
    if any(event[0] == "map_rescan" for event in cases["false"]["events"]):
        raise AssertionError("disabled OpsiGeneral random event rescanned map")
    rescans = [
        event for event in cases["true"]["events"] if event[0] == "map_rescan"
    ]
    if len(rescans) != 1 or rescans[0][1].get("rescan_mode") != "full":
        raise AssertionError("enabled OpsiGeneral random event rescan drifted")
    invalid = _rescan_case(method, do_random_map_event=None)
    if invalid != {"rejected": True, "result": None, "events": []}:
        raise AssertionError("invalid OpsiGeneral random event touched task state")
    explicit = _rescan_case(
        method,
        do_random_map_event=None,
        explicit_rescan="current",
    )
    explicit_rescans = [
        event for event in explicit["events"] if event[0] == "map_rescan"
    ]
    if (
        explicit["rejected"]
        or len(explicit_rescans) != 1
        or explicit_rescans[0][1].get("rescan_mode") != "current"
    ):
        raise AssertionError("explicit Operation Siren rescan API drifted")
    for case in (*cases.values(), explicit):
        for event in case["events"]:
            if isinstance(event, list) and event[0] == "map_rescan":
                event[1]["drop"] = "drop-recorder"
    return {"cases": cases, "invalid_entry": invalid, "explicit_rescan": explicit}


def _akashi_items():
    return [
        SimpleNamespace(
            name="ActionPoint",
            cost="YellowCoins",
            price=50,
            count=1,
            total_count=1,
        ),
        SimpleNamespace(
            name="PurpleCoins",
            cost="PurpleCoins",
            price=100,
            count=1,
            total_count=1,
        ),
        SimpleNamespace(
            name="LoggerAbyssalT6",
            cost="YellowCoins",
            price=500,
            count=1,
            total_count=1,
        ),
        SimpleNamespace(
            name="UnknownItem",
            cost="YellowCoins",
            price=1,
            count=1,
            total_count=1,
        ),
    ]


def _akashi_case(
    method,
    pretreatment,
    enough_coins,
    check_cl1,
    *,
    parser: object,
    yellow_coins: int = 100,
    purple_coins: int = 100,
    cl1_enabled: bool = False,
) -> dict[str, Any]:
    events: list[str] = []
    host = SimpleNamespace(
        config=SimpleNamespace(OpsiGeneral_AkashiShopFilter=parser),
        _shop_yellow_coins=yellow_coins,
        _shop_purple_coins=purple_coins,
        is_cl1_enabled=cl1_enabled,
    )
    bound_pretreatment = MethodType(pretreatment, host)
    host.pretreatment = lambda items: (
        events.append("pretreatment") or bound_pretreatment(items)
    )
    host.enough_coins_in_akashi = MethodType(enough_coins, host)
    host.check_cl1_purple_coins = MethodType(check_cl1, host)
    rejected = False
    try:
        result = MethodType(method, host)(_akashi_items())
    except SemanticGateClosed:
        rejected = True
        result = []
    return {
        "rejected": rejected,
        "items": [item.name for item in result],
        "events": events,
    }


def _verify_akashi_filter(
    method,
    pretreatment,
    enough_coins,
    check_cl1,
) -> dict[str, Any]:
    cases = {
        "default": _akashi_case(
            method,
            pretreatment,
            enough_coins,
            check_cl1,
            parser="ActionPoint > PurpleCoins",
        ),
        "fallback": _akashi_case(
            method,
            pretreatment,
            enough_coins,
            check_cl1,
            parser="  \n ",
        ),
        "unicode_separator": _akashi_case(
            method,
            pretreatment,
            enough_coins,
            check_cl1,
            parser="ActionPoint ＞ PurpleCoins",
        ),
        "cl1": _akashi_case(
            method,
            pretreatment,
            enough_coins,
            check_cl1,
            parser="ActionPoint > PurpleCoins",
            cl1_enabled=True,
        ),
        "insufficient": _akashi_case(
            method,
            pretreatment,
            enough_coins,
            check_cl1,
            parser="ActionPoint > PurpleCoins",
            yellow_coins=49,
            purple_coins=99,
        ),
        "tiered": _akashi_case(
            method,
            pretreatment,
            enough_coins,
            check_cl1,
            parser="LoggerAbyssalT6",
            yellow_coins=500,
        ),
    }
    expected = {
        "default": ["ActionPoint", "PurpleCoins"],
        "fallback": ["ActionPoint", "PurpleCoins"],
        "unicode_separator": ["ActionPoint", "PurpleCoins"],
        "cl1": ["ActionPoint"],
        "insufficient": [],
        "tiered": ["LoggerAbyssalT6"],
    }
    for name, item_names in expected.items():
        case = cases[name]
        if case["rejected"] or case["items"] != item_names:
            raise AssertionError(f"Akashi filter case drifted: {name}")
    invalid = {
        repr(value): _akashi_case(
            method,
            pretreatment,
            enough_coins,
            check_cl1,
            parser=value,
        )
        for value in ("ActionPoint > invalid", "ActionPoint >", None, True, 1, [], {})
    }
    if any(
        not case["rejected"] or case["events"]
        for case in invalid.values()
    ):
        raise AssertionError("invalid Akashi filter touched shop item state")
    return {"cases": cases, "invalid_entries": invalid}


def _opsi_shop_filter_case(
    method,
    pretreatment,
    check_cl1,
    check_count,
    *,
    preset: object,
    custom_filter: object = "ActionPoint > PurpleCoins",
    cl1_enabled: bool = False,
    logger_count: int = 1,
) -> dict[str, Any]:
    events: list[str] = []
    items = _akashi_items()
    items[2].count = logger_count
    host = SimpleNamespace(
        config=SimpleNamespace(
            OpsiShop_PresetFilter=preset,
            OpsiShop_CustomFilter=custom_filter,
        ),
        is_cl1_enabled=cl1_enabled,
    )
    bound_pretreatment = MethodType(pretreatment, host)
    host.pretreatment = lambda values: (
        events.append("pretreatment") or bound_pretreatment(values)
    )
    host.check_cl1_purple_coins = MethodType(check_cl1, host)
    host.check_item_count = MethodType(check_count, host)
    rejected = False
    try:
        result = MethodType(method, host)(items)
    except SemanticGateClosed:
        rejected = True
        result = []
    return {
        "rejected": rejected,
        "items": [item.name for item in result],
        "events": events,
    }


def _verify_opsi_shop_filter(
    method,
    pretreatment,
    check_cl1,
    check_count,
) -> dict[str, Any]:
    presets = {
        preset: _opsi_shop_filter_case(
            method,
            pretreatment,
            check_cl1,
            check_count,
            preset=preset,
        )
        for preset in ("max_benefit", "max_benefit_meta", "no_meta", "all")
    }
    for preset, case in presets.items():
        if case["rejected"] or case["items"] != [
            "LoggerAbyssalT6",
            "ActionPoint",
            "PurpleCoins",
        ]:
            raise AssertionError(f"OpsiShop preset drifted: {preset}")
    custom = _opsi_shop_filter_case(
        method,
        pretreatment,
        check_cl1,
        check_count,
        preset="custom",
        custom_filter="PurpleCoins > ActionPoint",
    )
    if custom["rejected"] or custom["items"] != ["PurpleCoins", "ActionPoint"]:
        raise AssertionError("OpsiShop custom priority drifted")
    fallback = _opsi_shop_filter_case(
        method,
        pretreatment,
        check_cl1,
        check_count,
        preset="custom",
        custom_filter=" \n ",
    )
    if fallback["rejected"] or fallback["items"] != [
        "LoggerAbyssalT6",
        "ActionPoint",
        "PurpleCoins",
    ]:
        raise AssertionError("OpsiShop custom fallback drifted")
    cl1 = _opsi_shop_filter_case(
        method,
        pretreatment,
        check_cl1,
        check_count,
        preset="custom",
        custom_filter="PurpleCoins > ActionPoint",
        cl1_enabled=True,
    )
    if cl1["rejected"] or cl1["items"] != ["ActionPoint"]:
        raise AssertionError("OpsiShop CL1 exclusion drifted")
    exhausted = _opsi_shop_filter_case(
        method,
        pretreatment,
        check_cl1,
        check_count,
        preset="max_benefit_meta",
        logger_count=0,
    )
    if exhausted["rejected"] or exhausted["items"] != [
        "ActionPoint",
        "PurpleCoins",
    ]:
        raise AssertionError("OpsiShop item-count exclusion drifted")
    invalid_values = (
        ("unknown", "ActionPoint"),
        (None, "ActionPoint"),
        ("custom", None),
        ("custom", "ActionPoint > invalid"),
        ("custom", "ActionPoint >"),
    )
    invalid = {
        f"{preset!r}:{custom_filter!r}": _opsi_shop_filter_case(
            method,
            pretreatment,
            check_cl1,
            check_count,
            preset=preset,
            custom_filter=custom_filter,
        )
        for preset, custom_filter in invalid_values
    }
    if any(
        not case["rejected"] or case["events"]
        for case in invalid.values()
    ):
        raise AssertionError("invalid OpsiShop filter touched shop item state")
    return {
        "presets": presets,
        "custom": custom,
        "fallback": fallback,
        "cl1": cl1,
        "exhausted": exhausted,
        "invalid_entries": invalid,
    }


def _voucher_filter_case(method, value: object) -> dict[str, Any]:
    host = SimpleNamespace(config=SimpleNamespace(OpsiVoucher_Filter=value))
    rejected = False
    try:
        result = MethodType(method, host)()
    except SemanticGateClosed:
        rejected = True
        result = None
    return {"rejected": rejected, "result": result, "events": []}


def _verify_voucher_filter(method) -> dict[str, Any]:
    cases = {
        "default": _voucher_filter_case(
            method,
            "LoggerAbyssal > LoggerObscure > Book > Coin > Fragment",
        ),
        "logger": _voucher_filter_case(method, "Logger > Coin"),
        "logger_t6": _voucher_filter_case(method, "LoggerT6 > Coin"),
        "archive_removed": _voucher_filter_case(method, "LoggerArchive"),
        "unicode_separator": _voucher_filter_case(method, "Coin ＞ Fragment"),
        "empty_skip": _voucher_filter_case(method, " \n "),
    }
    expected = {
        "default": "LoggerAbyssal > LoggerObscure > Book > Coin > Fragment",
        "logger": "LoggerAbyssal > LoggerObscure > Coin",
        "logger_t6": "LoggerAbyssalT6 > LoggerObscureT6 > Coin",
        "archive_removed": "",
        "unicode_separator": "Coin ＞ Fragment",
        "empty_skip": "",
    }
    for name, result in expected.items():
        case = cases[name]
        if case["rejected"] or case["result"] != result:
            raise AssertionError(f"OpsiVoucher filter redirect drifted: {name}")
    invalid = {
        repr(value): _voucher_filter_case(method, value)
        for value in ("Coin > unknown", "Coin >", None, True, 1, [], {})
    }
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid OpsiVoucher filter reached shop state")
    return {"cases": cases, "invalid_entries": invalid}


def _verify_contract(
    akashi_filter,
    opsi_shop_presets,
    voucher_filter,
    explore_resolver,
) -> tuple[int, int]:
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
            target_zone=0,
        )
        accepted += 1
    for use_logger in (False, True):
        validate_alas_opsi_storage_config(use_logger=use_logger)
        accepted += 1
    for buy_limit, oil_limit in product(range(6), (0, 1000, 50_000)):
        validate_alas_opsi_action_point_purchase(
            buy_limit=buy_limit,
            oil_limit=oil_limit,
        )
        accepted += 1
    for threshold in (-1, 0, 0.4, 1):
        validate_alas_opsi_repair_config(threshold=threshold)
        accepted += 1
    for do_random_map_event in (False, True):
        validate_alas_opsi_rescan_config(
            do_random_map_event=do_random_map_event,
        )
        accepted += 1
    for parser in (
        "ActionPoint",
        "ActionPoint > PurpleCoins",
        "ActionPoint ＞ PurpleCoins",
        "LoggerAbyssalT6",
        "RepairPack",
    ):
        validate_alas_opsi_akashi_filter(akashi_filter, parser)
        accepted += 1
    for preset in ("max_benefit", "max_benefit_meta", "no_meta", "all", "custom"):
        validate_alas_opsi_shop_preset(opsi_shop_presets, preset)
        accepted += 1
    for custom_filter in ("", "ActionPoint > PurpleCoins"):
        validate_alas_opsi_shop_custom_filter(custom_filter)
        accepted += 1
    for parser in ("ActionPoint", "LoggerAbyssalT6"):
        validate_alas_opsi_shop_filter(akashi_filter, parser)
        accepted += 1
    for parser in (
        "",
        "Coin",
        "Coin > Fragment",
        "LoggerAbyssal > LoggerObscure",
        "Coin ＞ Fragment",
    ):
        validate_alas_opsi_voucher_filter(voucher_filter, parser)
        accepted += 1
    explore_order = (22, 51)
    for value in (0, 22, "22", "Southeast Ocean Ridge A"):
        validate_alas_opsi_explore_last_zone(
            value=value,
            order=explore_order,
            resolver=explore_resolver,
        )
        accepted += 1
    for action_point_preserve in (0, 1000, 2500):
        validate_alas_opsi_meowfficer_config(
            action_point_preserve=action_point_preserve,
            hazard_level=5,
            target_zone=0,
        )
        accepted += 1
    for target_zone in (
        0,
        51,
        "51",
        "东南洋脊A",
        "Southeast Ocean Ridge A",
        "南東海嶺A",
        "東南洋脊A",
    ):
        validate_alas_opsi_meowfficer_config(
            action_point_preserve=1000,
            hazard_level=5,
            target_zone=target_zone,
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
                target_zone=0,
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
                target_zone=0,
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError(
                "invalid OpsiMeowfficerFarming.ActionPointPreserve was admitted"
            )
    for value in (-1, "", "   ", None, True, False, 51.0, [], {}):
        try:
            validate_alas_opsi_meowfficer_config(
                action_point_preserve=1000,
                hazard_level=5,
                target_zone=value,
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError(
                "invalid OpsiMeowfficerFarming.TargetZone was admitted"
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
    for value in INVALID_BOOLEANS:
        try:
            validate_alas_opsi_storage_config(use_logger=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiGeneral.UseLogger was admitted")
    for value in (-1, 6, None, True, False, "1", 1.0, [], {}):
        try:
            validate_alas_opsi_action_point_purchase(
                buy_limit=value,
                oil_limit=1000,
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiGeneral.BuyActionPointLimit was admitted")
    for value in (-1, None, True, False, "1000", 1000.0, [], {}):
        try:
            validate_alas_opsi_action_point_purchase(
                buy_limit=0,
                oil_limit=value,
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiGeneral.OilLimit was admitted")
    for value in (1.1, float("nan"), float("inf"), float("-inf"), None, True, False, "0.4", [], {}):
        try:
            validate_alas_opsi_repair_config(threshold=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiGeneral.RepairThreshold was admitted")
    for value in INVALID_BOOLEANS:
        try:
            validate_alas_opsi_rescan_config(do_random_map_event=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiGeneral.DoRandomMapEvent was admitted")
    for value in ("ActionPoint > invalid", "ActionPoint >", None, True, 1, [], {}):
        try:
            validate_alas_opsi_akashi_filter(akashi_filter, value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiGeneral.AkashiShopFilter was admitted")
    for value in ("", "unknown", None, 0, True, [], {}):
        try:
            validate_alas_opsi_shop_preset(opsi_shop_presets, value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiShop.PresetFilter was admitted")
    for value in (None, 0, True, [], {}):
        try:
            validate_alas_opsi_shop_custom_filter(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiShop.CustomFilter type was admitted")
    for value in ("ActionPoint >", "unknown"):
        try:
            validate_alas_opsi_shop_filter(akashi_filter, value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiShop.CustomFilter token was admitted")
    for value in ("Coin > unknown", "Coin >", None, True, 1, [], {}):
        try:
            validate_alas_opsi_voucher_filter(voucher_filter, value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiVoucher.Filter was admitted")
    for value in (None, True, "", "missing zone", 44):
        try:
            validate_alas_opsi_explore_last_zone(
                value=value,
                order=explore_order,
                resolver=explore_resolver,
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiExplore.LastZone was admitted")
    return accepted, invalid


def verify_opsi_task_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    args_path = alas_root / "module/config/argument/args.json"
    config_path = alas_root / "module/config/config.py"
    fleet_path = alas_root / "module/os/fleet.py"
    globe_zone_path = alas_root / "module/os/globe_zone.py"
    map_data_path = alas_root / "module/os/map_data.py"
    os_map_path = alas_root / "module/os/map.py"
    selector_path = alas_root / "module/os_shop/selector.py"
    os_shop_preset_path = alas_root / "module/os_shop/preset.py"
    filter_path = alas_root / "module/base/filter.py"
    shop_base_path = alas_root / "module/shop/base.py"
    shop_voucher_path = alas_root / "module/shop/shop_voucher.py"
    shop_filter_redirect_path = (
        alas_root / "module/config/redirect_utils/shop_filter.py"
    )
    action_point_path = alas_root / "module/os_handler/action_point.py"
    storage_path = alas_root / "module/os_handler/storage.py"
    explore_path = alas_root / "module/os/tasks/explore.py"
    order_path = alas_root / "module/os_handler/map_order.py"
    month_path = alas_root / "module/os/tasks/month_boss.py"
    abyssal_path = alas_root / "module/os/tasks/abyssal.py"
    obscure_path = alas_root / "module/os/tasks/obscure.py"
    daily_path = alas_root / "module/os/tasks/daily.py"
    hazard_path = alas_root / "module/os/tasks/hazard_leveling.py"
    meowfficer_path = alas_root / "module/os/tasks/meowfficer_farming.py"
    _verify_args(args_path)
    explore_consumers = _consumer_methods(
        explore_path,
        "OpsiExplore",
        ("OpsiExplore_SpecialRadar", "OpsiExplore_LastZone"),
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
            "OpsiMeowfficerFarming_TargetZone",
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
    consumers["OpsiGeneral_UseLogger"] = [
        *_consumer_methods(
            obscure_path,
            "OpsiObscure",
            ("OpsiGeneral_UseLogger",),
        )["OpsiGeneral_UseLogger"],
        *_consumer_methods(
            abyssal_path,
            "OpsiAbyssal",
            ("OpsiGeneral_UseLogger",),
        )["OpsiGeneral_UseLogger"],
    ]
    consumers.update(
        _consumer_methods(
            action_point_path,
            "ActionPointHandler",
            (
                "OpsiGeneral_BuyActionPointLimit",
                "OpsiGeneral_OilLimit",
            ),
        )
    )
    consumers.update(
        _consumer_methods(
            shop_voucher_path,
            "VoucherShop",
            ("OpsiVoucher_Filter",),
        )
    )
    consumers.update(
        _consumer_methods(
            selector_path,
            "Selector",
            ("OpsiGeneral_AkashiShopFilter",),
        )
    )
    consumers.update(
        _consumer_methods(
            selector_path,
            "Selector",
            ("OpsiShop_PresetFilter", "OpsiShop_CustomFilter"),
        )
    )
    consumers.update(
        _consumer_methods(
            os_map_path,
            "OSMap",
            (
                "OpsiGeneral_RepairThreshold",
                "OpsiGeneral_DoRandomMapEvent",
            ),
        )
    )
    for field, methods in _dynamic_delay_consumers(config_path).items():
        consumers.setdefault(field, []).extend(methods)
    expected = {
        "OpsiExplore_SpecialRadar": [
            "_os_explore",
            "AzurLaneConfig.opsi_task_delay",
        ],
        "OpsiExplore_LastZone": ["_os_explore"],
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
        "OpsiMeowfficerFarming_TargetZone": ["os_meowfficer_farming"],
        "OpsiGeneral_UseLogger": ["clear_obscure", "clear_abyssal"],
        "OpsiGeneral_BuyActionPointLimit": [
            "action_point_buy",
            "handle_action_point",
        ],
        "OpsiGeneral_OilLimit": ["handle_action_point"],
        "OpsiGeneral_RepairThreshold": ["handle_fleet_repair"],
        "OpsiGeneral_DoRandomMapEvent": ["run_auto_search"],
        "OpsiGeneral_AkashiShopFilter": ["items_filter_in_akashi_shop"],
        "OpsiShop_PresetFilter": ["items_filter_in_os_shop"],
        "OpsiShop_CustomFilter": ["items_filter_in_os_shop"],
        "OpsiVoucher_Filter": ["shop_filter"],
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
        "validate_alas_opsi_action_point_purchase": (
            validate_alas_opsi_action_point_purchase
        ),
        "validate_alas_opsi_akashi_filter": validate_alas_opsi_akashi_filter,
        "validate_alas_opsi_shop_custom_filter": (
            validate_alas_opsi_shop_custom_filter
        ),
        "validate_alas_opsi_shop_filter": validate_alas_opsi_shop_filter,
        "validate_alas_opsi_shop_preset": validate_alas_opsi_shop_preset,
        "validate_alas_opsi_voucher_filter": validate_alas_opsi_voucher_filter,
        "validate_alas_opsi_explore_last_zone": (
            validate_alas_opsi_explore_last_zone
        ),
        "validate_alas_opsi_hazard1_config": validate_alas_opsi_hazard1_config,
        "validate_alas_opsi_meowfficer_config": validate_alas_opsi_meowfficer_config,
        "validate_alas_opsi_repair_config": validate_alas_opsi_repair_config,
        "validate_alas_opsi_rescan_config": validate_alas_opsi_rescan_config,
        "validate_alas_opsi_storage_config": validate_alas_opsi_storage_config,
        "inflection": SimpleNamespace(underscore=lambda value: value.lower()),
        "SelectedGrids": _TaskList,
        "get_os_reset_remain": lambda: 1,
        "datetime": datetime,
        "timedelta": timedelta,
        "DEFAULT_TIME": datetime(1970, 1, 1),
        "dict_to_kv": lambda values: str(values),
        "deep_get": _deep_get,
        "ORDER_SCAN": "scan",
        "ORDER_SUBMARINE": "submarine",
        "RequestHumanTakeover": _HumanTakeover,
        "ScriptError": _ScriptError,
        "Zone": _ResolverZone,
        "ACTION_POINTS_BUY": {1: 4000, 2: 2000, 3: 2000, 4: 1000, 5: 1000},
    }
    fleet_node = _method(fleet_path, "OSFleet", "fleet_set")
    resolver_node = _method(globe_zone_path, "ZoneManager", "name_to_zone")
    storage_node = _method(storage_path, "StorageHandler", "storage_get_next_item")
    purchase_node = _method(action_point_path, "ActionPointHandler", "action_point_buy")
    repair_node = _method(os_map_path, "OSMap", "handle_fleet_repair")
    rescan_node = _method(os_map_path, "OSMap", "run_auto_search")
    akashi_node = _method(
        selector_path,
        "Selector",
        "items_filter_in_akashi_shop",
    )
    akashi_pretreatment_node = _method(
        selector_path,
        "Selector",
        "pretreatment",
    )
    akashi_coins_node = _method(
        selector_path,
        "Selector",
        "enough_coins_in_akashi",
    )
    akashi_cl1_node = _method(
        selector_path,
        "Selector",
        "check_cl1_purple_coins",
    )
    opsi_shop_node = _method(
        selector_path,
        "Selector",
        "items_filter_in_os_shop",
    )
    opsi_shop_count_node = _method(
        selector_path,
        "Selector",
        "check_item_count",
    )
    voucher_filter_node = _method(
        shop_voucher_path,
        "VoucherShop",
        "shop_filter",
    )
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
    explore_last_zone_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_explore_last_zone"
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
    storage_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_storage_config"
        for node in ast.walk(storage_node)
    )
    purchase_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_action_point_purchase"
        for node in ast.walk(purchase_node)
    )
    repair_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_repair_config"
        for node in ast.walk(repair_node)
    )
    rescan_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_rescan_config"
        for node in ast.walk(rescan_node)
    )
    akashi_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_akashi_filter"
        for node in ast.walk(akashi_node)
    )
    opsi_shop_guards = {
        name: any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
            for node in ast.walk(opsi_shop_node)
        )
        for name in (
            "validate_alas_opsi_shop_custom_filter",
            "validate_alas_opsi_shop_filter",
            "validate_alas_opsi_shop_preset",
        )
    }
    voucher_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_opsi_voucher_filter"
        for node in ast.walk(voucher_filter_node)
    )
    filter_type = _compile_class(
        _class(filter_path, "Filter"),
        {"reduce": reduce, "re": re, "logger": _Logger()},
    )
    akashi_regex = _assignment(selector_path, "FILTER_REGEX", {"re": re})
    akashi_filter = filter_type(
        akashi_regex,
        ("group", "sub_genre", "tier"),
    )
    opsi_shop_presets = _assignment(
        os_shop_preset_path,
        "OS_SHOP",
        {},
    )
    voucher_regex = _assignment(shop_base_path, "FILTER_REGEX", {"re": re})
    voucher_filter = filter_type(
        voucher_regex,
        ("group", "sub_genre", "tier"),
    )
    voucher_redirect_regex = _assignment(
        shop_filter_redirect_path,
        "FILTER_REGEX_VOUCHER",
        {"re": re},
    )
    voucher_redirect = _compile(
        _function(shop_filter_redirect_path, "voucher_redirect"),
        {"re": re, "FILTER_REGEX_VOUCHER": voucher_redirect_regex},
    )
    akashi_globals = {
        **globals_,
        "FILTER": akashi_filter,
        "FILTER_REGEX": akashi_regex,
        "OS_SHOP": opsi_shop_presets,
        "GeneratedConfig": SimpleNamespace(
            OpsiGeneral_AkashiShopFilter="ActionPoint > PurpleCoins",
            OpsiShop_PresetFilter="max_benefit_meta",
        ),
        "re": re,
        "List": list,
        "Item": SimpleNamespace,
    }
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
    resolver_method = _compile(resolver_node, globals_)
    zone_fixtures = _zone_fixtures(map_data_path)
    meowfficer = _verify_meowfficer(
        _compile(meowfficer_node, globals_),
        resolver_method,
        zone_fixtures,
    )
    explore_globals = {**globals_, "ScriptError": _ScriptError}
    explore = _verify_explore(
        _compile(explore_node, explore_globals),
        resolver_method,
        zone_fixtures,
    )
    delay = _verify_delay(_compile(delay_task_node, globals_))
    fleet_selection = _verify_fleet_selection(_compile(fleet_node, globals_))
    order = _verify_order(_compile(order_node, globals_))
    storage = _verify_storage(_compile(storage_node, globals_))
    purchase = _verify_purchase(_compile(purchase_node, globals_))
    repair = _verify_repair(_compile(repair_node, globals_))
    rescan = _verify_rescan(_compile(rescan_node, globals_))
    akashi = _verify_akashi_filter(
        _compile(akashi_node, akashi_globals),
        _compile(akashi_pretreatment_node, akashi_globals),
        _compile(akashi_coins_node, akashi_globals),
        _compile(akashi_cl1_node, akashi_globals),
    )
    opsi_shop = _verify_opsi_shop_filter(
        _compile(opsi_shop_node, akashi_globals),
        _compile(akashi_pretreatment_node, akashi_globals),
        _compile(akashi_cl1_node, akashi_globals),
        _compile(opsi_shop_count_node, akashi_globals),
    )
    voucher = _verify_voucher_filter(
        _compile(
            voucher_filter_node,
            {
                **globals_,
                "cached_property": lambda function: function,
                "FILTER": voucher_filter,
                "voucher_redirect": voucher_redirect,
            },
        )
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
    accepted, invalid = _verify_contract(
        akashi_filter,
        opsi_shop_presets,
        voucher_filter,
        MethodType(resolver_method, SimpleNamespace(zones=zone_fixtures)),
    )
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 24,
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
            and explore_last_zone_guard
            and delay_task_guard
            and fleet_guard
            and order_guard
            and storage_guard
            and purchase_guard
            and repair_guard
            and rescan_guard
            and akashi_guard
            and all(opsi_shop_guards.values())
            and voucher_guard
        ),
        "validated_runtime_boundaries": {
            "OpsiFleet.Fleet": "OSFleet.fleet_set",
            "OpsiFleet.Submarine": "MapOrderHandler.os_order_execute",
            "OpsiMeowfficerFarming.ActionPointPreserve": (
                "OpsiMeowfficerFarming.os_meowfficer_farming"
            ),
            "OpsiMeowfficerFarming.TargetZone": (
                "ZoneManager.name_to_zone -> "
                "OpsiMeowfficerFarming.os_meowfficer_farming"
            ),
            "OpsiGeneral.UseLogger": "StorageHandler.storage_get_next_item",
            "OpsiGeneral.BuyActionPointLimit": (
                "ActionPointHandler.action_point_buy"
            ),
            "OpsiGeneral.OilLimit": "ActionPointHandler.action_point_buy",
            "OpsiGeneral.RepairThreshold": "OSMap.handle_fleet_repair",
            "OpsiGeneral.DoRandomMapEvent": "OSMap.run_auto_search",
            "OpsiGeneral.AkashiShopFilter": (
                "Selector.items_filter_in_akashi_shop"
            ),
            "OpsiShop.PresetFilter": "Selector.items_filter_in_os_shop",
            "OpsiShop.CustomFilter": "Selector.items_filter_in_os_shop",
            "OpsiVoucher.Filter": "VoucherShop.shop_filter",
            "OpsiExplore.LastZone": "OpsiExplore._os_explore",
        },
        "fleet_selection": fleet_selection,
        "order": order,
        "storage": storage,
        "action_point_purchase": purchase,
        "fleet_repair": repair,
        "random_map_event": rescan,
        "akashi_shop_filter": akashi,
        "opsi_shop_filter": opsi_shop,
        "opsi_voucher_filter": voucher,
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
            "globe_zone": _sha256(globe_zone_path),
            "map_data": _sha256(map_data_path),
            "os_map": _sha256(os_map_path),
            "os_shop_selector": _sha256(selector_path),
            "os_shop_preset": _sha256(os_shop_preset_path),
            "base_filter": _sha256(filter_path),
            "shop_base": _sha256(shop_base_path),
            "shop_voucher": _sha256(shop_voucher_path),
            "shop_filter_redirect": _sha256(shop_filter_redirect_path),
            "action_point": _sha256(action_point_path),
            "storage": _sha256(storage_path),
            "explore": _sha256(explore_path),
            "map_order": _sha256(order_path),
            "month_boss": _sha256(month_path),
            "obscure": _sha256(obscure_path),
            "daily": _sha256(daily_path),
            "hazard1_leveling": _sha256(hazard_path),
            "meowfficer_farming": _sha256(meowfficer_path),
        },
    }
