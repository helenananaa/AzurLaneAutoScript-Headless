"""Fail-closed contracts for selected Operation Siren task settings."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .semantic_oracle import SemanticGateClosed


OPSI_MONTH_BOSS_MODES = ("normal", "normal_hard")
OPSI_HAZARD1_TARGET_ZONES = (0, 44, 22)
OPSI_MEOWFFICER_HAZARD_LEVELS = (3, 4, 5, 6, 10)
OPSI_FLEET_INDEXES = (1, 2, 3, 4)


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
    action_point_preserve: int
    hazard_level: int
    target_zone: int | str


@dataclass(frozen=True)
class AlasOpsiExploreConfigSnapshot:
    special_radar: bool


@dataclass(frozen=True)
class AlasOpsiDelayTaskConfigSnapshot:
    explore_force_run: bool
    obscure_force_run: bool
    abyssal_force_run: bool
    stronghold_force_run: bool
    special_radar: bool

    @property
    def force_run(self) -> bool:
        return (
            self.explore_force_run
            or self.obscure_force_run
            or self.abyssal_force_run
            or self.stronghold_force_run
        )


@dataclass(frozen=True)
class AlasOpsiFleetSelectionSnapshot:
    fleet: int


@dataclass(frozen=True)
class AlasOpsiOrderSnapshot:
    recon_scan: bool
    submarine_call: bool


@dataclass(frozen=True)
class AlasOpsiStorageConfigSnapshot:
    use_logger: bool


@dataclass(frozen=True)
class AlasOpsiActionPointPurchaseSnapshot:
    buy_limit: int
    oil_limit: int


@dataclass(frozen=True)
class AlasOpsiRepairConfigSnapshot:
    threshold: float


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
    *, action_point_preserve: object, hazard_level: object, target_zone: object
) -> AlasOpsiMeowfficerConfigSnapshot:
    if type(action_point_preserve) is not int or action_point_preserve < 0:
        raise SemanticGateClosed(
            "OpsiMeowfficerFarming.ActionPointPreserve must be a non-negative int"
        )
    if type(hazard_level) is not int or hazard_level not in OPSI_MEOWFFICER_HAZARD_LEVELS:
        raise SemanticGateClosed(
            "OpsiMeowfficerFarming.HazardLevel must be 3, 4, 5, 6, or 10"
        )
    if type(target_zone) is int:
        if target_zone < 0:
            raise SemanticGateClosed(
                "OpsiMeowfficerFarming.TargetZone must not be negative"
            )
    elif type(target_zone) is str:
        if not target_zone.strip():
            raise SemanticGateClosed(
                "OpsiMeowfficerFarming.TargetZone must not be blank"
            )
    else:
        raise SemanticGateClosed(
            "OpsiMeowfficerFarming.TargetZone must be a zone id or name"
        )
    return AlasOpsiMeowfficerConfigSnapshot(
        action_point_preserve=action_point_preserve,
        hazard_level=hazard_level,
        target_zone=target_zone,
    )


def validate_alas_opsi_explore_config(
    *, special_radar: object
) -> AlasOpsiExploreConfigSnapshot:
    if type(special_radar) is not bool:
        raise SemanticGateClosed("OpsiExplore.SpecialRadar must be a bool")
    return AlasOpsiExploreConfigSnapshot(special_radar=special_radar)


def validate_alas_opsi_delay_task_config(
    *,
    explore_force_run: object,
    obscure_force_run: object,
    abyssal_force_run: object,
    stronghold_force_run: object,
    special_radar: object,
) -> AlasOpsiDelayTaskConfigSnapshot:
    fields = {
        "OpsiExplore.ForceRun": explore_force_run,
        "OpsiObscure.ForceRun": obscure_force_run,
        "OpsiAbyssal.ForceRun": abyssal_force_run,
        "OpsiStronghold.ForceRun": stronghold_force_run,
        "OpsiExplore.SpecialRadar": special_radar,
    }
    for field, value in fields.items():
        if type(value) is not bool:
            raise SemanticGateClosed(f"{field} must be a bool")
    return AlasOpsiDelayTaskConfigSnapshot(
        explore_force_run=explore_force_run,
        obscure_force_run=obscure_force_run,
        abyssal_force_run=abyssal_force_run,
        stronghold_force_run=stronghold_force_run,
        special_radar=special_radar,
    )


def validate_alas_opsi_fleet_selection(
    *, fleet: object
) -> AlasOpsiFleetSelectionSnapshot:
    if type(fleet) is not int or fleet not in OPSI_FLEET_INDEXES:
        raise SemanticGateClosed("OpsiFleet.Fleet must be 1, 2, 3, or 4")
    return AlasOpsiFleetSelectionSnapshot(fleet=fleet)


def validate_alas_opsi_order(
    *, recon_scan: object, submarine_call: object
) -> AlasOpsiOrderSnapshot:
    if type(recon_scan) is not bool:
        raise SemanticGateClosed("Operation Siren recon_scan must be a bool")
    if type(submarine_call) is not bool:
        raise SemanticGateClosed("OpsiFleet.Submarine must be a bool")
    return AlasOpsiOrderSnapshot(
        recon_scan=recon_scan,
        submarine_call=submarine_call,
    )


def validate_alas_opsi_storage_config(
    *, use_logger: object
) -> AlasOpsiStorageConfigSnapshot:
    if type(use_logger) is not bool:
        raise SemanticGateClosed("OpsiGeneral.UseLogger must be a bool")
    return AlasOpsiStorageConfigSnapshot(use_logger=use_logger)


def validate_alas_opsi_action_point_purchase(
    *, buy_limit: object, oil_limit: object
) -> AlasOpsiActionPointPurchaseSnapshot:
    if type(buy_limit) is not int or buy_limit not in range(6):
        raise SemanticGateClosed(
            "OpsiGeneral.BuyActionPointLimit must be 0, 1, 2, 3, 4, or 5"
        )
    if type(oil_limit) is not int or oil_limit < 0:
        raise SemanticGateClosed("OpsiGeneral.OilLimit must be a non-negative int")
    return AlasOpsiActionPointPurchaseSnapshot(
        buy_limit=buy_limit,
        oil_limit=oil_limit,
    )


def validate_alas_opsi_repair_config(
    *, threshold: object
) -> AlasOpsiRepairConfigSnapshot:
    if type(threshold) not in (int, float) or not isfinite(threshold):
        raise SemanticGateClosed("OpsiGeneral.RepairThreshold must be finite")
    if threshold > 1:
        raise SemanticGateClosed("OpsiGeneral.RepairThreshold must not exceed 1")
    return AlasOpsiRepairConfigSnapshot(threshold=float(threshold))
