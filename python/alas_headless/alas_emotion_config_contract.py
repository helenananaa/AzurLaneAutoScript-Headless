"""Fail-closed contract for ALAS fleet-emotion bookkeeping settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .semantic_oracle import SemanticGateClosed


EMOTION_PUBLIC_MODES = ("calculate", "ignore", "calculate_ignore")
EMOTION_RUNTIME_MODES = EMOTION_PUBLIC_MODES + ("nothing",)
EMOTION_CONTROLS = (
    "keep_exp_bonus",
    "prevent_green_face",
    "prevent_yellow_face",
    "prevent_red_face",
)
EMOTION_RECOVERY_LOCATIONS = (
    "not_in_dormitory",
    "dormitory_floor_1",
    "dormitory_floor_2",
)
_EARLIEST_RECORD = datetime(2000, 1, 1)
_LATEST_RECORD = datetime(2100, 1, 1)


@dataclass(frozen=True)
class AlasFleetEmotionConfigSnapshot:
    value: int
    record: datetime
    control: str
    recover: str
    oath: bool


@dataclass(frozen=True)
class AlasEmotionConfigSnapshot:
    mode: str
    fleet1: AlasFleetEmotionConfigSnapshot
    fleet2: AlasFleetEmotionConfigSnapshot


def _enum(name: str, value: object, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SemanticGateClosed(f"{name} is outside the pinned ALAS surface")
    return value


def _fleet(
    index: int,
    *,
    value: object,
    record: object,
    control: object,
    recover: object,
    oath: object,
) -> AlasFleetEmotionConfigSnapshot:
    prefix = f"Emotion.Fleet{index}"
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 150:
        raise SemanticGateClosed(f"{prefix}Value must be an integer from 0 through 150")
    if (
        not isinstance(record, datetime)
        or record.tzinfo is not None
        or not _EARLIEST_RECORD <= record <= _LATEST_RECORD
    ):
        raise SemanticGateClosed(
            f"{prefix}Record must be a bounded naive datetime"
        )
    if type(oath) is not bool:
        raise SemanticGateClosed(f"{prefix}Oath must be a bool")
    control_value = _enum(f"{prefix}Control", control, EMOTION_CONTROLS)
    recover_value = _enum(
        f"{prefix}Recover", recover, EMOTION_RECOVERY_LOCATIONS
    )
    if control_value == "keep_exp_bonus" and recover_value == "not_in_dormitory":
        raise SemanticGateClosed(
            f"{prefix} cannot keep the experience bonus outside the dormitory"
        )
    return AlasFleetEmotionConfigSnapshot(
        value=value,
        record=record,
        control=control_value,
        recover=recover_value,
        oath=oath,
    )


def validate_alas_emotion_config(
    *,
    mode: object,
    fleet1_value: object,
    fleet1_record: object,
    fleet1_control: object,
    fleet1_recover: object,
    fleet1_oath: object,
    fleet2_value: object,
    fleet2_record: object,
    fleet2_control: object,
    fleet2_recover: object,
    fleet2_oath: object,
) -> AlasEmotionConfigSnapshot:
    """Validate all public fields plus pinned Hard's internal ``nothing`` mode."""

    return AlasEmotionConfigSnapshot(
        mode=_enum("Emotion.Mode", mode, EMOTION_RUNTIME_MODES),
        fleet1=_fleet(
            1,
            value=fleet1_value,
            record=fleet1_record,
            control=fleet1_control,
            recover=fleet1_recover,
            oath=fleet1_oath,
        ),
        fleet2=_fleet(
            2,
            value=fleet2_value,
            record=fleet2_record,
            control=fleet2_control,
            recover=fleet2_recover,
            oath=fleet2_oath,
        ),
    )
