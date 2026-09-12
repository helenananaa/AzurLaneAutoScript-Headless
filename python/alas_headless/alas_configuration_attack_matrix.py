"""Deterministic zero-input cross-field attacks for ALAS configuration gates.

The individual configuration replays prove each declared field against the
pinned source.  This module deliberately covers the places where independently
valid settings meet: campaign pre-sortie, emotion construction, and the
scheduler/event/idle path.  It never opens a runtime, reads a framebuffer, or
creates an action lease.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import json
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .alas_campaign_switch_config_contract import (
    validate_alas_campaign_switch_config,
)
from .alas_emotion_config_contract import validate_alas_emotion_config
from .alas_emotion_config_replay import verify_emotion_config
from .alas_event_general_config_contract import (
    validate_alas_event_general_config,
)
from .alas_event_general_config_replay import verify_event_general_config
from .alas_fleet_config_contract import validate_alas_fleet_config
from .alas_fleet_config_replay import verify_fleet_config
from .alas_hp_control_config_contract import validate_alas_hp_control_config
from .alas_hp_control_config_replay import verify_hp_control_config
from .alas_optimization_config_contract import (
    validate_alas_screenshot_interval_config,
    validate_alas_when_task_queue_empty,
)
from .alas_optimization_config_replay import verify_optimization_config
from .alas_scheduler_contract import (
    validate_alas_scheduler_config,
    validate_alas_task_hoarding_config,
)
from .alas_scheduler_replay import verify_scheduler_contract
from .alas_submarine_config_contract import validate_alas_submarine_config
from .alas_submarine_config_replay import verify_submarine_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.configuration-attack-matrix/v1"
FIXED_SEED = 0xA1A5C0DE
FROZEN_NOW = datetime(2026, 8, 15, 12, 0, 0)
ROOT = Path(__file__).resolve().parents[2]


def _campaign_profiles() -> tuple[Mapping[str, object], ...]:
    return (
        {
            "use_fleet_lock": False,
            "use_auto_search": False,
            "use_2x_book": False,
            "ambush_evade": False,
        },
        {
            "use_fleet_lock": True,
            "use_auto_search": True,
            "use_2x_book": False,
            "ambush_evade": False,
        },
        {
            "use_fleet_lock": False,
            "use_auto_search": False,
            "use_2x_book": True,
            "ambush_evade": True,
        },
        {
            "use_fleet_lock": True,
            "use_auto_search": True,
            "use_2x_book": True,
            "ambush_evade": True,
        },
    )


def _fleet_profiles() -> tuple[Mapping[str, object], ...]:
    return (
        {
            "fleet1": 1,
            "fleet1_formation": "double_line",
            "fleet1_mode": "combat_auto",
            "fleet1_step": 3,
            "fleet2": 2,
            "fleet2_formation": "double_line",
            "fleet2_mode": "combat_auto",
            "fleet2_step": 2,
            "fleet_order": "fleet1_mob_fleet2_boss",
        },
        {
            "fleet1": 6,
            "fleet1_formation": "double_line",
            "fleet1_mode": "combat_auto",
            "fleet1_step": 5,
            "fleet2": 0,
            "fleet2_formation": "double_line",
            "fleet2_mode": "combat_auto",
            "fleet2_step": 4,
            "fleet_order": "fleet1_mob_fleet2_boss",
        },
        {
            "fleet1": 2,
            "fleet1_formation": "double_line",
            "fleet1_mode": "combat_auto",
            "fleet1_step": 2,
            "fleet2": 6,
            "fleet2_formation": "double_line",
            "fleet2_mode": "combat_auto",
            "fleet2_step": 5,
            "fleet_order": "fleet1_mob_fleet2_boss",
        },
        {
            "fleet1": 5,
            "fleet1_formation": "double_line",
            "fleet1_mode": "combat_auto",
            "fleet1_step": 4,
            "fleet2": 1,
            "fleet2_formation": "double_line",
            "fleet2_mode": "combat_auto",
            "fleet2_step": 3,
            "fleet_order": "fleet1_mob_fleet2_boss",
        },
    )


def _hp_profiles() -> tuple[Mapping[str, object], ...]:
    return (
        {
            "use_hp_balance": False,
            "use_emergency_repair": False,
            "use_low_hp_retreat": False,
            "hp_balance_threshold": 0.2,
            "hp_balance_weight": "1000, 1000, 1000",
            "repair_use_single_threshold": 0.3,
            "repair_use_multi_threshold": 0.6,
            "low_hp_retreat_threshold": 0.3,
        },
        {
            "use_hp_balance": False,
            "use_emergency_repair": False,
            "use_low_hp_retreat": False,
            "hp_balance_threshold": 0,
            "hp_balance_weight": "1, 2, 3",
            "repair_use_single_threshold": 0,
            "repair_use_multi_threshold": 0,
            "low_hp_retreat_threshold": 0,
        },
        {
            "use_hp_balance": False,
            "use_emergency_repair": False,
            "use_low_hp_retreat": False,
            "hp_balance_threshold": 1,
            "hp_balance_weight": "1000， 500， 250",
            "repair_use_single_threshold": 1,
            "repair_use_multi_threshold": 1,
            "low_hp_retreat_threshold": 1,
        },
        {
            "use_hp_balance": False,
            "use_emergency_repair": False,
            "use_low_hp_retreat": False,
            "hp_balance_threshold": 0.5,
            "hp_balance_weight": "10, 2, 30",
            "repair_use_single_threshold": 0.1,
            "repair_use_multi_threshold": 0.9,
            "low_hp_retreat_threshold": 0.8,
        },
    )


def _submarine_profiles() -> tuple[Mapping[str, object], ...]:
    return (
        {
            "fleet": 0,
            "mode": "do_not_use",
            "auto_search_mode": "sub_standby",
            "distance_to_boss": "2_grid_to_boss",
        },
        {
            "fleet": 0,
            "mode": "every_combat",
            "auto_search_mode": "sub_auto_call",
            "distance_to_boss": "to_boss_position",
        },
        {
            "fleet": 0,
            "mode": "boss_only",
            "auto_search_mode": "sub_standby",
            "distance_to_boss": "1_grid_to_boss",
        },
        {
            "fleet": 0,
            "mode": "hunt_and_boss",
            "auto_search_mode": "sub_auto_call",
            "distance_to_boss": "use_open_ocean_support",
        },
    )


def _emotion_profiles() -> tuple[Mapping[str, object], ...]:
    record = datetime(2026, 8, 15)
    return (
        {
            "mode": "calculate",
            "fleet1_value": 119,
            "fleet1_record": record,
            "fleet1_control": "prevent_green_face",
            "fleet1_recover": "not_in_dormitory",
            "fleet1_oath": False,
            "fleet2_value": 119,
            "fleet2_record": record,
            "fleet2_control": "prevent_green_face",
            "fleet2_recover": "not_in_dormitory",
            "fleet2_oath": False,
        },
        {
            "mode": "ignore",
            "fleet1_value": 0,
            "fleet1_record": datetime(2000, 1, 1),
            "fleet1_control": "prevent_yellow_face",
            "fleet1_recover": "dormitory_floor_1",
            "fleet1_oath": True,
            "fleet2_value": 150,
            "fleet2_record": datetime(2100, 1, 1),
            "fleet2_control": "prevent_red_face",
            "fleet2_recover": "dormitory_floor_2",
            "fleet2_oath": False,
        },
        {
            "mode": "calculate_ignore",
            "fleet1_value": 1,
            "fleet1_record": record,
            "fleet1_control": "keep_exp_bonus",
            "fleet1_recover": "dormitory_floor_1",
            "fleet1_oath": False,
            "fleet2_value": 149,
            "fleet2_record": record,
            "fleet2_control": "prevent_green_face",
            "fleet2_recover": "not_in_dormitory",
            "fleet2_oath": True,
        },
        {
            "mode": "nothing",
            "fleet1_value": 75,
            "fleet1_record": record,
            "fleet1_control": "prevent_red_face",
            "fleet1_recover": "dormitory_floor_2",
            "fleet1_oath": True,
            "fleet2_value": 75,
            "fleet2_record": record,
            "fleet2_control": "prevent_yellow_face",
            "fleet2_recover": "dormitory_floor_1",
            "fleet2_oath": False,
        },
    )


def _scheduler_profiles() -> tuple[Mapping[str, object], ...]:
    return (
        {"Enable": True, "NextRun": FROZEN_NOW, "SuccessInterval": "30-60", "FailureInterval": "30-60", "ServerUpdate": "00:00"},
        {"Enable": False, "NextRun": FROZEN_NOW, "SuccessInterval": 0, "FailureInterval": 0, "ServerUpdate": "12:00"},
        {"Enable": True, "NextRun": FROZEN_NOW, "SuccessInterval": (5, 10), "FailureInterval": (10, 20), "ServerUpdate": ("00:00", "12:00")},
        {"Enable": True, "NextRun": FROZEN_NOW, "SuccessInterval": 15, "FailureInterval": 60, "ServerUpdate": "23:59"},
    )


def _event_profiles() -> tuple[Mapping[str, object], ...]:
    return (
        {"pt_limit": 0, "time_limit": datetime(2020, 1, 1), "task_balancer_enable": False, "task_balancer_coin_limit": 0, "task_balancer_task_call": "Main"},
        {"pt_limit": "100,000", "time_limit": datetime(2026, 8, 16), "task_balancer_enable": True, "task_balancer_coin_limit": 9_999, "task_balancer_task_call": "Main2"},
        {"pt_limit": 1_000_000, "time_limit": datetime(2026, 8, 14), "task_balancer_enable": True, "task_balancer_coin_limit": 10_000, "task_balancer_task_call": "Main3"},
        {"pt_limit": "42", "time_limit": FROZEN_NOW, "task_balancer_enable": False, "task_balancer_coin_limit": 1, "task_balancer_task_call": "Main"},
    )


def _optimization_profiles() -> tuple[Mapping[str, object], ...]:
    return (
        {"screenshot_interval": 0.1, "combat_screenshot_interval": 0.3, "idle": "stay_there", "hoarding": 0},
        {"screenshot_interval": 0, "combat_screenshot_interval": 1, "idle": "goto_main", "hoarding": 1},
        {"screenshot_interval": 0.3, "combat_screenshot_interval": 0.6, "idle": "close_game", "hoarding": 15},
        {"screenshot_interval": 2, "combat_screenshot_interval": 2, "idle": "stay_there", "hoarding": 1440},
    )


def _pairs(row: Sequence[int]) -> set[tuple[int, int, int, int]]:
    return {
        (left, right, row[left], row[right])
        for left in range(len(row))
        for right in range(left + 1, len(row))
    }


def _pairwise_rows(width: int, values: int) -> tuple[tuple[int, ...], ...]:
    """Greedily cover every cross-domain profile pair with a fixed seed."""

    candidates = list(itertools.product(range(values), repeat=width))
    random.Random(FIXED_SEED).shuffle(candidates)
    uncovered = {
        (left, right, left_value, right_value)
        for left in range(width)
        for right in range(left + 1, width)
        for left_value in range(values)
        for right_value in range(values)
    }
    selected: list[tuple[int, ...]] = []
    while uncovered:
        candidate = max(candidates, key=lambda row: len(_pairs(row) & uncovered))
        score = len(_pairs(candidate) & uncovered)
        if not score:
            raise AssertionError("pairwise candidate construction stalled")
        selected.append(candidate)
        uncovered.difference_update(_pairs(candidate))
        candidates.remove(candidate)
    return tuple(selected)


class _PreflightRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.pre_sortie_entries = 0
        self.action_authority = 0
        self.pixel_accesses = 0

    def begin_campaign_pre_sortie(self) -> None:
        self.pre_sortie_entries += 1


def _campaign_preflight(values: Mapping[str, Mapping[str, object]], recorder: _PreflightRecorder) -> None:
    """Mirror the audited patch order without replacing ALAS's campaign loop."""

    recorder.calls.append("campaign-switch")
    validate_alas_campaign_switch_config(**values["campaign"])
    recorder.calls.append("fleet")
    validate_alas_fleet_config(**values["fleet"])
    recorder.calls.append("hp-control")
    validate_alas_hp_control_config(**values["hp"])
    recorder.calls.append("submarine")
    validate_alas_submarine_config(**values["submarine"])
    recorder.begin_campaign_pre_sortie()


def _emotion_constructor(values: Mapping[str, object], recorder: _PreflightRecorder) -> None:
    recorder.calls.append("emotion")
    validate_alas_emotion_config(**values)


def _scheduler_data(profile: Mapping[str, object]) -> dict[str, object]:
    return {
        "Event": {
            "Scheduler": {
                "Enable": profile["Enable"],
                "NextRun": profile["NextRun"],
                "Command": "Event",
                "SuccessInterval": profile["SuccessInterval"],
                "FailureInterval": profile["FailureInterval"],
                "ServerUpdate": profile["ServerUpdate"],
            }
        }
    }


def _stable_value(value: object) -> object:
    """Compare malformed test values without letting NaN defeat equality."""

    if isinstance(value, float):
        if math.isnan(value):
            return "<nan>"
        if math.isinf(value):
            return "<infinity>" if value > 0 else "<-infinity>"
    if isinstance(value, datetime):
        return {"datetime": value.isoformat(), "tz": value.tzinfo is not None}
    if isinstance(value, Mapping):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_stable_value(item) for item in value)
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    return value


def _assert_unchanged(before: object, after: object, *, case: str) -> None:
    if _stable_value(before) != _stable_value(after):
        raise AssertionError(case + " mutated configuration before ALAS ownership")


def _assert_contract_sources_are_pure() -> None:
    contracts = (
        "alas_campaign_switch_config_contract.py",
        "alas_fleet_config_contract.py",
        "alas_hp_control_config_contract.py",
        "alas_submarine_config_contract.py",
        "alas_emotion_config_contract.py",
        "alas_scheduler_contract.py",
        "alas_event_general_config_contract.py",
        "alas_optimization_config_contract.py",
    )
    forbidden = {"click", "swipe", "drag", "screenshot", "crop", "ocr", "template"}
    for name in contracts:
        path = ROOT / "python" / "alas_headless" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        loaded_attributes = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
        }
        if forbidden & loaded_attributes:
            raise AssertionError(name + " exposes an input or pixel fallback")


def _verify_patch_order() -> None:
    patch = (ROOT / "integration" / "alas" / "series" / "0050-combat-flow-ports.patch").read_text(encoding="utf-8")
    ordered = (
        "self._validate_main_campaign_route_config(name, folder, mode)",
        "self._validate_campaign_switch_config()",
        "semantic_adapter.validate_campaign_fleet_config(",
        "semantic_adapter.validate_campaign_hp_control_config(",
        "semantic_adapter.validate_campaign_enemy_priority_config(",
        "semantic_adapter.validate_campaign_submarine_config(",
        "semantic_adapter.begin_campaign_pre_sortie(name, mode=mode)",
    )
    positions = [patch.index(value) for value in ordered]
    if positions != sorted(positions):
        raise AssertionError("campaign pre-sortie gate order drifted")
    emotion = patch.index("validate_alas_emotion_config(")
    config_assignment = patch.index("self.config = config", emotion)
    if emotion >= config_assignment:
        raise AssertionError("emotion validation no longer precedes state ownership")


def _valid_campaign_matrix() -> tuple[int, str]:
    profiles = (
        _campaign_profiles(),
        _fleet_profiles(),
        _hp_profiles(),
        _submarine_profiles(),
        _emotion_profiles(),
    )
    rows = _pairwise_rows(width=len(profiles), values=4)
    digest = hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()
    for index, row in enumerate(rows):
        values = {
            "campaign": copy.deepcopy(profiles[0][row[0]]),
            "fleet": copy.deepcopy(profiles[1][row[1]]),
            "hp": copy.deepcopy(profiles[2][row[2]]),
            "submarine": copy.deepcopy(profiles[3][row[3]]),
        }
        before = copy.deepcopy(values)
        recorder = _PreflightRecorder()
        _campaign_preflight(values, recorder)
        _assert_unchanged(before, values, case=f"pairwise seed={FIXED_SEED} row={index}")
        if recorder.calls != ["campaign-switch", "fleet", "hp-control", "submarine"]:
            raise AssertionError("valid campaign preflight call order drifted")
        if recorder.pre_sortie_entries != 1 or recorder.action_authority or recorder.pixel_accesses:
            raise AssertionError("valid campaign preflight exceeded zero-input boundary")
        emotion = copy.deepcopy(profiles[4][row[4]])
        emotion_before = copy.deepcopy(emotion)
        emotion_recorder = _PreflightRecorder()
        _emotion_constructor(emotion, emotion_recorder)
        _assert_unchanged(emotion_before, emotion, case=f"emotion seed={FIXED_SEED} row={index}")
        if emotion_recorder.calls != ["emotion"] or emotion_recorder.action_authority:
            raise AssertionError("valid emotion construction exceeded zero-input boundary")
    return len(rows), digest


def _valid_scheduler_matrix() -> tuple[int, str]:
    profiles = (_scheduler_profiles(), _event_profiles(), _optimization_profiles())
    rows = _pairwise_rows(width=len(profiles), values=4)
    digest = hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()
    for index, row in enumerate(rows):
        scheduler = _scheduler_data(copy.deepcopy(profiles[0][row[0]]))
        event = copy.deepcopy(profiles[1][row[1]])
        optimization = copy.deepcopy(profiles[2][row[2]])
        before = copy.deepcopy((scheduler, event, optimization))
        snapshots = validate_alas_scheduler_config(scheduler)
        validate_alas_event_general_config(**event)
        validate_alas_screenshot_interval_config(
            screenshot_interval=optimization["screenshot_interval"],
            combat_screenshot_interval=optimization["combat_screenshot_interval"],
        )
        validate_alas_when_task_queue_empty(optimization["idle"])
        validate_alas_task_hoarding_config(
            {"Alas": {"Optimization": {"TaskHoardingDuration": optimization["hoarding"]}}}
        )
        if len(snapshots) != 1 or snapshots[0].command != "Event":
            raise AssertionError("scheduler profile lost Event identity")
        _assert_unchanged(
            before,
            (scheduler, event, optimization),
            case=f"scheduler seed={FIXED_SEED} row={index}",
        )
    return len(rows), digest


def _invalid_cases() -> int:
    valid = {
        "campaign": dict(_campaign_profiles()[0]),
        "fleet": dict(_fleet_profiles()[0]),
        "hp": dict(_hp_profiles()[0]),
        "submarine": dict(_submarine_profiles()[0]),
    }
    cases: tuple[tuple[str, Callable[[dict[str, dict[str, object]]], None], tuple[str, ...]], ...] = (
        (
            "campaign-bool-alias",
            lambda values: values["campaign"].update(use_auto_search=1),
            ("campaign-switch",),
        ),
        (
            "fleet-bool-alias",
            lambda values: values["fleet"].update(fleet1=True),
            ("campaign-switch", "fleet"),
        ),
        (
            "hp-nan",
            lambda values: values["hp"].update(repair_use_multi_threshold=float("nan")),
            ("campaign-switch", "fleet", "hp-control"),
        ),
        (
            "submarine-invalid-fleet",
            lambda values: values["submarine"].update(fleet=3),
            ("campaign-switch", "fleet", "hp-control", "submarine"),
        ),
    )
    for name, mutate, expected_calls in cases:
        values = copy.deepcopy(valid)
        mutate(values)
        before = copy.deepcopy(values)
        recorder = _PreflightRecorder()
        try:
            _campaign_preflight(values, recorder)
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError(name + " was admitted")
        if tuple(recorder.calls) != expected_calls or recorder.pre_sortie_entries:
            raise AssertionError(name + " crossed a campaign ownership boundary")
        if recorder.action_authority or recorder.pixel_accesses:
            raise AssertionError(name + " minted input authority")
        _assert_unchanged(before, values, case=name)

    scheduler = _scheduler_data(_scheduler_profiles()[0])
    event = dict(_event_profiles()[0])
    optimization = dict(_optimization_profiles()[0])
    invalid_scalars = (
        ("scheduler-range", lambda: scheduler["Event"]["Scheduler"].update(SuccessInterval="60-30"), lambda: validate_alas_scheduler_config(scheduler)),
        ("event-bool-alias", lambda: event.update(task_balancer_coin_limit=True), lambda: validate_alas_event_general_config(**event)),
        ("optimization-infinity", lambda: optimization.update(combat_screenshot_interval=float("inf")), lambda: validate_alas_screenshot_interval_config(screenshot_interval=optimization["screenshot_interval"], combat_screenshot_interval=optimization["combat_screenshot_interval"])),
        ("idle-unknown", lambda: optimization.update(idle="reopen_game"), lambda: validate_alas_when_task_queue_empty(optimization["idle"])),
    )
    for name, mutate, verify in invalid_scalars:
        mutate()
        try:
            verify()
        except SemanticGateClosed:
            continue
        raise AssertionError(name + " was admitted")
    return len(cases) + len(invalid_scalars)


def _seeded_sequences() -> int:
    profiles = (_campaign_profiles(), _fleet_profiles(), _hp_profiles(), _submarine_profiles())
    generator = random.Random(FIXED_SEED)
    for offset in range(32):
        row = tuple(generator.randrange(4) for _ in profiles)
        values = {
            "campaign": copy.deepcopy(profiles[0][row[0]]),
            "fleet": copy.deepcopy(profiles[1][row[1]]),
            "hp": copy.deepcopy(profiles[2][row[2]]),
            "submarine": copy.deepcopy(profiles[3][row[3]]),
        }
        recorder = _PreflightRecorder()
        _campaign_preflight(values, recorder)
        if recorder.pre_sortie_entries != 1:
            raise AssertionError(f"seed={FIXED_SEED} sequence={offset} did not reach pre-sortie")
        invalid = copy.deepcopy(values)
        if offset % 4 == 0:
            invalid["campaign"]["use_auto_search"] = 1
        elif offset % 4 == 1:
            invalid["fleet"]["fleet1"] = True
        elif offset % 4 == 2:
            invalid["hp"]["low_hp_retreat_threshold"] = float("nan")
        else:
            invalid["submarine"]["fleet"] = 3
        before = copy.deepcopy(invalid)
        refused = _PreflightRecorder()
        try:
            _campaign_preflight(invalid, refused)
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError(f"seed={FIXED_SEED} sequence={offset} admitted invalid state")
        _assert_unchanged(before, invalid, case=f"seed={FIXED_SEED} sequence={offset}")
        if refused.pre_sortie_entries or refused.action_authority or refused.pixel_accesses:
            raise AssertionError(f"seed={FIXED_SEED} sequence={offset} leaked authority")
        next_row = tuple(generator.randrange(4) for _ in profiles)
        next_values = {
            "campaign": copy.deepcopy(profiles[0][next_row[0]]),
            "fleet": copy.deepcopy(profiles[1][next_row[1]]),
            "hp": copy.deepcopy(profiles[2][next_row[2]]),
            "submarine": copy.deepcopy(profiles[3][next_row[3]]),
        }
        recovered = _PreflightRecorder()
        _campaign_preflight(next_values, recovered)
        if recovered.pre_sortie_entries != 1:
            raise AssertionError(f"seed={FIXED_SEED} sequence={offset} did not recover")
    return 32


def _original_replays(alas_root: Path) -> Mapping[str, Mapping[str, object]]:
    replay_functions = {
        "scheduler": verify_scheduler_contract,
        "fleet": verify_fleet_config,
        "hp_control": verify_hp_control_config,
        "emotion": verify_emotion_config,
        "submarine": verify_submarine_config,
        "event_general": verify_event_general_config,
        "optimization": verify_optimization_config,
    }
    results: dict[str, Mapping[str, object]] = {}
    for name, verify in replay_functions.items():
        result = verify(alas_root)
        zero_input = (
            result.get("mutation_budget") == 0
            or result.get("temporary_config_only") is True
        )
        if result.get("passed") is not True or not zero_input:
            raise AssertionError(name + " original-method replay lost its zero-input contract")
        if result.get("android_input_injected") is not False:
            raise AssertionError(name + " original-method replay injected Android input")
        results[name] = result
    return results


def verify_configuration_attack_matrix(alas_root: Path) -> Mapping[str, object]:
    """Run the fixed-seed matrix against a clean pinned upstream checkout."""

    root = alas_root.resolve()
    if not root.joinpath(".git").exists():
        raise FileNotFoundError("ALAS matrix requires a Git checkout")
    _assert_contract_sources_are_pure()
    _verify_patch_order()
    campaign_rows, campaign_digest = _valid_campaign_matrix()
    scheduler_rows, scheduler_digest = _valid_scheduler_matrix()
    invalid_count = _invalid_cases()
    sequence_count = _seeded_sequences()
    replays = _original_replays(root)
    return {
        "schema": SCHEMA,
        "passed": True,
        "seed": FIXED_SEED,
        "campaign_pairwise_case_count": campaign_rows,
        "scheduler_pairwise_case_count": scheduler_rows,
        "seeded_sequence_count": sequence_count,
        "invalid_case_count": invalid_count,
        "campaign_pairwise_sha256": campaign_digest,
        "scheduler_pairwise_sha256": scheduler_digest,
        "mutation_budget": 0,
        "android_input_injected": False,
        "pixel_fallback_used": False,
        "original_method_replays": {
            name: {
                "source_sha256": value.get("source_sha256"),
                "case_count": value.get("case_count", value.get("accepted_case_count")),
            }
            for name, value in replays.items()
        },
    }
