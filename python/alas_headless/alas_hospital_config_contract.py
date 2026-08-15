"""Fail-closed contract for the pinned ALAS Hospital recommendation switch."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasHospitalConfigSnapshot:
    use_recommend_fleet: bool


def validate_alas_hospital_config(*, use_recommend_fleet: object) -> AlasHospitalConfigSnapshot:
    """Admit only an exact boolean before Hospital UI or fleet work begins."""

    if type(use_recommend_fleet) is not bool:
        raise SemanticGateClosed("Hospital.UseRecommendFleet must be a boolean")
    return AlasHospitalConfigSnapshot(use_recommend_fleet=use_recommend_fleet)
