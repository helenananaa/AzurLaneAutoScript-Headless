"""Fail-closed contract for ALAS Exercise task configuration."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class AlasExerciseConfigSnapshot:
    strategy: str
    opponent_mode: str
    opponent_trial: int


def validate_alas_exercise_config(
    *, strategy: object, opponent_mode: object, opponent_trial: object
) -> AlasExerciseConfigSnapshot:
    """Validate Exercise fields before navigation or consuming an attempt."""

    if type(strategy) is not str or strategy not in EXERCISE_STRATEGIES:
        raise SemanticGateClosed("Exercise.ExerciseStrategy is unsupported")
    if type(opponent_mode) is not str or opponent_mode not in EXERCISE_OPPONENT_MODES:
        raise SemanticGateClosed("Exercise.OpponentChooseMode is unsupported")
    if type(opponent_trial) is not int or opponent_trial < 1:
        raise SemanticGateClosed("Exercise.OpponentTrial must be a positive integer")
    return AlasExerciseConfigSnapshot(
        strategy=strategy,
        opponent_mode=opponent_mode,
        opponent_trial=opponent_trial,
    )
