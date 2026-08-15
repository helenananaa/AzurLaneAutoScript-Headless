"""Fail-closed contract for the pinned ALAS Coalition settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


COALITION_MODES = frozenset(("easy", "normal", "hard", "sp"))
COALITION_FLEETS = frozenset(("single", "multi"))


@dataclass(frozen=True)
class AlasCoalitionConfigSnapshot:
    mode: str
    fleet: str


def validate_alas_coalition_config(
    *, mode: object, fleet: object
) -> AlasCoalitionConfigSnapshot:
    """Admit only declared values before Coalition state or input work starts."""

    if type(mode) is not str or mode not in COALITION_MODES:
        raise SemanticGateClosed("Coalition.Mode is outside the pinned enum")
    if type(fleet) is not str or fleet not in COALITION_FLEETS:
        raise SemanticGateClosed("Coalition.Fleet is outside the pinned enum")
    return AlasCoalitionConfigSnapshot(mode=mode, fleet=fleet)
