"""Fail-closed contract for ALAS Gacha task configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


GACHA_POOLS = ("light", "heavy", "special", "event", "wishing_well")
GACHA_AMOUNTS = tuple(range(1, 11))


@dataclass(frozen=True)
class AlasGachaConfigSnapshot:
    pool: str
    amount: int
    use_ticket: bool
    use_drill: bool


def validate_alas_gacha_config(
    *, pool: object, amount: object, use_ticket: object, use_drill: object
) -> AlasGachaConfigSnapshot:
    """Validate Gacha fields before build scope entry or resource reads."""

    if type(pool) is not str or pool not in GACHA_POOLS:
        raise SemanticGateClosed("Gacha.Pool is outside the pinned ALAS surface")
    if type(amount) is not int or amount not in GACHA_AMOUNTS:
        raise SemanticGateClosed("Gacha.Amount must be an integer from 1 to 10")
    if type(use_ticket) is not bool:
        raise SemanticGateClosed("Gacha.UseTicket must be a bool")
    if type(use_drill) is not bool:
        raise SemanticGateClosed("Gacha.UseDrill must be a bool")
    return AlasGachaConfigSnapshot(
        pool=pool,
        amount=amount,
        use_ticket=use_ticket,
        use_drill=use_drill,
    )
