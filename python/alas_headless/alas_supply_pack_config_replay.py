"""Deterministic replay of ALAS free weekly supply-pack decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_supply_pack_config_contract import validate_alas_supply_pack_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.supply-pack-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> dict[str, object]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panel = document.get("Freebies")
    group = panel.get("SupplyPack") if isinstance(panel, dict) else None
    if not isinstance(group, dict) or set(group) != {"Collect", "DayOfWeek"}:
        raise AssertionError("SupplyPack field surface drifted")
    if group["Collect"].get("type") != "checkbox" or group["Collect"].get(
        "value"
    ) is not True:
        raise AssertionError("SupplyPack.Collect surface drifted")
    if (
        group["DayOfWeek"].get("type") != "select"
        or group["DayOfWeek"].get("option") != list(range(7))
        or group["DayOfWeek"].get("value") != 0
    ):
        raise AssertionError("SupplyPack.DayOfWeek surface drifted")
    return {"Collect": True, "DayOfWeek": 0}


def _verify_consumers(freebies_path: Path, supply_path: Path) -> dict[str, list[str]]:
    consumers: dict[str, list[str]] = {
        "SupplyPack.Collect": [],
        "SupplyPack.DayOfWeek": [],
        "patched_guards": [],
    }
    for path, class_name in (
        (freebies_path, "Freebies"),
        (supply_path, "SupplyPack"),
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        run = next(
            node
            for node in owner.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        attributes = {
            node.attr for node in ast.walk(run) if isinstance(node, ast.Attribute)
        }
        for field in ("Collect", "DayOfWeek"):
            if f"SupplyPack_{field}" not in attributes:
                raise AssertionError(f"SupplyPack.{field} {class_name}.run drifted")
            consumers[f"SupplyPack.{field}"].append(f"{class_name}.run")
        calls = {
            node.func.id
            for node in ast.walk(run)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        if "validate_alas_supply_pack_config" in calls:
            consumers["patched_guards"].append(f"{class_name}.run")
    if len(consumers["patched_guards"]) != 2:
        raise AssertionError("SupplyPack guards are not present at both entries")
    return consumers


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        freebies = importlib.import_module("module.freebies.freebies")
        supply = importlib.import_module("module.freebies.supply_pack")
        return freebies, supply, freebies.Freebies, supply.SupplyPack
    finally:
        sys.path.remove(root)


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for collect in (False, True):
        for day in range(7):
            snapshot = validate_alas_supply_pack_config(
                collect=collect, day_of_week=day
            )
            if snapshot.collect is not collect or snapshot.day_of_week != day:
                raise AssertionError("SupplyPack canonical values drifted")
            accepted += 1
    for value in (0, 1, "true", None):
        try:
            validate_alas_supply_pack_config(collect=value, day_of_week=0)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid SupplyPack.Collect was admitted")
    for value in (-1, 7, True, "0", 0.0, None):
        try:
            validate_alas_supply_pack_config(collect=True, day_of_week=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid SupplyPack.DayOfWeek was admitted")
    return accepted, invalid


class ReplayConfig:
    def __init__(self, *, collect: object, day: object):
        self.SupplyPack_Collect = collect
        self.SupplyPack_DayOfWeek = day
        self.BattlePass_Collect = False
        self.DataKey_Collect = False
        self.DataKey_ForceCollect = False
        self.events: list[tuple[Any, ...]] = []

    def task_delay(self, **kwargs: object) -> None:
        self.events.append(("delay", kwargs))


def _freebies_case(
    module: Any,
    freebies_type: type[Any],
    *,
    collect: object,
    day: object,
) -> dict[str, Any]:
    events: list[str] = []

    def recorder(name: str):
        class Recorded:
            def __init__(self, config: object, device: object):
                pass

            def run(self) -> None:
                events.append(name)

        return Recorded

    old = {
        name: getattr(module, name)
        for name in ("BattlePass", "DataKey", "MailWhite", "SupplyPack_250814")
    }
    module.BattlePass = recorder("battle_pass")
    module.DataKey = recorder("data_key")
    module.MailWhite = recorder("mail")
    module.SupplyPack_250814 = recorder("supply_pack")
    host = object.__new__(freebies_type)
    host.config = ReplayConfig(collect=collect, day=day)
    host.device = object()
    try:
        freebies_type.run(host)
    finally:
        for name, value in old.items():
            setattr(module, name, value)
    return {"calls": events, "config_events": host.config.events}


def _invalid_freebies_case(
    module: Any,
    freebies_type: type[Any],
    *,
    collect: object = True,
    day: object = 0,
) -> list[str]:
    events = []

    class Recorded:
        def __init__(self, config: object, device: object):
            pass

        def run(self) -> None:
            events.append("called")

    old_mail = module.MailWhite
    module.MailWhite = Recorded
    host = object.__new__(freebies_type)
    host.config = ReplayConfig(collect=collect, day=day)
    host.device = object()
    try:
        freebies_type.run(host)
    except SemanticGateClosed:
        pass
    else:
        raise AssertionError("invalid SupplyPack config entered Freebies state machine")
    finally:
        module.MailWhite = old_mail
    if events or host.config.events:
        raise AssertionError("invalid SupplyPack config caused a mutation")
    return events


def _supply_case(
    module: Any,
    supply_type: type[Any],
    *,
    day: int,
    today: int,
    oil: int,
) -> dict[str, Any]:
    host = object.__new__(supply_type)
    host.config = ReplayConfig(collect=True, day=day)
    host.device = SimpleNamespace(semantic_adapter=None)
    events: list[tuple[Any, ...]] = []
    host.ui_ensure = lambda page: events.append(("ui_ensure",))
    host.goto_supply_pack = lambda: events.append(("goto",))
    host.get_oil = lambda: oil
    host.supply_pack_buy = lambda button: events.append(("buy_candidate",)) or True
    old_weekday = module.get_server_weekday
    module.get_server_weekday = lambda: today
    try:
        supply_type.run(host)
    finally:
        module.get_server_weekday = old_weekday
    return {
        "events": events,
        "buy_candidates": sum(event[0] == "buy_candidate" for event in events),
    }


def _verify_original(
    freebies_module: Any,
    supply_module: Any,
    freebies_type: type[Any],
    supply_type: type[Any],
) -> dict[str, Any]:
    enabled = _freebies_case(
        freebies_module, freebies_type, collect=True, day=0
    )
    disabled = _freebies_case(
        freebies_module, freebies_type, collect=False, day=6
    )
    if enabled["calls"] != ["mail", "supply_pack"]:
        raise AssertionError("enabled SupplyPack Freebies order drifted")
    if disabled["calls"] != ["mail"]:
        raise AssertionError("disabled SupplyPack Freebies branch drifted")
    expected_delay = [("delay", {"server_update": True})]
    if enabled["config_events"] != expected_delay or disabled[
        "config_events"
    ] != expected_delay:
        raise AssertionError("Freebies scheduler tail drifted")
    weekday_cases = {
        str(day): _supply_case(
            supply_module, supply_type, day=day, today=3, oil=1_000
        )
        for day in range(7)
    }
    for day, case in ((int(day), case) for day, case in weekday_cases.items()):
        expected = 1 if day <= 3 else 0
        if case["buy_candidates"] != expected:
            raise AssertionError("SupplyPack weekday comparison drifted")
    high_oil = _supply_case(
        supply_module, supply_type, day=0, today=6, oil=21_000
    )
    if high_oil["buy_candidates"]:
        raise AssertionError("SupplyPack high-oil guard drifted")
    return {
        "enabled": enabled,
        "disabled": disabled,
        "weekday_cases": weekday_cases,
        "high_oil": high_oil,
        "invalid_collect_events": _invalid_freebies_case(
            freebies_module, freebies_type, collect=1
        ),
        "invalid_day_events": _invalid_freebies_case(
            freebies_module, freebies_type, day=7
        ),
    }


def verify_supply_pack_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    defaults = _verify_args(alas_root)
    freebies_path = alas_root / "module" / "freebies" / "freebies.py"
    supply_path = alas_root / "module" / "freebies" / "supply_pack.py"
    consumers = _verify_consumers(freebies_path, supply_path)
    freebies_module, supply_module, freebies_type, supply_type = _load_original(
        alas_root
    )
    accepted, invalid = _verify_contract()
    original = _verify_original(
        freebies_module, supply_module, freebies_type, supply_type
    )
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "defaults": defaults,
        "runtime_consumers": consumers,
        "original_decisions": original,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_claim_method_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module" / "config" / "argument" / "args.json"),
            "freebies": _sha256(freebies_path),
            "supply_pack": _sha256(supply_path),
        },
    }
