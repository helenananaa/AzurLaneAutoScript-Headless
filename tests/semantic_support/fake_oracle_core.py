"""Fake oracle core for the typed ALAS boundary."""

from __future__ import annotations

import re
from alas_headless import (
    Bounds,
    BuildPool,
    MissionDisposition,
    Point,
    RaidMultipleSortieState,
    RetirementExecutionReceipt,
    RetirementSettingsState,
)
from alas_headless.semantic_oracle import ActionReceipt, MetaAssistState
from alas_headless.oracle.surfaces import ObservationSurface
from types import SimpleNamespace


class FakeCoreOracle:
    def __init__(self):
        self.enabled_calls = []
        self.bounds_calls = []
        self.click_calls = []
        self.wait_calls = []
        self.wait_any_calls = []
        self.wait_any_results = []
        self.mission_disposition = MissionDisposition.UNFINISHED
        self.mission_dispositions = []
        self.streaming_mission_dispositions = []
        self.streaming_generation = 0
        self.mission_weekly_reward_available_value = False
        self.weekly_mission_progress_claim_available_value = False
        # Exact login/bulletin overlays are absent in ordinary adapter unit
        # fixtures unless a test opts them in explicitly.  Keeping the generic
        # default enabled preserves the older concise target fixtures without
        # making every unrelated page probe look blocked by a login surface.
        self.enabled_values = {
            "login/enter": False,
            "overlay/bulletin/close": False,
            "overlay/guild-message/close": False,
            "overlay/network-reconnect/cancel": False,
            "overlay/network-reconnect/confirm": False,
        }
        self.operation_siren_order_confirmation_visible_value = True
        self.operation_siren_page_visible_value = False
        self.operation_siren_local_map_visible_value = False
        self.exists_values = {}
        self.observation_surfaces = set()
        self.observation_prompt_kind_value = None
        self.enable_main_after_overlay_click = False
        self.text_groups = ()
        self.image_selected_values = {"task/nav/all": True}
        self.main_red_dot_values = {"main/task": False}
        self.toggle_selected_values = {}
        self.mail_empty = False
        self.mail_confirmation_kind_value = None
        self.mail_surface_kind_value = None
        self.main_page_visible_value = False
        self.raid_page_visible_value = False
        self.raid_page_visible_errors = []
        self.raid_stage_errors = []
        self.raid_fleet_ready_value = False
        self.raid_precombat_visible_value = False
        self.raid_precombat_notice_visible_value = False
        self.raid_precombat_multiple_visible_value = False
        self.raid_multiple_sortie_visible_value = False
        self.raid_multiple_sortie_state_value = RaidMultipleSortieState(
            generation=10,
            event="raid_20260827",
            sortie_count=1,
            ticket_selected=0,
            ticket_owned=0,
            bonus_count=14,
            zero_ticket_disabled=True,
            root="OverlayCamera/Overlay/UIMain/ContinuousOperationWindowUI(Clone)",
        )
        self.event_story_dialogue_visible_value = False
        self.event_story_skip_prompt_visible_value = False
        self.meta_page_visible_value = False
        self.meta_assist_state_value = MetaAssistState(
            remaining_attempts=3,
            attempt_capacity=3,
            selected_level=15,
            selected_hp=1600000,
            candidate_count=8,
            selected_candidate_index=2,
        )
        self.event_campaign_page_visible_value = False
        self.event_campaign_page_error = None
        self.game_room_page_visible_value = False
        self.daily_page_visible_value = False
        self.daily_detail_visible_value = False
        self.daily_precombat_visible_value = False
        self.meta_precombat_fleet_ready_value = True
        self.daily_selected_stage_visible_value = False
        self.daily_run_choices = set()
        self.research_project_values = []
        self.research_projects_visible_value = True
        self.research_detail_value = SimpleNamespace(
            code="G-412",
            resource_id="gold",
            resource_required=1500,
            can_start=True,
            can_queue=True,
            is_running=False,
        )
        self.research_queue_visible_value = True
        self.research_queue_value = SimpleNamespace(
            entries=(),
            reward_claimable=False,
            empty_slots=5,
            first_remaining_seconds=0,
        )
        self.research_prompt_cost = ("gold", 1500)
        self.tactical_slot_values = []
        self.tactical_remaining_values = ()
        self.tactical_prompt_text = None
        self.clear_tactical_prompt_on_cancel = True
        self.tactical_empty_slots_ready_value = True
        self.tactical_book_skill_progress_value = "900/3200"
        self.tactical_book_values = []
        self.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=0,
            oil_cost=0,
        )
        self.commission_transition_value = SimpleNamespace(
            name="日常资源开发III",
            before_duration_seconds=3600,
            after_duration_seconds=3595,
            after_status_sprite="tag_ongoing",
        )
        self.commission_start_prompt_cost_value = None
        self.commission_scroll_value = SimpleNamespace(
            position=0.0,
            page_fraction=0.8,
            scrollable=True,
            at_top=True,
            at_bottom=False,
        )
        self.commission_scroll_calls = []
        self.reward_summary_values = []
        self.state_generation = 20
        self.build_pool_value = BuildPool.LIGHT
        self.build_cost_value = SimpleNamespace(
            cubes_owned=10,
            cubes_per_build=1,
            coins_per_build=600,
        )
        self.build_submit_value = SimpleNamespace(
            count=1,
            cubes_owned=10,
            cubes_required=1,
            coins_required=600,
        )
        self.build_queue_empty_value = True
        self.build_queue_timer_values = ("99:99:99", "99:99:99")
        self.build_queue_visible_value = False
        self.build_queue_finish_prompt_value = None
        self.new_ship_reward_visible_value = False
        self.new_ship_reward_page_visible_value = False
        self.award_info_page_visible_value = False
        self.retirement_keep_limit_break = None
        self.enhancement_calls = []
        self.gems_calls = []
        self.gems_hard_occupied = {"flagship": True, "vanguard": True}
        self.gems_candidates = ()
        self.gems_filter_error = None
        self.gems_filter_cancel_error = None
        self.awaken_calls = []
        self.awaken_use_array = False
        self.awaken_sufficient = True
        self.awaken_candidate = SimpleNamespace(
            position=0, ship_id=100003, ship_name="C", level=115
        )
        self.enhancement_candidates = {
            "dd": [SimpleNamespace(position=0, ship_id=100001, ship_name="A", level=1)],
            "cl": [SimpleNamespace(position=0, ship_id=100002, ship_name="B", level=1)],
        }
        self.enhancement_ship_type = None
        self.retirement_receipt_value = RetirementExecutionReceipt(
            retired_count=68,
            capacity_before=882,
            capacity_after=814,
            capacity_total=910,
            settings=RetirementSettingsState(
                generation=20,
                unique_ship_protection=True,
                priority=("R", "SR", "N"),
                full_star_policy="keep_none",
                no_full_star_policy="keep_needed",
            ),
            rewards=(("物资", 1026), ("荣誉勋章", 22)),
            rarity_warning_confirmed=True,
            equipment_preserved=True,
            actions=(self.click_receipt("retirement/ships/confirm"),),
        )
        self.war_archives_visible_value = False
        self.war_archives_campaign_visible_value = False
        self.war_archives_collected_value = False
        self.war_archives_key_text_value = "300/300"
        self.data_key_limit_prompt_value = False
        self.battle_pass_page_visible_value = False
        self.battle_pass_reward_available_value = False
        self.battle_pass_claim_available_value = False
        self.recommendation_shop_visible_value = False
        self.gift_pack_page_visible_value = False
        self.free_weekly_supply_pack_available_value = False
        self.shop_oil_value = 12000
        self.main_gold_value = 10000
        self.build_gold_value = 10000
        self.dorm_state_value = SimpleNamespace(
            occupied_slots=2,
            total_slots=6,
            food=20000,
            food_capacity=40000,
            comfort=300,
            floor=1,
            food_countdown_seconds=3600,
        )
        self.dorm_feed_state_value = SimpleNamespace(
            food=0,
            capacity=40000,
            items=tuple(
                SimpleNamespace(item_id=50001 + index, value=1000, count=5)
                for index in range(6)
            ),
        )
        self.dorm_empty_food_cancel_value = False
        self.campaign_menu_value = False
        self.campaign_page_value = False
        self.campaign_page_error = None
        self.campaign_state_value = SimpleNamespace(
            generation=20,
            chapter_name="第一章",
            stages=(),
        )
        self.campaign_preparation_value = None
        self.campaign_preparation_error = None
        self.campaign_fleet_generation = 30
        self.campaign_fleets = {
            "fleet1": 1,
            "fleet2": 2,
            "submarine": 1,
        }
        self.campaign_empty_required_slots = {
            "fleet1": 0,
            "fleet2": 0,
            "submarine": 0,
        }
        self.campaign_fleet_dropdown_row = None
        self.campaign_role_tab_selected = False
        self.campaign_roles = ["all", "standby"]
        self.campaign_hard_mode = False
        self.campaign_oil_value = 9504
        self.event_points_value = 17060
        self.event_coin_value = 70477
        self.campaign_achievement_value = SimpleNamespace(
            generation=31,
            clear_percentage=1.0,
            achieved_stars=(True, True, True),
            threat_safe=True,
        )
        self.campaign_fleet_levels_value = (118, 109, 117, 110, 118, 107)
        self.campaign_in_map_value = False
        self.campaign_map_generation = 50
        self.campaign_map_state_calls = []
        self.campaign_map_cell_input_calls = []
        self.campaign_map_cell_click_calls = []
        self.campaign_map_target_raycast_top = True
        self.campaign_map_swipe_calls = []
        self.campaign_map_state_value = SimpleNamespace(
            generation=51,
            stage_code="12-4",
            rows=8,
            columns=11,
            cells=tuple(range(68)),
            land_nodes=tuple(range(20)),
            fleets=(SimpleNamespace(node="D6"), SimpleNamespace(node="F8")),
            enemies=(SimpleNamespace(node="C6"), SimpleNamespace(node="D6")),
            pickups=(SimpleNamespace(node="F2"),),
        )

    def _retry_transition_read(self, reader, **_kwargs):
        return reader()

    def enabled(self, semantic_id):
        self.enabled_calls.append(semantic_id)
        if semantic_id in self.enabled_values:
            return self.enabled_values[semantic_id]
        if semantic_id in (
            "login/enter",
            "overlay/bulletin/close",
            "overlay/guild-message/close",
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
            "reward/page/back",
            "reward/meta/enter",
        ):
            return False
        return True

    def exists(self, semantic_id):
        return self.exists_values.get(semantic_id, False)

    def observation_target_present(self, semantic_id):
        if semantic_id in self.exists_values:
            return self.exists_values[semantic_id]
        if semantic_id in self.enabled_values:
            return self.enabled_values[semantic_id]
        fields = {
            "raid/page/home": "raid_page_visible_value",
            "exercise/page/back": "exercise_page_visible_value",
            "exercise/opponent/back": "exercise_opponent_detail_visible_value",
            "daily/precombat/back": "daily_precombat_visible_value",
            "daily/page/back": "daily_page_visible_value",
            "meta/home": "meta_page_visible_value",
            "game-room/home": "game_room_page_visible_value",
            "battle-pass/home": "battle_pass_page_visible_value",
            "shop/home": "recommendation_shop_visible_value",
            "archive/page/back": "war_archives_visible_value",
            "os/page/back": "operation_siren_page_visible_value",
        }
        return bool(getattr(self, fields.get(semantic_id, ""), False))

    def observation_surface_present(self, surface):
        if surface in self.observation_surfaces:
            return True
        if surface is ObservationSurface.CURRENT_RAID:
            return bool(self.raid_page_visible_value or self.raid_page_visible_errors)
        if surface is ObservationSurface.STORY:
            return self.event_story_dialogue_visible_value or self.event_story_skip_prompt_visible_value
        if surface is ObservationSurface.GIFT_PACK:
            return self.gift_pack_page_visible_value
        return False

    def observation_prompt_kind(self):
        return self.observation_prompt_kind_value

    def bounds(self, semantic_id):
        self.bounds_calls.append(semantic_id)
        return Bounds(1, 2, 3, 4)

    def text_groups_in_bounds(self, bounds):
        self.last_text_bounds = tuple(bounds)
        return self.text_groups

    @staticmethod
    def _bounds_overlap(left, right):
        width = max(0.0, min(left.right, right.right) - max(left.left, right.left))
        height = max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
        return width * height

    def click(self, semantic_id):
        self.click_calls.append(semantic_id)
        if (
            semantic_id == "tactical/continue/cancel"
            and self.clear_tactical_prompt_on_cancel
        ):
            self.tactical_prompt_text = None
        role_match = re.fullmatch(
            r"campaign/fleet-preparation/roles/fleet([12])/"
            r"(mob|boss|all|standby)",
            semantic_id,
        )
        if role_match is not None:
            self.campaign_roles[int(role_match.group(1)) - 1] = (
                role_match.group(2)
            )
            self.campaign_fleet_generation += 1
        if semantic_id == "overlay/network-reconnect/confirm":
            self.enabled_values[semantic_id] = False
        if semantic_id == "meowfficer/get/lock":
            self.enabled_values[semantic_id] = False
            self.enabled_values["meowfficer/get/unlock"] = True
        if self.enable_main_after_overlay_click and semantic_id.startswith("overlay/"):
            self.enabled_values["main/task"] = True
        generation = 7
        path = "root/target"
        if semantic_id == "reward/campaign-total/exit":
            generation = getattr(self.read_state(), "generation", generation)
            path = (
                "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"
            )
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=generation,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path=path,
        )

    def image_selected(self, semantic_id):
        return self.image_selected_values.get(semantic_id, False)

    def click_image(self, semantic_id):
        self.click_calls.append(semantic_id)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=8,
            point=Point(50, 50),
            bounds=Bounds(0, 0, 100, 100),
            path="root/tagRoot/target/Image",
        )

    def toggle_selected(self, semantic_id):
        if semantic_id == "campaign/fleet-preparation/roles/tab":
            return self.campaign_role_tab_selected
        return self.toggle_selected_values.get(semantic_id, False)

    def toggle_present(self, semantic_id):
        return semantic_id in self.toggle_selected_values

    def click_toggle(self, semantic_id):
        self.click_calls.append(semantic_id)
        if semantic_id == "campaign/fleet-preparation/roles/tab":
            self.campaign_role_tab_selected = True
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=8,
            point=Point(50, 50),
            bounds=Bounds(0, 0, 100, 100),
            path="root/toggle",
        )

    def main_page_visible(self):
        return self.main_page_visible_value

    def award_info_page_visible(self):
        return self.award_info_page_visible_value

    def war_archives_page_visible(self):
        return self.war_archives_visible_value

    def gift_pack_page_visible(self):
        return self.gift_pack_page_visible_value

    def main_gold(self):
        return self.main_gold_value

    def game_room_page_visible(self):
        return self.game_room_page_visible_value

    def daily_page_visible(self):
        return self.daily_page_visible_value

    def daily_precombat_visible(self):
        return self.daily_precombat_visible_value

    def click_daily_control(self, semantic_id):
        return self.click(semantic_id)

    def click_daily_precombat_back(self):
        return self.click("daily/precombat/back")

    def click_daily_precombat_start(self):
        return self.click("daily/precombat/start")

    def daily_detail_visible(self):
        return self.daily_detail_visible_value

    def daily_selected_stage_visible(self, index):
        return self.daily_selected_stage_visible_value

    def daily_run_choice_visible(self, choice):
        return choice in self.daily_run_choices

    def daily_combat_visible(self):
        return False

    def daily_battle_result_visible(self):
        return False

    def server_maintenance_visible(self):
        return False

    def exercise_page_visible(self):
        return False

    def exercise_opponent_detail_visible(self):
        return False

    @staticmethod
    def click_receipt(semantic_id, generation=7):
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=generation,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="root/target",
        )

    def wait_for(self, semantic_id, timeout_seconds, minimum_generation=None):
        self.wait_calls.append((semantic_id, timeout_seconds, minimum_generation))
        return SimpleNamespace(path="root/" + semantic_id)

    def main_red_dot(self, semantic_id):
        return self.main_red_dot_values[semantic_id]

    def wait_for_any(
        self, semantic_ids, timeout_seconds, minimum_generation=None
    ):
        self.wait_any_calls.append(
            (semantic_ids, timeout_seconds, minimum_generation)
        )
        if self.wait_any_results:
            result = self.wait_any_results.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        return (semantic_ids[0], SimpleNamespace(path="root/target"))

    def read_state(self):
        return SimpleNamespace(generation=self.state_generation)
