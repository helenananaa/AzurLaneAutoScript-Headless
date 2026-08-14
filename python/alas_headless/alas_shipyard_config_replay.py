"""Deterministic replay of pinned ALAS Shipyard task configuration."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_shipyard_config_contract import (
    SHIPYARD_DR_SERIES,
    SHIPYARD_INDICES,
    SHIPYARD_PR_SERIES,
    SHIPYARD_VERIFIED_BUY_AMOUNTS,
    validate_alas_shipyard_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.shipyard-config-replay/v1"
INVALID_PR_SERIES = (0, 7, True, 1.0, "1", None, [])
INVALID_DR_SERIES = (1, 6, True, 2.0, "2", None, [])
INVALID_INDICES = (-1, 7, True, 1.0, "1", None, [])
INVALID_BUY_AMOUNTS = (-1, 16, True, 1.0, "2", None, [], {})
INVALID_LAST_RUNS = (
    None,
    "2020-01-01 00:00:00",
    0,
    True,
    datetime(1999, 12, 31, 23, 59, 59),
    datetime(2100, 1, 1, 0, 0, 1),
    datetime(2026, 8, 15, tzinfo=timezone.utc),
)
DEFAULT_LAST_RUN = datetime(2020, 1, 1)
SERVER_UPDATE = datetime(2026, 8, 15, 4, 0, 0)
FROZEN_NOW = datetime(2026, 8, 15, 7, 0, 0)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    expected = {
        "Shipyard": {
            "ResearchSeries": (1, SHIPYARD_PR_SERIES),
            "ShipIndex": (0, SHIPYARD_INDICES),
            "BuyAmount": (2, None),
            "LastRun": ("2020-01-01 00:00:00", None),
        },
        "ShipyardDr": {
            "ResearchSeries": (2, SHIPYARD_DR_SERIES),
            "ShipIndex": (0, SHIPYARD_INDICES),
            "BuyAmount": (2, None),
            "LastRun": ("2020-01-01 00:00:00", None),
        },
    }
    for group_name, fields in expected.items():
        group = document.get("Shipyard", {}).get(group_name)
        if not isinstance(group, dict):
            raise AssertionError(f"{group_name} field surface is missing")
        for field, (default, options) in fields.items():
            declaration = group.get(field)
            valid = isinstance(declaration, dict) and declaration.get("value") == default
            if field in ("ResearchSeries", "ShipIndex"):
                valid = bool(
                    valid
                    and declaration.get("type") == "select"
                    and tuple(declaration.get("option", ())) == options
                )
            elif field == "BuyAmount":
                valid = bool(valid and declaration.get("type") == "input")
            else:
                valid = bool(
                    valid
                    and declaration.get("type") == "datetime"
                    and declaration.get("validate") == "datetime"
                )
            if not valid:
                raise AssertionError(f"{group_name}.{field} declaration drifted")


def _source_flags(reward_path: Path) -> tuple[dict[str, list[str]], bool]:
    tree = ast.parse(reward_path.read_text(encoding="utf-8"), filename=str(reward_path))
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "RewardShipyard"
        ),
        None,
    )
    if target is None:
        raise AssertionError("RewardShipyard is missing")
    run = next(
        (
            node
            for node in target.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        ),
        None,
    )
    if run is None:
        raise AssertionError("RewardShipyard.run is missing")
    mapping = {
        "Shipyard_ResearchSeries": [],
        "Shipyard_ShipIndex": [],
        "Shipyard_BuyAmount": [],
        "Shipyard_LastRun": [],
        "ShipyardDr_ResearchSeries": [],
        "ShipyardDr_ShipIndex": [],
        "ShipyardDr_BuyAmount": [],
        "ShipyardDr_LastRun": [],
    }
    for field in mapping:
        if any(
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == field
            for node in ast.walk(run)
        ):
            mapping[field].append("run")
    if mapping != {field: ["run"] for field in mapping}:
        raise AssertionError("Shipyard focus consumer surface drifted")
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_shipyard_config"
        for node in ast.walk(run)
    )
    if guard_present:
        executable = [
            statement
            for statement in run.body
            if not isinstance(statement, (ast.Import, ast.ImportFrom))
            and not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ]
        first = executable[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "validate_alas_shipyard_config"
        ):
            raise AssertionError("Shipyard configuration guard is not first in run")
    return mapping, guard_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        reward = importlib.import_module("module.shipyard.shipyard_reward")
        ui = importlib.import_module("module.shipyard.ui")
        return reward, ui
    finally:
        sys.path.remove(root)


def _verify_focus_matrix(ui_module: Any) -> dict[str, Any]:
    result = {"success": 0, "disabled": 0, "series_restricted": 0}
    for series, index in itertools.product(SHIPYARD_PR_SERIES, SHIPYARD_INDICES):
        events = []
        host = object.__new__(ui_module.ShipyardUI)
        host._shipyard_set_series = MethodType(
            lambda self, value, skip_first_screenshot=True: events.append(
                ["series", value]
            )
            or True,
            host,
        )
        host.shipyard_bottom_navbar_ensure = MethodType(
            lambda self, left=None, right=None, skip_first_screenshot=True: events.append(
                ["index", left]
            )
            or bool(left is not None and 1 <= left <= 6),
            host,
        )
        decision = ui_module.ShipyardUI.shipyard_set_focus(
            host,
            series=series,
            index=index,
        )
        restricted = series > 2 and index > 5
        expected = index > 0 and not restricted
        if bool(decision) is not expected:
            raise AssertionError("original Shipyard focus decision drifted")
        if restricted:
            if events:
                raise AssertionError("restricted Shipyard focus touched navigation")
            result["series_restricted"] += 1
        elif index == 0:
            if events != [["series", series], ["index", 0]]:
                raise AssertionError("disabled Shipyard focus dispatch drifted")
            result["disabled"] += 1
        else:
            if events != [["series", series], ["index", index]]:
                raise AssertionError("Shipyard focus dispatch drifted")
            result["success"] += 1
    return result


class _Config(SimpleNamespace):
    def __init__(
        self,
        *,
        pr_series: object,
        pr_index: object,
        pr_buy_amount: object = 2,
        pr_last_run: object = DEFAULT_LAST_RUN,
        dr_series: object,
        dr_index: object,
        dr_buy_amount: object = 2,
        dr_last_run: object = DEFAULT_LAST_RUN,
        events: list[Any] | None = None,
    ):
        super().__init__(
            Shipyard_ResearchSeries=pr_series,
            Shipyard_ShipIndex=pr_index,
            Shipyard_BuyAmount=pr_buy_amount,
            Shipyard_LastRun=pr_last_run,
            ShipyardDr_ResearchSeries=dr_series,
            ShipyardDr_ShipIndex=dr_index,
            ShipyardDr_BuyAmount=dr_buy_amount,
            ShipyardDr_LastRun=dr_last_run,
            Scheduler_Enable=True,
        )
        self.events = events if events is not None else []

    def task_delay(self, **kwargs):
        self.events.append(["task_delay", kwargs])

    def task_stop(self):
        self.events.append("task_stop")


def _run_case(
    reward_module: Any,
    *,
    pr_series: object,
    pr_index: object,
    pr_buy_amount: object = 2,
    pr_last_run: object = DEFAULT_LAST_RUN,
    dr_series: object,
    dr_index: object,
    dr_buy_amount: object = 2,
    dr_last_run: object = DEFAULT_LAST_RUN,
) -> list[Any]:
    events = []
    host = object.__new__(reward_module.RewardShipyard)
    host.config = _Config(
        pr_series=pr_series,
        pr_index=pr_index,
        pr_buy_amount=pr_buy_amount,
        pr_last_run=pr_last_run,
        dr_series=dr_series,
        dr_index=dr_index,
        dr_buy_amount=dr_buy_amount,
        dr_last_run=dr_last_run,
        events=events,
    )
    host.shipyard_run = MethodType(
        lambda self, series, index, count: events.append(
            [self._shipyard_bp_rarity, series, index, count]
        )
        or True,
        host,
    )
    original_update = reward_module.get_server_last_update
    reward_module.get_server_last_update = lambda value: SERVER_UPDATE
    try:
        reward_module.RewardShipyard.run(host)
    finally:
        reward_module.get_server_last_update = original_update
    return events


def _verify_dispatch(reward_module: Any) -> dict[str, Any]:
    samples = {
        "normal": {
            "expected": [
                ["DR", 2, 1, 2],
                ["PR", 1, 1, 2],
                ["task_delay", {"server_update": True}],
            ],
        },
        "exact_boundary_runs": {
            "pr_last_run": SERVER_UPDATE,
            "dr_last_run": SERVER_UPDATE,
            "expected": [
                ["DR", 2, 1, 2],
                ["PR", 1, 1, 2],
                ["task_delay", {"server_update": True}],
            ],
        },
        "dr_already_run": {
            "dr_last_run": SERVER_UPDATE + timedelta(seconds=1),
            "expected": [["PR", 1, 1, 2], ["task_delay", {"server_update": True}]],
        },
        "pr_already_run": {
            "pr_last_run": SERVER_UPDATE + timedelta(seconds=1),
            "expected": [
                ["DR", 2, 1, 2],
                ["task_delay", {"server_update": True}],
                "task_stop",
                ["task_delay", {"server_update": True}],
            ],
        },
        "both_disabled": {
            "pr_buy_amount": 0,
            "dr_buy_amount": 0,
            "expected": [
                "task_stop",
                ["DR", 2, 1, 0],
                ["PR", 1, 1, 0],
                ["task_delay", {"server_update": True}],
            ],
        },
        "independent_amounts": {
            "pr_buy_amount": 15,
            "dr_buy_amount": 1,
            "expected": [
                ["DR", 2, 1, 1],
                ["PR", 1, 1, 15],
                ["task_delay", {"server_update": True}],
            ],
        },
    }
    result = {}
    logger_methods = {
        name: getattr(reward_module.logger, name) for name in ("hr", "attr", "warning")
    }
    for name in logger_methods:
        setattr(reward_module.logger, name, lambda *args, **kwargs: None)
    try:
        for name, sample in samples.items():
            overrides = {
                key: value for key, value in sample.items() if key != "expected"
            }
            events = _run_case(
                reward_module,
                pr_series=1,
                pr_index=1,
                dr_series=2,
                dr_index=1,
                **overrides,
            )
            if events != sample["expected"]:
                raise AssertionError("original Shipyard run dispatch drifted")
            result[name] = events
    finally:
        for name, value in logger_methods.items():
            setattr(reward_module.logger, name, value)
    return result


def _base_contract_case() -> dict[str, object]:
    return {
        "pr_series": 1,
        "pr_index": 1,
        "pr_buy_amount": 2,
        "pr_last_run": DEFAULT_LAST_RUN,
        "dr_series": 2,
        "dr_index": 1,
        "dr_buy_amount": 2,
        "dr_last_run": DEFAULT_LAST_RUN,
    }


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    for pr_series, pr_index, dr_series, dr_index in itertools.product(
        SHIPYARD_PR_SERIES,
        SHIPYARD_INDICES,
        SHIPYARD_DR_SERIES,
        SHIPYARD_INDICES,
    ):
        validate_alas_shipyard_config(
            pr_series=pr_series,
            pr_index=pr_index,
            pr_buy_amount=2,
            pr_last_run=DEFAULT_LAST_RUN,
            dr_series=dr_series,
            dr_index=dr_index,
            dr_buy_amount=2,
            dr_last_run=DEFAULT_LAST_RUN,
        )
        accepted += 1
    for pr_buy_amount, dr_buy_amount in itertools.product(
        SHIPYARD_VERIFIED_BUY_AMOUNTS, repeat=2
    ):
        case = _base_contract_case()
        case.update(
            pr_buy_amount=pr_buy_amount,
            dr_buy_amount=dr_buy_amount,
        )
        validate_alas_shipyard_config(**case)
        accepted += 1
    for value in (
        datetime(2000, 1, 1),
        SERVER_UPDATE,
        SERVER_UPDATE + timedelta(seconds=1),
        FROZEN_NOW,
        datetime(2100, 1, 1),
    ):
        case = _base_contract_case()
        case.update(pr_last_run=value, dr_last_run=value)
        validate_alas_shipyard_config(**case)
        accepted += 1
    invalid_count = 0
    invalid = {
        "pr_series": INVALID_PR_SERIES,
        "pr_index": INVALID_INDICES,
        "pr_buy_amount": INVALID_BUY_AMOUNTS,
        "pr_last_run": INVALID_LAST_RUNS,
        "dr_series": INVALID_DR_SERIES,
        "dr_index": INVALID_INDICES,
        "dr_buy_amount": INVALID_BUY_AMOUNTS,
        "dr_last_run": INVALID_LAST_RUNS,
    }
    for field, values in invalid.items():
        for value in values:
            case = _base_contract_case()
            case[field] = value
            try:
                validate_alas_shipyard_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Shipyard {field} was admitted")
    return accepted, invalid_count


def _verify_price_calculation(reward_module: Any) -> dict[str, Any]:
    host = object.__new__(reward_module.RewardShipyard)
    expected = {
        "PR": (
            0, 0, 150, 150, 300, 300, 300, 600, 600, 600,
            1050, 1050, 1050, 1050, 1050, 1500,
        ),
        "DR": (
            0, 0, 600, 600, 600, 600, 1200, 1200, 1200, 1200,
            3000, 3000, 3000, 3000, 3000, 6000,
        ),
    }
    result = {}
    for rarity, prices in expected.items():
        host._shipyard_bp_rarity = rarity
        actual = tuple(host._shipyard_get_cost(index) for index in range(1, 17))
        if actual != prices:
            raise AssertionError(f"original {rarity} Shipyard price schedule drifted")
        total = sum(prices[:15])
        host._coin_count = total
        if host._shipyard_buy_calc(1, 15) != (16, 15):
            raise AssertionError(f"original {rarity} exact-coin boundary drifted")
        host._coin_count = total - 1
        if host._shipyard_buy_calc(1, 15) != (15, 14):
            raise AssertionError(f"original {rarity} insufficient-coin boundary drifted")
        host._coin_count = total
        if host._shipyard_pay_calc(1, 15) != (16, 15) or host._coin_count != 0:
            raise AssertionError(f"original {rarity} payment accounting drifted")
        result[rarity] = {"prices_1_to_16": prices, "total_1_to_15": total}
    return result


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls(*FROZEN_NOW.timetuple()[:6])
        return cls(*FROZEN_NOW.timetuple()[:6], tzinfo=tz)


def _verify_last_run_write(reward_module: Any) -> dict[str, Any]:
    original_datetime = reward_module.datetime
    reward_module.datetime = _FrozenDateTime
    result = {}
    try:
        for rarity, field in (
            ("DR", "ShipyardDr_LastRun"),
            ("PR", "Shipyard_LastRun"),
        ):
            events = []
            host = object.__new__(reward_module.RewardShipyard)
            host.config = _Config(pr_series=1, pr_index=1, dr_series=2, dr_index=1)
            host._shipyard_bp_rarity = rarity
            host._coin_count = 0
            host._shipyard_buy_enter = MethodType(lambda self: True, host)
            host._shipyard_cannot_strengthen = MethodType(lambda self: False, host)
            host._shipyard_ensure_index = MethodType(lambda self, count: 0, host)
            host._shipyard_buy_confirm = MethodType(
                lambda self, mode: events.append(["confirm_stub", mode]), host
            )
            reward_module.RewardShipyard._shipyard_buy(host, 2)
            recorded = getattr(host.config, field)
            if recorded != FROZEN_NOW or events != [["confirm_stub", "BP_BUY"]]:
                raise AssertionError(f"original {rarity} LastRun write drifted")
            result[rarity] = {"last_run": recorded.isoformat(), "events": events}
    finally:
        reward_module.datetime = original_datetime
    return result


def _verify_invalid_entry(reward_module: Any, guard_present: bool) -> dict[str, Any]:
    if not guard_present:
        return {}
    invalid = {
        "Shipyard_ResearchSeries": {"pr_series": 0},
        "Shipyard_ShipIndex": {"pr_index": 7},
        "Shipyard_BuyAmount": {"pr_buy_amount": 16},
        "Shipyard_LastRun": {"pr_last_run": None},
        "ShipyardDr_ResearchSeries": {"dr_series": 1},
        "ShipyardDr_ShipIndex": {"dr_index": -1},
        "ShipyardDr_BuyAmount": {"dr_buy_amount": -1},
        "ShipyardDr_LastRun": {
            "dr_last_run": datetime(2026, 8, 15, tzinfo=timezone.utc)
        },
    }
    result = {}
    for field, override in invalid.items():
        case = _base_contract_case()
        case.update(override)
        try:
            _run_case(reward_module, **case)
        except SemanticGateClosed:
            result[field] = []
        else:
            raise AssertionError(f"patched Shipyard admitted invalid {field}")
    return result


def verify_shipyard_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    reward_path = alas_root / "module/shipyard/shipyard_reward.py"
    ui_path = alas_root / "module/shipyard/ui.py"
    consumers, guard_present = _source_flags(reward_path)
    reward_module, ui_module = _load_original(alas_root)
    focus = _verify_focus_matrix(ui_module)
    dispatch = _verify_dispatch(reward_module)
    accepted, invalid = _verify_contract()
    price_calculation = _verify_price_calculation(reward_module)
    last_run_write = _verify_last_run_write(reward_module)
    invalid_entry = _verify_invalid_entry(reward_module, guard_present)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 8,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "focus_matrix": focus,
        "original_dispatch": dispatch,
        "price_calculation": price_calculation,
        "last_run_write": last_run_write,
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "invalid_entry_events": invalid_entry,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_blueprints_consumed": False,
        "real_coin_consumed": False,
        "real_navigation_performed": False,
        "purchase_confirms_stubbed": True,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "reward": _sha256(reward_path),
            "ui": _sha256(ui_path),
        },
    }
