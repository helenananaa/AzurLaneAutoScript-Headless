"""Fail-closed contract for shared ALAS campaign HP-control settings."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasHpControlConfigSnapshot:
    use_hp_balance: bool
    use_emergency_repair: bool
    use_low_hp_retreat: bool
    hp_balance_threshold: float
    hp_balance_weight: tuple[int, int, int]
    repair_use_single_threshold: float
    repair_use_multi_threshold: float
    low_hp_retreat_threshold: float


def _boolean(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise SemanticGateClosed(f"{name} must be a bool")
    return value


def _ratio(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticGateClosed(f"{name} must be a finite ratio")
    ratio = float(value)
    if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
        raise SemanticGateClosed(f"{name} must be between zero and one")
    return ratio


def _weights(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise SemanticGateClosed("HpControl_HpBalanceWeight must be text")
    parts = tuple(part.strip() for part in value.replace("，", ",").split(","))
    if len(parts) != 3 or any(not part for part in parts):
        raise SemanticGateClosed(
            "HpControl_HpBalanceWeight must contain exactly three weights"
        )
    try:
        weights = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise SemanticGateClosed(
            "HpControl_HpBalanceWeight contains a non-number"
        ) from exc
    if any(weight <= 0 for weight in weights):
        raise SemanticGateClosed(
            "HpControl_HpBalanceWeight values must be finite and positive"
        )
    return weights  # type: ignore[return-value]


def validate_alas_hp_control_config(
    *,
    use_hp_balance: object,
    use_emergency_repair: object,
    use_low_hp_retreat: object,
    hp_balance_threshold: object,
    hp_balance_weight: object,
    repair_use_single_threshold: object,
    repair_use_multi_threshold: object,
    low_hp_retreat_threshold: object,
) -> AlasHpControlConfigSnapshot:
    """Validate values; unsupported input branches fail at their owning port."""

    snapshot = AlasHpControlConfigSnapshot(
        use_hp_balance=_boolean("HpControl_UseHpBalance", use_hp_balance),
        use_emergency_repair=_boolean(
            "HpControl_UseEmergencyRepair", use_emergency_repair
        ),
        use_low_hp_retreat=_boolean(
            "HpControl_UseLowHpRetreat", use_low_hp_retreat
        ),
        hp_balance_threshold=_ratio(
            "HpControl_HpBalanceThreshold", hp_balance_threshold
        ),
        hp_balance_weight=_weights(hp_balance_weight),
        repair_use_single_threshold=_ratio(
            "HpControl_RepairUseSingleThreshold", repair_use_single_threshold
        ),
        repair_use_multi_threshold=_ratio(
            "HpControl_RepairUseMultiThreshold", repair_use_multi_threshold
        ),
        low_hp_retreat_threshold=_ratio(
            "HpControl_LowHpRetreatThreshold", low_hp_retreat_threshold
        ),
    )
    return snapshot
