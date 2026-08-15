"""Deterministic replay for ALAS MedalShop2 entry configuration."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

import yaml

from .alas_medal_shop_config_contract import (
    MEDAL_SHOP_SECONDARY_CHOICES,
    validate_alas_medal_shop_filter,
    validate_alas_medal_shop_secondary_choices,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.medal-shop-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == method_name)


def _assignment(path: Path, name: str, globals_: dict[str, Any]) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignment = next(
        node for node in tree.body if isinstance(node, ast.Assign)
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
    exec(compile(module, "<alas-medal-shop-replay>", "exec"), namespace)
    return namespace[method.name]


class _Logger:
    @staticmethod
    def hr(*_args, **_kwargs) -> None:
        return None


def _verify_generated_config(config_path: Path) -> dict[str, object]:
    expected = {
        "MedalShop2_Filter": (
            "DR > PR\n> BookRedT3 > BookYellowT3 > BookBlueT3\n> BookRedT2 > "
            "BookYellowT2 > BookBlueT2\n> RetrofitT3\n> FoodT6 > FoodT5\n> "
            "PlateGeneralT3 > PlateWildT3"
        ),
        "MedalShop2_RETROFIT_T1": "cl",
        "MedalShop2_RETROFIT_T2": "cl",
        "MedalShop2_RETROFIT_T3": "cl",
        "MedalShop2_PLATE_T1": "general",
        "MedalShop2_PLATE_T2": "general",
        "MedalShop2_PLATE_T3": "general",
    }
    tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    values: dict[str, object] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in expected:
                    value = ast.literal_eval(node.value)
                    if type(value) is not type(expected[target.id]) or value != expected[target.id]:
                        raise AssertionError(f"{target.id} generated default drifted")
                    values[target.id] = value
    if values != expected:
        raise AssertionError("MedalShop2 configuration surface drifted")
    return {
        "Filter": values["MedalShop2_Filter"],
        **{field: values[f"MedalShop2_{field}"] for field in MEDAL_SHOP_SECONDARY_CHOICES},
    }


def _verify_argument_schema(argument_path: Path, defaults: dict[str, object]) -> None:
    document = yaml.safe_load(argument_path.read_text(encoding="utf-8"))
    group = document.get("MedalShop2") if isinstance(document, dict) else None
    if not isinstance(group, dict):
        raise AssertionError("MedalShop2 argument schema is unavailable")
    for field, choices in MEDAL_SHOP_SECONDARY_CHOICES.items():
        definition = group.get(field)
        if not isinstance(definition, dict) or tuple(definition.get("option", ())) != choices:
            raise AssertionError(f"MedalShop2.{field} options drifted")
        if definition.get("value") != defaults[field]:
            raise AssertionError(f"MedalShop2.{field} default drifted")


def _kwargs(values: dict[str, object]) -> dict[str, object]:
    return {field.lower(): value for field, value in values.items()}


def _verify_contract(filter_: object, defaults: dict[str, object]) -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for value in ("DR > PR > BookRedT3", " DR ＞ FoodT6 ", " \n "):
        if validate_alas_medal_shop_filter(filter_=filter_, value=value) != value:
            raise AssertionError("MedalShop2.Filter canonical value drifted")
        accepted += 1
    for value in ("DR > invalid", "DR >", None, True, 1, [], {}):
        try:
            validate_alas_medal_shop_filter(filter_=filter_, value=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid MedalShop2.Filter was admitted")
    for field, choices in MEDAL_SHOP_SECONDARY_CHOICES.items():
        for choice in choices:
            values = dict(defaults)
            values[field] = choice
            snapshot = validate_alas_medal_shop_secondary_choices(**_kwargs(values))
            if getattr(snapshot, field.lower()) != choice:
                raise AssertionError(f"MedalShop2.{field} canonical value drifted")
            accepted += 1
        for value in ("invalid", None):
            values = dict(defaults)
            values[field] = value
            try:
                validate_alas_medal_shop_secondary_choices(**_kwargs(values))
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid MedalShop2.{field} was admitted")
    return accepted, invalid


def _run_case(method, *, secondary_values: dict[str, object], shop_filter: str) -> dict[str, object]:
    events: list[str] = []
    config = SimpleNamespace(**{f"MedalShop2_{field}": value for field, value in secondary_values.items()})
    host = SimpleNamespace(
        config=config,
        shop_filter=shop_filter,
        device=SimpleNamespace(semantic_adapter=object()),
        shop_buy=lambda: events.append("shop_buy"),
    )
    try:
        result = method(host)
    except SemanticGateClosed:
        rejected = True
        result = None
    else:
        rejected = False
    return {"rejected": rejected, "result": result, "events": events}


def _verify_run(method, defaults: dict[str, object]) -> dict[str, object]:
    empty = _run_case(method, secondary_values=defaults, shop_filter="")
    semantic = _run_case(method, secondary_values=defaults, shop_filter="DR")
    if empty["rejected"] or empty["events"]:
        raise AssertionError("MedalShop2 empty-filter branch drifted")
    if semantic["rejected"] or semantic["events"] != ["shop_buy"]:
        raise AssertionError("MedalShop2 semantic entry branch drifted")
    invalid = {}
    for field in MEDAL_SHOP_SECONDARY_CHOICES:
        values = dict(defaults)
        values[field] = "invalid"
        invalid[field] = _run_case(method, secondary_values=values, shop_filter="DR")
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid MedalShop2 choice entered the shop loop")
    return {"empty": empty, "semantic": semantic, "invalid_entries": invalid}


def _filter_case(method, value: object) -> dict[str, object]:
    host = SimpleNamespace(config=SimpleNamespace(MedalShop2_Filter=value))
    try:
        result = method(host)
    except SemanticGateClosed:
        return {"rejected": True, "result": None, "events": []}
    return {"rejected": False, "result": result, "events": []}


def _verify_filter(method) -> dict[str, object]:
    cases = {value: _filter_case(method, value) for value in ("DR > PR", " DR ＞ FoodT6 ", " \n ")}
    expected = {"DR > PR": "DR > PR", " DR ＞ FoodT6 ": "DR ＞ FoodT6", " \n ": ""}
    if any(case["rejected"] or case["result"] != expected[value] for value, case in cases.items()):
        raise AssertionError("MedalShop2.Filter property drifted")
    invalid = {repr(value): _filter_case(method, value) for value in ("DR > invalid", "DR >", None, True, 1, [], {})}
    if any(not case["rejected"] for case in invalid.values()):
        raise AssertionError("invalid MedalShop2.Filter escaped its gate")
    return {"cases": cases, "invalid_entries": invalid}


def verify_medal_shop_config(alas_root: Path) -> dict[str, object]:
    root = alas_root.resolve()
    shop_path = root / "module" / "shop" / "shop_medal.py"
    base_path = root / "module" / "shop" / "base.py"
    config_path = root / "module" / "config" / "config_generated.py"
    argument_path = root / "module" / "config" / "argument" / "argument.yaml"
    if not all(path.is_file() for path in (shop_path, base_path, config_path, argument_path)):
        raise FileNotFoundError("ALAS MedalShop2 source is incomplete")
    generated = _verify_generated_config(config_path)
    defaults = {field: generated[field] for field in MEDAL_SHOP_SECONDARY_CHOICES}
    _verify_argument_schema(argument_path, defaults)
    run_method = _method(shop_path, "MedalShop2_250814", "run")
    filter_method = _method(shop_path, "MedalShop2_250814", "shop_filter")
    filter_contract = SimpleNamespace(regex=_assignment(base_path, "FILTER_REGEX", {"re": re}), preset=())
    run_calls = {node.func.id for node in ast.walk(run_method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    run_attrs = {node.attr for node in ast.walk(run_method) if isinstance(node, ast.Attribute)}
    if "validate_alas_medal_shop_secondary_choices" not in run_calls:
        raise AssertionError("MedalShop2 secondary-choice guard is absent")
    if not {f"MedalShop2_{field}" for field in MEDAL_SHOP_SECONDARY_CHOICES} <= run_attrs:
        raise AssertionError("MedalShop2 secondary-choice surface drifted")
    filter_calls = {node.func.id for node in ast.walk(filter_method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    if "validate_alas_medal_shop_filter" not in filter_calls:
        raise AssertionError("MedalShop2.Filter guard is absent")
    accepted, invalid = _verify_contract(filter_contract, defaults)
    run = _verify_run(_compile(run_method, {"logger": _Logger(), "validate_alas_medal_shop_secondary_choices": validate_alas_medal_shop_secondary_choices}), defaults)
    filter_result = _verify_filter(_compile(filter_method, {"FILTER": filter_contract, "cached_property": lambda method: method, "validate_alas_medal_shop_filter": validate_alas_medal_shop_filter}))
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 7,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_defaults": generated,
        "runtime_consumers": {
            "MedalShop2.Filter": "MedalShop2_250814.shop_filter",
            **{f"MedalShop2.{field}": "MedalShop2_250814.run preflight -> ShopClerk.shop_get_choice" for field in MEDAL_SHOP_SECONDARY_CHOICES},
        },
        "patched_guard_present": True,
        "original_decisions": {"run": run, "filter": filter_result},
        "mutation_budget": 0,
        "real_purchase_performed": False,
        "real_refresh_performed": False,
        "android_input_injected": False,
        "source_sha256": {"shop_medal": _sha256(shop_path), "shop_base": _sha256(base_path), "config_generated": _sha256(config_path), "argument_schema": _sha256(argument_path)},
    }
