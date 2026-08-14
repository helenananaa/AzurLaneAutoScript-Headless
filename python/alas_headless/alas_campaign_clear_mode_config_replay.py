"""Deterministic replay of pinned ALAS campaign clear-mode decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_campaign_clear_mode_config_contract import (
    validate_alas_campaign_clear_mode_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.campaign-clear-mode-config-replay/v1"
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> tuple[str, ...]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panels = []
    for panel, groups in document.items():
        campaign = groups.get("Campaign")
        if not isinstance(campaign, dict) or "UseClearMode" not in campaign:
            continue
        panels.append(panel)
        field = campaign["UseClearMode"]
        if field.get("type") != "checkbox" or field.get("value") is not True:
            raise AssertionError("Campaign.UseClearMode declaration drifted")
    if tuple(panels) != EXPECTED_PANELS:
        raise AssertionError("Campaign.UseClearMode shared panel surface drifted")
    return tuple(panels)


def _verify_consumers(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    consumers = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "FastForwardHandler":
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if child.name == "_validate_campaign_clear_mode_config":
                continue
            if any(
                isinstance(item, ast.Attribute)
                and isinstance(item.ctx, ast.Load)
                and item.attr == "Campaign_UseClearMode"
                for item in ast.walk(child)
            ):
                consumers.add(child.name)
    if consumers != {"handle_fast_forward"}:
        raise AssertionError("Campaign.UseClearMode runtime consumer drifted")
    return tuple(sorted(consumers))


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.handler.fast_forward")
        return module, module.FastForwardHandler
    finally:
        sys.path.remove(root)


def _config(use_clear_mode: object, *, clear_all: bool = False):
    return SimpleNamespace(
        Campaign_UseClearMode=use_clear_mode,
        Campaign_UseAutoSearch=True,
        Campaign_Use2xBook=True,
        MAP_CLEAR_ALL_THIS_TIME=clear_all,
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


def _host(handler_type: type[Any], config: Any, *, available: bool):
    host = object.__new__(handler_type)
    host.config = config
    host.map_has_clear_mode = available
    host.map_is_clear_mode = True
    host.map_is_auto_search = True
    host.map_is_2x_book = True
    host.wait_calls = 0
    host.map_wait_auto_search = MethodType(
        lambda self: setattr(self, "wait_calls", self.wait_calls + 1), host
    )
    return host


def _run_case(
    module: Any,
    handler_type: type[Any],
    *,
    use_clear_mode: object,
    available: bool,
    clear_all: bool = False,
    changed: bool = False,
) -> dict[str, Any]:
    config = _config(use_clear_mode, clear_all=clear_all)
    host = _host(handler_type, config, available=available)
    switch_calls = []
    old_switch = module.FAST_FORWARD
    module.FAST_FORWARD = SimpleNamespace(
        set=lambda state, main: switch_calls.append((state, main is host)) or changed
    )
    try:
        result = handler_type.handle_fast_forward(host)
    finally:
        module.FAST_FORWARD = old_switch
    disabled_flags = tuple(
        name
        for name in (
            "MAP_HAS_AMBUSH",
            "MAP_HAS_FLEET_STEP",
            "MAP_HAS_MOVABLE_ENEMY",
            "MAP_HAS_MOVABLE_NORMAL_ENEMY",
            "MAP_HAS_PORTAL",
            "MAP_HAS_LAND_BASED",
            "MAP_HAS_MAZE",
            "MAP_HAS_FORTRESS",
            "MAP_HAS_BOUNCING_ENEMY",
            "MAP_HAS_DECOY_ENEMY",
        )
        if getattr(config, name) is False
    )
    return {
        "result": bool(result),
        "clear_mode": host.map_is_clear_mode,
        "auto_search": host.map_is_auto_search,
        "two_x_book": host.map_is_2x_book,
        "switch_calls": switch_calls,
        "wait_calls": host.wait_calls,
        "disabled_flag_count": len(disabled_flags),
    }


def _verify_original(module: Any, handler_type: type[Any]) -> list[dict[str, Any]]:
    cases = [
        _run_case(
            module,
            handler_type,
            use_clear_mode=True,
            available=False,
        ),
        _run_case(
            module,
            handler_type,
            use_clear_mode=False,
            available=True,
        ),
        _run_case(
            module,
            handler_type,
            use_clear_mode=True,
            available=True,
        ),
        _run_case(
            module,
            handler_type,
            use_clear_mode=True,
            available=True,
            clear_all=True,
        ),
        _run_case(
            module,
            handler_type,
            use_clear_mode=True,
            available=True,
            changed=True,
        ),
    ]
    expected = [
        (False, False, False, False, [], 0, 0),
        (False, False, False, False, [("off", True)], 0, 0),
        (False, True, True, True, [("on", True)], 0, 10),
        (False, True, False, True, [("on", True)], 0, 10),
        (True, True, True, True, [("on", True)], 1, 10),
    ]
    actual = [
        (
            case["result"],
            case["clear_mode"],
            case["auto_search"],
            case["two_x_book"],
            case["switch_calls"],
            case["wait_calls"],
            case["disabled_flag_count"],
        )
        for case in cases
    ]
    if actual != expected:
        raise AssertionError("original campaign clear-mode decisions drifted")
    return cases


def verify_campaign_clear_mode_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    panels = _verify_args(alas_root)
    source = alas_root / "module" / "handler" / "fast_forward.py"
    consumers = _verify_consumers(source)
    module, handler_type = _load_original(alas_root)
    decisions = _verify_original(module, handler_type)

    for value in (False, True):
        validate_alas_campaign_clear_mode_config(use_clear_mode=value)
    invalid_count = 0
    for value in (0, 1, None, "true", [], {}):
        try:
            validate_alas_campaign_clear_mode_config(use_clear_mode=value)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid Campaign.UseClearMode was admitted")

    guard_present = hasattr(handler_type, "_validate_campaign_clear_mode_config")
    if guard_present:
        invalid_host = _host(handler_type, _config(1), available=False)
        try:
            handler_type.handle_fast_forward(invalid_host)
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError("patched original admitted invalid clear-mode config")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "panel_count": len(panels),
        "accepted_case_count": 2,
        "invalid_case_count": invalid_count,
        "runtime_consumers": consumers,
        "original_decisions": decisions,
        "patched_guard_present": guard_present,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "fast_forward": _sha256(source),
        },
    }
