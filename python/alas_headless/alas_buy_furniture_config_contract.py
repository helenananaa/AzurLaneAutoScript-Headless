"""Fail-closed contract for ALAS Dorm furniture-purchase configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .semantic_oracle import SemanticGateClosed


BUY_FURNITURE_OPTIONS = ("set", "all")
_MIN_RECORD = datetime(2000, 1, 1)
_MAX_RECORD = datetime(2100, 1, 1)


@dataclass(frozen=True)
class AlasBuyFurnitureConfigSnapshot:
    enable: bool
    buy_option: str
    last_run: datetime


def validate_alas_buy_furniture_config(
    *, enable: object, buy_option: object, last_run: object
) -> AlasBuyFurnitureConfigSnapshot:
    """Validate furniture fields before date arithmetic, navigation, or purchase."""

    if type(enable) is not bool:
        raise SemanticGateClosed("BuyFurniture.Enable must be a bool")
    if type(buy_option) is not str or buy_option not in BUY_FURNITURE_OPTIONS:
        raise SemanticGateClosed(
            "BuyFurniture.BuyOption is outside the pinned ALAS surface"
        )
    if type(last_run) is not datetime:
        raise SemanticGateClosed("BuyFurniture.LastRun must be a datetime")
    if last_run.tzinfo is not None:
        raise SemanticGateClosed("BuyFurniture.LastRun must be timezone-naive")
    if not _MIN_RECORD <= last_run <= _MAX_RECORD:
        raise SemanticGateClosed("BuyFurniture.LastRun is outside the safe range")
    return AlasBuyFurnitureConfigSnapshot(
        enable=enable,
        buy_option=buy_option,
        last_run=last_run,
    )
