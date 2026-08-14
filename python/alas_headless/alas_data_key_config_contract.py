"""Fail-closed contract for ALAS Data Key collection switches."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasDataKeyConfigSnapshot:
    collect: bool
    force_collect: bool


def validate_alas_data_key_config(
    *, collect: object, force_collect: object
) -> AlasDataKeyConfigSnapshot:
    """Validate Data Key switches before any Freebies module can navigate."""

    if type(collect) is not bool:
        raise SemanticGateClosed("DataKey.Collect must be a bool")
    if type(force_collect) is not bool:
        raise SemanticGateClosed("DataKey.ForceCollect must be a bool")
    return AlasDataKeyConfigSnapshot(
        collect=collect,
        force_collect=force_collect,
    )
