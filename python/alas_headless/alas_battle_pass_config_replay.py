"""Deterministic replay of the pinned ALAS Battle Pass dispatch switch."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_battle_pass_config_contract import validate_alas_battle_pass_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.battle-pass-config-replay/v1"
INVALID_VALUES = (0, 1, None, "true", "false", [], {})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    path = alas_root / "module/config/argument/args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    group = document.get("Freebies", {}).get("BattlePass")
    if not isinstance(group, dict) or set(group) != {"Collect"}:
        raise AssertionError("BattlePass field surface drifted")
    declaration = group["Collect"]
    if declaration.get("type") != "checkbox" or declaration.get("value") is not True:
        raise AssertionError("BattlePass.Collect declaration drifted")


def _verify_consumer(path: Path) -> tuple[list[str], bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    target = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Freebies"
    )
    run = next(
        node
        for node in target.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    consumers = [
        "run"
        for node in ast.walk(run)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and node.attr == "BattlePass_Collect"
    ]
    if consumers != ["run"]:
        raise AssertionError("BattlePass.Collect consumer surface drifted")
    calls = [
        node
        for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_battle_pass_config"
    ]
    guard = len(calls) == 1
    if guard:
        executable = [
            statement
            for statement in run.body
            if not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ]
        first = executable[0]
        if not (
            isinstance(first, ast.Assign)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "validate_alas_battle_pass_config"
        ):
            raise AssertionError("BattlePass guard is not first in Freebies.run")
    return consumers, guard


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.freebies.freebies")
    finally:
        sys.path.remove(root)


class _Config(SimpleNamespace):
    def __init__(self, *, collect: object):
        super().__init__(
            BattlePass_Collect=collect,
            DataKey_Collect=False,
            DataKey_ForceCollect=False,
            SupplyPack_Collect=False,
            SupplyPack_DayOfWeek=0,
        )
        self.events: list[Any] = []

    def task_delay(self, **kwargs):
        self.events.append(["delay", kwargs])


def _run_case(module: Any, *, collect: object) -> dict[str, Any]:
    config = _Config(collect=collect)
    device = object()
    host = object.__new__(module.Freebies)
    host.config = config
    host.device = device
    events: list[str] = []

    def factory(name: str):
        def create(actual_config, actual_device):
            if actual_config is not config or actual_device is not device:
                raise AssertionError("Freebies child constructor forwarding drifted")
            return SimpleNamespace(run=lambda: events.append(name))

        return create

    names = ("BattlePass", "DataKey", "MailWhite", "SupplyPack_250814")
    originals = {name: getattr(module, name) for name in names}
    for name, event in zip(names, ("battle_pass", "data_key", "mail", "supply_pack")):
        setattr(module, name, factory(event))
    try:
        module.Freebies.run(host)
    finally:
        for name, value in originals.items():
            setattr(module, name, value)
    return {"events": events, "config_events": config.events}


def verify_battle_pass_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    freebies_path = alas_root / "module/freebies/freebies.py"
    consumers, guard = _verify_consumer(freebies_path)
    module = _load_original(alas_root)
    decisions = {
        "disabled": _run_case(module, collect=False),
        "enabled": _run_case(module, collect=True),
    }
    expected_delay = [["delay", {"server_update": True}]]
    if decisions != {
        "disabled": {"events": ["mail"], "config_events": expected_delay},
        "enabled": {
            "events": ["battle_pass", "mail"],
            "config_events": expected_delay,
        },
    }:
        raise AssertionError("original BattlePass dispatch drifted")
    for value in (False, True):
        validate_alas_battle_pass_config(collect=value)
    invalid_count = 0
    for value in INVALID_VALUES:
        try:
            validate_alas_battle_pass_config(collect=value)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid BattlePass.Collect was admitted")
    invalid_entry_events = {}
    if guard:
        try:
            _run_case(module, collect=None)
        except SemanticGateClosed:
            invalid_entry_events["BattlePass_Collect"] = []
        else:
            raise AssertionError("patched Freebies admitted invalid BattlePass.Collect")
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "accepted_case_count": 2,
        "invalid_case_count": invalid_count,
        "runtime_consumers": {"BattlePass_Collect": consumers},
        "patched_guard_present": guard,
        "original_decisions": decisions,
        "invalid_entry_events": invalid_entry_events,
        "mutation_budget": 0,
        "real_battle_pass_run_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "freebies": _sha256(freebies_path),
        },
    }
