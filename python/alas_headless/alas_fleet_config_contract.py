"""Fail-closed campaign Fleet configuration contract for semantic ALAS runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .semantic_oracle import SemanticGateClosed


FLEET_FORMATIONS = ("line_ahead", "double_line", "diamond")
FLEET_MODES = (
    "combat_auto",
    "combat_manual",
    "stand_still_in_the_middle",
    "hide_in_bottom_left",
    "hide_in_upper_left",
)
FLEET_STEPS = (2, 3, 4, 5)
FLEET_ORDERS = (
    "fleet1_mob_fleet2_boss",
    "fleet1_boss_fleet2_mob",
    "fleet1_all_fleet2_standby",
    "fleet1_standby_fleet2_all",
)


@dataclass(frozen=True)
class AlasFleetConfigSnapshot:
    fleet1: int
    fleet1_formation: str
    fleet1_mode: str
    fleet1_step: int
    fleet2: int
    fleet2_formation: str
    fleet2_mode: str
    fleet2_step: int
    fleet_order: str


def _bounded_integer(value: Any, *, field: str, low: int, high: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value not in range(low, high + 1)
    ):
        raise SemanticGateClosed(
            f"{field} must be an integer from {low} through {high}"
        )
    return value


def _enum(value: Any, *, field: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SemanticGateClosed(
            f"{field} is outside the pinned ALAS configuration surface"
        )
    return value


def validate_alas_fleet_config(
    *,
    fleet1: Any,
    fleet1_formation: Any,
    fleet1_mode: Any,
    fleet1_step: Any,
    fleet2: Any,
    fleet2_formation: Any,
    fleet2_mode: Any,
    fleet2_step: Any,
    fleet_order: Any,
) -> AlasFleetConfigSnapshot:
    """Classify the complete pinned Fleet surface before ALAS navigates.

    Fleet selection and step values remain owned by ALAS and its existing map
    state machine. The pinned ALAS tree never consumes either Formation field,
    while non-auto combat modes still require untyped directional/weapon input.
    The semantic campaign sortie has only reviewed one FleetOrder. Refuse those
    valid-but-unqualified values early instead of silently ignoring or reaching
    a legacy pixel/input path.
    """

    snapshot = AlasFleetConfigSnapshot(
        fleet1=_bounded_integer(fleet1, field="Fleet.Fleet1", low=1, high=6),
        fleet1_formation=_enum(
            fleet1_formation,
            field="Fleet.Fleet1Formation",
            allowed=FLEET_FORMATIONS,
        ),
        fleet1_mode=_enum(
            fleet1_mode, field="Fleet.Fleet1Mode", allowed=FLEET_MODES
        ),
        fleet1_step=_bounded_integer(
            fleet1_step, field="Fleet.Fleet1Step", low=2, high=5
        ),
        fleet2=_bounded_integer(fleet2, field="Fleet.Fleet2", low=0, high=6),
        fleet2_formation=_enum(
            fleet2_formation,
            field="Fleet.Fleet2Formation",
            allowed=FLEET_FORMATIONS,
        ),
        fleet2_mode=_enum(
            fleet2_mode, field="Fleet.Fleet2Mode", allowed=FLEET_MODES
        ),
        fleet2_step=_bounded_integer(
            fleet2_step, field="Fleet.Fleet2Step", low=2, high=5
        ),
        fleet_order=_enum(
            fleet_order, field="Fleet.FleetOrder", allowed=FLEET_ORDERS
        ),
    )
    if (
        snapshot.fleet1_formation != "double_line"
        or snapshot.fleet2_formation != "double_line"
    ):
        raise SemanticGateClosed(
            "non-default Fleet formation is not consumed by pinned ALAS"
        )
    if (
        snapshot.fleet1_mode != "combat_auto"
        or snapshot.fleet2_mode != "combat_auto"
    ):
        raise SemanticGateClosed(
            "manual Fleet modes require unqualified directional or weapon input"
        )
    reviewed_order = snapshot.fleet_order == "fleet1_mob_fleet2_boss" or (
        snapshot.fleet2 == 0
        and snapshot.fleet_order == "fleet1_all_fleet2_standby"
    ) or (
        snapshot.fleet2 != 0
        and snapshot.fleet_order == "fleet1_standby_fleet2_all"
    )
    if not reviewed_order:
        raise SemanticGateClosed(
            "campaign Fleet order is not semantically qualified"
        )
    return snapshot
