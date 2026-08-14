"""Fail-closed contract for ALAS free weekly supply-pack settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasSupplyPackConfigSnapshot:
    collect: bool
    day_of_week: int


def validate_alas_supply_pack_config(
    *, collect: object, day_of_week: object
) -> AlasSupplyPackConfigSnapshot:
    """Validate the Freebies gate and Monday-zero target weekday."""

    if type(collect) is not bool:
        raise SemanticGateClosed("SupplyPack.Collect must be a bool")
    if type(day_of_week) is not int or day_of_week not in range(7):
        raise SemanticGateClosed("SupplyPack.DayOfWeek must be an integer from 0 to 6")
    return AlasSupplyPackConfigSnapshot(collect=collect, day_of_week=day_of_week)
