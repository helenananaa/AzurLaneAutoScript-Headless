"""Dispatch for the typed ALAS boundary."""

from __future__ import annotations

from typing import Any
from ...semantic_oracle import ActionReceipt
from .dispatch_result import UNHANDLED
from .resources import (
    BUILD_POOL_NAVBAR_PATTERN,
    BUILD_SIDE_NAVBAR_PATTERN,
    CAMPAIGN_FLEET_BAR_PATTERN,
    COMMISSION_ROW_PATTERN,
    MISSION_NAVBAR_PATTERN,
    UI_PAGE_CHECK_RESOURCES,
)


class DispatchAdapterPorts:
    """Dispatch ports on the shared adapter context."""

    def _appear_once(self, button: Any) -> bool:
        if self._observation_oracle_override is not None:
            return self._appear_once_bound(button)
        self._observation_oracle_override = self._frame_or_live_observation_oracle()
        try:
            return self._appear_once_bound(button)
        finally:
            self._observation_oracle_override = None

    def _appear_once_bound(self, button: Any) -> bool:
        name = self._button_name(button)
        result = self._appear_priority(name)
        if result is not UNHANDLED:
            return result
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        result = self._appear_campaign_stage(name, campaign_stage_code)
        if result is not UNHANDLED:
            return result
        semantic_id = self._meowfficer_contextual_target(name)
        if semantic_id is None:
            semantic_id = self._mappings.get(name)
        if semantic_id is None and name == "EVENT_CHECK":
            # EVENT_CHECK is an observation-only page marker. It must never
            # enter the generic click mapping used by legacy callers.
            semantic_id = "event/mode/story"
        if (
            not self._login_flow.active
            and semantic_id is None
            and name in UI_PAGE_CHECK_RESOURCES
            and name != "RESHMENU_CHECK"
            and self.oracle.exists("research-menu/page/back")
        ):
            # SelectTechnologyUI is an owned top-level menu.  Once its exact
            # root is present, unmapped ALAS page probes cannot describe the
            # current page and must not fan out into unrelated task readers.
            # RESHMENU_CHECK is the one virtual page marker handled below.
            return False
        result = self._appear_opsi_order(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_tactical(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_confirmation(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_opsi(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_event(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_meta(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_login(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_mail_entry(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_rewards(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_blocking_overlay(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_event_selector(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_passive_surface(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_unmapped(name, semantic_id)
        if result is not UNHANDLED:
            return result
        self._package_gate()
        result = self._appear_context(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_pages(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_campaign(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_research(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_dorm(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_minigame(name, button)
        if result is not UNHANDLED:
            return result
        result = self._appear_build(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_navigation(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._appear_mail(name)
        if result is not UNHANDLED:
            return result
        result = self._appear_fallback(name, semantic_id)
        if result is not UNHANDLED:
            return result

    def click(self, button: Any) -> ActionReceipt:
        if self._campaign_grid_location(button) is not None:
            return self.click_campaign_combat_grid(button)
        name = self._button_name(button)
        result = self._click_priority(name)
        if result is not UNHANDLED:
            return result
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        result = self._click_archives(name)
        if result is not UNHANDLED:
            return result
        result = self._click_login(name)
        if result is not UNHANDLED:
            return result
        semantic_id = self._meowfficer_contextual_target(name)
        if semantic_id is None:
            semantic_id = self._mappings.get(name)
        result = self._click_opsi_order(name)
        if result is not UNHANDLED:
            return result
        result = self._click_campaign_confirmation(name)
        if result is not UNHANDLED:
            return result
        navbar_match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        commission_row_match = COMMISSION_ROW_PATTERN.fullmatch(name)
        build_side_navbar_match = BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
        build_pool_navbar_match = BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        campaign_fleet_bar_match = CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name)
        result = self._click_rewards(name)
        if result is not UNHANDLED:
            return result
        result = self._click_opsi_mission(name)
        if result is not UNHANDLED:
            return result
        result = self._click_minigame(name)
        if result is not UNHANDLED:
            return result
        result = self._click_mail_blocked(name)
        if result is not UNHANDLED:
            return result
        result = self._click_campaign_strategy(name)
        if result is not UNHANDLED:
            return result
        result = self._click_back(name)
        if result is not UNHANDLED:
            return result
        result = self._click_daily(name)
        if result is not UNHANDLED:
            return result
        result = self._click_admission(name, semantic_id, campaign_stage_code, navbar_match, commission_row_match, build_side_navbar_match, build_pool_navbar_match)
        if result is not UNHANDLED:
            return result
        self._package_gate()
        result = self._click_campaign_stage(name, campaign_stage_code)
        if result is not UNHANDLED:
            return result
        result = self._click_campaign_fleet(name, campaign_fleet_bar_match)
        if result is not UNHANDLED:
            return result
        result = self._click_campaign_preparation(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._click_build_nav(build_side_navbar_match, build_pool_navbar_match)
        if result is not UNHANDLED:
            return result
        result = self._click_tactical(name)
        if result is not UNHANDLED:
            return result
        result = self._click_research(name)
        if result is not UNHANDLED:
            return result
        result = self._click_dorm(name)
        if result is not UNHANDLED:
            return result
        result = self._click_build(name)
        if result is not UNHANDLED:
            return result
        result = self._click_main(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._click_mail_manager(name)
        if result is not UNHANDLED:
            return result
        result = self._click_confirmation(name)
        if result is not UNHANDLED:
            return result
        result = self._click_mapped(name, semantic_id)
        if result is not UNHANDLED:
            return result
        result = self._click_commission(name, button, semantic_id, commission_row_match)
        if result is not UNHANDLED:
            return result
        result = self._click_mail(name)
        if result is not UNHANDLED:
            return result
        result = self._click_reward_navigation(name, navbar_match)
        if result is not UNHANDLED:
            return result
        result = self._click_guild(name)
        if result is not UNHANDLED:
            return result
        result = self._click_mission(name)
        if result is not UNHANDLED:
            return result
