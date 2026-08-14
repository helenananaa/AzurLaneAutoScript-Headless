"""Fail-closed contract for ALAS Shipyard focus configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


SHIPYARD_PR_SERIES = (1, 2, 3, 4, 5, 6)
SHIPYARD_DR_SERIES = (2, 3, 4, 5)
SHIPYARD_INDICES = (0, 1, 2, 3, 4, 5, 6)


@dataclass(frozen=True)
class AlasShipyardConfigSnapshot:
    pr_series: int
    pr_index: int
    dr_series: int
    dr_index: int


def _exact_member(name: str, value: object, allowed: tuple[int, ...]) -> int:
    if type(value) is not int or value not in allowed:
        raise SemanticGateClosed(f"{name} is outside the pinned ALAS surface")
    return value


def validate_alas_shipyard_config(
    *,
    pr_series: object,
    pr_index: object,
    dr_series: object,
    dr_index: object,
) -> AlasShipyardConfigSnapshot:
    """Validate both Shipyard focus pairs before navigation or blueprint use."""

    return AlasShipyardConfigSnapshot(
        pr_series=_exact_member(
            "Shipyard.ResearchSeries", pr_series, SHIPYARD_PR_SERIES
        ),
        pr_index=_exact_member("Shipyard.ShipIndex", pr_index, SHIPYARD_INDICES),
        dr_series=_exact_member(
            "ShipyardDr.ResearchSeries", dr_series, SHIPYARD_DR_SERIES
        ),
        dr_index=_exact_member(
            "ShipyardDr.ShipIndex", dr_index, SHIPYARD_INDICES
        ),
    )
