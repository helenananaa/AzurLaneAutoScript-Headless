"""Fail-closed contracts for selected Operation Siren task settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


OPSI_MONTH_BOSS_MODES = ("normal", "normal_hard")


@dataclass(frozen=True)
class AlasOpsiMonthBossConfigSnapshot:
    mode: str
    check_adaptability: bool


@dataclass(frozen=True)
class AlasOpsiObscureConfigSnapshot:
    force_run: bool


def validate_alas_opsi_month_boss_config(
    *, mode: object, check_adaptability: object
) -> AlasOpsiMonthBossConfigSnapshot:
    if type(mode) is not str or mode not in OPSI_MONTH_BOSS_MODES:
        raise SemanticGateClosed(
            "OpsiMonthBoss.Mode must be normal or normal_hard"
        )
    if type(check_adaptability) is not bool:
        raise SemanticGateClosed("OpsiMonthBoss.CheckAdaptability must be a bool")
    return AlasOpsiMonthBossConfigSnapshot(
        mode=mode,
        check_adaptability=check_adaptability,
    )


def validate_alas_opsi_obscure_config(
    *, force_run: object
) -> AlasOpsiObscureConfigSnapshot:
    if type(force_run) is not bool:
        raise SemanticGateClosed("OpsiObscure.ForceRun must be a bool")
    return AlasOpsiObscureConfigSnapshot(force_run=force_run)
