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
    OPSI_HAZARD1_TARGET_ZONES,
    OPSI_MEOWFFICER_HAZARD_LEVELS,
    OPSI_MONTH_BOSS_MODES,
    validate_alas_opsi_daily_config,
    validate_alas_opsi_hazard1_config,
    validate_alas_opsi_meowfficer_config,
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
    "OpsiDaily_DoMission",
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
    def __init__(
        self,
        *,
        mode: object,
        check: object,
        force: object = False,
        use_tuning_sample: object = True,
        hazard_target_zone: object = 0,
        meowfficer_hazard_level: object = 5,
    ):
        super().__init__(
            OpsiMonthBoss_Mode=mode,
            OpsiMonthBoss_CheckAdaptability=check,
            OpsiMonthBoss_ForceRun=False,
            OpsiObscure_ForceRun=force,
            OpsiDaily_UseTuningSample=use_tuning_sample,
            OpsiHazard1Leveling_TargetZone=hazard_target_zone,
            OpsiMeowfficerFarming_HazardLevel=meowfficer_hazard_level,
            OpsiMeowfficerFarming_ActionPointPreserve=1000,
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


def _meowfficer_case(method, *, hazard_level: object) -> dict[str, Any]:
    config = _Config(
        mode="normal",
        check=False,
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
    return {"rejected": rejected, "switched": switched, "events": events}


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
    invalid = _meowfficer_case(method, hazard_level=7)
    if invalid != {"rejected": True, "switched": False, "events": []}:
        raise AssertionError("invalid meowfficer hazard level touched task state")
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
        validate_alas_opsi_meowfficer_config(hazard_level=hazard_level)
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
            validate_alas_opsi_meowfficer_config(hazard_level=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OpsiMeowfficerFarming.HazardLevel was admitted")
    return accepted, invalid


def verify_opsi_task_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    args_path = alas_root / "module/config/argument/args.json"
    month_path = alas_root / "module/os/tasks/month_boss.py"
    obscure_path = alas_root / "module/os/tasks/obscure.py"
    daily_path = alas_root / "module/os/tasks/daily.py"
    hazard_path = alas_root / "module/os/tasks/hazard_leveling.py"
    meowfficer_path = alas_root / "module/os/tasks/meowfficer_farming.py"
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
        ("OpsiMeowfficerFarming_HazardLevel",),
    )
    consumers = {
        **month_consumers,
        **obscure_consumers,
        **daily_consumers,
        **hazard_consumers,
        **meowfficer_consumers,
    }
    expected = {
        "OpsiMonthBoss_Mode": ["clear_month_boss", "month_boss_delay"],
        "OpsiMonthBoss_CheckAdaptability": ["clear_month_boss", "month_boss_delay"],
        "OpsiObscure_ForceRun": ["clear_obscure", "os_obscure"],
        "OpsiDaily_UseTuningSample": ["os_daily"],
        "OpsiHazard1Leveling_TargetZone": ["os_hazard1_leveling"],
        "OpsiMeowfficerFarming_HazardLevel": ["os_meowfficer_farming"],
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
        "validate_alas_opsi_daily_config": validate_alas_opsi_daily_config,
        "validate_alas_opsi_hazard1_config": validate_alas_opsi_hazard1_config,
        "validate_alas_opsi_meowfficer_config": validate_alas_opsi_meowfficer_config,
        "SelectedGrids": lambda value: value,
        "get_os_reset_remain": lambda: 1,
    }
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
        "field_count": 6,
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
        ),
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
            "month_boss": _sha256(month_path),
            "obscure": _sha256(obscure_path),
            "daily": _sha256(daily_path),
            "hazard1_leveling": _sha256(hazard_path),
            "meowfficer_farming": _sha256(meowfficer_path),
        },
    }
