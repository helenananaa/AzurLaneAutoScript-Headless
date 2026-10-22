"""Fail-closed contract for ALAS tactical overflow and student settings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


MAX_TACTICAL_LEVEL = 125
MAX_TACTICAL_OVERFLOW = 5_800
TACTICAL_RAPID_TRAINING_SLOTS = (
    "do_not_use",
    "slot_1",
    "slot_2",
    "slot_3",
    "slot_4",
)
_TACTICAL_FILTER_TOKEN = re.compile(
    r"(same)?(red|blue|yellow)?-?(t[1234])?",
    flags=re.IGNORECASE,
)
_FILTER_SEPARATOR_TRANSLATION = str.maketrans("＞﹥›˃ᐳ❯", ">>>>>>")
_FILTER_HYPHEN_TRANSLATION = str.maketrans("‐‑‒–—―−－﹣﹘⁃", "-----------")


@dataclass(frozen=True)
class AlasTacticalConfigSnapshot:
    tactical_filter: str
    rapid_training_slot: str
    control_exp_overflow_enable: bool
    t1_allow: int | None
    t2_allow: int | None
    t3_allow: int | None
    t4_allow: int | None
    add_new_student_enable: bool
    add_new_student_favorite: bool | None
    add_new_student_min_level: int | None


def _bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise SemanticGateClosed(f"{field} must be a bool")
    return value


def _bounded_integer(
    value: object, *, field: str, low: int, high: int, allow_text: bool = False
) -> int:
    if isinstance(value, bool):
        raise SemanticGateClosed(f"{field} must be a bounded integer")
    if allow_text and isinstance(value, str):
        raw = value.strip()
        if not raw.isdigit():
            raise SemanticGateClosed(f"{field} must contain decimal digits")
        parsed = int(raw)
    elif isinstance(value, int):
        parsed = value
    else:
        raise SemanticGateClosed(f"{field} must be a bounded integer")
    if not low <= parsed <= high:
        raise SemanticGateClosed(f"{field} is outside safe bounds")
    return parsed


def _rapid_training_slot(value: object) -> str:
    if type(value) is not str or value not in TACTICAL_RAPID_TRAINING_SLOTS:
        raise SemanticGateClosed("Tactical.RapidTrainingSlot is unsupported")
    return value


def _tactical_filter(value: object) -> str:
    if type(value) is not str:
        raise SemanticGateClosed("Tactical.TacticalFilter must be text")
    normalized = re.sub(r"[ \t\r\n]", "", value)
    normalized = normalized.translate(_FILTER_SEPARATOR_TRANSLATION)
    normalized = normalized.translate(_FILTER_HYPHEN_TRANSLATION)
    tokens = normalized.split(">")
    if not tokens or any(not token for token in tokens):
        raise SemanticGateClosed("Tactical.TacticalFilter contains an empty token")
    for token in tokens:
        if token.lower() == "first":
            continue
        match = _TACTICAL_FILTER_TOKEN.fullmatch(token)
        if match is None or not any(match.groups()):
            raise SemanticGateClosed(
                f'Tactical.TacticalFilter contains an invalid token: "{token}"'
            )
    return " > ".join(tokens)


def validate_alas_tactical_config(
    *,
    tactical_filter: object,
    rapid_training_slot: object,
    control_exp_overflow_enable: object,
    t1_allow: object,
    t2_allow: object,
    t3_allow: object,
    t4_allow: object,
    add_new_student_enable: object,
    add_new_student_favorite: object,
    add_new_student_min_level: object,
) -> AlasTacticalConfigSnapshot:
    """Validate the settings consumed by enabled original tactical branches."""

    overflow_enabled = _bool(
        control_exp_overflow_enable, field="ControlExpOverflow.Enable"
    )
    student_enabled = _bool(add_new_student_enable, field="AddNewStudent.Enable")

    def overflow_allowance(value: object, *, field: str) -> int | None:
        # Original ALAS reads allowances only inside the enabled overflow
        # branch.  Unused saved values must not block reward/book handling.
        if not overflow_enabled:
            return None
        return _bounded_integer(value, field=field, low=0, high=MAX_TACTICAL_OVERFLOW)

    return AlasTacticalConfigSnapshot(
        tactical_filter=_tactical_filter(tactical_filter),
        rapid_training_slot=_rapid_training_slot(rapid_training_slot),
        control_exp_overflow_enable=overflow_enabled,
        t1_allow=overflow_allowance(
            t1_allow, field="ControlExpOverflow.T1Allow"
        ),
        t2_allow=overflow_allowance(
            t2_allow, field="ControlExpOverflow.T2Allow"
        ),
        t3_allow=overflow_allowance(
            t3_allow, field="ControlExpOverflow.T3Allow"
        ),
        t4_allow=overflow_allowance(
            t4_allow, field="ControlExpOverflow.T4Allow"
        ),
        add_new_student_enable=student_enabled,
        add_new_student_favorite=(
            _bool(add_new_student_favorite, field="AddNewStudent.Favorite")
            if student_enabled else None
        ),
        add_new_student_min_level=(
            _bounded_integer(
                add_new_student_min_level,
                field="AddNewStudent.MinLevel",
                low=1,
                high=MAX_TACTICAL_LEVEL,
                allow_text=True,
            ) if student_enabled else None
        ),
    )
