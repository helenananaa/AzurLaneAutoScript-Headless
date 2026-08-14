"""Fail-closed contract for shared ALAS campaign enemy priority."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


ENEMY_PRIORITY_MODES = (
    "default_mode",
    "S3_enemy_first",
    "S1_enemy_first",
)


@dataclass(frozen=True)
class AlasEnemyPriorityConfigSnapshot:
    enemy_scale_balance_weight: str


def validate_alas_enemy_priority_config(
    *, enemy_scale_balance_weight: object
) -> AlasEnemyPriorityConfigSnapshot:
    """Validate the complete pinned EnemyPriority enum before navigation."""

    if (
        not isinstance(enemy_scale_balance_weight, str)
        or enemy_scale_balance_weight not in ENEMY_PRIORITY_MODES
    ):
        raise SemanticGateClosed(
            "EnemyPriority.EnemyScaleBalanceWeight is outside the pinned ALAS "
            "configuration surface"
        )
    return AlasEnemyPriorityConfigSnapshot(
        enemy_scale_balance_weight=enemy_scale_balance_weight
    )
