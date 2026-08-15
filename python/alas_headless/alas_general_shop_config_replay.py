"""Deterministic replay for pure ALAS GeneralShop custom-item choices."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from .alas_general_shop_config_contract import (
    validate_alas_general_shop_custom_items_config,
    validate_alas_general_shop_filter,
    validate_alas_general_shop_refresh,
    validate_alas_general_shop_use_gems,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.general-shop-config-replay/v1"


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
    exec(compile(module, "<alas-general-shop-replay>", "exec"), namespace)
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
    values: dict[str, object] = {}
    expected = {
        "GeneralShop_ConsumeCoins": False,
        "GeneralShop_BuySkinBox": False,
        "GeneralShop_UseGems": False,
        "GeneralShop_Refresh": False,
        "GeneralShop_Filter": "BookRedT3 > BookYellowT3 > BookBlueT3 > BookRedT2\n> Cube\n> FoodT6 > FoodT5",
    }
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
        raise AssertionError("GeneralShop custom-item configuration surface drifted")
    return {
        "ConsumeCoins": values["GeneralShop_ConsumeCoins"],
        "BuySkinBox": values["GeneralShop_BuySkinBox"],
        "UseGems": values["GeneralShop_UseGems"],
        "Refresh": values["GeneralShop_Refresh"],
        "Filter": values["GeneralShop_Filter"],
    }


def _verify_contract(filter_: object) -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for consume_coins in (False, True):
        for buy_skin_box in (False, True):
            snapshot = validate_alas_general_shop_custom_items_config(
                consume_coins=consume_coins,
                buy_skin_box=buy_skin_box,
            )
            if (
                snapshot.consume_coins is not consume_coins
                or snapshot.buy_skin_box is not buy_skin_box
            ):
                raise AssertionError("GeneralShop custom-item canonical values drifted")
            accepted += 1
    for use_gems in (False, True):
        if validate_alas_general_shop_use_gems(use_gems=use_gems) is not use_gems:
            raise AssertionError("GeneralShop.UseGems canonical value drifted")
        accepted += 1
    for refresh in (False, True):
        if validate_alas_general_shop_refresh(refresh=refresh) is not refresh:
            raise AssertionError("GeneralShop.Refresh canonical value drifted")
        accepted += 1
    for value in (
        "BookRedT3 > Cube > FoodT6",
        " Cube ＞ FoodT6 ",
        " \n ",
    ):
        if validate_alas_general_shop_filter(filter_=filter_, value=value) != value:
            raise AssertionError("GeneralShop.Filter canonical value drifted")
        accepted += 1
    for field in ("consume_coins", "buy_skin_box"):
        for value in ("true", None, 0, 1, [], {}):
            values = {"consume_coins": False, "buy_skin_box": False}
            values[field] = value
            try:
                validate_alas_general_shop_custom_items_config(**values)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid GeneralShop.{field} was admitted")
    for value in ("true", None, 0, 1, [], {}):
        try:
            validate_alas_general_shop_use_gems(use_gems=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid GeneralShop.UseGems was admitted")
    for value in ("true", None, 0, 1, [], {}):
        try:
            validate_alas_general_shop_refresh(refresh=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid GeneralShop.Refresh was admitted")
    for value in ("Cube > invalid", "Cube >", None, True, 1, [], {}):
        try:
            validate_alas_general_shop_filter(filter_=filter_, value=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid GeneralShop.Filter was admitted")
    return accepted, invalid


def _case(
    method,
    *,
    consume_coins: object,
    buy_skin_box: object,
    currency: int,
    cost: str,
    price: int,
    amount: int,
    known: bool,
) -> dict[str, Any]:
    events: list[tuple[Any, ...]] = []

    item = SimpleNamespace(
        cost=cost,
        price=price,
        amount=amount,
        is_known_item=lambda: events.append(("is_known_item", known)) or known,
    )
    host = SimpleNamespace(
        config=SimpleNamespace(
            GeneralShop_ConsumeCoins=consume_coins,
            GeneralShop_BuySkinBox=buy_skin_box,
        ),
        _currency=currency,
    )
    try:
        result = method(host, item)
    except SemanticGateClosed:
        rejected = True
        result = None
    else:
        rejected = False
    return {"rejected": rejected, "result": result, "events": events}


def _verify_original(method) -> dict[str, object]:
    cases = {
        "disabled": _case(
            method,
            consume_coins=False,
            buy_skin_box=False,
            currency=600000,
            cost="Coins",
            price=7000,
            amount=1,
            known=False,
        ),
        "consume_coins": _case(
            method,
            consume_coins=True,
            buy_skin_box=False,
            currency=550000,
            cost="Coins",
            price=1,
            amount=1,
            known=True,
        ),
        "consume_threshold": _case(
            method,
            consume_coins=True,
            buy_skin_box=False,
            currency=549999,
            cost="Coins",
            price=1,
            amount=1,
            known=True,
        ),
        "skin_box": _case(
            method,
            consume_coins=False,
            buy_skin_box=True,
            currency=7000,
            cost="Coins",
            price=7000,
            amount=1,
            known=False,
        ),
        "skin_box_known": _case(
            method,
            consume_coins=False,
            buy_skin_box=True,
            currency=7000,
            cost="Coins",
            price=7000,
            amount=1,
            known=True,
        ),
    }
    if any(case["rejected"] for case in cases.values()):
        raise AssertionError("valid GeneralShop custom-item config was rejected")
    if cases["disabled"]["result"] is not False or cases["disabled"]["events"]:
        raise AssertionError("disabled GeneralShop custom-item branch drifted")
    if cases["consume_coins"]["result"] is not True:
        raise AssertionError("GeneralShop.ConsumeCoins threshold branch drifted")
    if cases["consume_threshold"]["result"] is not False:
        raise AssertionError("GeneralShop.ConsumeCoins lower threshold drifted")
    if cases["skin_box"]["result"] is not True:
        raise AssertionError("GeneralShop.BuySkinBox predicate drifted")
    if cases["skin_box_known"]["result"] is not False:
        raise AssertionError("GeneralShop.BuySkinBox known-item exclusion drifted")
    invalid = {}
    for field in ("consume_coins", "buy_skin_box"):
        for value in ("true", None, 0, 1, [], {}):
            values = {"consume_coins": False, "buy_skin_box": False}
            values[field] = value
            invalid[f"{field}:{value!r}"] = _case(
                method,
                currency=600000,
                cost="Coins",
                price=7000,
                amount=1,
                known=False,
                **values,
            )
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid GeneralShop config reached item inspection")
    return {"cases": cases, "invalid_entries": invalid}


def _item_check_case(
    method,
    *,
    use_gems: object,
    currency: int,
    gems: int,
    cost: str,
    price: int,
) -> dict[str, object]:
    events: list[str] = []

    class Item:
        def __init__(self) -> None:
            self.cost = cost
            self.price = price

        def __getattribute__(self, name: str):
            if name in {"cost", "price"}:
                events.append(f"item.{name}")
            return object.__getattribute__(self, name)

    item = Item()
    host = SimpleNamespace(
        config=SimpleNamespace(GeneralShop_UseGems=use_gems),
        _currency=currency,
        gems=gems,
    )
    try:
        result = method(host, item)
    except SemanticGateClosed:
        rejected = True
        result = None
    else:
        rejected = False
    return {"rejected": rejected, "result": result, "events": events}


def _verify_item_check(method) -> dict[str, object]:
    cases = {
        "coins": _item_check_case(
            method,
            use_gems=False,
            currency=100,
            gems=0,
            cost="Coins",
            price=100,
        ),
        "gems_disabled": _item_check_case(
            method,
            use_gems=False,
            currency=0,
            gems=100,
            cost="Gems",
            price=1,
        ),
        "gems_affordable": _item_check_case(
            method,
            use_gems=True,
            currency=0,
            gems=100,
            cost="Gems",
            price=100,
        ),
        "gems_insufficient": _item_check_case(
            method,
            use_gems=True,
            currency=0,
            gems=99,
            cost="Gems",
            price=100,
        ),
    }
    if any(case["rejected"] for case in cases.values()):
        raise AssertionError("valid GeneralShop.UseGems was rejected")
    if (
        cases["coins"]["result"] is not True
        or cases["gems_disabled"]["result"] is not False
        or cases["gems_affordable"]["result"] is not True
        or cases["gems_insufficient"]["result"] is not False
    ):
        raise AssertionError("GeneralShop.UseGems price branches drifted")
    invalid = {
        repr(value): _item_check_case(
            method,
            use_gems=value,
            currency=0,
            gems=100,
            cost="Gems",
            price=1,
        )
        for value in ("true", None, 0, 1, [], {})
    }
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid GeneralShop.UseGems reached item inspection")
    return {"cases": cases, "invalid_entries": invalid}


def _run_case(
    method,
    *,
    refresh: object,
    shop_filter: str,
    buy_outcomes: tuple[bool, ...],
    refresh_outcomes: tuple[bool, ...] = (),
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

    host = SimpleNamespace(
        config=SimpleNamespace(GeneralShop_Refresh=refresh),
        shop_filter=shop_filter,
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


def _verify_run(method) -> dict[str, object]:
    cases = {
        "empty": _run_case(
            method,
            refresh=False,
            shop_filter="",
            buy_outcomes=(True,),
        ),
        "disabled": _run_case(
            method,
            refresh=False,
            shop_filter="Cube",
            buy_outcomes=(True,),
        ),
        "refresh_success": _run_case(
            method,
            refresh=True,
            shop_filter="Cube",
            buy_outcomes=(True, False),
            refresh_outcomes=(True,),
        ),
        "refresh_unavailable": _run_case(
            method,
            refresh=True,
            shop_filter="Cube",
            buy_outcomes=(True,),
            refresh_outcomes=(False,),
        ),
    }
    if any(case["rejected"] for case in cases.values()):
        raise AssertionError("valid GeneralShop.Refresh was rejected")
    if cases["empty"]["events"]:
        raise AssertionError("empty GeneralShop filter entered the shop loop")
    if cases["disabled"]["events"] != ["shop_buy"]:
        raise AssertionError("disabled GeneralShop.Refresh branch drifted")
    if cases["refresh_success"]["events"] != [
        "shop_buy",
        "shop_refresh",
        "shop_buy",
    ]:
        raise AssertionError("GeneralShop.Refresh second-pass branch drifted")
    if cases["refresh_unavailable"]["events"] != ["shop_buy", "shop_refresh"]:
        raise AssertionError("GeneralShop.Refresh unavailable branch drifted")
    invalid = {
        repr(value): _run_case(
            method,
            refresh=value,
            shop_filter="Cube",
            buy_outcomes=(True,),
        )
        for value in ("true", None, 0, 1, [], {})
    }
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid GeneralShop.Refresh entered the shop loop")
    return {"cases": cases, "invalid_entries": invalid}


def _filter_case(method, value: object) -> dict[str, object]:
    host = SimpleNamespace(config=SimpleNamespace(GeneralShop_Filter=value))
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
        for value in (
            "BookRedT3 > Cube > FoodT6",
            " Cube ＞ FoodT6 ",
            " \n ",
        )
    }
    expected = {
        "BookRedT3 > Cube > FoodT6": "BookRedT3 > Cube > FoodT6",
        " Cube ＞ FoodT6 ": "Cube ＞ FoodT6",
        " \n ": "",
    }
    for value, result in cases.items():
        if result["rejected"] or result["result"] != expected[value]:
            raise AssertionError(f"GeneralShop.Filter property drifted: {value!r}")
    invalid = {
        repr(value): _filter_case(method, value)
        for value in ("Cube > invalid", "Cube >", None, True, 1, [], {})
    }
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid GeneralShop.Filter escaped its fail-closed gate")
    return {"cases": cases, "invalid_entries": invalid}


def verify_general_shop_config(alas_root: Path) -> dict[str, object]:
    alas_root = alas_root.resolve()
    source_path = alas_root / "module" / "shop" / "shop_general.py"
    shop_base_path = alas_root / "module" / "shop" / "base.py"
    config_path = alas_root / "module" / "config" / "config_generated.py"
    if not source_path.is_file() or not shop_base_path.is_file() or not config_path.is_file():
        raise FileNotFoundError("ALAS GeneralShop source is incomplete")
    generated = _verify_generated_config(config_path)
    method = _method(source_path, "GeneralShop_250814", "shop_check_custom_item")
    item_check_method = _method(source_path, "GeneralShop_250814", "shop_check_item")
    run_method = _method(source_path, "GeneralShop_250814", "run")
    filter_method = _method(source_path, "GeneralShop_250814", "shop_filter")
    filter_regex = _assignment(shop_base_path, "FILTER_REGEX", {"re": re})
    filter_contract = SimpleNamespace(regex=filter_regex, preset=())
    attributes = {
        node.attr for node in ast.walk(method) if isinstance(node, ast.Attribute)
    }
    expected_attributes = {
        "GeneralShop_ConsumeCoins",
        "GeneralShop_BuySkinBox",
    }
    if not expected_attributes <= attributes:
        raise AssertionError("GeneralShop custom-item consumer surface drifted")
    guards = {
        node.func.id
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_general_shop_custom_items_config" not in guards:
        raise AssertionError("GeneralShop custom-item fail-closed guard is absent")
    item_check_attributes = {
        node.attr
        for node in ast.walk(item_check_method)
        if isinstance(node, ast.Attribute)
    }
    if "GeneralShop_UseGems" not in item_check_attributes:
        raise AssertionError("GeneralShop.UseGems consumer surface drifted")
    item_check_guards = {
        node.func.id
        for node in ast.walk(item_check_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_general_shop_use_gems" not in item_check_guards:
        raise AssertionError("GeneralShop.UseGems fail-closed guard is absent")
    run_attributes = {
        node.attr for node in ast.walk(run_method) if isinstance(node, ast.Attribute)
    }
    if "GeneralShop_Refresh" not in run_attributes:
        raise AssertionError("GeneralShop.Refresh consumer surface drifted")
    run_guards = {
        node.func.id
        for node in ast.walk(run_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_general_shop_refresh" not in run_guards:
        raise AssertionError("GeneralShop.Refresh fail-closed guard is absent")
    filter_attributes = {
        node.attr for node in ast.walk(filter_method) if isinstance(node, ast.Attribute)
    }
    if "GeneralShop_Filter" not in filter_attributes:
        raise AssertionError("GeneralShop.Filter consumer surface drifted")
    filter_guards = {
        node.func.id
        for node in ast.walk(filter_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_general_shop_filter" not in filter_guards:
        raise AssertionError("GeneralShop.Filter fail-closed guard is absent")
    accepted, invalid = _verify_contract(filter_contract)
    original = _verify_original(
        _compile(
            method,
            {
                "logger": _Logger(),
                "validate_alas_general_shop_custom_items_config": (
                    validate_alas_general_shop_custom_items_config
                ),
            },
        )
    )
    item_decisions = _verify_item_check(
        _compile(
            item_check_method,
            {
                "validate_alas_general_shop_use_gems": (
                    validate_alas_general_shop_use_gems
                ),
            },
        )
    )
    run_decisions = _verify_run(
        _compile(
            run_method,
            {
                "logger": _Logger(),
                "validate_alas_general_shop_refresh": (
                    validate_alas_general_shop_refresh
                ),
            },
        )
    )
    filter_decisions = _verify_filter_property(
        _compile(
            filter_method,
            {
                "FILTER": filter_contract,
                "cached_property": lambda method: method,
                "validate_alas_general_shop_filter": validate_alas_general_shop_filter,
            },
        )
    )
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 5,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_defaults": generated,
        "runtime_consumers": {
            "GeneralShop.ConsumeCoins": "GeneralShop_250814.shop_check_custom_item",
            "GeneralShop.BuySkinBox": "GeneralShop_250814.shop_check_custom_item",
            "GeneralShop.UseGems": "GeneralShop_250814.shop_check_item",
            "GeneralShop.Refresh": "GeneralShop_250814.run",
            "GeneralShop.Filter": "GeneralShop_250814.shop_filter",
        },
        "patched_guard_present": True,
        "original_decisions": {
            "custom_items": original,
            "item_check": item_decisions,
            "run": run_decisions,
            "filter": filter_decisions,
        },
        "mutation_budget": 0,
        "real_purchase_performed": False,
        "real_refresh_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "shop_general": _sha256(source_path),
            "shop_base": _sha256(shop_base_path),
            "config_generated": _sha256(config_path),
        },
    }
