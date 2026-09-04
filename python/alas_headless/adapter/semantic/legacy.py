"""Legacy for the typed ALAS boundary."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


def _legacy_action_grants(
    *,
    allow_mission_claim_once: bool,
    allow_mail_mutations: bool,
    mail_mutation_budget: int,
    minigame_play_budget: int,
    meta_assist_budget: int,
    operation_siren_coordinate_checkout_budget: int,
    allow_tactical_rewards: bool,
    tactical_assign_budget: int,
    commission_reward_budget: int,
    commission_start_budget: int,
    daily_execute_budget: int,
    exercise_execute_budget: int,
    exercise_refresh_budget: int,
    research_reward_budget: int,
    research_start_budget: int,
    dorm_collect_budget: int,
    dorm_feed_budget: int,
    awaken_budget: int,
    enhancement_budget: int,
    build_submit_budget: int,
    retirement_budget: int,
    shop_purchase_budget: int,
    campaign_stage_entry_budget: int,
    campaign_fleet_mutation_budget: int,
    campaign_sortie_budget: int,
    campaign_combat_budget: int,
    campaign_viewport_swipe_budget: int,
    campaign_camera_positioning_budget: int,
) -> Mapping[str, int]:
    return MappingProxyType(
        {
            "mission.claim": int(bool(allow_mission_claim_once)),
            "mail.mutation": max(
                int(bool(allow_mail_mutations)), mail_mutation_budget
            ),
            "minigame.play": minigame_play_budget,
            "meta.assist": meta_assist_budget,
            "operation_siren.coordinate_checkout": (
                operation_siren_coordinate_checkout_budget
            ),
            "tactical.reward": int(bool(allow_tactical_rewards)),
            "tactical.assign": tactical_assign_budget,
            "commission.reward": commission_reward_budget,
            "commission.start": commission_start_budget,
            "daily.execute": daily_execute_budget,
            "exercise.execute": exercise_execute_budget,
            "exercise.refresh": exercise_refresh_budget,
            "research.reward": research_reward_budget,
            "research.start": research_start_budget,
            "dorm.collect": dorm_collect_budget,
            "dorm.feed": dorm_feed_budget,
            "awaken.execute": awaken_budget,
            "enhancement.execute": enhancement_budget,
            "build.submit": build_submit_budget,
            "retirement.execute": retirement_budget,
            "shop.purchase": shop_purchase_budget,
            "campaign.stage_entry": campaign_stage_entry_budget,
            "campaign.fleet_mutation": campaign_fleet_mutation_budget,
            "campaign.sortie": campaign_sortie_budget,
            "campaign.grid_click": campaign_combat_budget,
            "campaign.viewport_swipe": campaign_viewport_swipe_budget,
            "campaign.camera_positioning": campaign_camera_positioning_budget,
        }
    )
