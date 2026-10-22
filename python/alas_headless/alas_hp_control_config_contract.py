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
    hp_balance_threshold: float | None
    hp_balance_weight: tuple[int, int, int]
    repair_use_single_threshold: float | None
    repair_use_multi_threshold: float | None
    low_hp_retreat_threshold: float | None


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

    balance = _boolean("HpControl_UseHpBalance", use_hp_balance)
    repair = _boolean("HpControl_UseEmergencyRepair", use_emergency_repair)
    retreat = _boolean("HpControl_UseLowHpRetreat", use_low_hp_retreat)
    snapshot = AlasHpControlConfigSnapshot(
        use_hp_balance=balance,
        use_emergency_repair=repair,
        use_low_hp_retreat=retreat,
        hp_balance_threshold=_ratio(
            "HpControl_HpBalanceThreshold", hp_balance_threshold
        ) if balance else None,
        # hp_get uses weights even with every HP-control switch disabled.
        hp_balance_weight=_weights(hp_balance_weight),
        repair_use_single_threshold=_ratio(
            "HpControl_RepairUseSingleThreshold", repair_use_single_threshold
        ) if repair else None,
        repair_use_multi_threshold=_ratio(
            "HpControl_RepairUseMultiThreshold", repair_use_multi_threshold
        ) if repair else None,
        low_hp_retreat_threshold=_ratio(
            "HpControl_LowHpRetreatThreshold", low_hp_retreat_threshold
        ) if retreat else None,
    )
    return snapshot
