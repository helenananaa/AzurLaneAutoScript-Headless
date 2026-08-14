"""Fail-closed contract for ALAS Reward collection switches."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasRewardConfigSnapshot:
    collect_oil: bool
    collect_coin: bool
    collect_exp: bool
    collect_mission: bool
    collect_weekly_mission: bool


def _bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise SemanticGateClosed(f"{field} must be a bool")
    return value


def validate_alas_reward_config(
    *,
    collect_oil: object,
    collect_coin: object,
    collect_exp: object,
    collect_mission: object,
    collect_weekly_mission: object,
) -> AlasRewardConfigSnapshot:
    """Validate all Reward switches before either task entry can claim."""

    return AlasRewardConfigSnapshot(
        collect_oil=_bool(collect_oil, field="Reward.CollectOil"),
        collect_coin=_bool(collect_coin, field="Reward.CollectCoin"),
        collect_exp=_bool(collect_exp, field="Reward.CollectExp"),
        collect_mission=_bool(collect_mission, field="Reward.CollectMission"),
        collect_weekly_mission=_bool(
            collect_weekly_mission, field="Reward.CollectWeeklyMission"
        ),
    )
