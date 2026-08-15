"""Deterministic replay for pure ALAS GuildShop entry decisions."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any
import yaml

from .alas_guild_shop_config_contract import (
    GUILD_SHOP_SECONDARY_CHOICES,
    validate_alas_guild_shop_filter,
    validate_alas_guild_shop_refresh,
    validate_alas_guild_shop_secondary_choices,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.guild-shop-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _assignment(path: Path, name: str, globals_: dict[str, Any]) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    module = ast.Module(body=[assignment], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


def _compile(method: ast.FunctionDef, globals_: dict[str, Any]):
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_)
    exec(compile(module, "<alas-guild-shop-replay>", "exec"), namespace)
    return namespace[method.name]


class _Logger:
    @staticmethod
    def hr(*_args, **_kwargs) -> None:
        return None

    @staticmethod
    def info(*_args, **_kwargs) -> None:
        return None


def _verify_generated_config(config_path: Path) -> dict[str, object]:
    tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    expected = {
        "GuildShop_Refresh": True,
        "GuildShop_Filter": (
            "PlateT4 > BookT3 > PR > CatT3 > Chip > BookT2 > Retrofit > FoodT6 "
            "> FoodT5 > CatT2 > BoxT4"
        ),
        "GuildShop_BOX_T3": "ironblood",
        "GuildShop_BOX_T4": "ironblood",
        "GuildShop_BOOK_T2": "red",
        "GuildShop_BOOK_T3": "red",
        "GuildShop_RETROFIT_T2": "cl",
        "GuildShop_RETROFIT_T3": "cl",
        "GuildShop_PLATE_T2": "general",
        "GuildShop_PLATE_T3": "general",
        "GuildShop_PLATE_T4": "gun",
        "GuildShop_PR1": "neptune",
        "GuildShop_PR2": "seattle",
        "GuildShop_PR3": "cheshire",
    }
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
        raise AssertionError("GuildShop entry configuration surface drifted")
    return {
        "Refresh": values["GuildShop_Refresh"],
        "Filter": values["GuildShop_Filter"],
        **{
            field: values[f"GuildShop_{field}"]
            for field in GUILD_SHOP_SECONDARY_CHOICES
        },
    }


def _verify_argument_schema(argument_path: Path, defaults: dict[str, object]) -> None:
    document = yaml.safe_load(argument_path.read_text(encoding="utf-8"))
    group = document.get("GuildShop") if isinstance(document, dict) else None
    if not isinstance(group, dict):
        raise AssertionError("GuildShop argument schema is unavailable")
    for field, choices in GUILD_SHOP_SECONDARY_CHOICES.items():
        definition = group.get(field)
        if not isinstance(definition, dict):
            raise AssertionError(f"GuildShop.{field} argument schema drifted")
        if tuple(definition.get("option", ())) != choices:
            raise AssertionError(f"GuildShop.{field} choice options drifted")
        if definition.get("value") != defaults[field]:
            raise AssertionError(f"GuildShop.{field} default drifted")


def _secondary_kwargs(values: dict[str, object]) -> dict[str, object]:
    return {field.lower(): value for field, value in values.items()}


def _verify_contract(
    filter_: object,
    secondary_defaults: dict[str, object],
) -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for refresh in (False, True):
        if validate_alas_guild_shop_refresh(refresh=refresh) is not refresh:
            raise AssertionError("GuildShop.Refresh canonical value drifted")
        accepted += 1
    for value in ("PlateT4 > BookT3 > PR", " PlateT4 ＞ FoodT6 ", " \n "):
        if validate_alas_guild_shop_filter(filter_=filter_, value=value) != value:
            raise AssertionError("GuildShop.Filter canonical value drifted")
        accepted += 1
    for value in ("true", None, 0, 1, [], {}):
        try:
            validate_alas_guild_shop_refresh(refresh=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid GuildShop.Refresh was admitted")
    for value in ("PlateT4 > invalid", "PlateT4 >", None, True, 1, [], {}):
        try:
            validate_alas_guild_shop_filter(filter_=filter_, value=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid GuildShop.Filter was admitted")
    for field, choices in GUILD_SHOP_SECONDARY_CHOICES.items():
        for choice in choices:
            values = dict(secondary_defaults)
            values[field] = choice
            snapshot = validate_alas_guild_shop_secondary_choices(
                **_secondary_kwargs(values)
            )
            if getattr(snapshot, field.lower()) != choice:
                raise AssertionError(f"GuildShop.{field} canonical value drifted")
            accepted += 1
        for value in ("invalid", None):
            values = dict(secondary_defaults)
            values[field] = value
            try:
                validate_alas_guild_shop_secondary_choices(
                    **_secondary_kwargs(values)
                )
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid GuildShop.{field} was admitted")
    return accepted, invalid


def _run_case(
    method,
    *,
    refresh: object,
    shop_filter: str,
    currency: int,
    buy_outcomes: tuple[bool, ...],
    refresh_outcomes: tuple[bool, ...] = (),
    secondary_values: dict[str, object],
) -> dict[str, object]:
    events: list[str] = []
    buy_iter = iter(buy_outcomes)
    refresh_iter = iter(refresh_outcomes)

    def shop_buy() -> bool:
        events.append("shop_buy")
        return next(buy_iter, False)

    def shop_refresh() -> bool:
        events.append("shop_refresh")
        return next(refresh_iter, False)

    config_values = {
        "GuildShop_Refresh": refresh,
        **{f"GuildShop_{field}": value for field, value in secondary_values.items()},
    }
    host = SimpleNamespace(
        config=SimpleNamespace(**config_values),
        shop_filter=shop_filter,
        _currency=currency,
        shop_buy=shop_buy,
        shop_refresh=shop_refresh,
    )
    try:
        result = method(host)
    except SemanticGateClosed:
        rejected = True
        result = None
    else:
        rejected = False
    return {"rejected": rejected, "result": result, "events": events}


def _verify_run(method, secondary_defaults: dict[str, object]) -> dict[str, object]:
    cases = {
        "empty": _run_case(
            method,
            refresh=True,
            shop_filter="",
            currency=110,
            buy_outcomes=(True,),
            secondary_values=secondary_defaults,
        ),
        "disabled": _run_case(
            method,
            refresh=False,
            shop_filter="Cube",
            currency=110,
            buy_outcomes=(True,),
            secondary_values=secondary_defaults,
        ),
        "insufficient": _run_case(
            method,
            refresh=True,
            shop_filter="Cube",
            currency=109,
            buy_outcomes=(True,),
            secondary_values=secondary_defaults,
        ),
        "refresh_success": _run_case(
            method,
            refresh=True,
            shop_filter="Cube",
            currency=110,
            buy_outcomes=(True, False),
            refresh_outcomes=(True,),
            secondary_values=secondary_defaults,
        ),
        "refresh_unavailable": _run_case(
            method,
            refresh=True,
            shop_filter="Cube",
            currency=110,
            buy_outcomes=(True,),
            refresh_outcomes=(False,),
            secondary_values=secondary_defaults,
        ),
    }
    expected = {
        "empty": [],
        "disabled": ["shop_buy"],
        "insufficient": ["shop_buy"],
        "refresh_success": ["shop_buy", "shop_refresh", "shop_buy"],
        "refresh_unavailable": ["shop_buy", "shop_refresh"],
    }
    for name, events in expected.items():
        case = cases[name]
        if case["rejected"] or case["events"] != events:
            raise AssertionError(f"GuildShop.Refresh run branch drifted: {name}")
    invalid = {
        repr(value): _run_case(
            method,
            refresh=value,
            shop_filter="Cube",
            currency=110,
            buy_outcomes=(True,),
            secondary_values=secondary_defaults,
        )
        for value in ("true", None, 0, 1, [], {})
    }
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid GuildShop.Refresh entered the shop loop")
    invalid_secondary = {}
    for field in GUILD_SHOP_SECONDARY_CHOICES:
        values = dict(secondary_defaults)
        values[field] = "invalid"
        invalid_secondary[field] = _run_case(
            method,
            refresh=True,
            shop_filter="Cube",
            currency=110,
            buy_outcomes=(True,),
            secondary_values=values,
        )
    if any(
        not case["rejected"] or case["events"]
        for case in invalid_secondary.values()
    ):
        raise AssertionError("invalid GuildShop secondary choice entered the shop loop")
    return {
        "cases": cases,
        "invalid_entries": invalid,
        "invalid_secondary_entries": invalid_secondary,
    }


def _filter_case(method, value: object) -> dict[str, object]:
    host = SimpleNamespace(config=SimpleNamespace(GuildShop_Filter=value))
    try:
        result = method(host)
    except SemanticGateClosed:
        rejected = True
        result = None
    else:
        rejected = False
    return {"rejected": rejected, "result": result, "events": []}


def _verify_filter_property(method) -> dict[str, object]:
    cases = {
        value: _filter_case(method, value)
        for value in ("PlateT4 > BookT3 > PR", " PlateT4 ＞ FoodT6 ", " \n ")
    }
    expected = {
        "PlateT4 > BookT3 > PR": "PlateT4 > BookT3 > PR",
        " PlateT4 ＞ FoodT6 ": "PlateT4 ＞ FoodT6",
        " \n ": "",
    }
    for value, result in cases.items():
        if result["rejected"] or result["result"] != expected[value]:
            raise AssertionError(f"GuildShop.Filter property drifted: {value!r}")
    invalid = {
        repr(value): _filter_case(method, value)
        for value in ("PlateT4 > invalid", "PlateT4 >", None, True, 1, [], {})
    }
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid GuildShop.Filter escaped its fail-closed gate")
    return {"cases": cases, "invalid_entries": invalid}


def verify_guild_shop_config(alas_root: Path) -> dict[str, object]:
    alas_root = alas_root.resolve()
    source_path = alas_root / "module" / "shop" / "shop_guild.py"
    shop_base_path = alas_root / "module" / "shop" / "base.py"
    config_path = alas_root / "module" / "config" / "config_generated.py"
    argument_path = alas_root / "module" / "config" / "argument" / "argument.yaml"
    if (
        not source_path.is_file()
        or not shop_base_path.is_file()
        or not config_path.is_file()
        or not argument_path.is_file()
    ):
        raise FileNotFoundError("ALAS GuildShop source is incomplete")
    generated = _verify_generated_config(config_path)
    secondary_defaults = {
        field: generated[field] for field in GUILD_SHOP_SECONDARY_CHOICES
    }
    _verify_argument_schema(argument_path, secondary_defaults)
    run_method = _method(source_path, "GuildShop_250814", "run")
    filter_method = _method(source_path, "GuildShop_250814", "shop_filter")
    filter_regex = _assignment(shop_base_path, "FILTER_REGEX", {"re": re})
    filter_contract = SimpleNamespace(regex=filter_regex, preset=())
    run_attributes = {
        node.attr for node in ast.walk(run_method) if isinstance(node, ast.Attribute)
    }
    if "GuildShop_Refresh" not in run_attributes:
        raise AssertionError("GuildShop.Refresh consumer surface drifted")
    run_guards = {
        node.func.id
        for node in ast.walk(run_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_guild_shop_refresh" not in run_guards:
        raise AssertionError("GuildShop.Refresh fail-closed guard is absent")
    if "validate_alas_guild_shop_secondary_choices" not in run_guards:
        raise AssertionError("GuildShop secondary-choice fail-closed guard is absent")
    secondary_attributes = {f"GuildShop_{field}" for field in GUILD_SHOP_SECONDARY_CHOICES}
    if not secondary_attributes <= run_attributes:
        raise AssertionError("GuildShop secondary-choice consumer surface drifted")
    filter_attributes = {
        node.attr for node in ast.walk(filter_method) if isinstance(node, ast.Attribute)
    }
    if "GuildShop_Filter" not in filter_attributes:
        raise AssertionError("GuildShop.Filter consumer surface drifted")
    filter_guards = {
        node.func.id
        for node in ast.walk(filter_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_guild_shop_filter" not in filter_guards:
        raise AssertionError("GuildShop.Filter fail-closed guard is absent")
    accepted, invalid = _verify_contract(filter_contract, secondary_defaults)
    run_decisions = _verify_run(
        _compile(
            run_method,
            {
                "logger": _Logger(),
                "validate_alas_guild_shop_refresh": validate_alas_guild_shop_refresh,
                "validate_alas_guild_shop_secondary_choices": (
                    validate_alas_guild_shop_secondary_choices
                ),
            },
        ),
        secondary_defaults,
    )
    filter_decisions = _verify_filter_property(
        _compile(
            filter_method,
            {
                "FILTER": filter_contract,
                "cached_property": lambda method: method,
                "validate_alas_guild_shop_filter": validate_alas_guild_shop_filter,
            },
        )
    )
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 14,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_defaults": generated,
        "runtime_consumers": {
            "GuildShop.Refresh": "GuildShop_250814.run",
            "GuildShop.Filter": "GuildShop_250814.shop_filter",
            **{
                f"GuildShop.{field}": "GuildShop_250814.run preflight -> ShopClerk.shop_get_choice"
                for field in GUILD_SHOP_SECONDARY_CHOICES
            },
        },
        "patched_guard_present": True,
        "original_decisions": {"run": run_decisions, "filter": filter_decisions},
        "mutation_budget": 0,
        "real_purchase_performed": False,
        "real_refresh_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "shop_guild": _sha256(source_path),
            "shop_base": _sha256(shop_base_path),
            "config_generated": _sha256(config_path),
            "argument_schema": _sha256(argument_path),
        },
    }
