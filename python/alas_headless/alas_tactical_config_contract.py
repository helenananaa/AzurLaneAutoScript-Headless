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
    t1_allow: int
    t2_allow: int
    t3_allow: int
    t4_allow: int
    add_new_student_enable: bool
    add_new_student_favorite: bool
    add_new_student_min_level: int


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
    """Validate all ten shared tactical settings before original decisions."""

    return AlasTacticalConfigSnapshot(
        tactical_filter=_tactical_filter(tactical_filter),
        rapid_training_slot=_rapid_training_slot(rapid_training_slot),
        control_exp_overflow_enable=_bool(
            control_exp_overflow_enable, field="ControlExpOverflow.Enable"
        ),
        t1_allow=_bounded_integer(
            t1_allow, field="ControlExpOverflow.T1Allow", low=0, high=MAX_TACTICAL_OVERFLOW
        ),
        t2_allow=_bounded_integer(
            t2_allow, field="ControlExpOverflow.T2Allow", low=0, high=MAX_TACTICAL_OVERFLOW
        ),
        t3_allow=_bounded_integer(
            t3_allow, field="ControlExpOverflow.T3Allow", low=0, high=MAX_TACTICAL_OVERFLOW
        ),
        t4_allow=_bounded_integer(
            t4_allow, field="ControlExpOverflow.T4Allow", low=0, high=MAX_TACTICAL_OVERFLOW
        ),
        add_new_student_enable=_bool(
            add_new_student_enable, field="AddNewStudent.Enable"
        ),
        add_new_student_favorite=_bool(
            add_new_student_favorite, field="AddNewStudent.Favorite"
        ),
        add_new_student_min_level=_bounded_integer(
            add_new_student_min_level,
            field="AddNewStudent.MinLevel",
            low=1,
            high=MAX_TACTICAL_LEVEL,
            allow_text=True,
        ),
    )
