"""Fail-closed contracts for ALAS global runtime optimization settings."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


WHEN_TASK_QUEUE_EMPTY = ("stay_there", "goto_main", "close_game")


@dataclass(frozen=True)
class AlasScreenshotIntervalConfigSnapshot:
    screenshot_interval: int | float
    combat_screenshot_interval: int | float


def _finite_number(value: object, *, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticGateClosed(field + " must be a finite number")
    if not math.isfinite(value):
        raise SemanticGateClosed(field + " must be finite")
    return value


def validate_alas_screenshot_interval_config(
    *, screenshot_interval: object, combat_screenshot_interval: object
) -> AlasScreenshotIntervalConfigSnapshot:
    """Validate both global screenshot intervals before changing the timer."""

    return AlasScreenshotIntervalConfigSnapshot(
        screenshot_interval=_finite_number(
            screenshot_interval,
            field="Optimization.ScreenshotInterval",
        ),
        combat_screenshot_interval=_finite_number(
            combat_screenshot_interval,
            field="Optimization.CombatScreenshotInterval",
        ),
    )


def validate_alas_when_task_queue_empty(value: object) -> str:
    """Validate the original ALAS idle behavior before dequeuing a task."""

    if type(value) is not str or value not in WHEN_TASK_QUEUE_EMPTY:
        raise SemanticGateClosed(
            "Optimization.WhenTaskQueueEmpty must be stay_there, goto_main, or close_game"
        )
    return value
