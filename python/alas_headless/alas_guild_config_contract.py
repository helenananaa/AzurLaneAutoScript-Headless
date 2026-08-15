"""Fail-closed contract for the pinned ALAS Guild task settings."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasGuildConfigSnapshot:
    logistics_enable: bool
    logistics_select_new_mission: bool
    logistics_exchange_filter: str
    operation_enable: bool
    operation_select_new_operation: bool
    operation_new_operation_max_date: int
    operation_join_threshold: float
    operation_attack_boss: bool
    operation_boss_fleet_recommend: bool


def validate_alas_guild_config(
    *,
    logistics_enable: object,
    logistics_select_new_mission: object,
    logistics_exchange_filter: object,
    operation_enable: object,
    operation_select_new_operation: object,
    operation_new_operation_max_date: object,
    operation_join_threshold: object,
    operation_attack_boss: object,
    operation_boss_fleet_recommend: object,
) -> AlasGuildConfigSnapshot:
    """Admit exact Guild settings before state, observation, or input work."""

    for name, value in (
        ("GuildLogistics.Enable", logistics_enable),
        ("GuildLogistics.SelectNewMission", logistics_select_new_mission),
        ("GuildOperation.Enable", operation_enable),
        ("GuildOperation.SelectNewOperation", operation_select_new_operation),
        ("GuildOperation.AttackBoss", operation_attack_boss),
        ("GuildOperation.BossFleetRecommend", operation_boss_fleet_recommend),
    ):
        if type(value) is not bool:
            raise SemanticGateClosed(name + " must be a boolean")
    if type(logistics_exchange_filter) is not str:
        raise SemanticGateClosed("GuildLogistics.ExchangeFilter must be text")
    if (
        type(operation_new_operation_max_date) is not int
        or not 1 <= operation_new_operation_max_date <= 31
    ):
        raise SemanticGateClosed("GuildOperation.NewOperationMaxDate must be an integer from 1 to 31")
    if (
        type(operation_join_threshold) not in (int, float)
        or not math.isfinite(operation_join_threshold)
        or not 0 <= operation_join_threshold <= 1
    ):
        raise SemanticGateClosed("GuildOperation.JoinThreshold must be finite and within 0 to 1")
    return AlasGuildConfigSnapshot(
        logistics_enable=logistics_enable,
        logistics_select_new_mission=logistics_select_new_mission,
        logistics_exchange_filter=logistics_exchange_filter,
        operation_enable=operation_enable,
        operation_select_new_operation=operation_select_new_operation,
        operation_new_operation_max_date=operation_new_operation_max_date,
        operation_join_threshold=float(operation_join_threshold),
        operation_attack_boss=operation_attack_boss,
        operation_boss_fleet_recommend=operation_boss_fleet_recommend,
    )
