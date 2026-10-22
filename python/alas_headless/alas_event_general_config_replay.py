"""Deterministic replay of pinned ALAS event-limit and balancer methods."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_event_general_config_contract import (
    TASK_BALANCER_CALLS,
    validate_alas_event_general_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.event-general-config-replay/v1"
FROZEN_NOW = datetime(2026, 8, 15, 12, 0, 0)
EXPECTED_CONSUMERS = {
    "EventGeneral_PtLimit": {"module/campaign/campaign_event.py"},
    "EventGeneral_TimeLimit": {"module/campaign/campaign_event.py"},
    "TaskBalancer_Enable": {
        "module/campaign/run.py",
        "module/coalition/coalition.py",
        "module/event_hospital/combat.py",
        "module/raid/raid.py",
    },
    "TaskBalancer_CoinLimit": {
        "module/campaign/campaign_event.py",
        "module/combat/auto_search_combat.py",
    },
    "TaskBalancer_TaskCall": {"module/campaign/campaign_event.py"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _defaults() -> dict[str, object]:
    return {
        "pt_limit": 0,
        "time_limit": datetime(2020, 1, 1),
        "task_balancer_enable": False,
        "task_balancer_coin_limit": 10_000,
        "task_balancer_task_call": "Main",
    }


def _verify_args(alas_root: Path) -> None:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panel = document.get("EventGeneral")
    if not isinstance(panel, dict) or set(panel) != {
        "EventGeneral",
        "TaskBalancer",
        "Storage",
    }:
        raise AssertionError("EventGeneral panel surface drifted")
    if tuple(panel["EventGeneral"]) != ("PtLimit", "TimeLimit"):
        raise AssertionError("EventGeneral field surface drifted")
    if tuple(panel["TaskBalancer"]) != ("Enable", "CoinLimit", "TaskCall"):
        raise AssertionError("TaskBalancer field surface drifted")
    if tuple(panel["TaskBalancer"]["TaskCall"].get("option", ())) != TASK_BALANCER_CALLS:
        raise AssertionError("TaskBalancer task-call surface drifted")


def _verify_consumers(alas_root: Path) -> dict[str, list[str]]:
    found = {name: set() for name in EXPECTED_CONSUMERS}
    for relative in sorted(set().union(*EXPECTED_CONSUMERS.values())):
        path = alas_root / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        attributes = set()

        class ConsumerVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                if node.name == "_validate_event_general_config":
                    return
                self.generic_visit(node)

            def visit_Attribute(self, node: ast.Attribute) -> None:
                if isinstance(node.ctx, ast.Load):
                    attributes.add(node.attr)
                self.generic_visit(node)

        ConsumerVisitor().visit(tree)
        for name in found:
            if name in attributes:
                found[name].add(relative)
    if found != EXPECTED_CONSUMERS:
        raise AssertionError("EventGeneral runtime consumer surface drifted")
    return {name: sorted(paths) for name, paths in found.items()}


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.campaign.campaign_event")
        return module, module.CampaignEvent
    finally:
        sys.path.remove(root)


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return tz.fromutc(FROZEN_NOW.replace(tzinfo=tz))
        return cls(*FROZEN_NOW.timetuple()[:6])


class _Config(SimpleNamespace):
    def __init__(self, **values: object):
        super().__init__(**values)
        self.delays = []
        self.calls = []
        self.stops = 0
        self.cross_writes = []

    def task_delay(self, **values: object) -> None:
        self.delays.append(dict(values))

    def task_call(self, task: str) -> None:
        self.calls.append(task)

    def task_stop(self) -> None:
        self.stops += 1

    def multi_set(self):
        return nullcontext()

    def cross_set(self, *, keys: str, value: object) -> None:
        self.cross_writes.append((keys, value))

    def cross_get(self, *, keys: str, default: object) -> object:
        return default


def _config(**overrides: object) -> _Config:
    values = {
        "EventGeneral_PtLimit": 0,
        "EventGeneral_TimeLimit": datetime(2020, 1, 1),
        "TaskBalancer_Enable": False,
        "TaskBalancer_CoinLimit": 10_000,
        "TaskBalancer_TaskCall": "Main",
        "Scheduler_Command": "Event",
        "Campaign_Name": "A1",
    }
    values.update(overrides)
    return _Config(**values)


def _host(event_type: type[Any], config: _Config):
    host = object.__new__(event_type)
    host.config = config
    host.stage_is_main = MethodType(lambda self, name: False, host)
    host.get_event_pt = MethodType(lambda self: 0, host)
    host.get_coin = MethodType(lambda self: 0, host)
    host.is_balancer_task = MethodType(lambda self: True, host)
    host._disable_tasks = MethodType(lambda self, tasks: None, host)
    return host


def _verify_original(module: Any, event_type: type[Any]) -> dict[str, Any]:
    old_datetime = module.datetime
    module.datetime = _FrozenDateTime
    try:
        pt_cases = []
        for limit, pt, command, stage_main, expected in (
            (0, 999_999, "Event", False, False),
            ("100,000", 99_999, "Event", False, False),
            ("100,000", 100_000, "Event", False, True),
            (100_000, 100_000, "Main", False, False),
            (100_000, 100_000, "GemsFarming", True, False),
        ):
            config = _config(EventGeneral_PtLimit=limit, Scheduler_Command=command)
            host = _host(event_type, config)
            disabled = []
            host.get_event_pt = MethodType(lambda self, value=pt: value, host)
            host.stage_is_main = MethodType(
                lambda self, name, value=stage_main: value, host
            )
            host._disable_tasks = MethodType(
                lambda self, tasks: disabled.append(tuple(tasks)), host
            )
            actual = bool(event_type.event_pt_limit_triggered(host))
            if actual is not expected or bool(disabled) is not expected:
                raise AssertionError("original event PT limit decision drifted")
            pt_cases.append(actual)

        time_cases = []
        for limit, command, stage_main, expected in (
            (datetime(2020, 1, 1), "Event", False, False),
            (FROZEN_NOW + timedelta(seconds=1), "Event", False, False),
            (FROZEN_NOW - timedelta(seconds=1), "Event", False, True),
            (FROZEN_NOW - timedelta(seconds=1), "Main", False, False),
            (FROZEN_NOW - timedelta(seconds=1), "GemsFarming", True, False),
        ):
            config = _config(EventGeneral_TimeLimit=limit, Scheduler_Command=command)
            host = _host(event_type, config)
            disabled = []
            host.stage_is_main = MethodType(
                lambda self, name, value=stage_main: value, host
            )
            host._disable_tasks = MethodType(
                lambda self, tasks: disabled.append(tuple(tasks)), host
            )
            actual = bool(event_type.event_time_limit_triggered(host))
            if actual is not expected or bool(disabled) is not expected:
                raise AssertionError("original event time-limit decision drifted")
            time_cases.append(actual)

        coin_cases = []
        for coin, balancer_task, expected in (
            (0, True, False),
            (9_999, True, True),
            (10_000, True, False),
            (20_000, False, False),
        ):
            config = _config(TaskBalancer_Enable=True)
            host = _host(event_type, config)
            host.get_coin = MethodType(lambda self, value=coin: value, host)
            host.is_balancer_task = MethodType(
                lambda self, value=balancer_task: value, host
            )
            actual = bool(event_type.triggered_task_balancer(host))
            if actual is not expected:
                raise AssertionError("original task-balancer coin decision drifted")
            coin_cases.append(actual)

        task_calls = []
        for task in TASK_BALANCER_CALLS:
            config = _config(TaskBalancer_Enable=True, TaskBalancer_TaskCall=task)
            host = _host(event_type, config)
            event_type.handle_task_balancer(host)
            if config.delays != [{"minute": 5}] or config.calls != [task] or config.stops != 1:
                raise AssertionError("original task-balancer result handling drifted")
            task_calls.append(task)

        config = _config()
        host = _host(event_type, config)
        event_task = module.EVENTS[0]
        gems_task = module.GEMS_FARMINGS[0]
        event_type._disable_tasks(host, [event_task, gems_task])
        write_keys = [key for key, value in config.cross_writes]
        if (
            f"{event_task}.Scheduler.Enable" not in write_keys
            or f"{gems_task}.Campaign.Name" not in write_keys
            or "EventGeneral.EventGeneral.TimeLimit" not in write_keys
        ):
            raise AssertionError("original event disable/reset writes drifted")

        return {
            "pt_cases": pt_cases,
            "time_cases": time_cases,
            "coin_cases": coin_cases,
            "task_calls": task_calls,
            "disable_write_keys": write_keys,
        }
    finally:
        module.datetime = old_datetime


def verify_event_general_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    consumers = _verify_consumers(alas_root)
    module, event_type = _load_original(alas_root)
    decisions = _verify_original(module, event_type)

    accepted = 0
    for pt in (0, 1, 100_000, "100,000", "100。000"):
        for enabled in (False, True):
            for task in TASK_BALANCER_CALLS:
                values = _defaults()
                values.update(
                    pt_limit=pt,
                    task_balancer_enable=enabled,
                    task_balancer_task_call=task,
                )
                validate_alas_event_general_config(**values)
                accepted += 1
    invalid_count = 0
    for field, value in (
        ("pt_limit", -1),
        ("pt_limit", True),
        ("pt_limit", "1e5"),
        ("time_limit", "2026-08-15"),
        ("time_limit", datetime(1900, 1, 1)),
        ("task_balancer_enable", 1),
        ("task_balancer_coin_limit", -1),
        ("task_balancer_coin_limit", True),
        ("task_balancer_task_call", "Reward"),
    ):
        values = _defaults()
        values["task_balancer_enable"] = True
        values[field] = value
        try:
            validate_alas_event_general_config(**values)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid EventGeneral value was admitted")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 5,
        "panel_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid_count,
        "runtime_consumers": consumers,
        "original_decisions": decisions,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "campaign_event": _sha256(
                alas_root / "module" / "campaign" / "campaign_event.py"
            ),
        },
    }
