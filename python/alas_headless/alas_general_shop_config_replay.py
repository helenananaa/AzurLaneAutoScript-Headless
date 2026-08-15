"""Deterministic replay for pure ALAS GeneralShop custom-item choices."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_general_shop_config_contract import (
    validate_alas_general_shop_custom_items_config,
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


def _compile(method: ast.FunctionDef, globals_: dict[str, Any]):
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_)
    exec(compile(module, "<alas-general-shop-replay>", "exec"), namespace)
    return namespace[method.name]


class _Logger:
    @staticmethod
    def info(*_args, **_kwargs) -> None:
        return None


def _verify_generated_config(config_path: Path) -> dict[str, bool]:
    tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    values: dict[str, bool] = {}
    expected = {
        "GeneralShop_ConsumeCoins": False,
        "GeneralShop_BuySkinBox": False,
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in expected:
                value = ast.literal_eval(node.value)
                if type(value) is not bool or value is not expected[target.id]:
                    raise AssertionError(f"{target.id} generated default drifted")
                values[target.id] = value
    if values != expected:
        raise AssertionError("GeneralShop custom-item configuration surface drifted")
    return {
        "ConsumeCoins": values["GeneralShop_ConsumeCoins"],
        "BuySkinBox": values["GeneralShop_BuySkinBox"],
    }


def _verify_contract() -> tuple[int, int]:
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


def verify_general_shop_config(alas_root: Path) -> dict[str, object]:
    alas_root = alas_root.resolve()
    source_path = alas_root / "module" / "shop" / "shop_general.py"
    config_path = alas_root / "module" / "config" / "config_generated.py"
    if not source_path.is_file() or not config_path.is_file():
        raise FileNotFoundError("ALAS GeneralShop source is incomplete")
    generated = _verify_generated_config(config_path)
    method = _method(source_path, "GeneralShop_250814", "shop_check_custom_item")
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
    accepted, invalid = _verify_contract()
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
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_defaults": generated,
        "runtime_consumers": {
            "GeneralShop.ConsumeCoins": "GeneralShop_250814.shop_check_custom_item",
            "GeneralShop.BuySkinBox": "GeneralShop_250814.shop_check_custom_item",
        },
        "patched_guard_present": True,
        "original_decisions": original,
        "mutation_budget": 0,
        "real_purchase_performed": False,
        "real_refresh_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "shop_general": _sha256(source_path),
            "config_generated": _sha256(config_path),
        },
    }
