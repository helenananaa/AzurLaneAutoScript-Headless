"""Fail-closed contract for ALAS tactical overflow and student settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


MAX_TACTICAL_LEVEL = 125
MAX_TACTICAL_OVERFLOW = 5_800


@dataclass(frozen=True)
class AlasTacticalConfigSnapshot:
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


def validate_alas_tactical_config(
    *,
    control_exp_overflow_enable: object,
    t1_allow: object,
    t2_allow: object,
    t3_allow: object,
    t4_allow: object,
    add_new_student_enable: object,
    add_new_student_favorite: object,
    add_new_student_min_level: object,
) -> AlasTacticalConfigSnapshot:
    """Validate all eight shared tactical settings before original decisions."""

    return AlasTacticalConfigSnapshot(
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
