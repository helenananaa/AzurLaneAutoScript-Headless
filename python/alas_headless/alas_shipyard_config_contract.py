"""Fail-closed contract for ALAS Shipyard task configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from collections.abc import Mapping

from .semantic_oracle import SemanticGateClosed


# Frozen replay choices; installed ALAS declarations may extend them at runtime.
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
    pr_series: int | None
    pr_index: int | None
    pr_buy_amount: int
    pr_last_run: datetime
    dr_series: int | None
    dr_index: int | None
    dr_buy_amount: int
    dr_last_run: datetime


def _declared_member(name: str, value: object, baseline: tuple[int, ...], options: object) -> int:
    """Accept declared upstream choices without claiming typed purchase support."""
    if type(value) is int and value in baseline:
        return value
    field = name.rsplit('.', 1)[-1]
    declaration = options.get(field) if isinstance(options, Mapping) else None
    choices = declaration.get('option') if isinstance(declaration, Mapping) else None
    minimum = 1 if field == 'ResearchSeries' else 0
    if (type(value) is int and value >= minimum and isinstance(choices, (list, tuple))
            and any(type(choice) is int and choice == value for choice in choices)):
        return value
    raise SemanticGateClosed(f"{name} is not a declared ALAS choice")


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
    pr_options: object = None,
    dr_options: object = None,
) -> AlasShipyardConfigSnapshot:
    """Validate time arithmetic and the Shipyard groups ALAS will execute."""

    pr_amount = _buy_amount("Shipyard.BuyAmount", pr_buy_amount)
    dr_amount = _buy_amount("ShipyardDr.BuyAmount", dr_buy_amount)
    # ALAS shipyard_run returns before reading series/index or navigating when
    # count is zero.  LastRun still participates in the parent run's date
    # comparison, so its validation remains independent of this branch.

    return AlasShipyardConfigSnapshot(
        pr_series=_declared_member(
            "Shipyard.ResearchSeries", pr_series, SHIPYARD_PR_SERIES, pr_options
        ) if pr_amount else None,
        pr_index=_declared_member(
            "Shipyard.ShipIndex", pr_index, SHIPYARD_INDICES, pr_options
        ) if pr_amount else None,
        pr_buy_amount=pr_amount,
        pr_last_run=_last_run("Shipyard.LastRun", pr_last_run),
        dr_series=_declared_member(
            "ShipyardDr.ResearchSeries", dr_series, SHIPYARD_DR_SERIES, dr_options
        ) if dr_amount else None,
        dr_index=_declared_member(
            "ShipyardDr.ShipIndex", dr_index, SHIPYARD_INDICES, dr_options
        ) if dr_amount else None,
        dr_buy_amount=dr_amount,
        dr_last_run=_last_run("ShipyardDr.LastRun", dr_last_run),
    )
