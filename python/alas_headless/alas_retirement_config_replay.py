"""Deterministic replay of pinned ALAS retirement mode decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_retirement_config_contract import (
    RETIREMENT_MODES,
    validate_alas_retirement_config,
)
from .runtime import bind_semantic_session, reset_semantic_session
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.retirement-config-replay/v1"
INVALID_MODES = (None, True, 1, "", "unknown", [], {})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    declaration = document.get("General", {}).get("Retirement", {}).get("RetireMode")
    if (
        not isinstance(declaration, dict)
        or declaration.get("type") != "select"
        or declaration.get("value") != "one_click_retire"
        or tuple(declaration.get("option", ())) != RETIREMENT_MODES
    ):
        raise AssertionError("Retirement.RetireMode declaration drifted")


def _method(class_node: ast.ClassDef, name: str) -> ast.FunctionDef:
    target = next(
        (
            child
            for child in class_node.body
            if isinstance(child, ast.FunctionDef) and child.name == name
        ),
        None,
    )
    if target is None:
        raise AssertionError(f"{class_node.name}.{name} is missing")
    return target


def _source_flags(retirement_path: Path, enhancement_path: Path) -> tuple[dict[str, list[str]], bool]:
    retirement_tree = ast.parse(
        retirement_path.read_text(encoding="utf-8"), filename=str(retirement_path)
    )
    enhancement_tree = ast.parse(
        enhancement_path.read_text(encoding="utf-8"), filename=str(enhancement_path)
    )
    retirement_class = next(
        node
        for node in retirement_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Retirement"
    )
    enhancement_class = next(
        node
        for node in enhancement_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Enhancement"
    )
    methods = {
        "handle_retirement": _method(retirement_class, "handle_retirement"),
        "_retire_handler": _method(retirement_class, "_retire_handler"),
        "_retire_amount": _method(enhancement_class, "_retire_amount"),
    }
    consumers = {
        "Retirement_RetireMode": [
            name
            for name, method in methods.items()
            if any(
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and node.attr == "Retirement_RetireMode"
                for node in ast.walk(method)
            )
        ]
    }
    if consumers["Retirement_RetireMode"] != [
        "handle_retirement",
        "_retire_handler",
        "_retire_amount",
    ]:
        raise AssertionError(f"retirement mode consumers drifted: {consumers!r}")

    handle = methods["handle_retirement"]
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_retirement_config"
        for node in ast.walk(handle)
    )
    if guard_present:
        statements = list(handle.body)
        if (
            statements
            and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)
        ):
            statements.pop(0)
        executable = [
            statement
            for statement in statements
            if not isinstance(statement, (ast.Import, ast.ImportFrom))
        ]
        first = executable[0]
        if not (
            isinstance(first, ast.Assign)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "validate_alas_retirement_config"
        ):
            raise AssertionError("retirement config guard is not first in handle_retirement")
        if not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "require_semantic_entry"
            for node in ast.walk(handle)
        ):
            raise AssertionError("old-retire semantic refusal is missing")
    return consumers, guard_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.retire.retirement")
    finally:
        sys.path.remove(root)


class _Config(SimpleNamespace):
    def __init__(self, mode: object, old_amount: str = "retire_all"):
        super().__init__(
            Retirement_RetireMode=mode,
            OldRetire_RetireAmount=old_amount,
            OneClickRetire_KeepLimitBreak="keep_limit_break",
            DOCK_FULL_TRIGGERED=False,
        )


def _retire_amount_case(module: Any, mode: str, old_amount: str) -> int:
    host = object.__new__(module.Retirement)
    host.config = _Config(mode, old_amount)
    return module.Retirement._retire_amount.fget(host)


def _verify_retire_amount(module: Any) -> dict[str, int]:
    result = {
        "one_click_retire": _retire_amount_case(module, "one_click_retire", "retire_10"),
        "enhance": _retire_amount_case(module, "enhance", "retire_10"),
        "old_retire_all": _retire_amount_case(module, "old_retire", "retire_all"),
        "old_retire_10": _retire_amount_case(module, "old_retire", "retire_10"),
    }
    expected = {
        "one_click_retire": 3000,
        "enhance": 3000,
        "old_retire_all": 3000,
        "old_retire_10": 10,
    }
    if result != expected:
        raise AssertionError("original retirement amount mapping drifted")
    return result


def _handler_case(module: Any, mode: str) -> dict[str, Any]:
    events: list[Any] = []
    host = object.__new__(module.Retirement)
    host.config = _Config(mode)
    host.retire_ships_one_click = MethodType(
        lambda self: events.append("one_click") or 2, host
    )
    host.server_support_quick_retire_setting_fallback = MethodType(
        lambda self: False, host
    )
    host.retire_gems_farming_flagships = MethodType(
        lambda self, keep_one=False: events.append(["gems", keep_one]) or 1, host
    )
    host.handle_dock_cards_loading = MethodType(
        lambda self: events.append("dock_loading"), host
    )
    host.retire_ships_old = MethodType(
        lambda self: events.append("old_retire") or 2, host
    )
    host._retirement_quit = MethodType(
        lambda self: events.append("quit"), host
    )
    total = module.Retirement._retire_handler(host, mode=mode)
    return {
        "total": total,
        "events": events,
        "dock_full_triggered": host.config.DOCK_FULL_TRIGGERED,
    }


def _verify_handlers(module: Any) -> dict[str, Any]:
    one_click = _handler_case(module, "one_click_retire")
    old_retire = _handler_case(module, "old_retire")
    if one_click != {
        "total": 3,
        "events": ["one_click", ["gems", True], "quit"],
        "dock_full_triggered": True,
    }:
        raise AssertionError("original one-click retirement handler drifted")
    if old_retire != {
        "total": 3,
        "events": ["dock_loading", "old_retire", ["gems", False], "quit"],
        "dock_full_triggered": True,
    }:
        raise AssertionError("original old-retire handler drifted")
    host = object.__new__(module.Retirement)
    host.config = _Config("unknown")
    try:
        module.Retirement._retire_handler(host, mode="unknown")
    except module.ScriptError:
        invalid = "ScriptError"
    else:
        raise AssertionError("original retirement handler admitted an unknown mode")
    return {"one_click_retire": one_click, "old_retire": old_retire, "invalid": invalid}


def _entry_case(module: Any, mode: object, *, semantic: bool) -> list[Any]:
    events: list[Any] = []
    host = object.__new__(module.Retirement)
    host.config = _Config(mode)
    host.__dict__["_unable_to_enhance"] = False
    host.map_cat_attack_timer = SimpleNamespace(reset=lambda: events.append("timer_reset"))
    host.handle_game_tips = MethodType(
        lambda self: events.append("game_tips") or False, host
    )
    host.appear_then_click = MethodType(lambda self, *args, **kwargs: False, host)
    host.appear = MethodType(lambda self, *args, **kwargs: True, host)
    host.interval_clear = MethodType(lambda self, *args, **kwargs: events.append("clear"), host)
    host.interval_reset = MethodType(lambda self, *args, **kwargs: events.append("reset"), host)
    host.handle_dock_cards_loading = MethodType(
        lambda self: events.append("dock_loading"), host
    )
    host._enhance_handler = MethodType(
        lambda self: events.append("enhance") or (1, 5), host
    )
    host._retire_handler = MethodType(
        lambda self, mode=None: events.append(["retire", mode]), host
    )
    token = bind_semantic_session(SimpleNamespace()) if semantic else None
    try:
        module.Retirement.handle_retirement(host)
    finally:
        if token is not None:
            reset_semantic_session(token)
    return events


def _verify_entry(module: Any, guard_present: bool) -> dict[str, Any]:
    if not guard_present:
        return {}
    one_click = _entry_case(module, "one_click_retire", semantic=True)
    enhance = _entry_case(module, "enhance", semantic=True)
    old_legacy = _entry_case(module, "old_retire", semantic=False)
    old_semantic = _entry_case(module, "old_retire", semantic=True)
    if old_semantic != old_legacy:
        raise AssertionError("typed old retirement changed original entry dispatch")
    if [event for event in one_click if isinstance(event, list)] != [["retire", None]]:
        raise AssertionError("one-click entry dispatch drifted")
    if "enhance" not in enhance or any(
        isinstance(event, list) and event[0] == "retire" for event in enhance
    ):
        raise AssertionError("enhancement entry dispatch drifted")
    if [event for event in old_legacy if isinstance(event, list)] != [["retire", None]]:
        raise AssertionError("legacy old-retire dispatch drifted")

    refused: dict[str, list[Any]] = {}
    for name, value, semantic in (
        ("unknown", "unknown", False),
        ("wrong_type", 1, False),
    ):
        try:
            events = _entry_case(module, value, semantic=semantic)
        except SemanticGateClosed:
            refused[name] = []
        else:
            raise AssertionError(f"retirement entry admitted {name}: {events!r}")
    return {
        "one_click_retire": one_click,
        "enhance": enhance,
        "old_retire_legacy": old_legacy,
        "old_retire_semantic": old_semantic,
        "refused_before_events": refused,
    }


def _verify_contract() -> tuple[int, int, dict[str, bool]]:
    admission = {}
    for mode in RETIREMENT_MODES:
        snapshot = validate_alas_retirement_config(mode=mode)
        admission[mode] = snapshot.semantic_admitted
    invalid_count = 0
    for value in INVALID_MODES:
        try:
            validate_alas_retirement_config(mode=value)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid retirement mode was admitted")
    return len(RETIREMENT_MODES), invalid_count, admission


def verify_retirement_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    retirement = alas_root / "module/retire/retirement.py"
    enhancement = alas_root / "module/retire/enhancement.py"
    consumers, guard_present = _source_flags(retirement, enhancement)
    module = _load_original(alas_root)
    amounts = _verify_retire_amount(module)
    handlers = _verify_handlers(module)
    entry = _verify_entry(module, guard_present)
    accepted, invalid, admission = _verify_contract()
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "semantic_admission": admission,
        "retire_amount_mapping": amounts,
        "original_handlers": handlers,
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "entry_dispatch": entry,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_retirement_performed": False,
        "real_enhancement_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "retirement": _sha256(retirement),
            "enhancement": _sha256(enhancement),
        },
    }
