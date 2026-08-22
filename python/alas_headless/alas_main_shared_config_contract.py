"""Fail-closed contract for the Main/Main2/Main3 stop-condition surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .alas_campaign_route_config_contract import MAIN_TASKS
from .semantic_oracle import SemanticGateClosed


MAIN_SHARED_GROUPS = (
    "Scheduler",
    "Campaign",
    "StopCondition",
    "Fleet",
    "Submarine",
    "Emotion",
    "HpControl",
    "EnemyPriority",
    "Storage",
)
STOP_CONDITION_MAP_ACHIEVEMENTS = (
    "non_stop",
    "100_percent_clear",
    "map_3_stars",
    "threat_safe",
    "threat_safe_without_3_stars",
)


@dataclass(frozen=True)
class AlasMainStopConditionConfigSnapshot:
    task: str
    oil_limit: int
    run_count: int
    map_achievement: str
    stage_increase: bool
    get_new_ship: bool
    reach_level: int


def _non_negative_integer(field: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SemanticGateClosed(field + " must be a non-negative integer")
    return value


def validate_alas_main_stop_condition_config(
    *,
    task: object,
    oil_limit: object,
    run_count: object,
    map_achievement: object,
    stage_increase: object,
    get_new_ship: object,
    reach_level: object,
) -> Optional[AlasMainStopConditionConfigSnapshot]:
    """Validate all six fields for the three normal Main task instances.

    Other campaign families retain their existing behavior.  This validator
    classifies configuration only; the original ALAS methods remain the sole
    owners of stop ordering, decrement, persistence, and scheduling.
    """

    if not isinstance(task, str) or not task:
        raise SemanticGateClosed("campaign scheduler command is missing")
    if task not in MAIN_TASKS:
        return None
    if (
        not isinstance(map_achievement, str)
        or map_achievement not in STOP_CONDITION_MAP_ACHIEVEMENTS
    ):
        raise SemanticGateClosed(
            "StopCondition.MapAchievement is outside the pinned ALAS surface"
        )
    if type(stage_increase) is not bool:
        raise SemanticGateClosed("StopCondition.StageIncrease must be a bool")
    if type(get_new_ship) is not bool:
        raise SemanticGateClosed("StopCondition.GetNewShip must be a bool")
    return AlasMainStopConditionConfigSnapshot(
        task=task,
        oil_limit=_non_negative_integer("StopCondition.OilLimit", oil_limit),
        run_count=_non_negative_integer("StopCondition.RunCount", run_count),
        map_achievement=map_achievement,
        stage_increase=stage_increase,
        get_new_ship=get_new_ship,
        reach_level=_non_negative_integer("StopCondition.ReachLevel", reach_level),
    )


__all__ = (
    "AlasMainStopConditionConfigSnapshot",
    "MAIN_SHARED_GROUPS",
    "STOP_CONDITION_MAP_ACHIEVEMENTS",
    "validate_alas_main_stop_condition_config",
)
