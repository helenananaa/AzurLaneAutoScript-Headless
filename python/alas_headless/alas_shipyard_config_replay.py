"""Deterministic replay of pinned ALAS Shipyard focus configuration."""

from __future__ import annotations

import ast
from datetime import datetime
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
    validate_alas_shipyard_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.shipyard-config-replay/v1"
INVALID_PR_SERIES = (0, 7, True, 1.0, "1", None, [])
INVALID_DR_SERIES = (1, 6, True, 2.0, "2", None, [])
INVALID_INDICES = (-1, 7, True, 1.0, "1", None, [])


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
        },
        "ShipyardDr": {
            "ResearchSeries": (2, SHIPYARD_DR_SERIES),
            "ShipIndex": (0, SHIPYARD_INDICES),
        },
    }
    for group_name, fields in expected.items():
        group = document.get("Shipyard", {}).get(group_name)
        if not isinstance(group, dict):
            raise AssertionError(f"{group_name} field surface is missing")
        for field, (default, options) in fields.items():
            declaration = group.get(field)
            if (
                not isinstance(declaration, dict)
                or declaration.get("type") != "select"
                or declaration.get("value") != default
                or tuple(declaration.get("option", ())) != options
            ):
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
        "ShipyardDr_ResearchSeries": [],
        "ShipyardDr_ShipIndex": [],
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
        dr_series: object,
        dr_index: object,
    ):
        super().__init__(
            Shipyard_ResearchSeries=pr_series,
            Shipyard_ShipIndex=pr_index,
            ShipyardDr_ResearchSeries=dr_series,
            ShipyardDr_ShipIndex=dr_index,
            Shipyard_BuyAmount=1,
            ShipyardDr_BuyAmount=1,
            Shipyard_LastRun=datetime(2020, 1, 1),
            ShipyardDr_LastRun=datetime(2020, 1, 1),
            Scheduler_Enable=True,
        )
        self.events = []

    def task_delay(self, **kwargs):
        self.events.append(["task_delay", kwargs])

    def task_stop(self):
        self.events.append("task_stop")


def _run_case(
    reward_module: Any,
    *,
    pr_series: object,
    pr_index: object,
    dr_series: object,
    dr_index: object,
) -> list[Any]:
    events = []
    host = object.__new__(reward_module.RewardShipyard)
    host.config = _Config(
        pr_series=pr_series,
        pr_index=pr_index,
        dr_series=dr_series,
        dr_index=dr_index,
    )
    host.shipyard_run = MethodType(
        lambda self, series, index, count: events.append(
            [self._shipyard_bp_rarity, series, index, count]
        )
        or True,
        host,
    )
    original_update = reward_module.get_server_last_update
    reward_module.get_server_last_update = lambda value: datetime(2026, 8, 15)
    try:
        reward_module.RewardShipyard.run(host)
    finally:
        reward_module.get_server_last_update = original_update
    return events + host.config.events


def _verify_dispatch(reward_module: Any) -> dict[str, Any]:
    samples = {
        "normal": (1, 1, 2, 1),
        "disabled_indices": (6, 0, 5, 0),
        "restricted_indices": (3, 6, 3, 6),
    }
    result = {}
    logger_methods = {
        name: getattr(reward_module.logger, name) for name in ("hr", "attr", "warning")
    }
    for name in logger_methods:
        setattr(reward_module.logger, name, lambda *args, **kwargs: None)
    try:
        for name, (pr_series, pr_index, dr_series, dr_index) in samples.items():
            events = _run_case(
                reward_module,
                pr_series=pr_series,
                pr_index=pr_index,
                dr_series=dr_series,
                dr_index=dr_index,
            )
            expected = [
                ["DR", dr_series, dr_index, 1],
                ["PR", pr_series, pr_index, 1],
                ["task_delay", {"server_update": True}],
            ]
            if events != expected:
                raise AssertionError("original Shipyard run dispatch drifted")
            result[name] = events
    finally:
        for name, value in logger_methods.items():
            setattr(reward_module.logger, name, value)
    return result


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
            dr_series=dr_series,
            dr_index=dr_index,
        )
        accepted += 1
    invalid_count = 0
    invalid = {
        "pr_series": INVALID_PR_SERIES,
        "pr_index": INVALID_INDICES,
        "dr_series": INVALID_DR_SERIES,
        "dr_index": INVALID_INDICES,
    }
    for field, values in invalid.items():
        for value in values:
            case = {"pr_series": 1, "pr_index": 1, "dr_series": 2, "dr_index": 1}
            case[field] = value
            try:
                validate_alas_shipyard_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Shipyard {field} was admitted")
    return accepted, invalid_count


def _verify_invalid_entry(reward_module: Any, guard_present: bool) -> dict[str, Any]:
    if not guard_present:
        return {}
    invalid = {
        "Shipyard_ResearchSeries": {"pr_series": 0},
        "Shipyard_ShipIndex": {"pr_index": 7},
        "ShipyardDr_ResearchSeries": {"dr_series": 1},
        "ShipyardDr_ShipIndex": {"dr_index": -1},
    }
    result = {}
    for field, override in invalid.items():
        case = {"pr_series": 1, "pr_index": 1, "dr_series": 2, "dr_index": 1}
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
    invalid_entry = _verify_invalid_entry(reward_module, guard_present)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 4,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "focus_matrix": focus,
        "original_dispatch": dispatch,
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "invalid_entry_events": invalid_entry,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_blueprints_consumed": False,
        "real_coin_consumed": False,
        "real_navigation_performed": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "reward": _sha256(reward_path),
            "ui": _sha256(ui_path),
        },
    }
