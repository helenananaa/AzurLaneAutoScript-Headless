"""Deterministic replay of shared ALAS campaign switch decisions."""

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

from .alas_campaign_switch_config_contract import (
    validate_alas_campaign_switch_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.campaign-switch-config-replay/v1"
FIELDS = (
    "UseFleetLock",
    "UseAutoSearch",
    "Use2xBook",
    "AmbushEvade",
)
EXPECTED_PANELS = (
    "Main",
    "Main2",
    "Main3",
    "GemsFarming",
    "Coalition",
    "Event",
    "Event2",
    "Raid",
    "WarArchives",
    "CoalitionSp",
    "EventA",
    "EventB",
    "EventC",
    "EventD",
    "EventSp",
    "RaidDaily",
)
INVALID_VALUES = (0, 1, None, "true", [], {})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> tuple[str, ...]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panels = []
    for panel, groups in document.items():
        campaign = groups.get("Campaign")
        if not isinstance(campaign, dict) or "UseFleetLock" not in campaign:
            continue
        panels.append(panel)
        for field in FIELDS:
            declaration = campaign.get(field)
            if not isinstance(declaration, dict):
                raise AssertionError(f"Campaign.{field} declaration is missing")
            if declaration.get("type") != "checkbox":
                raise AssertionError(f"Campaign.{field} type drifted")
            if type(declaration.get("value")) is not bool:
                raise AssertionError(f"Campaign.{field} default drifted")
    if tuple(panels) != EXPECTED_PANELS:
        raise AssertionError("Campaign switch shared panel surface drifted")
    return tuple(panels)


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        run_module = importlib.import_module("module.campaign.run")
        fast_module = importlib.import_module("module.handler.fast_forward")
        ambush_module = importlib.import_module("module.handler.ambush")
        return run_module, fast_module, ambush_module
    finally:
        sys.path.remove(root)


def _verify_guard(run_path: Path) -> bool:
    tree = ast.parse(run_path.read_text(encoding="utf-8"), filename=str(run_path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "CampaignRun":
            continue
        methods = {
            child.name: child
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        guard = methods.get("_validate_campaign_switch_config")
        if guard is None:
            return False
        run = methods.get("run")
        if run is None or not run.body:
            raise AssertionError("CampaignRun.run is missing")
        if len(run.body) < 2:
            raise AssertionError("CampaignRun.run guards are missing")
        first = run.body[0]
        second = run.body[1]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Attribute)
            and first.value.func.attr == "_validate_main_campaign_route_config"
            and isinstance(second, ast.Expr)
            and isinstance(second.value, ast.Call)
            and isinstance(second.value.func, ast.Attribute)
            and second.value.func.attr == "_validate_campaign_switch_config"
        ):
            raise AssertionError("Campaign route/switch guards are not first in CampaignRun.run")
        attrs = {
            item.attr
            for item in ast.walk(guard)
            if isinstance(item, ast.Attribute) and isinstance(item.ctx, ast.Load)
        }
        expected = {f"Campaign_{field}" for field in FIELDS}
        if not expected.issubset(attrs):
            raise AssertionError("Campaign switch guard field surface drifted")
        return True
    raise AssertionError("CampaignRun class is missing")


def _switch_config(values: tuple[bool, bool, bool, bool]):
    fleet_lock, auto_search, two_x_book, ambush_evade = values
    return SimpleNamespace(
        Campaign_UseFleetLock=fleet_lock,
        Campaign_UseAutoSearch=auto_search,
        Campaign_Use2xBook=two_x_book,
        Campaign_AmbushEvade=ambush_evade,
        Campaign_UseClearMode=True,
        MAP_CLEAR_ALL_THIS_TIME=False,
        MAP_HAS_AMBUSH=True,
        MAP_HAS_FLEET_STEP=True,
        MAP_HAS_MOVABLE_ENEMY=True,
        MAP_HAS_MOVABLE_NORMAL_ENEMY=True,
        MAP_HAS_PORTAL=True,
        MAP_HAS_LAND_BASED=True,
        MAP_HAS_MAZE=True,
        MAP_HAS_FORTRESS=True,
        MAP_HAS_BOUNCING_ENEMY=True,
        MAP_HAS_DECOY_ENEMY=True,
    )


def _fast_forward_decision(module: Any, config: Any) -> dict[str, Any]:
    handler_type = module.FastForwardHandler
    host = object.__new__(handler_type)
    host.config = config
    host.map_has_clear_mode = True
    host.map_is_clear_mode = False
    host.map_is_auto_search = False
    host.map_is_2x_book = False
    host.map_wait_auto_search = MethodType(lambda self: None, host)
    calls = []
    original = module.FAST_FORWARD
    module.FAST_FORWARD = SimpleNamespace(
        set=lambda state, main: calls.append([state, main is host]) or False
    )
    try:
        result = handler_type.handle_fast_forward(host)
    finally:
        module.FAST_FORWARD = original
    return {
        "result": bool(result),
        "auto_search": host.map_is_auto_search,
        "two_x_book": host.map_is_2x_book,
        "switch_calls": calls,
    }


def _fleet_lock_decision(module: Any, config: Any) -> dict[str, Any]:
    handler_type = module.FastForwardHandler
    host = object.__new__(handler_type)
    host.config = config
    calls = []
    original = module.FLEET_LOCK
    module.FLEET_LOCK = SimpleNamespace(
        appear=lambda main: main is host,
        set=lambda state, main: calls.append([state, main is host]) or True,
    )
    try:
        result = handler_type.handle_map_fleet_lock(host)
    finally:
        module.FLEET_LOCK = original
    return {"result": bool(result), "switch_calls": calls}


def _ambush_decision(module: Any, config: Any) -> dict[str, Any]:
    handler_type = module.AmbushHandler
    host = object.__new__(handler_type)
    host.config = config
    calls = []
    host._handle_ambush_evade = MethodType(
        lambda self: calls.append("evade") or "evade", host
    )
    host._handle_ambush_attack = MethodType(
        lambda self: calls.append("attack") or "attack", host
    )
    result = handler_type._handle_ambush(host)
    return {"result": result, "calls": calls}


def _verify_original(fast_module: Any, ambush_module: Any) -> dict[str, Any]:
    cases = {}
    for values in itertools.product((False, True), repeat=4):
        config = _switch_config(values)
        key = "".join("1" if value else "0" for value in values)
        case = {
            "fast_forward": _fast_forward_decision(fast_module, config),
            "fleet_lock": _fleet_lock_decision(fast_module, config),
            "ambush": _ambush_decision(ambush_module, config),
        }
        expected_state = "on" if values[0] else "off"
        expected_ambush = "evade" if values[3] else "attack"
        if case["fast_forward"] != {
            "result": False,
            "auto_search": values[1],
            "two_x_book": values[2],
            "switch_calls": [["on", True]],
        }:
            raise AssertionError("original fast-forward switch decision drifted")
        if case["fleet_lock"] != {
            "result": True,
            "switch_calls": [[expected_state, True]],
        }:
            raise AssertionError("original fleet-lock switch decision drifted")
        if case["ambush"] != {
            "result": expected_ambush,
            "calls": [expected_ambush],
        }:
            raise AssertionError("original ambush switch decision drifted")
        cases[key] = case
    return cases


def _validate_cases() -> int:
    invalid_count = 0
    names = (
        "use_fleet_lock",
        "use_auto_search",
        "use_2x_book",
        "ambush_evade",
    )
    defaults = dict(
        use_fleet_lock=True,
        use_auto_search=True,
        use_2x_book=False,
        ambush_evade=True,
    )
    for values in itertools.product((False, True), repeat=4):
        validate_alas_campaign_switch_config(
            **dict(zip(names, values, strict=True))
        )
    for name in names:
        for value in INVALID_VALUES:
            case = dict(defaults)
            case[name] = value
            try:
                validate_alas_campaign_switch_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid {name} was admitted")
    return invalid_count


def _verify_invalid_entry(run_type: type[Any]) -> dict[str, list[Any]]:
    if not hasattr(run_type, "_validate_campaign_switch_config"):
        return {}
    results = {}
    field_names = (
        "Campaign_UseFleetLock",
        "Campaign_UseAutoSearch",
        "Campaign_Use2xBook",
        "Campaign_AmbushEvade",
    )
    for field in field_names:
        config = _switch_config((True, True, False, True))
        setattr(config, field, None)
        host = object.__new__(run_type)
        host.config = config
        try:
            run_type.run(host, "12-4")
        except SemanticGateClosed:
            results[field] = []
        else:
            raise AssertionError(f"patched CampaignRun admitted invalid {field}")
    return results


def verify_campaign_switch_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    panels = _verify_args(alas_root)
    run_path = alas_root / "module" / "campaign" / "run.py"
    guard_present = _verify_guard(run_path)
    run_module, fast_module, ambush_module = _load_original(alas_root)
    original = _verify_original(fast_module, ambush_module)
    invalid_count = _validate_cases()
    invalid_entry_events = _verify_invalid_entry(run_module.CampaignRun)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 4,
        "panel_count": len(panels),
        "accepted_case_count": len(original),
        "invalid_case_count": invalid_count,
        "patched_guard_present": guard_present,
        "guarded_entry": "CampaignRun.run",
        "original_decisions": original,
        "invalid_entry_events": invalid_entry_events,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_map_method_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "run": _sha256(run_path),
            "fast_forward": _sha256(
                alas_root / "module" / "handler" / "fast_forward.py"
            ),
            "ambush": _sha256(
                alas_root / "module" / "handler" / "ambush.py"
            ),
        },
    }
