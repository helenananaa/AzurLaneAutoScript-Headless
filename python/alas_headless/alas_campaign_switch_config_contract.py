"""Fail-closed contract for shared ALAS campaign switches."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasCampaignSwitchConfigSnapshot:
    use_fleet_lock: bool
    use_auto_search: bool
    use_2x_book: bool
    ambush_evade: bool


def validate_alas_campaign_switch_config(
    *,
    use_fleet_lock: object,
    use_auto_search: object,
    use_2x_book: object,
    ambush_evade: object,
) -> AlasCampaignSwitchConfigSnapshot:
    """Validate switches before the original campaign runner can navigate."""

    values = {
        "Campaign.UseFleetLock": use_fleet_lock,
        "Campaign.UseAutoSearch": use_auto_search,
        "Campaign.Use2xBook": use_2x_book,
        "Campaign.AmbushEvade": ambush_evade,
    }
    for field, value in values.items():
        if type(value) is not bool:
            raise SemanticGateClosed(f"{field} must be a bool")
    return AlasCampaignSwitchConfigSnapshot(
        use_fleet_lock=use_fleet_lock,
        use_auto_search=use_auto_search,
        use_2x_book=use_2x_book,
        ambush_evade=ambush_evade,
    )
