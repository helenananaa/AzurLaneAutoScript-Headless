"""Fail-closed contract for the shared ALAS Daily configuration group."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


THREE_STAGE_VALUES = ("skip", "first", "second", "third")
TWO_STAGE_VALUES = ("skip", "first", "second")


@dataclass(frozen=True)
class AlasDailyConfigSnapshot:
    use_daily_skip: bool
    escort_mission: str
    escort_mission_fleet: int
    advance_mission: str
    advance_mission_fleet: int
    fierce_assault: str
    fierce_assault_fleet: int
    tactical_training: str
    tactical_training_fleet: int
    supply_line_disruption: str
    module_development: str
    module_development_fleet: int
    emergency_module_development: str
    emergency_module_development_fleet: int


def _bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise SemanticGateClosed(f"{field} must be a bool")
    return value


def _stage(value: object, *, field: str, allowed: tuple[str, ...]) -> str:
    if type(value) is not str or value not in allowed:
        raise SemanticGateClosed(f"{field} is outside the declared stage choices")
    return value


def _fleet(value: object, *, field: str) -> int:
    if type(value) is not int or value not in range(1, 7):
        raise SemanticGateClosed(f"{field} must be an integer from 1 to 6")
    return value


def validate_alas_daily_config(
    *,
    use_daily_skip: object,
    escort_mission: object,
    escort_mission_fleet: object,
    advance_mission: object,
    advance_mission_fleet: object,
    fierce_assault: object,
    fierce_assault_fleet: object,
    tactical_training: object,
    tactical_training_fleet: object,
    supply_line_disruption: object,
    module_development: object,
    module_development_fleet: object,
    emergency_module_development: object,
    emergency_module_development_fleet: object,
) -> AlasDailyConfigSnapshot:
    """Validate all fourteen Daily fields before ALAS enters its state machine."""

    return AlasDailyConfigSnapshot(
        use_daily_skip=_bool(use_daily_skip, field="Daily.UseDailySkip"),
        escort_mission=_stage(
            escort_mission, field="Daily.EscortMission", allowed=THREE_STAGE_VALUES
        ),
        escort_mission_fleet=_fleet(
            escort_mission_fleet, field="Daily.EscortMissionFleet"
        ),
        advance_mission=_stage(
            advance_mission, field="Daily.AdvanceMission", allowed=THREE_STAGE_VALUES
        ),
        advance_mission_fleet=_fleet(
            advance_mission_fleet, field="Daily.AdvanceMissionFleet"
        ),
        fierce_assault=_stage(
            fierce_assault, field="Daily.FierceAssault", allowed=THREE_STAGE_VALUES
        ),
        fierce_assault_fleet=_fleet(
            fierce_assault_fleet, field="Daily.FierceAssaultFleet"
        ),
        tactical_training=_stage(
            tactical_training,
            field="Daily.TacticalTraining",
            allowed=THREE_STAGE_VALUES,
        ),
        tactical_training_fleet=_fleet(
            tactical_training_fleet, field="Daily.TacticalTrainingFleet"
        ),
        supply_line_disruption=_stage(
            supply_line_disruption,
            field="Daily.SupplyLineDisruption",
            allowed=THREE_STAGE_VALUES,
        ),
        module_development=_stage(
            module_development,
            field="Daily.ModuleDevelopment",
            allowed=TWO_STAGE_VALUES,
        ),
        module_development_fleet=_fleet(
            module_development_fleet, field="Daily.ModuleDevelopmentFleet"
        ),
        emergency_module_development=_stage(
            emergency_module_development,
            field="Daily.EmergencyModuleDevelopment",
            allowed=TWO_STAGE_VALUES,
        ),
        emergency_module_development_fleet=_fleet(
            emergency_module_development_fleet,
            field="Daily.EmergencyModuleDevelopmentFleet",
        ),
    )
