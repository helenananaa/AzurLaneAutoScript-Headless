"""Fail-closed contract for ALAS Exercise task configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .semantic_oracle import SemanticGateClosed


EXERCISE_STRATEGIES = (
    "aggressive",
    "fri18",
    "sat0",
    "sat12",
    "sat18",
    "sun0",
    "sun12",
    "sun18",
)
EXERCISE_OPPONENT_MODES = (
    "max_exp",
    "easiest",
    "leftmost",
    "easiest_else_exp",
)
_EARLIEST_RECORD = datetime(2000, 1, 1)
_LATEST_RECORD = datetime(2100, 1, 1)


@dataclass(frozen=True)
class AlasExerciseConfigSnapshot:
    strategy: str
    opponent_mode: str
    opponent_trial: int
    low_hp_threshold: float
    opponent_refresh_value: int
    opponent_refresh_record: datetime


def validate_alas_exercise_config(
    *,
    strategy: object,
    opponent_mode: object,
    opponent_trial: object,
    low_hp_threshold: object,
    opponent_refresh_value: object,
    opponent_refresh_record: object,
) -> AlasExerciseConfigSnapshot:
    """Validate consumed Exercise fields before navigation or an attempt."""

    if type(strategy) is not str or strategy not in EXERCISE_STRATEGIES:
        raise SemanticGateClosed("Exercise.ExerciseStrategy is unsupported")
    if type(opponent_mode) is not str or opponent_mode not in EXERCISE_OPPONENT_MODES:
        raise SemanticGateClosed("Exercise.OpponentChooseMode is unsupported")
    if type(opponent_trial) is not int or opponent_trial < 1:
        raise SemanticGateClosed("Exercise.OpponentTrial must be a positive integer")
    if (
        isinstance(low_hp_threshold, bool)
        or not isinstance(low_hp_threshold, (int, float))
        or not math.isfinite(low_hp_threshold)
        or not 0 <= low_hp_threshold <= 1
    ):
        raise SemanticGateClosed("Exercise.LowHpThreshold must be between 0 and 1")
    if (
        type(opponent_refresh_value) is not int
        or not 0 <= opponent_refresh_value <= 6
    ):
        raise SemanticGateClosed(
            "Exercise.OpponentRefreshValue must be an integer from 0 to 6"
        )
    if (
        not isinstance(opponent_refresh_record, datetime)
        or opponent_refresh_record.tzinfo is not None
        or not _EARLIEST_RECORD <= opponent_refresh_record <= _LATEST_RECORD
    ):
        raise SemanticGateClosed(
            "Exercise.OpponentRefreshRecord must be a bounded naive datetime"
        )
    return AlasExerciseConfigSnapshot(
        strategy=strategy,
        opponent_mode=opponent_mode,
        opponent_trial=opponent_trial,
        low_hp_threshold=float(low_hp_threshold),
        opponent_refresh_value=opponent_refresh_value,
        opponent_refresh_record=opponent_refresh_record,
    )
