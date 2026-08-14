"""Deterministic replay of pinned ALAS emotion bookkeeping."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_emotion_config_contract import (
    EMOTION_CONTROLS,
    EMOTION_PUBLIC_MODES,
    EMOTION_RECOVERY_LOCATIONS,
    validate_alas_emotion_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.emotion-config-replay/v1"
FIELD_NAMES = (
    "Mode",
    "Fleet1Value",
    "Fleet1Record",
    "Fleet1Control",
    "Fleet1Recover",
    "Fleet1Oath",
    "Fleet2Value",
    "Fleet2Record",
    "Fleet2Control",
    "Fleet2Recover",
    "Fleet2Oath",
)
FROZEN_NOW = datetime(2026, 8, 15, 12, 0, 0)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _defaults() -> dict[str, object]:
    return {
        "mode": "calculate",
        "fleet1_value": 119,
        "fleet1_record": FROZEN_NOW,
        "fleet1_control": "prevent_green_face",
        "fleet1_recover": "not_in_dormitory",
        "fleet1_oath": False,
        "fleet2_value": 119,
        "fleet2_record": FROZEN_NOW,
        "fleet2_control": "prevent_green_face",
        "fleet2_recover": "not_in_dormitory",
        "fleet2_oath": False,
    }


def _verify_args(alas_root: Path) -> tuple[str, ...]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panels = []
    for panel, groups in document.items():
        if "Emotion" not in groups:
            continue
        panels.append(panel)
        group = groups["Emotion"]
        if tuple(group) != FIELD_NAMES:
            raise AssertionError("Emotion field set or order drifted")
        if tuple(group["Mode"].get("option", ())) != EMOTION_PUBLIC_MODES:
            raise AssertionError("Emotion mode surface drifted")
        for prefix in ("Fleet1", "Fleet2"):
            if tuple(group[prefix + "Control"].get("option", ())) != EMOTION_CONTROLS:
                raise AssertionError("Emotion control surface drifted")
            if (
                tuple(group[prefix + "Recover"].get("option", ()))
                != EMOTION_RECOVERY_LOCATIONS
            ):
                raise AssertionError("Emotion recovery surface drifted")
    if len(panels) != 17:
        raise AssertionError("Emotion shared panel surface drifted")
    return tuple(panels)


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.combat.emotion")
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
        self.record_writes = []
        self.delay_targets = []

    def set_record(self, **values: object) -> None:
        self.record_writes.append(dict(values))

    def task_delay(self, *, target: datetime) -> None:
        self.delay_targets.append(target)


def _native_config(**overrides: object) -> _Config:
    values = {
        "Emotion_Mode": "calculate",
        "Emotion_Fleet1Value": 119,
        "Emotion_Fleet1Record": FROZEN_NOW,
        "Emotion_Fleet1Control": "prevent_green_face",
        "Emotion_Fleet1Recover": "not_in_dormitory",
        "Emotion_Fleet1Oath": False,
        "Emotion_Fleet2Value": 119,
        "Emotion_Fleet2Record": FROZEN_NOW,
        "Emotion_Fleet2Control": "prevent_green_face",
        "Emotion_Fleet2Recover": "not_in_dormitory",
        "Emotion_Fleet2Oath": False,
        "Campaign_Use2xBook": False,
        "Fleet_FleetOrder": "fleet1_mob_fleet2_boss",
    }
    values.update(overrides)
    return _Config(**values)


def _verify_original(original: Any) -> dict[str, Any]:
    old_datetime = original.datetime
    old_sleep = original.sleep
    original.datetime = _FrozenDateTime
    original.sleep = lambda seconds: (_ for _ in ()).throw(
        AssertionError("emotion replay attempted to sleep")
    )
    try:
        mode_truth = {}
        for mode in EMOTION_PUBLIC_MODES + ("nothing",):
            emotion = original.Emotion(_native_config(Emotion_Mode=mode))
            mode_truth[mode] = {
                "calculate": bool(emotion.is_calculate),
                "ignore": bool(emotion.is_ignore),
            }

        property_cases = 0
        for fleet_index in (1, 2):
            for control in EMOTION_CONTROLS:
                for recover in EMOTION_RECOVERY_LOCATIONS:
                    for oath in (False, True):
                        config = _native_config(
                            **{
                                f"Emotion_Fleet{fleet_index}Control": control,
                                f"Emotion_Fleet{fleet_index}Recover": recover,
                                f"Emotion_Fleet{fleet_index}Oath": oath,
                            }
                        )
                        fleet = original.FleetEmotion(config, fleet_index)
                        expected_speed = original.DIC_RECOVER[recover]
                        if oath:
                            expected_speed += original.OATH_RECOVER
                        if (
                            fleet.speed != expected_speed // 10
                            or fleet.limit != original.DIC_LIMIT[control]
                            or fleet.max != original.DIC_RECOVER_MAX[recover]
                        ):
                            raise AssertionError("original Emotion property mapping drifted")
                        property_cases += 1

        config = _native_config(
            Emotion_Fleet1Value=30,
            Emotion_Fleet1Record=FROZEN_NOW - timedelta(minutes=12),
        )
        fleet = original.FleetEmotion(config, 1)
        fleet.update()
        if fleet.current != 34:
            raise AssertionError("original Emotion recovery update drifted")
        future = original.FleetEmotion(
            _native_config(
                Emotion_Fleet1Value=30,
                Emotion_Fleet1Record=FROZEN_NOW + timedelta(minutes=12),
            ),
            1,
        )
        future.update()
        if future.current != 30:
            raise AssertionError("future Emotion record handling drifted")

        class CaptureFleet:
            def __init__(self, index: int):
                self.fleet = index
                self.value_name = f"Emotion_Fleet{index}Value"
                self.value = 119
                self.current = 119
                self.expected = []

            def update(self) -> None:
                pass

            def get_recovered(self, expected_reduce=0):
                self.expected.append(int(expected_reduce))
                return FROZEN_NOW - timedelta(minutes=1)

        order_vectors = {}
        for order, expected in (
            ("fleet1_mob_fleet2_boss", (4, 2)),
            ("fleet1_boss_fleet2_mob", (2, 4)),
            ("fleet1_all_fleet2_standby", (6, 0)),
            ("fleet1_standby_fleet2_all", (0, 6)),
        ):
            emotion = original.Emotion(_native_config(Fleet_FleetOrder=order))
            fleets = [CaptureFleet(1), CaptureFleet(2)]
            emotion.fleet_1, emotion.fleet_2, emotion.fleets = fleets[0], fleets[1], fleets
            emotion.check_reduce(3)
            actual = tuple(item.expected[0] for item in fleets)
            if actual != expected:
                raise AssertionError("original Emotion fleet-order reduction drifted")
            order_vectors[order] = list(actual)

        doubled = original.Emotion(
            _native_config(
                Fleet_FleetOrder="fleet1_all_fleet2_standby",
                Campaign_Use2xBook=True,
            )
        )
        fleets = [CaptureFleet(1), CaptureFleet(2)]
        doubled.fleet_1, doubled.fleet_2, doubled.fleets = fleets[0], fleets[1], fleets
        doubled.check_reduce(3)
        if tuple(item.expected[0] for item in fleets) != (12, 0):
            raise AssertionError("original pre-entry 2x Emotion reduction drifted")

        wait_config = _native_config()
        wait_emotion = original.Emotion(wait_config)
        wait_emotion.wait(1)
        if not wait_config.record_writes:
            raise AssertionError("original Emotion wait did not record state")

        reduce_config = _native_config()
        reduce_emotion = original.Emotion(reduce_config)
        reduce_emotion.total_reduced = 0
        reduce_emotion.reduce(1)
        if (
            reduce_emotion.total_reduced != 2
            or reduce_config.record_writes[-1]["Emotion_Fleet1Value"] != 117
        ):
            raise AssertionError("original Emotion reduction record drifted")

        return {
            "mode_truth_table": mode_truth,
            "fleet_property_cases": property_cases,
            "recovered_value": fleet.current,
            "future_record_value": future.current,
            "fleet_order_vectors": order_vectors,
            "two_x_vector": [12, 0],
            "wait_record_writes": len(wait_config.record_writes),
            "reduce_record_writes": len(reduce_config.record_writes),
        }
    finally:
        original.datetime = old_datetime
        original.sleep = old_sleep


def verify_emotion_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    panels = _verify_args(alas_root)
    original = _load_original(alas_root)
    decisions = _verify_original(original)

    accepted_cases = 0
    for mode in EMOTION_PUBLIC_MODES + ("nothing",):
        config = _defaults()
        config["mode"] = mode
        validate_alas_emotion_config(**config)
        accepted_cases += 1
    for fleet in (1, 2):
        for control in EMOTION_CONTROLS:
            for recover in EMOTION_RECOVERY_LOCATIONS:
                if control == "keep_exp_bonus" and recover == "not_in_dormitory":
                    continue
                for oath in (False, True):
                    config = _defaults()
                    config[f"fleet{fleet}_control"] = control
                    config[f"fleet{fleet}_recover"] = recover
                    config[f"fleet{fleet}_oath"] = oath
                    validate_alas_emotion_config(**config)
                    accepted_cases += 1

    invalid_cases = (
        ("mode", "unknown"),
        ("fleet1_value", -1),
        ("fleet1_value", 151),
        ("fleet1_value", True),
        ("fleet1_record", "2026-08-15"),
        ("fleet1_record", datetime(1900, 1, 1)),
        ("fleet1_control", "unknown"),
        ("fleet1_recover", "unknown"),
        ("fleet1_oath", 1),
    )
    invalid_count = 0
    for field, value in invalid_cases:
        config = _defaults()
        config[field] = value
        try:
            validate_alas_emotion_config(**config)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid Emotion value was admitted")
    incompatible_count = 0
    for fleet in (1, 2):
        config = _defaults()
        config[f"fleet{fleet}_control"] = "keep_exp_bonus"
        config[f"fleet{fleet}_recover"] = "not_in_dormitory"
        try:
            validate_alas_emotion_config(**config)
        except SemanticGateClosed:
            incompatible_count += 1
        else:
            raise AssertionError("incompatible Emotion settings were admitted")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": len(FIELD_NAMES),
        "panel_count": len(panels),
        "panels": list(panels),
        "accepted_case_count": accepted_cases,
        "invalid_case_count": invalid_count,
        "incompatible_case_count": incompatible_count,
        "original_decisions": decisions,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "emotion": _sha256(
                alas_root / "module" / "combat" / "emotion.py"
            ),
        },
    }
