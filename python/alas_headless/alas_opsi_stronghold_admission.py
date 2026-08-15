"""Explicitly refuse the unobserved OpsiStronghold task in headless mode."""

from __future__ import annotations

from .semantic_oracle import SemanticGateClosed


OPSI_STRONGHOLD_BLOCK_REASON = (
    "OpsiStronghold is skipped in headless mode: the 3D vortex presence, entry, "
    "fleet, combat, retreat, and settlement observations are not qualified"
)


def block_alas_opsi_stronghold_headless(*, semantic_adapter: object) -> None:
    """Stop before campaign creation whenever the semantic headless adapter is active."""

    if semantic_adapter is not None:
        raise SemanticGateClosed(OPSI_STRONGHOLD_BLOCK_REASON)
