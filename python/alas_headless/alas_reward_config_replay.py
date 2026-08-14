"""Deterministic replay of Reward switches across Reward and RaidDaily."""

from __future__ import annotations

import ast
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_reward_config_contract import validate_alas_reward_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.reward-config-replay/v1"
FIELDS = (
    "CollectOil",
    "CollectCoin",
    "CollectExp",
    "CollectMission",
    "CollectWeeklyMission",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "collect_oil": True,
        "collect_coin": True,
        "collect_exp": True,
        "collect_mission": True,
        "collect_weekly_mission": True,
    }
    values.update(overrides)
    return values


class ReplayConfig:
    def __init__(self, **overrides: object):
        values = _values(**overrides)
        self.Reward_CollectOil = values["collect_oil"]
        self.Reward_CollectCoin = values["collect_coin"]
        self.Reward_CollectExp = values["collect_exp"]
        self.Reward_CollectMission = values["collect_mission"]
        self.Reward_CollectWeeklyMission = values["collect_weekly_mission"]
        self.Campaign_Event = "raid_fixture"
        self.RaidDaily_StageFilter = "hard"
        self.Scheduler_Enable = True
        self.events: list[tuple[Any, ...]] = []

    def task_delay(self, **kwargs: object) -> None:
        self.events.append(("delay", kwargs))

    def task_stop(self) -> None:
        self.events.append(("stop",))


def _verify_args(alas_root: Path) -> dict[str, bool]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panel = document.get("Reward")
    group = panel.get("Reward") if isinstance(panel, dict) else None
    if not isinstance(group, dict) or set(group) != set(FIELDS):
        raise AssertionError("Reward field surface drifted")
    for field in FIELDS:
        if group[field].get("type") != "checkbox" or group[field].get(
            "value"
        ) is not True:
            raise AssertionError(f"Reward.{field} surface drifted")
    return {field: True for field in FIELDS}


def _verify_consumers(reward_path: Path, raid_path: Path) -> dict[str, list[str]]:
    result = {f"Reward.{field}": [] for field in FIELDS}
    result["patched_guards"] = []
    for path, class_name in ((reward_path, "Reward"), (raid_path, "RaidDaily")):
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
        for field in FIELDS:
            if f"Reward_{field}" in attributes:
                result[f"Reward.{field}"].append(f"{class_name}.run")
        calls = {
            node.func.id
            for node in ast.walk(run)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        if "validate_alas_reward_config" in calls:
            result["patched_guards"].append(f"{class_name}.run")
    expected = {
        "Reward.CollectOil": ["Reward.run", "RaidDaily.run"],
        "Reward.CollectCoin": ["Reward.run", "RaidDaily.run"],
        "Reward.CollectExp": ["Reward.run", "RaidDaily.run"],
        "Reward.CollectMission": ["Reward.run", "RaidDaily.run"],
        "Reward.CollectWeeklyMission": ["Reward.run", "RaidDaily.run"],
        "patched_guards": ["Reward.run", "RaidDaily.run"],
    }
    if result != expected:
        raise AssertionError("Reward runtime consumer surface drifted")
    return result


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        reward = importlib.import_module("module.reward.reward")
        raid = importlib.import_module("module.raid.daily")
        raid_base = importlib.import_module("module.raid.run")
        return reward, raid, raid_base, reward.Reward, raid.RaidDaily
    finally:
        sys.path.remove(root)


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    keys = tuple(_values())
    for combination in itertools.product((False, True), repeat=5):
        values = dict(zip(keys, combination))
        snapshot = validate_alas_reward_config(**values)
        if tuple(getattr(snapshot, key) for key in keys) != combination:
            raise AssertionError("Reward boolean forwarding drifted")
        accepted += 1
    for key in keys:
        for value in (0, 1, "true", None):
            try:
                validate_alas_reward_config(**_values(**{key: value}))
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid Reward value was admitted: {key}")
    return accepted, invalid


def _reward_case(reward_type: type[Any], combination: tuple[bool, ...]) -> dict[str, Any]:
    keys = tuple(_values())
    host = object.__new__(reward_type)
    host.config = ReplayConfig(**dict(zip(keys, combination)))
    host.device = SimpleNamespace(semantic_adapter=None)
    events: list[tuple[Any, ...]] = []
    host.ui_ensure = lambda page: events.append(("ui_ensure",))
    host.reward_receive = lambda **kwargs: events.append(("receive", kwargs))
    host.ui_goto = lambda page: events.append(("ui_goto",))
    host.reward_mission = lambda **kwargs: events.append(("mission", kwargs))
    reward_type.run(host)
    expected = [
        (
            "receive",
            {
                "oil": combination[0],
                "coin": combination[1],
                "exp": combination[2],
            },
        ),
        (
            "mission",
            {"daily": combination[3], "weekly": combination[4]},
        ),
    ]
    forwarded = [event for event in events if event[0] in ("receive", "mission")]
    if forwarded != expected:
        raise AssertionError("Reward.run option forwarding drifted")
    if host.config.events != [("delay", {"success": True})]:
        raise AssertionError("Reward scheduler tail drifted")
    return {"events": events, "config_events": host.config.events}


def _invalid_reward_case(reward_type: type[Any], *, field: str) -> list[Any]:
    host = object.__new__(reward_type)
    host.config = ReplayConfig(**{field: 1})
    host.device = SimpleNamespace(semantic_adapter=None)
    events = []
    host.ui_ensure = lambda page: events.append("ui")
    try:
        reward_type.run(host)
    except SemanticGateClosed:
        pass
    else:
        raise AssertionError("invalid Reward config entered Reward.run")
    if events or host.config.events:
        raise AssertionError("invalid Reward config caused a mutation")
    return events


def _raid_case(
    raid_module: Any,
    raid_base: Any,
    raid_type: type[Any],
    *,
    collect_mission: bool,
    ex: bool,
) -> dict[str, Any]:
    host = object.__new__(raid_type)
    host.config = ReplayConfig(collect_mission=collect_mission)
    host.config.RaidDaily_StageFilter = "hard > ex" if ex else "hard"
    host.device = object()
    events: list[tuple[Any, ...]] = []
    host.is_raid_rpg = lambda: False
    host.ui_ensure = lambda page: events.append(("ui_ensure",))
    host.get_remain = lambda mode: 2 if mode == "ex" else 0
    host.ui_goto_main = lambda: events.append(("goto_main",))

    class RewardRecorder:
        def __init__(self, config: object, device: object):
            pass

        def reward_mission(self, **kwargs: object) -> None:
            events.append(("reward_mission", kwargs))

    old_filter = raid_module.STAGE_FILTER
    old_reward = raid_module.Reward
    old_run = raid_base.RaidRun.run
    raid_module.STAGE_FILTER = SimpleNamespace(
        load=lambda value: events.append(("filter", value)),
        apply=lambda stages: [],
    )
    raid_module.Reward = RewardRecorder
    raid_base.RaidRun.run = lambda self, **kwargs: events.append(("raid_run", kwargs))
    try:
        raid_type.run(host)
    finally:
        raid_module.STAGE_FILTER = old_filter
        raid_module.Reward = old_reward
        raid_base.RaidRun.run = old_run
    reward_calls = [event for event in events if event[0] == "reward_mission"]
    raid_calls = [event for event in events if event[0] == "raid_run"]
    if ex:
        if reward_calls != [
            ("reward_mission", {"daily": collect_mission, "weekly": False})
        ]:
            raise AssertionError("RaidDaily Reward.CollectMission forwarding drifted")
        if raid_calls != [
            ("raid_run", {"name": "raid_fixture", "mode": "ex", "total": 2})
        ]:
            raise AssertionError("RaidDaily EX run tail drifted")
    elif reward_calls or raid_calls:
        raise AssertionError("non-EX RaidDaily unexpectedly entered reward or EX run")
    if host.config.events != [("delay", {"server_update": True})]:
        raise AssertionError("RaidDaily scheduler tail drifted")
    return {"events": events, "config_events": host.config.events}


def _invalid_raid_case(raid_type: type[Any]) -> list[Any]:
    host = object.__new__(raid_type)
    host.config = ReplayConfig(collect_weekly_mission=1)
    host.device = object()
    events = []
    host.is_raid_rpg = lambda: events.append("is_raid_rpg") or False
    try:
        raid_type.run(host)
    except SemanticGateClosed:
        pass
    else:
        raise AssertionError("invalid Reward config entered RaidDaily.run")
    if events or host.config.events:
        raise AssertionError("invalid Reward config mutated RaidDaily")
    return events


def _verify_original(
    reward_type: type[Any],
    raid_module: Any,
    raid_base: Any,
    raid_type: type[Any],
) -> dict[str, Any]:
    reward_cases = {}
    for combination in itertools.product((False, True), repeat=5):
        key = "".join("1" if value else "0" for value in combination)
        reward_cases[key] = _reward_case(reward_type, combination)
    invalid_reward = {
        key: _invalid_reward_case(reward_type, field=key) for key in _values()
    }
    return {
        "reward_cases": reward_cases,
        "raid_ex_enabled": _raid_case(
            raid_module,
            raid_base,
            raid_type,
            collect_mission=True,
            ex=True,
        ),
        "raid_ex_disabled": _raid_case(
            raid_module,
            raid_base,
            raid_type,
            collect_mission=False,
            ex=True,
        ),
        "raid_without_ex": _raid_case(
            raid_module,
            raid_base,
            raid_type,
            collect_mission=True,
            ex=False,
        ),
        "invalid_reward_events": invalid_reward,
        "invalid_raid_events": _invalid_raid_case(raid_type),
    }


def verify_reward_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    defaults = _verify_args(alas_root)
    reward_path = alas_root / "module" / "reward" / "reward.py"
    raid_path = alas_root / "module" / "raid" / "daily.py"
    consumers = _verify_consumers(reward_path, raid_path)
    reward_module, raid_module, raid_base, reward_type, raid_type = _load_original(
        alas_root
    )
    del reward_module
    accepted, invalid = _verify_contract()
    original = _verify_original(reward_type, raid_module, raid_base, raid_type)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 5,
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
            "reward": _sha256(reward_path),
            "raid_daily": _sha256(raid_path),
        },
    }
