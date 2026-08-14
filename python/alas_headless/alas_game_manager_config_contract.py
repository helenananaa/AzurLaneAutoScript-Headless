"""Fail-closed contract for the ALAS Game Manager restart switch."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasGameManagerConfigSnapshot:
    auto_restart: bool


def validate_alas_game_manager_config(
    *, auto_restart: object
) -> AlasGameManagerConfigSnapshot:
    """Validate AutoRestart before the original task can stop the app."""

    if type(auto_restart) is not bool:
        raise SemanticGateClosed("GameManager.AutoRestart must be a bool")
    return AlasGameManagerConfigSnapshot(auto_restart=auto_restart)
