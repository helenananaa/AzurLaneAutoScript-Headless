"""Fail-closed contract for the pinned ALAS Awaken task settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


AWAKEN_LEVEL_CAPS = frozenset(("level120", "level125"))


@dataclass(frozen=True)
class AlasAwakenConfigSnapshot:
    """The two validated settings consumed by ``Awaken.run``."""

    level_cap: str
    favourite: bool


def validate_alas_awaken_config(
    *, level_cap: object, favourite: object
) -> AlasAwakenConfigSnapshot:
    """Admit only the fixed upstream enum and an exact favourite boolean."""

    if type(level_cap) is not str or level_cap not in AWAKEN_LEVEL_CAPS:
        raise SemanticGateClosed("Awaken.LevelCap is outside the pinned enum")
    if type(favourite) is not bool:
        raise SemanticGateClosed("Awaken.Favourite must be a boolean")
    return AlasAwakenConfigSnapshot(level_cap=level_cap, favourite=favourite)
