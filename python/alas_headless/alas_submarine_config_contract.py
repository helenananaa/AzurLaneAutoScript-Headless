"""Fail-closed contract for shared ALAS campaign submarine settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


SUBMARINE_FLEETS = (0, 1, 2)
SUBMARINE_MODES = (
    "do_not_use",
    "hunt_only",
    "boss_only",
    "hunt_and_boss",
    "every_combat",
)
SUBMARINE_AUTO_SEARCH_MODES = ("sub_standby", "sub_auto_call")
SUBMARINE_BOSS_DISTANCES = (
    "to_boss_position",
    "1_grid_to_boss",
    "2_grid_to_boss",
    "use_open_ocean_support",
)


@dataclass(frozen=True)
class AlasSubmarineConfigSnapshot:
    fleet: int
    mode: str
    auto_search_mode: str
    distance_to_boss: str


def _enum(name: str, value: object, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SemanticGateClosed(f"{name} is outside the pinned ALAS surface")
    return value


def validate_alas_submarine_config(
    *,
    fleet: object,
    mode: object,
    auto_search_mode: object,
    distance_to_boss: object,
) -> AlasSubmarineConfigSnapshot:
    """Classify configuration; capability-specific ports own execution admission."""

    if isinstance(fleet, bool) or not isinstance(fleet, int) or fleet not in SUBMARINE_FLEETS:
        raise SemanticGateClosed("Submarine.Fleet must be 0, 1, or 2")
    snapshot = AlasSubmarineConfigSnapshot(
        fleet=fleet,
        mode=_enum("Submarine.Mode", mode, SUBMARINE_MODES),
        auto_search_mode=_enum(
            "Submarine.AutoSearchMode",
            auto_search_mode,
            SUBMARINE_AUTO_SEARCH_MODES,
        ),
        distance_to_boss=_enum(
            "Submarine.DistanceToBoss",
            distance_to_boss,
            SUBMARINE_BOSS_DISTANCES,
        ),
    )
    return snapshot
