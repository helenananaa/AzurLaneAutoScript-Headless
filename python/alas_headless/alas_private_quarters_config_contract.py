"""Fail-closed contract for the pinned ALAS Private Quarters settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


PRIVATE_QUARTERS_SHIPS = frozenset(
    ("anchorage", "noshiro", "sirius", "new_jersey", "taihou", "aegir", "nakhimov")
)


@dataclass(frozen=True)
class AlasPrivateQuartersConfigSnapshot:
    buy_roses: bool
    buy_cake: bool
    target_interact: bool
    target_ship: str


def validate_alas_private_quarters_config(
    *,
    buy_roses: object,
    buy_cake: object,
    target_interact: object,
    target_ship: object,
) -> AlasPrivateQuartersConfigSnapshot:
    """Admit declared values before Private Quarters UI, currency, or input work."""

    for name, value in (
        ("BuyRoses", buy_roses),
        ("BuyCake", buy_cake),
        ("TargetInteract", target_interact),
    ):
        if type(value) is not bool:
            raise SemanticGateClosed("PrivateQuarters." + name + " must be a boolean")
    # ALAS logs the name even with interaction disabled, then consults its own
    # available_targets at the interaction branch. New upstream roles need not
    # be copied into a second configuration catalog; typed inputs still require
    # a supported, unique target at the actual room-navigation boundary.
    if type(target_ship) is not str or not target_ship.strip():
        raise SemanticGateClosed("PrivateQuarters.TargetShip must be non-empty text")
    return AlasPrivateQuartersConfigSnapshot(
        buy_roses=buy_roses,
        buy_cake=buy_cake,
        target_interact=target_interact,
        target_ship=target_ship,
    )
