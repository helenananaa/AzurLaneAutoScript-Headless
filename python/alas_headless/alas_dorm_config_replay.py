"""Deterministic replay of pinned ALAS Dorm configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_dorm_config_contract import (
    DORM_FOOD_VALUES,
    parse_alas_dorm_feed_filter,
    validate_alas_dorm_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.dorm-config-replay/v1"
DEFAULT_FILTER = "20000 > 10000 > 5000 > 3000 > 2000 > 1000"
INVALID_BOOL_VALUES = (0, 1, None, "true", [], {})
INVALID_FILTER_VALUES = (
    None,
    True,
    1,
    "",
    "unknown",
    "1000 >> 2000",
    "1000 > 1000",
    "4000",
    "01000",
    "1000x",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_food_orders():
    for length in range(1, len(DORM_FOOD_VALUES) + 1):
        yield from itertools.permutations(DORM_FOOD_VALUES, length)


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    group = document.get("Dorm", {}).get("Dorm")
    expected = {
        "Collect": ("checkbox", True),
        "Feed": ("checkbox", True),
        "FeedFilter": ("textarea", DEFAULT_FILTER),
    }
    if not isinstance(group, dict) or set(group) != set(expected):
        raise AssertionError("Dorm field surface drifted")
    for field, (kind, default) in expected.items():
        declaration = group[field]
        if declaration.get("type") != kind or declaration.get("value") != default:
            raise AssertionError(f"Dorm.{field} declaration drifted")


def _source_flags(path: Path) -> tuple[dict[str, list[str]], bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    expected = {
        "Dorm_Collect": {"_run_alas_state_machine"},
        "Dorm_Feed": {"_run_alas_state_machine"},
        "Dorm_FeedFilter": {"dorm_feed_once"},
    }
    consumers: dict[str, list[str]] = {}
    run = None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "RewardDorm":
            continue
        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            if child.name == "run":
                run = child
            for field in expected:
                if any(
                    isinstance(item, ast.Attribute)
                    and isinstance(item.ctx, ast.Load)
                    and item.attr == field
                    for item in ast.walk(child)
                ):
                    consumers.setdefault(field, []).append(child.name)
    if run is None:
        raise AssertionError("RewardDorm.run is missing")
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_dorm_config"
        for node in ast.walk(run)
    )
    expected_consumers = {
        field: methods | ({"run"} if guard_present else set())
        for field, methods in expected.items()
    }
    normalized = {field: sorted(consumers.get(field, [])) for field in expected}
    if normalized != {
        field: sorted(methods) for field, methods in expected_consumers.items()
    }:
        raise AssertionError("Dorm configuration consumer surface drifted")
    if guard_present:
        executable = [
            statement
            for statement in run.body
            if not isinstance(statement, (ast.Import, ast.ImportFrom))
        ]
        first = executable[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "validate_alas_dorm_config"
        ):
            raise AssertionError("Dorm configuration guard is not first in run")
    return normalized, guard_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.dorm.dorm")
    finally:
        sys.path.remove(root)


class _TaskStopped(RuntimeError):
    pass


class _Config(SimpleNamespace):
    def __init__(self, *, collect: object, feed: object, feed_filter: object):
        super().__init__(
            Dorm_Collect=collect,
            Dorm_Feed=feed,
            Dorm_FeedFilter=feed_filter,
            BuyFurniture_Enable=False,
            BuyFurniture_BuyOption="all",
            BuyFurniture_LastRun=datetime(2020, 1, 1),
            Scheduler_Enable=True,
            Scheduler_SuccessInterval=278,
        )
        self.events: list[Any] = []

    def task_stop(self):
        self.events.append("task_stop")
        raise _TaskStopped

    def task_delay(self, **kwargs):
        self.events.append(["task_delay", kwargs])


def _state_machine_case(module: Any, *, collect: bool, feed: bool) -> dict[str, Any]:
    config = _Config(collect=collect, feed=feed, feed_filter=DEFAULT_FILTER)
    host = object.__new__(module.RewardDorm)
    host.config = config
    events = []
    host.dorm_run = MethodType(
        lambda self, **kwargs: events.append(["dorm_run", kwargs]), host
    )
    host.get_dorm_ship_amount = MethodType(lambda self: 3, host)
    try:
        module.RewardDorm._run_alas_state_machine(host)
    except _TaskStopped:
        stopped = True
    else:
        stopped = False
    return {
        "stopped": stopped,
        "scheduler_enabled": config.Scheduler_Enable,
        "events": events + config.events,
    }


def _verify_state_machine(module: Any) -> dict[str, Any]:
    result = {}
    for collect, feed in itertools.product((False, True), repeat=2):
        key = f"{int(collect)}{int(feed)}"
        case = _state_machine_case(module, collect=collect, feed=feed)
        if not collect and not feed:
            expected = {
                "stopped": True,
                "scheduler_enabled": False,
                "events": ["task_stop"],
            }
        else:
            expected = {
                "stopped": False,
                "scheduler_enabled": True,
                "events": [
                    [
                        "dorm_run",
                        {
                            "feed": feed,
                            "collect": collect,
                            "buy_furniture": False,
                        },
                    ],
                    ["task_delay", {"minute": 417}],
                ],
            }
        if case != expected:
            raise AssertionError("original Dorm switch decision drifted")
        result[key] = case
    return result


def _verify_filter_orders(module: Any) -> int:
    foods = [module.Food(feed=value, amount=1) for value in DORM_FOOD_VALUES]
    count = 0
    for order in _all_food_orders():
        text = " > ".join(str(value) for value in order)
        if parse_alas_dorm_feed_filter(text) != order:
            raise AssertionError("Dorm filter contract order drifted")
        module.FOOD_FILTER.load(text)
        selected = tuple(item.feed for item in module.FOOD_FILTER.apply(foods))
        if selected != order:
            raise AssertionError("original Dorm food filter order drifted")
        count += 1
    unicode_text = "20000 ＞ 10000﹥5000 › 3000˃2000 ᐳ 1000"
    if parse_alas_dorm_feed_filter(unicode_text) != (
        20000,
        10000,
        5000,
        3000,
        2000,
        1000,
    ):
        raise AssertionError("Dorm unicode filter separator drifted")
    return count


def _feed_once_case(
    module: Any, *, feed_filter: str, foods: list[tuple[int, int]], fill: int
) -> dict[str, Any]:
    host = object.__new__(module.RewardDorm)
    host.config = SimpleNamespace(Dorm_FeedFilter=feed_filter)
    host.device = SimpleNamespace()
    host._dorm_food = SimpleNamespace(buttons=list(range(len(foods))))
    host.loop = MethodType(lambda self: iter((None,)), host)
    host.handle_info_bar = MethodType(lambda self: False, host)
    host.dorm_food_get = MethodType(
        lambda self: (
            [module.Food(feed=value, amount=amount) for value, amount in foods],
            fill,
        ),
        host,
    )
    events = []
    host._dorm_feed_click = MethodType(
        lambda self, *, button, count: events.append([button, count]), host
    )
    executed = module.RewardDorm.dorm_feed_once(host)
    return {"executed": bool(executed), "clicks": events}


def _verify_feed_boundaries(module: Any) -> dict[str, Any]:
    cases = {
        "strict_fill_boundary": _feed_once_case(
            module,
            feed_filter="20000",
            foods=[(20000, 3)],
            fill=20000,
        ),
        "one_above_boundary": _feed_once_case(
            module,
            feed_filter="20000",
            foods=[(20000, 3)],
            fill=20001,
        ),
        "skip_empty_priority": _feed_once_case(
            module,
            feed_filter="20000 > 10000",
            foods=[(20000, 0), (10000, 2)],
            fill=25000,
        ),
        "no_available_food": _feed_once_case(
            module,
            feed_filter="1000 > 2000",
            foods=[(1000, 0), (2000, 0)],
            fill=25000,
        ),
    }
    expected = {
        "strict_fill_boundary": {"executed": False, "clicks": []},
        "one_above_boundary": {"executed": True, "clicks": [[0, 1]]},
        "skip_empty_priority": {"executed": True, "clicks": [[1, 2]]},
        "no_available_food": {"executed": False, "clicks": []},
    }
    if cases != expected:
        raise AssertionError("original Dorm feed boundary drifted")
    return cases


def _verify_contract() -> tuple[int, int]:
    order_count = 0
    for order in _all_food_orders():
        text = ">".join(str(value) for value in order)
        for collect, feed in itertools.product((False, True), repeat=2):
            snapshot = validate_alas_dorm_config(
                collect=collect,
                feed=feed,
                feed_filter=text,
            )
            if snapshot.feed_order != (order if feed else ()):
                raise AssertionError("Dorm accepted configuration drifted")
        order_count += 1
    invalid_count = 0
    for field in ("collect", "feed"):
        for value in INVALID_BOOL_VALUES:
            case = {"collect": True, "feed": True, "feed_filter": DEFAULT_FILTER}
            case[field] = value
            try:
                validate_alas_dorm_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Dorm.{field} was admitted")
    for value in INVALID_FILTER_VALUES:
        try:
            validate_alas_dorm_config(
                collect=True,
                feed=True,
                feed_filter=value,
            )
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid Dorm.FeedFilter was admitted")
    return order_count * 4, invalid_count


def _entry_case(
    module: Any, *, collect: object, feed: object, feed_filter: object
) -> list[Any]:
    events = []
    session = SimpleNamespace(
        begin_dorm=lambda: events.append("begin_dorm"),
        end_dorm=lambda: events.append("end_dorm"),
    )
    host = object.__new__(module.RewardDorm)
    host.config = _Config(collect=collect, feed=feed, feed_filter=feed_filter)
    host.device = SimpleNamespace(semantic_adapter=session)
    host._run_alas_state_machine = MethodType(
        lambda self: events.append("state_machine"), host
    )
    module.RewardDorm.run(host)
    return events


def _verify_entry(module: Any, guard_present: bool) -> dict[str, Any]:
    if not guard_present:
        return {"valid": {}, "invalid": {}}
    valid = {}
    for collect, feed in itertools.product((False, True), repeat=2):
        key = f"{int(collect)}{int(feed)}"
        events = _entry_case(
            module,
            collect=collect,
            feed=feed,
            feed_filter=DEFAULT_FILTER,
        )
        if events != ["begin_dorm", "state_machine", "end_dorm"]:
            raise AssertionError("valid Dorm entry dispatch drifted")
        valid[key] = events
    invalid = {}
    cases = {
        "Dorm_Collect": (None, True, DEFAULT_FILTER),
        "Dorm_Feed": (True, None, DEFAULT_FILTER),
        "Dorm_FeedFilter": (True, True, "unknown"),
    }
    for field, (collect, feed, feed_filter) in cases.items():
        try:
            _entry_case(
                module,
                collect=collect,
                feed=feed,
                feed_filter=feed_filter,
            )
        except SemanticGateClosed:
            invalid[field] = []
        else:
            raise AssertionError(f"patched Dorm admitted invalid {field}")
    return {"valid": valid, "invalid": invalid}


def verify_dorm_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    source = alas_root / "module/dorm/dorm.py"
    consumers, guard_present = _source_flags(source)
    module = _load_original(alas_root)
    switch_decisions = _verify_state_machine(module)
    filter_order_count = _verify_filter_orders(module)
    feed_boundaries = _verify_feed_boundaries(module)
    accepted_count, invalid_count = _verify_contract()
    entry = _verify_entry(module, guard_present)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted_count,
        "food_order_count": filter_order_count,
        "invalid_case_count": invalid_count,
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "original_switch_decisions": switch_decisions,
        "original_feed_boundaries": feed_boundaries,
        "entry_decisions": entry,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_collect_called": False,
        "real_feed_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "dorm": _sha256(source),
        },
    }
