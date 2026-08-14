"""Deterministic replay of pinned ALAS furniture-purchase decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_buy_furniture_config_contract import (
    BUY_FURNITURE_OPTIONS,
    validate_alas_buy_furniture_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.buy-furniture-config-replay/v1"
FROZEN_NOW = datetime(2026, 8, 15, 7, 0, 0)
VALID_RECORDS = (
    datetime(2000, 1, 1),
    datetime(2020, 1, 1),
    FROZEN_NOW - timedelta(days=6),
    FROZEN_NOW,
    datetime(2100, 1, 1),
)
INVALID_BOOL_VALUES = (0, 1, None, "true", [], {})
INVALID_OPTION_VALUES = (None, True, 1, "", "unknown", [])
INVALID_RECORD_VALUES = (
    None,
    True,
    "2020-01-01 00:00:00",
    date(2020, 1, 1),
    datetime(2020, 1, 1, tzinfo=timezone.utc),
    datetime(1999, 12, 31, 23, 59, 59),
    datetime(2100, 1, 1, 0, 0, 1),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    group = document.get("Dorm", {}).get("BuyFurniture")
    expected = {
        "Enable": {"type": "checkbox", "value": False},
        "BuyOption": {
            "type": "select",
            "value": "all",
            "option": list(BUY_FURNITURE_OPTIONS),
        },
        "LastRun": {
            "type": "datetime",
            "value": "2020-01-01 00:00:00",
            "validate": "datetime",
        },
    }
    if not isinstance(group, dict) or set(group) != set(expected):
        raise AssertionError("BuyFurniture field surface drifted")
    for field, values in expected.items():
        if any(group[field].get(key) != value for key, value in values.items()):
            raise AssertionError(f"BuyFurniture.{field} declaration drifted")


def _class_method(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    target = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        (
            node
            for node in target.body
            if isinstance(node, ast.FunctionDef) and node.name == method_name
        ),
        None,
    )
    if method is None:
        raise AssertionError(f"{class_name}.{method_name} is missing")
    return method


def _has_field(method: ast.FunctionDef, field: str) -> bool:
    return any(
        isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and node.attr == field
        for node in ast.walk(method)
    )


def _guard_is_first(method: ast.FunctionDef, validator: str) -> None:
    statements = list(method.body)
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
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == validator
    ):
        raise AssertionError(f"{validator} is not the first business statement")


def _source_flags(dorm_path: Path, furniture_path: Path) -> tuple[dict[str, list[str]], bool, bool]:
    dorm_run = _class_method(dorm_path, "RewardDorm", "run")
    dorm_state = _class_method(dorm_path, "RewardDorm", "_run_alas_state_machine")
    furniture_run = _class_method(furniture_path, "BuyFurniture", "run")
    furniture_decision = _class_method(
        furniture_path, "BuyFurniture", "_buy_furniture_run"
    )
    methods = {
        "RewardDorm.run": dorm_run,
        "RewardDorm._run_alas_state_machine": dorm_state,
        "BuyFurniture.run": furniture_run,
        "BuyFurniture._buy_furniture_run": furniture_decision,
    }
    fields = (
        "BuyFurniture_Enable",
        "BuyFurniture_BuyOption",
        "BuyFurniture_LastRun",
    )
    consumers = {
        field: [name for name, method in methods.items() if _has_field(method, field)]
        for field in fields
    }
    dorm_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_buy_furniture_config"
        for node in ast.walk(dorm_run)
    )
    furniture_guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_buy_furniture_config"
        for node in ast.walk(furniture_run)
    )
    expected = {
        "BuyFurniture_Enable": {"RewardDorm._run_alas_state_machine"},
        "BuyFurniture_BuyOption": {"BuyFurniture._buy_furniture_run"},
        "BuyFurniture_LastRun": {"BuyFurniture.run"},
    }
    if dorm_guard:
        for field in fields:
            expected[field].add("RewardDorm.run")
    if furniture_guard:
        for field in fields:
            expected[field].add("BuyFurniture.run")
    if {field: set(values) for field, values in consumers.items()} != expected:
        raise AssertionError(f"BuyFurniture consumer surface drifted: {consumers!r}")
    if dorm_guard:
        calls = [
            node.func.id
            for node in ast.walk(dorm_run)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        if calls.index("validate_alas_dorm_config") > calls.index(
            "validate_alas_buy_furniture_config"
        ):
            raise AssertionError("Dorm base guard must precede furniture guard")
    if furniture_guard:
        _guard_is_first(furniture_run, "validate_alas_buy_furniture_config")
    return consumers, dorm_guard, furniture_guard


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        dorm = importlib.import_module("module.dorm.dorm")
        furniture = importlib.import_module("module.dorm.buy_furniture")
        return dorm, furniture
    finally:
        sys.path.remove(root)


class _Config(SimpleNamespace):
    def __init__(
        self,
        *,
        enable: object,
        buy_option: object,
        last_run: object,
    ):
        super().__init__(
            BuyFurniture_Enable=enable,
            BuyFurniture_BuyOption=buy_option,
            BuyFurniture_LastRun=last_run,
            Dorm_Collect=True,
            Dorm_Feed=True,
            Dorm_FeedFilter="20000 > 10000 > 5000 > 3000 > 2000 > 1000",
        )


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return FROZEN_NOW.replace(tzinfo=timezone.utc).astimezone(tz)
        return cls(*FROZEN_NOW.timetuple()[:6])


def _timing_case(module: Any, last_run: datetime) -> list[Any]:
    events: list[Any] = []
    host = object.__new__(module.BuyFurniture)
    host.config = _Config(enable=True, buy_option="all", last_run=last_run)
    host.buy_furniture_run = MethodType(
        lambda self: events.append("buy_furniture_run"), host
    )
    original_datetime = module.datetime
    module.datetime = _FrozenDateTime
    try:
        module.BuyFurniture.run(host)
    finally:
        module.datetime = original_datetime
    return events


def _verify_timing(module: Any) -> dict[str, list[Any]]:
    cases = {
        "one_second_overdue": _timing_case(
            module, FROZEN_NOW - timedelta(days=6, seconds=1)
        ),
        "exact_boundary": _timing_case(module, FROZEN_NOW - timedelta(days=6)),
        "one_second_early": _timing_case(
            module, FROZEN_NOW - timedelta(days=6) + timedelta(seconds=1)
        ),
        "future_record": _timing_case(module, FROZEN_NOW + timedelta(days=1)),
        "old_record": _timing_case(module, datetime(2020, 1, 1)),
    }
    expected = {
        "one_second_overdue": ["buy_furniture_run"],
        "exact_boundary": ["buy_furniture_run"],
        "one_second_early": [],
        "future_record": [],
        "old_record": ["buy_furniture_run"],
    }
    if cases != expected:
        raise AssertionError("original furniture interval decision drifted")
    return cases


def _loop_case(module: Any) -> dict[str, Any]:
    events: list[Any] = []
    host = object.__new__(module.BuyFurniture)
    host.config = _Config(
        enable=True, buy_option="set", last_run=datetime(2020, 1, 1)
    )
    decisions = iter((True, True, False))
    host._buy_furniture_run = MethodType(
        lambda self: events.append("scan") or next(decisions), host
    )
    host.furniture_details_page_quit = MethodType(
        lambda self, **kwargs: events.append(["details_quit", kwargs]), host
    )
    host.furniture_shop_quit = MethodType(
        lambda self, **kwargs: events.append(["shop_quit", kwargs]), host
    )
    original_datetime = module.datetime
    module.datetime = _FrozenDateTime
    try:
        module.BuyFurniture.buy_furniture_run(host)
    finally:
        module.datetime = original_datetime
    return {"events": events, "last_run": host.config.BuyFurniture_LastRun.isoformat()}


def _verify_loop(module: Any) -> dict[str, Any]:
    result = _loop_case(module)
    expected = {
        "events": [
            "scan",
            "scan",
            "scan",
            ["details_quit", {"skip_first_screenshot": True}],
            ["shop_quit", {"skip_first_screenshot": True}],
        ],
        "last_run": FROZEN_NOW.isoformat(),
    }
    if result != expected:
        raise AssertionError("original furniture loop or LastRun update drifted")
    return result


def _purchase_case(module: Any, *, option: str, coin: int, price: int) -> dict[str, Any]:
    events: list[Any] = []
    host = object.__new__(module.BuyFurniture)
    host.device = SimpleNamespace(image=object())
    host.furniture_payment_enter = MethodType(
        lambda self, button, **kwargs: events.append(
            ["payment", option, button is module.FURNITURE_BUY_BUTTON[option], kwargs]
        ),
        host,
    )
    host.buy_furniture_confirm = MethodType(
        lambda self, **kwargs: events.append(["confirm_stub", kwargs]), host
    )
    host.furniture_details_page_quit = MethodType(
        lambda self, **kwargs: events.append(["details_quit", kwargs]), host
    )
    original_coin = module.OCR_FURNITURE_COIN
    original_price = module.OCR_FURNITURE_PRICE
    module.OCR_FURNITURE_COIN = SimpleNamespace(ocr=lambda image: coin)
    module.OCR_FURNITURE_PRICE = SimpleNamespace(ocr=lambda image: price)
    try:
        result = module.BuyFurniture.buy_furniture_once(host, option)
    finally:
        module.OCR_FURNITURE_COIN = original_coin
        module.OCR_FURNITURE_PRICE = original_price
    return {"result": result, "events": events}


def _verify_purchase_boundaries(module: Any) -> dict[str, Any]:
    cases = {
        "set_equal": _purchase_case(module, option="set", coin=100, price=100),
        "all_surplus": _purchase_case(module, option="all", coin=101, price=100),
        "insufficient": _purchase_case(module, option="all", coin=99, price=100),
        "zero_price": _purchase_case(module, option="set", coin=100, price=0),
    }
    if cases["set_equal"]["result"] is not True:
        raise AssertionError("equal furniture balance must remain affordable")
    if cases["all_surplus"]["result"] is not True:
        raise AssertionError("surplus furniture balance must remain affordable")
    if cases["insufficient"]["result"] is not False:
        raise AssertionError("insufficient furniture balance was admitted")
    if cases["zero_price"]["result"] is not False:
        raise AssertionError("zero furniture price was admitted")
    if not all(case["events"][0][2] for case in cases.values()):
        raise AssertionError("furniture option-to-button mapping drifted")
    return cases


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    for enable in (False, True):
        for option in BUY_FURNITURE_OPTIONS:
            for record in VALID_RECORDS:
                snapshot = validate_alas_buy_furniture_config(
                    enable=enable, buy_option=option, last_run=record
                )
                if (snapshot.enable, snapshot.buy_option, snapshot.last_run) != (
                    enable,
                    option,
                    record,
                ):
                    raise AssertionError("furniture config snapshot drifted")
                accepted += 1
    invalid = 0
    cases = {
        "enable": INVALID_BOOL_VALUES,
        "buy_option": INVALID_OPTION_VALUES,
        "last_run": INVALID_RECORD_VALUES,
    }
    for field, values in cases.items():
        for value in values:
            config = {
                "enable": True,
                "buy_option": "all",
                "last_run": datetime(2020, 1, 1),
            }
            config[field] = value
            try:
                validate_alas_buy_furniture_config(**config)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid BuyFurniture.{field} was admitted")
    return accepted, invalid


def _dorm_entry_case(dorm: Any, **values: object) -> list[Any]:
    events: list[Any] = []
    host = object.__new__(dorm.RewardDorm)
    host.config = _Config(**values)
    host.device = SimpleNamespace(
        semantic_adapter=SimpleNamespace(
            begin_dorm=lambda: events.append("begin_dorm"),
            end_dorm=lambda: events.append("end_dorm"),
        )
    )
    host._run_alas_state_machine = MethodType(
        lambda self: events.append("state_machine"), host
    )
    dorm.RewardDorm.run(host)
    return events


def _furniture_entry_case(module: Any, **values: object) -> list[Any]:
    events: list[Any] = []
    host = object.__new__(module.BuyFurniture)
    host.config = _Config(**values)
    host.buy_furniture_run = MethodType(
        lambda self: events.append("buy_furniture_run"), host
    )
    original_datetime = module.datetime
    module.datetime = _FrozenDateTime
    try:
        module.BuyFurniture.run(host)
    finally:
        module.datetime = original_datetime
    return events


def _verify_entry(dorm: Any, furniture: Any, dorm_guard: bool, furniture_guard: bool) -> dict[str, Any]:
    if not dorm_guard or not furniture_guard:
        return {}
    valid = {
        "enable": True,
        "buy_option": "all",
        "last_run": FROZEN_NOW,
    }
    dorm_events = _dorm_entry_case(dorm, **valid)
    furniture_events = _furniture_entry_case(furniture, **valid)
    if dorm_events != ["begin_dorm", "state_machine", "end_dorm"]:
        raise AssertionError("valid furniture config changed Dorm dispatch")
    if furniture_events:
        raise AssertionError("current furniture record should skip direct purchase")
    invalid = {}
    for field, value in (
        ("BuyFurniture_Enable", 1),
        ("BuyFurniture_BuyOption", "unknown"),
        ("BuyFurniture_LastRun", None),
    ):
        key = {
            "BuyFurniture_Enable": "enable",
            "BuyFurniture_BuyOption": "buy_option",
            "BuyFurniture_LastRun": "last_run",
        }[field]
        values = dict(valid)
        values[key] = value
        for name, runner in (("dorm", _dorm_entry_case), ("furniture", _furniture_entry_case)):
            try:
                runner(dorm if name == "dorm" else furniture, **values)
            except SemanticGateClosed:
                invalid[f"{name}:{field}"] = []
            else:
                raise AssertionError(f"{name} admitted invalid {field}")
    return {"dorm": dorm_events, "furniture": furniture_events, "invalid": invalid}


def verify_buy_furniture_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    dorm_source = alas_root / "module/dorm/dorm.py"
    furniture_source = alas_root / "module/dorm/buy_furniture.py"
    consumers, dorm_guard, furniture_guard = _source_flags(
        dorm_source, furniture_source
    )
    dorm, furniture = _load_original(alas_root)
    timing = _verify_timing(furniture)
    loop = _verify_loop(furniture)
    purchase = _verify_purchase_boundaries(furniture)
    accepted, invalid = _verify_contract()
    entry = _verify_entry(dorm, furniture, dorm_guard, furniture_guard)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "patched_dorm_guard_present": dorm_guard,
        "patched_furniture_guard_present": furniture_guard,
        "original_interval_decisions": timing,
        "original_purchase_boundaries": purchase,
        "original_loop": loop,
        "entry_decisions": entry,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_furniture_coin_consumed": False,
        "real_purchase_confirmed": False,
        "real_navigation_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "dorm": _sha256(dorm_source),
            "buy_furniture": _sha256(furniture_source),
        },
    }
