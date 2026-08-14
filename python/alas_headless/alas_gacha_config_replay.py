"""Deterministic replay of pinned ALAS Gacha configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_gacha_config_contract import (
    GACHA_AMOUNTS,
    GACHA_POOLS,
    validate_alas_gacha_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.gacha-config-replay/v1"
INVALID_POOLS = (None, True, 1, "", "unknown", [])
INVALID_AMOUNTS = (0, 11, True, 1.0, "1", None, [])
INVALID_BOOLEANS = (None, 0, 1, "true", [], {})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    group = document.get("Gacha", {}).get("Gacha")
    if not isinstance(group, dict):
        raise AssertionError("Gacha field surface is missing")
    expected = {
        "Pool": ("select", "light", GACHA_POOLS),
        "Amount": ("select", 1, GACHA_AMOUNTS),
        "UseTicket": ("checkbox", True, None),
        "UseDrill": ("checkbox", False, None),
    }
    for field, (kind, default, options) in expected.items():
        declaration = group.get(field)
        if (
            not isinstance(declaration, dict)
            or declaration.get("type") != kind
            or declaration.get("value") != default
        ):
            raise AssertionError(f"Gacha.{field} declaration drifted")
        if options is not None and tuple(declaration.get("option", ())) != options:
            raise AssertionError(f"Gacha.{field} options drifted")


def _source_flags(path: Path) -> tuple[dict[str, list[str]], bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "RewardGacha"
        ),
        None,
    )
    if target is None:
        raise AssertionError("RewardGacha is missing")
    methods = {
        node.name: node for node in target.body if isinstance(node, ast.FunctionDef)
    }
    run = methods.get("run")
    gacha_run = methods.get("gacha_run")
    if run is None or gacha_run is None:
        raise AssertionError("Gacha run surface is missing")
    fields = (
        "Gacha_Pool",
        "Gacha_Amount",
        "Gacha_UseTicket",
        "Gacha_UseDrill",
    )
    mapping = {field: [] for field in fields}
    for name, method in (("gacha_run", gacha_run), ("run", run)):
        for field in fields:
            if any(
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and node.attr == field
                for node in ast.walk(method)
            ):
                mapping[field].append(name)
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_gacha_config"
        for node in ast.walk(run)
    )
    expected = {
        field: ["gacha_run", "run"] if guard_present else ["gacha_run"]
        for field in fields
    }
    if mapping != expected:
        raise AssertionError(f"Gacha consumer surface drifted: {mapping!r}")
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
            and first.value.func.id == "validate_alas_gacha_config"
        ):
            raise AssertionError("Gacha configuration guard is not first in run")
    return mapping, guard_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.gacha.gacha_reward")
    finally:
        sys.path.remove(root)


def _pool_case(module: Any, pool: str, *, event_available=True, wishing_available=True, wishing_configured=False):
    events = []
    host = object.__new__(module.RewardGacha)
    host.__dict__["_gacha_side_navbar"] = SimpleNamespace(
        get_total=lambda main: 5 if wishing_available else 4
    )
    host._gacha_bottom_navbar = MethodType(
        lambda self, is_build=True: SimpleNamespace(
            get_total=lambda main: 4 if event_available else 3
        ),
        host,
    )
    host.gacha_bottom_navbar_ensure = MethodType(
        lambda self, left=None, right=None, is_build=True: events.append(
            ["bottom", left, right]
        )
        or True,
        host,
    )
    host.gacha_side_navbar_ensure = MethodType(
        lambda self, upper=None, bottom=None: events.append(
            ["side", upper, bottom]
        )
        or True,
        host,
    )
    host.appear = MethodType(lambda self, button: wishing_configured, host)
    try:
        actual = module.RewardGacha.gacha_goto_pool(host, pool)
    except module.ScriptError:
        return {"result": "rejected_configured_wishing_well", "events": events}
    return {"result": actual, "events": events}


def _verify_pool_routing(module: Any) -> dict[str, Any]:
    available = {pool: _pool_case(module, pool) for pool in GACHA_POOLS}
    expected = {
        "light": "light",
        "heavy": "heavy",
        "special": "special",
        "event": "event",
        "wishing_well": "wishing_well",
    }
    if {key: value["result"] for key, value in available.items()} != expected:
        raise AssertionError("original Gacha pool routing drifted")
    event_fallback = _pool_case(module, "event", event_available=False)
    wishing_fallback = _pool_case(module, "wishing_well", wishing_available=False)
    wishing_rejected = _pool_case(
        module,
        "wishing_well",
        wishing_available=True,
        wishing_configured=True,
    )
    if event_fallback["result"] != "light" or wishing_fallback["result"] != "light":
        raise AssertionError("original Gacha unavailable-pool fallback drifted")
    if wishing_rejected["result"] != "rejected_configured_wishing_well":
        raise AssertionError("original configured wishing-well refusal drifted")
    return {
        "available": available,
        "event_fallback": event_fallback,
        "wishing_fallback": wishing_fallback,
        "wishing_rejected": wishing_rejected,
    }


def _verify_resource_calculation(module: Any) -> dict[str, Any]:
    cases = {
        "light_exact": (3, 1_800, 3, 600, 1, 3, 0, 0),
        "coin_limited": (3, 1_200, 10, 600, 1, 2, 0, 8),
        "cube_insufficient": (3, 10_000, 1, 1_500, 2, 0, 10_000, 1),
        "zero": (0, 10_000, 10, 600, 1, 0, 10_000, 10),
    }
    result = {}
    for name, (target, coins, cubes, gold_cost, cube_cost, expected, remain_coins, remain_cubes) in cases.items():
        host = object.__new__(module.RewardGacha)
        host.build_coin_count = coins
        host.build_cube_count = cubes
        actual = module.RewardGacha.gacha_calculate(
            host, target, gold_cost, cube_cost
        )
        if (
            actual != expected
            or host.build_coin_count != remain_coins
            or host.build_cube_count != remain_cubes
        ):
            raise AssertionError("original Gacha affordability calculation drifted")
        result[name] = [actual, host.build_coin_count, host.build_cube_count]
    return result


class _Config(SimpleNamespace):
    def __init__(self, *, pool: object, amount: object, use_ticket: object, use_drill: object):
        super().__init__(
            Gacha_Pool=pool,
            Gacha_Amount=amount,
            Gacha_UseTicket=use_ticket,
            Gacha_UseDrill=use_drill,
        )
        self.events = []

    def task_delay(self, **kwargs):
        self.events.append(["task_delay", kwargs])


def _decision_case(module: Any, *, pool: str, amount: int, use_ticket: bool, use_drill: bool):
    events = []
    host = object.__new__(module.RewardGacha)
    host.config = _Config(
        pool=pool,
        amount=amount,
        use_ticket=use_ticket,
        use_drill=use_drill,
    )
    host.device = SimpleNamespace(image=object())
    host.build_ticket_count = 0
    host.ui_goto_gacha = MethodType(lambda self: events.append("goto"), host)
    host.gacha_flush_queue = MethodType(lambda self: events.append("flush"), host)
    host.gacha_goto_pool = MethodType(
        lambda self, target: events.append(["pool", target]) or target, host
    )
    host.appear = MethodType(lambda self, button, offset=None: True, host)
    host.gacha_calculate = MethodType(
        lambda self, target, gold, cube: events.append(
            ["calculate", target, gold, cube]
        )
        or target,
        host,
    )
    host.gacha_prep = MethodType(
        lambda self, count: events.append(["prep", count]) or count > 0, host
    )
    host.gacha_submit = MethodType(lambda self: events.append("submit"), host)
    original_coin = module.OCR_COIN
    original_cube = module.OCR_BUILD_CUBE_COUNT
    original_ticket = module.OCR_BUILD_TICKET_COUNT
    module.OCR_COIN = SimpleNamespace(ocr=lambda image: 1_000_000)
    module.OCR_BUILD_CUBE_COUNT = SimpleNamespace(ocr=lambda image: 1_000)
    module.OCR_BUILD_TICKET_COUNT = SimpleNamespace(ocr=lambda image: 3)
    try:
        result = module.RewardGacha.gacha_run(host)
    finally:
        module.OCR_COIN = original_coin
        module.OCR_BUILD_CUBE_COUNT = original_cube
        module.OCR_BUILD_TICKET_COUNT = original_ticket
    ticket_count = min(3, amount) if pool == "event" and use_ticket else 0
    cube_count = amount - ticket_count
    expected = ["goto", "flush", ["pool", pool]]
    if cube_count:
        costs = (600, 1) if pool == "light" else (1_500, 2)
        expected.append(["calculate", cube_count, *costs])
    for count in (ticket_count, cube_count):
        expected.append(["prep", count])
        if count:
            expected.append("submit")
            if use_drill:
                expected.append("flush")
    if events != expected or bool(result) is not True:
        raise AssertionError("original Gacha configuration decision drifted")
    return events


def _verify_decision_matrix(module: Any) -> dict[str, int]:
    count = 0
    split_submissions = 0
    logger_methods = {
        name: getattr(module.logger, name) for name in ("info", "warning")
    }
    for name in logger_methods:
        setattr(module.logger, name, lambda *args, **kwargs: None)
    try:
        for pool, amount, use_ticket, use_drill in itertools.product(
            GACHA_POOLS, GACHA_AMOUNTS, (False, True), (False, True)
        ):
            events = _decision_case(
                module,
                pool=pool,
                amount=amount,
                use_ticket=use_ticket,
                use_drill=use_drill,
            )
            count += 1
            if events.count("submit") == 2:
                split_submissions += 1
    finally:
        for name, value in logger_methods.items():
            setattr(module.logger, name, value)
    return {"cases": count, "ticket_cube_split_cases": split_submissions}


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    for pool, amount, use_ticket, use_drill in itertools.product(
        GACHA_POOLS, GACHA_AMOUNTS, (False, True), (False, True)
    ):
        validate_alas_gacha_config(
            pool=pool,
            amount=amount,
            use_ticket=use_ticket,
            use_drill=use_drill,
        )
        accepted += 1
    invalid_count = 0
    invalid = {
        "pool": INVALID_POOLS,
        "amount": INVALID_AMOUNTS,
        "use_ticket": INVALID_BOOLEANS,
        "use_drill": INVALID_BOOLEANS,
    }
    for field, values in invalid.items():
        for value in values:
            case = {"pool": "light", "amount": 1, "use_ticket": True, "use_drill": False}
            case[field] = value
            try:
                validate_alas_gacha_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Gacha.{field} was admitted")
    return accepted, invalid_count


class _Scope:
    def __init__(self, events: list[Any]):
        self.events = events

    def begin_build(self):
        self.events.append("begin_build")

    def end_build(self):
        self.events.append("end_build")


def _entry_case(module: Any, **values: object) -> list[Any]:
    events = []
    host = object.__new__(module.RewardGacha)
    host.config = _Config(**values)
    host.device = SimpleNamespace(semantic_adapter=_Scope(events))
    host._run_alas_state_machine = MethodType(
        lambda self: events.append("state_machine"), host
    )
    module.RewardGacha.run(host)
    return events


def _verify_entry(module: Any, guard_present: bool) -> dict[str, Any]:
    if not guard_present:
        return {}
    valid = {"pool": "light", "amount": 1, "use_ticket": True, "use_drill": False}
    events = _entry_case(module, **valid)
    if events != ["begin_build", "state_machine", "end_build"]:
        raise AssertionError("valid Gacha entry dispatch drifted")
    result = {"valid": events}
    invalid = {
        "Gacha_Pool": {"pool": "unknown"},
        "Gacha_Amount": {"amount": 0},
        "Gacha_UseTicket": {"use_ticket": 1},
        "Gacha_UseDrill": {"use_drill": None},
    }
    for field, override in invalid.items():
        case = dict(valid)
        case.update(override)
        try:
            _entry_case(module, **case)
        except SemanticGateClosed:
            result[field] = []
        else:
            raise AssertionError(f"patched Gacha admitted invalid {field}")
    return result


def verify_gacha_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    source = alas_root / "module/gacha/gacha_reward.py"
    consumers, guard_present = _source_flags(source)
    module = _load_original(alas_root)
    pool_routing = _verify_pool_routing(module)
    affordability = _verify_resource_calculation(module)
    decisions = _verify_decision_matrix(module)
    accepted, invalid = _verify_contract()
    entry = _verify_entry(module, guard_present)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 4,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "pool_routing": pool_routing,
        "resource_calculation": affordability,
        "decision_matrix": decisions,
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "entry_events": entry,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_build_submitted": False,
        "real_ticket_consumed": False,
        "real_cube_consumed": False,
        "real_coin_consumed": False,
        "real_drill_consumed": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "gacha_reward": _sha256(source),
        },
    }
