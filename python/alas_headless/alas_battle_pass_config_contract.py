"""Fail-closed contract for ALAS Battle Pass collection configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasBattlePassConfigSnapshot:
    collect: bool


def validate_alas_battle_pass_config(
    *, collect: object
) -> AlasBattlePassConfigSnapshot:
    """Validate the Battle Pass switch before any Freebies child can run."""

    if type(collect) is not bool:
        raise SemanticGateClosed("BattlePass.Collect must be a bool")
    return AlasBattlePassConfigSnapshot(collect=collect)
