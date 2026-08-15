"""Fail-closed contracts for selected Operation Siren task settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


OPSI_MONTH_BOSS_MODES = ("normal", "normal_hard")
OPSI_HAZARD1_TARGET_ZONES = (0, 44, 22)
OPSI_MEOWFFICER_HAZARD_LEVELS = (3, 4, 5, 6, 10)


@dataclass(frozen=True)
class AlasOpsiMonthBossConfigSnapshot:
    mode: str
    check_adaptability: bool


@dataclass(frozen=True)
class AlasOpsiObscureConfigSnapshot:
    force_run: bool


@dataclass(frozen=True)
class AlasOpsiDailyConfigSnapshot:
    use_tuning_sample: bool


@dataclass(frozen=True)
class AlasOpsiHazard1ConfigSnapshot:
    target_zone: int


@dataclass(frozen=True)
class AlasOpsiMeowfficerConfigSnapshot:
    hazard_level: int


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


def validate_alas_opsi_daily_config(
    *, use_tuning_sample: object
) -> AlasOpsiDailyConfigSnapshot:
    if type(use_tuning_sample) is not bool:
        raise SemanticGateClosed("OpsiDaily.UseTuningSample must be a bool")
    return AlasOpsiDailyConfigSnapshot(use_tuning_sample=use_tuning_sample)


def validate_alas_opsi_hazard1_config(
    *, target_zone: object
) -> AlasOpsiHazard1ConfigSnapshot:
    if type(target_zone) is not int or target_zone not in OPSI_HAZARD1_TARGET_ZONES:
        raise SemanticGateClosed("OpsiHazard1Leveling.TargetZone must be 0, 22, or 44")
    return AlasOpsiHazard1ConfigSnapshot(target_zone=target_zone)


def validate_alas_opsi_meowfficer_config(
    *, hazard_level: object
) -> AlasOpsiMeowfficerConfigSnapshot:
    if type(hazard_level) is not int or hazard_level not in OPSI_MEOWFFICER_HAZARD_LEVELS:
        raise SemanticGateClosed(
            "OpsiMeowfficerFarming.HazardLevel must be 3, 4, 5, 6, or 10"
        )
    return AlasOpsiMeowfficerConfigSnapshot(hazard_level=hazard_level)
