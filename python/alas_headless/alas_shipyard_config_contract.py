"""Fail-closed contract for ALAS Shipyard task configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .semantic_oracle import SemanticGateClosed


SHIPYARD_PR_SERIES = (1, 2, 3, 4, 5, 6)
SHIPYARD_DR_SERIES = (2, 3, 4, 5)
SHIPYARD_INDICES = (0, 1, 2, 3, 4, 5, 6)
# Pinned ALAS has explicit per-item price evidence for purchases 1..15.  It
# assigns a fallback price after that point, but the current semantic observer
# cannot prove the game's displayed quantity or total-price postcondition for
# those unbounded values.  Keep that wider upstream surface fail-closed until
# the purchase panel itself has a typed receipt.
SHIPYARD_VERIFIED_BUY_AMOUNTS = tuple(range(16))
_MIN_RECORD = datetime(2000, 1, 1)
_MAX_RECORD = datetime(2100, 1, 1)


@dataclass(frozen=True)
class AlasShipyardConfigSnapshot:
    pr_series: int
    pr_index: int
    pr_buy_amount: int
    pr_last_run: datetime
    dr_series: int
    dr_index: int
    dr_buy_amount: int
    dr_last_run: datetime


def _exact_member(name: str, value: object, allowed: tuple[int, ...]) -> int:
    if type(value) is not int or value not in allowed:
        raise SemanticGateClosed(f"{name} is outside the pinned ALAS surface")
    return value


def _last_run(name: str, value: object) -> datetime:
    if type(value) is not datetime:
        raise SemanticGateClosed(f"{name} must be a datetime")
    if value.tzinfo is not None:
        raise SemanticGateClosed(f"{name} must be timezone-naive")
    if not _MIN_RECORD <= value <= _MAX_RECORD:
        raise SemanticGateClosed(f"{name} is outside the safe range")
    return value


def _buy_amount(name: str, value: object) -> int:
    if type(value) is not int or value not in SHIPYARD_VERIFIED_BUY_AMOUNTS:
        raise SemanticGateClosed(f"{name} is outside the verified safe subset 0..15")
    return value


def validate_alas_shipyard_config(
    *,
    pr_series: object,
    pr_index: object,
    pr_buy_amount: object,
    pr_last_run: object,
    dr_series: object,
    dr_index: object,
    dr_buy_amount: object,
    dr_last_run: object,
) -> AlasShipyardConfigSnapshot:
    """Validate both Shipyard groups before time arithmetic or blueprint use."""

    return AlasShipyardConfigSnapshot(
        pr_series=_exact_member(
            "Shipyard.ResearchSeries", pr_series, SHIPYARD_PR_SERIES
        ),
        pr_index=_exact_member("Shipyard.ShipIndex", pr_index, SHIPYARD_INDICES),
        pr_buy_amount=_buy_amount("Shipyard.BuyAmount", pr_buy_amount),
        pr_last_run=_last_run("Shipyard.LastRun", pr_last_run),
        dr_series=_exact_member(
            "ShipyardDr.ResearchSeries", dr_series, SHIPYARD_DR_SERIES
        ),
        dr_index=_exact_member(
            "ShipyardDr.ShipIndex", dr_index, SHIPYARD_INDICES
        ),
        dr_buy_amount=_buy_amount("ShipyardDr.BuyAmount", dr_buy_amount),
        dr_last_run=_last_run("ShipyardDr.LastRun", dr_last_run),
    )
