"""Fail-closed contract for ALAS campaign clear-mode selection."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasCampaignClearModeConfigSnapshot:
    use_clear_mode: bool


def validate_alas_campaign_clear_mode_config(
    *, use_clear_mode: object
) -> AlasCampaignClearModeConfigSnapshot:
    """Validate the shared clear-mode switch before ALAS mutates map flags."""

    if type(use_clear_mode) is not bool:
        raise SemanticGateClosed("Campaign.UseClearMode must be a bool")
    return AlasCampaignClearModeConfigSnapshot(use_clear_mode=use_clear_mode)
