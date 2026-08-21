"""Fail-closed contracts for selected Operation Siren task settings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite
from typing import Callable, Mapping

from .semantic_oracle import SemanticGateClosed


OPSI_MONTH_BOSS_MODES = ("normal", "normal_hard")
OPSI_ASH_BEACON_ATTACK_MODES = ("current", "current_dossier")
OPSI_HAZARD1_TARGET_ZONES = (0, 44, 22)
OPSI_MEOWFFICER_HAZARD_LEVELS = (3, 4, 5, 6, 10)
OPSI_FLEET_INDEXES = (1, 2, 3, 4)
OPSI_FLEET_FILTER_REGEX = re.compile(r"fleet-?(\d)", re.IGNORECASE)
OPSI_FLEET_FILTER_PRESETS = ("callsubmarine",)


@dataclass(frozen=True)
class AlasOpsiMonthBossConfigSnapshot:
    mode: str
    check_adaptability: bool
    force_run: bool


@dataclass(frozen=True)
class AlasOpsiObscureConfigSnapshot:
    force_run: bool


@dataclass(frozen=True)
class AlasOpsiDailyConfigSnapshot:
    do_mission: bool
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
    month_boss_force_run: bool
    special_radar: bool

    @property
    def force_run(self) -> bool:
        return (
            self.explore_force_run
            or self.obscure_force_run
            or self.abyssal_force_run
            or self.stronghold_force_run
            or self.month_boss_force_run
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


@dataclass(frozen=True)
class AlasOpsiRescanConfigSnapshot:
    do_random_map_event: bool


def validate_alas_opsi_month_boss_config(
    *, mode: object, check_adaptability: object, force_run: object = False
) -> AlasOpsiMonthBossConfigSnapshot:
    if type(mode) is not str or mode not in OPSI_MONTH_BOSS_MODES:
        raise SemanticGateClosed(
            "OpsiMonthBoss.Mode must be normal or normal_hard"
        )
    if type(check_adaptability) is not bool:
        raise SemanticGateClosed("OpsiMonthBoss.CheckAdaptability must be a bool")
    if type(force_run) is not bool:
        raise SemanticGateClosed("OpsiMonthBoss.ForceRun must be a bool")
    return AlasOpsiMonthBossConfigSnapshot(
        mode=mode,
        check_adaptability=check_adaptability,
        force_run=force_run,
    )


def validate_alas_opsi_ash_beacon_attack_mode(*, attack_mode: object) -> str:
    """Validate the original beacon-versus-dossier selection mode."""
    if type(attack_mode) is not str or attack_mode not in OPSI_ASH_BEACON_ATTACK_MODES:
        raise SemanticGateClosed(
            "OpsiAshBeacon.AttackMode must be current or current_dossier"
        )
    return attack_mode


def validate_alas_opsi_ash_beacon_one_hit_mode(*, one_hit_mode: object) -> bool:
    """Validate the one-hit beacon switch at its original decision points."""
    if type(one_hit_mode) is not bool:
        raise SemanticGateClosed("OpsiAshBeacon.OneHitMode must be a bool")
    return one_hit_mode


def validate_alas_opsi_ash_beacon_request_assist(*, request_assist: object) -> bool:
    """Validate the beacon help-request switch before the original branch."""
    if type(request_assist) is not bool:
        raise SemanticGateClosed("OpsiAshBeacon.RequestAssist must be a bool")
    return request_assist


def validate_alas_opsi_ash_beacon_dossier_auto_attack(
    *, dossier_auto_attack: object
) -> bool:
    """Validate the dossier auto-attack switch before the original branch."""
    if type(dossier_auto_attack) is not bool:
        raise SemanticGateClosed(
            "OpsiAshBeacon.DossierAutoAttackMode must be a bool"
        )
    return dossier_auto_attack


def validate_alas_opsi_obscure_config(
    *, force_run: object
) -> AlasOpsiObscureConfigSnapshot:
    if type(force_run) is not bool:
        raise SemanticGateClosed("OpsiObscure.ForceRun must be a bool")
    return AlasOpsiObscureConfigSnapshot(force_run=force_run)


def validate_alas_opsi_daily_config(
    *, do_mission: object, use_tuning_sample: object
) -> AlasOpsiDailyConfigSnapshot:
    if type(do_mission) is not bool:
        raise SemanticGateClosed("OpsiDaily.DoMission must be a bool")
    if type(use_tuning_sample) is not bool:
        raise SemanticGateClosed("OpsiDaily.UseTuningSample must be a bool")
    return AlasOpsiDailyConfigSnapshot(
        do_mission=do_mission,
        use_tuning_sample=use_tuning_sample,
    )


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
    month_boss_force_run: object,
    special_radar: object,
) -> AlasOpsiDelayTaskConfigSnapshot:
    fields = {
        "OpsiExplore.ForceRun": explore_force_run,
        "OpsiObscure.ForceRun": obscure_force_run,
        "OpsiAbyssal.ForceRun": abyssal_force_run,
        "OpsiStronghold.ForceRun": stronghold_force_run,
        "OpsiMonthBoss.ForceRun": month_boss_force_run,
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
        month_boss_force_run=month_boss_force_run,
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


def validate_alas_opsi_rescan_config(
    *, do_random_map_event: object
) -> AlasOpsiRescanConfigSnapshot:
    if type(do_random_map_event) is not bool:
        raise SemanticGateClosed("OpsiGeneral.DoRandomMapEvent must be a bool")
    return AlasOpsiRescanConfigSnapshot(
        do_random_map_event=do_random_map_event,
    )


def _validate_alas_opsi_filter_tokens(
    filter_: object,
    value: object,
    *,
    field: str,
    allow_empty: bool = False,
    fallback_regex: object = None,
    fallback_presets: tuple[str, ...] = (),
) -> str:
    if not isinstance(value, str):
        raise SemanticGateClosed(f"{field} must be text")
    normalized = re.sub(r"[ \t\r\n]", "", value)
    normalized = re.sub(r"[＞﹥›˃ᐳ❯]", ">", normalized)
    normalized = re.sub(r"[‐‑‒–—―−－﹣﹘⁃]", "-", normalized)
    if not normalized and allow_empty:
        return value
    tokens = normalized.split(">")
    regex = getattr(filter_, "regex", fallback_regex)
    if not hasattr(regex, "fullmatch"):
        raise SemanticGateClosed("pinned ALAS Operation Siren filter grammar is unavailable")
    presets = tuple(
        str(item).lower()
        for item in getattr(filter_, "preset", fallback_presets)
    )
    invalid = tuple(
        token
        for token in tokens
        if not token
        or (
            token.lower() not in presets
            and regex.fullmatch(token.lower()) is None
        )
    )
    if invalid:
        raise SemanticGateClosed(
            f"{field} contains invalid token(s): "
            + ", ".join(invalid)
        )
    return value


def validate_alas_opsi_akashi_filter(filter_: object, value: object) -> str:
    """Validate Akashi tokens with the pinned ALAS selector grammar."""

    return _validate_alas_opsi_filter_tokens(
        filter_,
        value,
        field="OpsiGeneral.AkashiShopFilter",
    )


def validate_alas_opsi_shop_preset(
    presets: object,
    preset: object,
) -> str:
    if not isinstance(presets, Mapping) or not presets:
        raise SemanticGateClosed("pinned ALAS OpsiShop presets are unavailable")
    if not isinstance(preset, str) or preset not in (*presets.keys(), "custom"):
        raise SemanticGateClosed("OpsiShop.PresetFilter is unknown")
    return preset


def validate_alas_opsi_shop_custom_filter(value: object) -> str:
    if not isinstance(value, str):
        raise SemanticGateClosed("OpsiShop.CustomFilter must be text")
    return value


def validate_alas_opsi_shop_filter(filter_: object, value: object) -> str:
    """Validate the selected OpsiShop parser with the pinned grammar."""

    return _validate_alas_opsi_filter_tokens(
        filter_,
        value,
        field="OpsiShop.CustomFilter",
    )


def validate_alas_opsi_voucher_filter(filter_: object, value: object) -> str:
    """Validate the redirected voucher filter; empty means intentional skip."""

    if not isinstance(value, str):
        raise SemanticGateClosed("OpsiVoucher.Filter must be text")
    if not value.strip():
        return value
    return _validate_alas_opsi_filter_tokens(
        filter_,
        value,
        field="OpsiVoucher.Filter",
    )


def validate_alas_opsi_explore_last_zone(
    *,
    value: object,
    order: object,
    resolver: Callable[[object], object],
) -> int:
    if type(value) is not int and (
        not isinstance(value, str) or not value.strip()
    ):
        raise SemanticGateClosed("OpsiExplore.LastZone must be an id or name")
    if (
        not isinstance(order, (list, tuple))
        or not order
        or any(type(zone) is not int or zone <= 0 for zone in order)
    ):
        raise SemanticGateClosed("pinned ALAS OpsiExplore order is unavailable")
    try:
        zone = resolver(value)
        zone_id = zone.zone_id
    except Exception as exc:
        raise SemanticGateClosed("OpsiExplore.LastZone cannot be resolved") from exc
    if type(zone_id) is not int or (zone_id != 0 and zone_id not in order):
        raise SemanticGateClosed("OpsiExplore.LastZone is outside the explore order")
    return zone_id


def validate_alas_opsi_ash_assist_tier(*, tier: object) -> int:
    """Validate the integer threshold consumed by the original assist selector."""
    if type(tier) is not int:
        raise SemanticGateClosed("OpsiAshAssist.Tier must be an int")
    return tier


def validate_alas_opsi_ash_beacon_ensure_fully_collected(
    *, ensure_fully_collected: object
) -> bool:
    if type(ensure_fully_collected) is not bool:
        raise SemanticGateClosed(
            "OpsiAshBeacon.EnsureFullyCollected must be a bool"
        )
    return ensure_fully_collected


def validate_alas_opsi_fleet_filter(
    *,
    value: object,
    filter_: object = None,
    allow_empty: bool = False,
) -> str:
    """Validate fleet selector text against the pinned ALAS grammar."""
    return _validate_alas_opsi_filter_tokens(
        filter_,
        value,
        field="OpsiFleetFilter.Filter",
        allow_empty=allow_empty,
        fallback_regex=OPSI_FLEET_FILTER_REGEX,
        fallback_presets=OPSI_FLEET_FILTER_PRESETS,
    )
