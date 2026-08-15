"""Fail-closed contract for ALAS daemon polling configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasDaemonConfigSnapshot:
    enter_map: bool


@dataclass(frozen=True)
class AlasOpsiDaemonConfigSnapshot:
    opsi_repair_ship: bool
    opsi_select_enemy: bool


def validate_alas_daemon_config(
    *, enter_map: object
) -> AlasDaemonConfigSnapshot:
    """Validate the normal daemon switch before polling or page input."""

    if type(enter_map) is not bool:
        raise SemanticGateClosed("Daemon.EnterMap must be a bool")
    return AlasDaemonConfigSnapshot(enter_map=enter_map)


def validate_alas_opsi_daemon_config(
    *, repair_ship: object, select_enemy: object
) -> AlasOpsiDaemonConfigSnapshot:
    """Validate OS daemon switches before config merge, polling, or page input."""

    if type(repair_ship) is not bool:
        raise SemanticGateClosed("OpsiDaemon.RepairShip must be a bool")
    if type(select_enemy) is not bool:
        raise SemanticGateClosed("OpsiDaemon.SelectEnemy must be a bool")
    return AlasOpsiDaemonConfigSnapshot(
        opsi_repair_ship=repair_ship,
        opsi_select_enemy=select_enemy,
    )
