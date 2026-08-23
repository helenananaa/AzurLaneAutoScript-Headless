import re
import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from alas_headless import (
    AlasCombatObserverManifest,
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    AlasCampaignDecisionPreview,
    MissionClaimableDetected,
    AndroidPackageFingerprint,
    AwakenCostState,
    AwakenDetailState,
    AwakenExecutionReceipt,
    Bounds,
    BuildPool,
    ButtonState,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapState,
    CampaignMapViewportSwipeProof,
    MissionDisposition,
    EnhancementNoMaterialReceipt,
    PINNED_CN_GAME_FINGERPRINT,
    PinnedPackageGate,
    Point,
    ResearchProjectStatus,
    RetirementExecutionReceipt,
    RetirementNoCandidateReceipt,
    RetirementSettingsState,
    SemanticGateClosed,
)
from alas_headless.semantic_oracle import (
    ActionReceipt,
    AdbObserverBridge,
    MetaAssistState,
    ObserverTransportError,
)
from alas_headless.adapter import SemanticFrameIdentity


class NamedButton:
    def __init__(self, name):
        self.name = name


class CampaignGridButton:
    def __init__(self, global_location):
        self.location = (0, 0)
        self.corner = object()
        self.button = (1, 2, 3, 4)
        self.__str__ = global_location


def make_campaign_combat_state(generation=51, *, after=False):
    cell = CampaignMapCellState(
        row=6,
        column=4,
        node="D6",
        button_path="root/DragLayer/plane/quads/chapter_cell_quad_6_4",
        point=Point(640, 360),
        bounds=Bounds(600, 320, 680, 400),
    )
    enemies = () if after else (
        CampaignMapEnemyState(
            row=6,
            column=4,
            node="D6",
            object_id=104,
            sprite="zl2",
            scale=2,
            genre="Main",
            level=114,
            fighting=True,
        ),
    )
    return CampaignMapState(
        generation=generation,
        stage_code="12-4",
        rows=8,
        columns=11,
        cells=(cell,),
        land_nodes=("A1",),
        fleets=(
            CampaignMapFleetState(
                marker="cell_fleet_shengwang_younv",
                node="D6",
                ammo=(4 if after else 5),
                ammo_capacity=5,
            ),
        ),
        enemies=enemies,
        pickups=(),
        displayed_fleet_index=1,
        current_fleet_marker="cell_fleet_shengwang_younv",
        current_fleet_roster_sprites=("shengwang_younv",),
    )


def make_campaign_combat_decision(generation=51):
    return AlasCampaignDecisionPreview(
        generation=generation,
        stage_code="12-4",
        battle_count=0,
        branch_name="battle_0",
        fleet_index=1,
        fleet_marker="cell_fleet_shengwang_younv",
        origin_node="D6",
        target_node="D6",
        target_kind="enemy",
        expected="combat",
        cost=0,
        weight=50.0,
        route_nodes=("D6",),
        goto_nodes=("D6",),
        step_optimize=False,
        turning_optimize=True,
    )


class FakeOracle:
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
        self.enable_main_after_overlay_click = False
        self.text_groups = ()
        self.image_selected_values = {"task/nav/all": True}
        self.main_red_dot_values = {"main/task": False}
        self.toggle_selected_values = {}
        self.mail_empty = False
        self.mail_confirmation_kind_value = None
        self.mail_surface_kind_value = None
        self.main_page_visible_value = False
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
        self.war_archives_collected_value = False
        self.war_archives_key_text_value = "300/300"
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
        self.campaign_fleet_dropdown_row = None
        self.campaign_role_tab_selected = False
        self.campaign_roles = ["all", "standby"]
        self.campaign_hard_mode = False
        self.campaign_oil_value = 9504
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

    def mail_surface_kind(self):
        if self.mail_surface_kind_value is not None:
            return self.mail_surface_kind_value
        if self.enabled_values.get("mail/manage/back") is True:
            return "manager"
        if self.exists_values.get("mail/page/back") is True or self.enabled_values.get(
            "mail/page/back"
        ) is True:
            return "page"
        return None

    def exists(self, semantic_id):
        return self.exists_values.get(semantic_id, False)

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
        if self.enable_main_after_overlay_click and semantic_id.startswith("overlay/"):
            self.enabled_values["main/task"] = True
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="root/target",
        )

    def click_mission_claim_row(self, expected_path):
        self.click_calls.append("task/claim/row/0")
        return ActionReceipt(
            semantic_id="task/claim/row/0",
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path=expected_path,
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

    def campaign_auto_search_selected(self):
        return self.toggle_selected_values.get(
            "campaign/map-preparation/auto-search", False
        )

    def event_campaign_page_visible(self):
        return self.event_campaign_page_visible_value

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

    def mail_is_empty(self):
        return self.mail_empty

    def mail_confirmation_kind(self):
        return self.mail_confirmation_kind_value

    def main_page_visible(self):
        return self.main_page_visible_value

    def meta_page_visible(self):
        return self.meta_page_visible_value

    def meta_current_detail_state(self):
        raise SemanticGateClosed("META current detail identity is absent")

    def meta_assist_state(self):
        return self.meta_assist_state_value

    def click_meta_assist_next_candidate(self, *, expected_index, expected_level):
        if (
            expected_index != self.meta_assist_state_value.selected_candidate_index
            or expected_level != self.meta_assist_state_value.selected_level
        ):
            raise SemanticGateClosed("META assist candidate changed before selection")
        self.click_calls.append("meta/assist/candidate/3")
        return self.click_receipt("meta/assist/candidate/3")

    def click_meta_home(self):
        self.click_calls.append("meta/home")
        return self.click_receipt("meta/home")

    def research_projects(self):
        if not self.research_projects_visible_value:
            raise SemanticGateClosed("research page identity is not proven")
        return tuple(self.research_project_values)

    def click_research_project(self, slot):
        self.click_calls.append("research/project/{0}".format(slot))
        return self.click_receipt("research/project/{0}".format(slot))

    def research_detail_state(self):
        return self.research_detail_value

    def research_queue_state(self):
        if not self.research_queue_visible_value:
            raise SemanticGateClosed("research queue identity is not proven")
        return self.research_queue_value

    def research_start_prompt_cost(self):
        return self.research_prompt_cost

    def research_queue_add_available(self):
        return self.enabled_values.get("research/detail/queue", True)

    def click_research_queue_add(self):
        return self.click("research/detail/queue")

    def build_selected_pool(self):
        return self.build_pool_value

    def build_costs(self):
        return self.build_cost_value

    def build_submit_state(self):
        return self.build_submit_value

    def build_coins_owned(self):
        return self.build_gold_value

    def build_queue_empty(self):
        return self.build_queue_empty_value

    def build_queue_all_launch_available(self):
        return not self.build_queue_empty_value

    def click_build_queue_all_launch(self):
        return self.click("build/queue/all-launch")

    def build_queue_timers(self):
        if not self.build_queue_visible_value:
            raise SemanticGateClosed("construction queue is not visible")
        return self.build_queue_timer_values

    def build_queue_finish_prompt_cost(self):
        return self.build_queue_finish_prompt_value

    def new_ship_reward_visible(self):
        return self.new_ship_reward_visible_value

    def new_ship_reward_page_visible(self):
        return self.new_ship_reward_page_visible_value

    def award_info_page_visible(self):
        return self.award_info_page_visible_value

    def retire_ships_one_click(self, keep_limit_break):
        self.retirement_keep_limit_break = keep_limit_break
        return self.retirement_receipt_value

    def set_enhancement_dock_favourite(self, enabled):
        self.enhancement_calls.append(("favourite", enabled))
        self.awaken_calls.append(("favourite", enabled))

    def _enhancement_dock_records(self):
        return object(), object()

    def set_awaken_dock_filter(self, use_array):
        self.awaken_use_array = use_array
        self.awaken_calls.append(("filter", use_array))
        return ()

    def awaken_dock_candidates(self):
        self.awaken_calls.append(("candidates", self.awaken_use_array))
        if self.awaken_use_array:
            return (
                SimpleNamespace(
                    position=0, ship_id=100004, ship_name="D", level=120
                ),
            )
        return (self.awaken_candidate,)

    def open_awaken_dock_candidate(self, position, ship_id, ship_name, level):
        self.awaken_calls.append(("open", ship_id))
        return (
            AwakenDetailState(
                generation=30,
                ship_id=ship_id,
                ship_name=ship_name,
                level=level,
                exp_maxed=True,
                use_array=level >= 120,
            ),
            (self.click_receipt("awaken/dock/ship/{0}".format(ship_id), 30),),
        )

    def open_awaken_confirmation(self, detail):
        self.awaken_calls.append(("modal", detail.ship_id))
        cost = AwakenCostState(
            generation=31,
            ship_id=detail.ship_id,
            ship_name=detail.ship_name,
            current_level=detail.level,
            target_level=detail.level + 5,
            coins_available=20000 if self.awaken_sufficient else 0,
            coins_required=2000 if detail.use_array else 10000,
            chips_available=75000,
            chips_required=200 if detail.use_array else 1000,
            arrays_available=9000 if detail.use_array else None,
            arrays_required=100 if detail.use_array else None,
        )
        return cost, self.click_receipt("awaken/detail/open", 31)

    def cancel_awaken_confirmation(self, cost):
        self.awaken_calls.append(("cancel", cost.ship_id))
        return self.click_receipt("awaken/confirm/cancel", 32)

    def commit_awaken_confirmation(self, cost):
        self.awaken_calls.append(("commit", cost.ship_id))
        return AwakenExecutionReceipt(
            ship_id=cost.ship_id,
            ship_name=cost.ship_name,
            current_level=cost.current_level,
            target_level=cost.target_level,
            observed_level=cost.target_level,
            cost=cost,
            actions=(
                self.click_receipt("awaken/confirm/commit", 32),
                self.click_receipt("awaken/completion/close", 33),
            ),
        )

    def return_from_awaken_detail_to_dock(self):
        self.awaken_calls.append(("back", self.awaken_use_array))
        return self.click_receipt("awaken/detail/back", 34)

    def set_enhancement_dock_filter(self, ship_type):
        self.enhancement_ship_type = ship_type
        self.enhancement_calls.append(("filter", ship_type))
        return ()

    def enhancement_dock_candidates(self):
        self.enhancement_calls.append(("candidates", self.enhancement_ship_type))
        return tuple(self.enhancement_candidates.get(self.enhancement_ship_type, ()))

    def open_enhancement_dock_candidate(self, position, ship_id, ship_name, level):
        self.enhancement_calls.append(("open", ship_id))
        return self.click_receipt("enhancement/dock/ship/{0}".format(ship_id))

    def enhance_with_official_recommendation(self):
        self.enhancement_calls.append(("recommend", self.enhancement_ship_type))
        return EnhancementNoMaterialReceipt(
            generation=30,
            target_name="fixture",
            recommendation=self.click_receipt("enhancement/recommend", 30),
        )

    def return_to_enhancement_dock(self):
        self.enhancement_calls.append(("back", self.enhancement_ship_type))
        return self.click_receipt("enhancement/dock/back", 31)

    def reset_enhancement_dock(self):
        self.enhancement_calls.append(("reset", None))
        self.awaken_calls.append(("reset", None))
        return ()

    def war_archives_page_visible(self):
        return self.war_archives_visible_value

    def war_archives_data_key_collected(self):
        if not self.war_archives_visible_value:
            raise SemanticGateClosed("war archives page identity is not proven")
        return self.war_archives_collected_value

    def war_archives_data_key_text(self):
        if not self.war_archives_visible_value:
            raise SemanticGateClosed("war archives page identity is not proven")
        return self.war_archives_key_text_value

    def main_gold(self):
        return self.main_gold_value

    def dorm_state(self):
        return self.dorm_state_value

    def game_room_page_visible(self):
        return self.game_room_page_visible_value

    def dorm_feed_state(self):
        return self.dorm_feed_state_value

    def dorm_empty_food_cancel_available(self):
        return self.dorm_empty_food_cancel_value

    def click_dorm_food(self, item_id):
        before = self.dorm_feed_state_value
        items = []
        for item in before.items:
            items.append(
                SimpleNamespace(
                    item_id=item.item_id,
                    value=item.value,
                    count=item.count - (1 if item.item_id == item_id else 0),
                )
            )
        selected = next(item for item in before.items if item.item_id == item_id)
        self.dorm_feed_state_value = SimpleNamespace(
            food=before.food + selected.value,
            capacity=before.capacity,
            items=tuple(items),
        )
        self.click_calls.append("dorm/feed/item/{0}".format(item_id))
        return self.click_receipt("dorm/feed/item/{0}".format(item_id))

    def campaign_menu_is_entry(self):
        return self.campaign_menu_value

    def campaign_page_is_normal(self):
        if self.campaign_page_error is not None:
            raise self.campaign_page_error
        return self.campaign_page_value

    def campaign_page_state(self):
        if self.campaign_page_error is not None:
            raise self.campaign_page_error
        if not self.campaign_page_value:
            raise SemanticGateClosed("campaign page identity is not proven")
        return self.campaign_state_value

    def campaign_is_in_map(self):
        return self.campaign_in_map_value

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

    def meta_precombat_fleet_ready(self):
        return self.meta_precombat_fleet_ready_value

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

    def operation_siren_battle_result_visible(self):
        return False

    def operation_siren_battle_result_grade(self):
        raise SemanticGateClosed("operation siren battle result is absent")

    def server_maintenance_visible(self):
        return False

    def operation_siren_exit_prompt_visible(self):
        return False

    def click_operation_siren_exit(self, confirm):
        if not self.operation_siren_exit_prompt_visible():
            raise SemanticGateClosed("operation siren exit prompt is absent")
        return self.click("os/exit/confirm" if confirm else "os/exit/cancel")

    def operation_siren_abyssal_entry_prompt_visible(self):
        return False

    def operation_siren_state(self):
        raise SemanticGateClosed("Operation Siren page identity is not proven")

    def operation_siren_local_map_visible(self):
        return self.operation_siren_local_map_visible_value

    def operation_siren_page_visible(self):
        return self.operation_siren_page_visible_value

    def operation_siren_current_fleet(self):
        return 1

    def operation_siren_globe_state(self):
        raise SemanticGateClosed("Operation Siren globe identity is not proven")

    def operation_siren_mission_list_visible(self):
        return False

    def click_operation_siren_order(self, order_kind):
        return self.click("os/order/" + order_kind)

    def operation_siren_order_confirmation_visible(self, order_kind):
        return self.operation_siren_order_confirmation_visible_value

    def click_operation_siren_order_confirmation(self, order_kind, *, confirm):
        return self.click(
            "os/order/" + ("confirm" if confirm else "cancel")
        )

    def exercise_page_visible(self):
        return False

    def exercise_opponent_detail_visible(self):
        return False

    def meta_assist_sortie_prompt_visible(self):
        return False

    def meta_simulation_prompt_visible(self):
        return False

    def meta_help_visible(self):
        return False

    def campaign_map_entry_state(self):
        if not self.campaign_in_map_value:
            raise SemanticGateClosed("campaign map-scene identity is absent")
        return SimpleNamespace(
            generation=self.campaign_map_generation,
            root_path="LevelCamera/Canvas/UIMain/LevelGrid",
            button_paths=(
                "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat",
            ),
            image_paths=(
                "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                "display/mask/sea",
            ),
        )

    def campaign_auto_search_active_state(self):
        if not self.campaign_in_map_value:
            raise SemanticGateClosed(
                "campaign official auto-search surface is not proven"
            )
        return SimpleNamespace(
            generation=self.campaign_map_generation,
            root_path="UICamera/Canvas/UIMain/CombatUIStandard(Clone)",
        )

    def campaign_map_state(
        self,
        stage_code,
        *,
        columns,
        rows,
        land_cells,
        expected_fleet_count,
    ):
        self.campaign_map_state_calls.append(
            (
                stage_code,
                columns,
                rows,
                tuple(land_cells),
                expected_fleet_count,
            )
        )
        return self.campaign_map_state_value

    def campaign_map_cell_input(
        self, state, node, *, allow_expected_enemy_coverage=False
    ):
        self.campaign_map_cell_input_calls.append(
            (node, allow_expected_enemy_coverage)
        )
        cell = next(item for item in state.cells if item.node == node)
        return ButtonState(
            name="chapter_cell_quad_6_4",
            path=cell.button_path,
            active_in_hierarchy=True,
            active_and_enabled=True,
            interactable=True,
            raycast_top=True,
            point=cell.point,
            bounds=cell.bounds,
            raw={},
        )

    def campaign_map_cell_viewport_target(self, state, node):
        return replace(
            self.campaign_map_cell_input(state, node),
            raycast_top=self.campaign_map_target_raycast_top,
        )

    def campaign_map_viewport_swipe(
        self,
        state,
        target_node,
        intent,
        *,
        start,
        end,
        duration_ms,
        columns,
        rows,
        land_cells,
        expected_fleet_count,
        allow_enemy_additions=False,
    ):
        self.campaign_map_swipe_calls.append(
            (
                target_node,
                intent,
                start,
                end,
                duration_ms,
                columns,
                rows,
                tuple(land_cells),
                expected_fleet_count,
                allow_enemy_additions,
            )
        )
        target = next(cell for cell in state.cells if cell.node == target_node)
        after_point = Point(target.point.x + 200, target.point.y)
        after_bounds = Bounds(
            target.bounds.left + 200,
            target.bounds.top,
            target.bounds.right + 200,
            target.bounds.bottom,
        )
        post_state = replace(
            state,
            generation=state.generation + 2,
            cells=tuple(
                replace(cell, point=after_point, bounds=after_bounds)
                if cell.node == target_node
                else cell
                for cell in state.cells
            ),
        )
        self.campaign_map_state_value = post_state
        self.campaign_map_target_raycast_top = True
        return CampaignMapViewportSwipeProof(
            semantic_id="campaign/map/viewport/" + target_node,
            target_node=target_node,
            pre_generation=state.generation,
            input_generation=state.generation + 1,
            post_generation=post_state.generation,
            name=intent.name,
            grid_vector=intent.grid_vector,
            pixel_vector=intent.pixel_vector,
            start=start,
            end=end,
            duration_ms=duration_ms,
            coherent_cell_count=len(state.cells),
            median_cell_delta=(200.0, 0.0),
            maximum_delta_residual=0.0,
            target_path=target.button_path,
            target_before_point=target.point,
            target_after_point=after_point,
            target_after_bounds=after_bounds,
            post_state=post_state,
        )

    def click_campaign_map_cell(
        self, state, node, *, allow_expected_enemy_coverage=False
    ):
        self.campaign_map_cell_click_calls.append(
            (node, allow_expected_enemy_coverage)
        )
        target = self.campaign_map_cell_input(
            state,
            node,
            allow_expected_enemy_coverage=allow_expected_enemy_coverage,
        )
        semantic_id = "campaign/map/grid/" + node
        self.click_calls.append(semantic_id)
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation + 1,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def campaign_mode_switch_state(self):
        return "hard"

    def campaign_oil(self):
        return self.campaign_oil_value

    def campaign_map_achievement_state(self, stage_code):
        return self.campaign_achievement_value

    def campaign_fleet_levels(self):
        return self.campaign_fleet_levels_value

    def campaign_stage_actionable(self, stage_code):
        return any(
            stage.stage_code == stage_code and stage.button.actionable
            for stage in self.campaign_state_value.stages
        )

    def click_campaign_stage(self, stage_code):
        self.click_calls.append("campaign/stage/" + stage_code)
        self.campaign_preparation_value = SimpleNamespace(kind="map")
        return self.click_receipt("campaign/stage/" + stage_code, generation=7)

    def campaign_preparation_state(self, stage_code):
        if self.campaign_preparation_error is not None:
            raise self.campaign_preparation_error
        return self.campaign_preparation_value

    def click_campaign_map_preparation(self, stage_code):
        self.click_calls.append("campaign/map-preparation/proceed")
        self.campaign_preparation_value = SimpleNamespace(kind="fleet")
        return self.click_receipt(
            "campaign/map-preparation/proceed", generation=8
        )

    def cancel_campaign_map_preparation(self, stage_code):
        self.click_calls.append("campaign/map-preparation/cancel")
        self.campaign_preparation_value = None
        return self.click_receipt(
            "campaign/map-preparation/cancel", generation=9
        )

    def cancel_campaign_fleet_preparation(self, stage_code):
        self.click_calls.append("campaign/fleet-preparation/cancel")
        self.campaign_preparation_value = None
        return self.click_receipt(
            "campaign/fleet-preparation/cancel", generation=9
        )

    def campaign_fleet_selection_state(self, stage_code, fallback_oil_cost=None):
        rows = tuple(
            SimpleNamespace(
                row_key=row_key,
                selected_fleet=(selected or None),
                in_use=bool(selected),
                ship_levels=((100,) if selected else ()),
                available=True,
                select_button=SimpleNamespace(
                    generation=self.campaign_fleet_generation,
                    point=Point(2, 3),
                    bounds=Bounds(1, 2, 3, 4),
                    path="root/{0}/select".format(row_key),
                ),
                clear_button=SimpleNamespace(
                    generation=self.campaign_fleet_generation,
                    point=Point(2, 3),
                    bounds=Bounds(1, 2, 3, 4),
                    path="root/{0}/clear".format(row_key),
                ),
                hard_satisfied=(
                    bool(selected) if self.campaign_hard_mode and row_key != "submarine"
                    else None
                ),
            )
            for row_key, selected in self.campaign_fleets.items()
        )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            stage_code=stage_code,
            surface_fleets=(
                int(bool(self.campaign_fleets["fleet1"]))
                + int(bool(self.campaign_fleets["fleet2"])),
                2,
            ),
            submarine_fleets=(int(bool(self.campaign_fleets["submarine"])), 1),
            mob_oil_cost=42,
            boss_oil_cost=55,
            submarine_oil_cost=17,
            rows=rows,
            sortie_button=SimpleNamespace(actionable=True),
            hard_mode=self.campaign_hard_mode,
            hard_requirements=(
                (SimpleNamespace(satisfied=True),)
                if self.campaign_hard_mode else ()
            ),
        )

    def campaign_fleet_dropdown_state(self):
        if self.campaign_fleet_dropdown_row is None:
            return None
        if self.campaign_fleet_dropdown_row == "submarine":
            selected = (self.campaign_fleets["submarine"],)
        else:
            selected = (
                self.campaign_fleets["fleet1"],
                self.campaign_fleets["fleet2"],
            )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            active_indices=tuple(
                sorted(set(value for value in selected if value))
            ),
        )

    def click_campaign_fleet_row(self, row_key, action):
        if action == "select":
            self.campaign_fleet_dropdown_row = row_key
        elif action == "clear":
            self.campaign_fleets[row_key] = 0
        else:
            raise AssertionError("unexpected fake campaign fleet action")
        self.campaign_fleet_generation += 1
        semantic_row = (
            "submarine/1"
            if row_key == "submarine"
            else row_key.replace("fleet", "fleet/")
        )
        semantic_id = "campaign/fleet-preparation/{0}/{1}".format(
            semantic_row, action
        )
        self.click_calls.append(semantic_id)
        return self.click_receipt(
            semantic_id, generation=self.campaign_fleet_generation
        )

    def click_campaign_fleet_option(self, index):
        if self.campaign_fleet_dropdown_row is None:
            raise AssertionError("fake campaign fleet dropdown is closed")
        if self.campaign_fleet_dropdown_row == "submarine":
            active = {self.campaign_fleets["submarine"]}
        else:
            active = {
                self.campaign_fleets["fleet1"],
                self.campaign_fleets["fleet2"],
            }
        active.discard(0)
        if index not in active:
            self.campaign_fleets[self.campaign_fleet_dropdown_row] = index
        self.campaign_fleet_dropdown_row = None
        self.campaign_fleet_generation += 1
        semantic_id = "campaign/fleet-preparation/option/{0}".format(index)
        self.click_calls.append(semantic_id)
        return self.click_receipt(
            semantic_id, generation=self.campaign_fleet_generation
        )

    def click_campaign_sortie(self, stage_code, fallback_oil_cost=None):
        self.click_calls.append("campaign/fleet-preparation/sortie")
        self.campaign_preparation_value = None
        self.campaign_in_map_value = True
        self.campaign_map_generation = self.campaign_fleet_generation + 3
        return self.click_receipt(
            "campaign/fleet-preparation/sortie",
            generation=self.campaign_fleet_generation,
        )

    def click_campaign_auto_search_sortie(self, stage_code):
        return self.click_campaign_sortie(stage_code)

    def campaign_auto_search_role_state(self):
        if (
            self.campaign_hard_mode
            and "campaign/fleet-preparation/roles/tab"
            not in self.toggle_selected_values
        ):
            return SimpleNamespace(
                generation=self.campaign_fleet_generation,
                fleet1_role="game-managed",
                fleet2_role="game-managed",
            )
        if not self.campaign_role_tab_selected:
            raise SemanticGateClosed(
                "campaign auto-search role tab is not selected"
            )
        return SimpleNamespace(
            generation=self.campaign_fleet_generation,
            fleet1_role=self.campaign_roles[0],
            fleet2_role=self.campaign_roles[1],
        )

    def tactical_slots(self):
        return tuple(self.tactical_slot_values)

    def tactical_empty_slots_ready(self):
        return self.tactical_empty_slots_ready_value

    def tactical_books(self):
        return tuple(self.tactical_book_values)

    def tactical_book_skill_progress(self):
        return self.tactical_book_skill_progress_value

    def tactical_remaining_seconds(self):
        return tuple(self.tactical_remaining_values)

    def tactical_continue_prompt_text(self):
        return self.tactical_prompt_text

    @staticmethod
    def click_receipt(semantic_id, generation=7):
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=generation,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="root/target",
        )

    def commission_scroll_state(self):
        self.commission_scroll_calls.append("state")
        return self.commission_scroll_value

    def commission_scroll_next(self):
        self.commission_scroll_calls.append("next")
        return SimpleNamespace(direction="next")

    def commission_scroll_to_top(self):
        self.commission_scroll_calls.append("top")
        return SimpleNamespace(direction="top")

    def wait_for(self, semantic_id, timeout_seconds, minimum_generation=None):
        self.wait_calls.append((semantic_id, timeout_seconds, minimum_generation))
        return SimpleNamespace(path="root/" + semantic_id)

    def wait_for_mission_state(self, timeout_seconds):
        disposition = (
            self.mission_dispositions.pop(0)
            if self.mission_dispositions
            else self.mission_disposition
        )
        return SimpleNamespace(
            disposition=disposition,
            generation=9,
            claim_all=(object() if disposition == MissionDisposition.CLAIMABLE_ALL else None),
            claim_rows=((object(),) if disposition == MissionDisposition.CLAIMABLE_ROW else ()),
            unfinished_rows=(object(),),
        )

    def mission_page_state(self):
        disposition = (
            self.streaming_mission_dispositions.pop(0)
            if self.streaming_mission_dispositions
            else self.mission_disposition
        )
        self.streaming_generation += 1
        return SimpleNamespace(
            disposition=disposition,
            generation=self.streaming_generation,
            signature=(disposition,),
            claim_all=(
                object()
                if disposition == MissionDisposition.CLAIMABLE_ALL
                else None
            ),
            claim_rows=(
                (
                    SimpleNamespace(
                        path="root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                        "right_panel/content/0/frame/get_btn"
                    ),
                )
                if disposition == MissionDisposition.CLAIMABLE_ROW
                else ()
            ),
            unfinished_rows=(
                (object(),)
                if disposition == MissionDisposition.UNFINISHED
                else ()
            ),
        )

    def mission_weekly_reward_available(self):
        return self.mission_weekly_reward_available_value

    def weekly_mission_progress_claim_available(self):
        return self.weekly_mission_progress_claim_available_value

    def click_weekly_mission_progress_claim(self):
        self.click_calls.append("task/weekly-progress/claim")
        self.weekly_mission_progress_claim_available_value = False
        return self.click_receipt("task/weekly-progress/claim")

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

    def commission_rows(self):
        return ()

    def commission_is_empty(self):
        return False

    def reward_summary_count(self, section, counter):
        self.last_reward_summary_query = (section, counter)
        if not self.reward_summary_values:
            return 0
        return self.reward_summary_values.pop(0)

    def read_state(self):
        return SimpleNamespace(generation=self.state_generation)

    def commission_detail_state(self):
        return self.commission_detail_value

    def commission_start_prompt_cost(self):
        return self.commission_start_prompt_cost_value

    def click_commission_row(self, signature):
        self.click_calls.append("commission/row/{0}".format(signature[0]))
        return ActionReceipt(
            semantic_id="commission/row/{0}".format(signature[0]),
            generation=10,
            point=Point(640, 190),
            bounds=Bounds(100, 100, 1180, 250),
            path="root/commission/row/{0}".format(signature[0]),
        )

    def click_commission_recommend(self, signature):
        self.click_calls.append("commission/detail/recommend")
        return ActionReceipt(
            semantic_id="commission/detail/recommend",
            generation=11,
            point=Point(935, 363),
            bounds=Bounds(855, 316, 1015, 410),
            path="root/commission/detail/recommend",
        )

    def click_commission_start(self, signature):
        self.click_calls.append("commission/detail/start")
        return ActionReceipt(
            semantic_id="commission/detail/start",
            generation=12,
            point=Point(1092, 363),
            bounds=Bounds(1012, 316, 1172, 410),
            path="root/commission/detail/start",
        )

    def commission_start_transition(self, signature):
        self.last_commission_transition_signature = tuple(signature)
        return self.commission_transition_value


class FakePackageBridge:
    def __init__(self):
        self.pid = 1234
        self.calls = []

    def require_package_compatibility(self, required_primary_abi):
        self.calls.append(required_primary_abi)
        return {"primary_abi": required_primary_abi}


class AlasSemanticAdapterTests(unittest.TestCase):
    @staticmethod
    def frame_identity():
        return SemanticFrameIdentity(
            frame_id="adapter-unit-frame",
            pid=1234,
            generation=10,
            scene_handle=-76,
            fingerprint_sha256="a" * 64,
            raw_state_sha256="b" * 64,
        )

    def make_adapter(self, **authority):
        oracle = FakeOracle()
        gate_calls = []
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: gate_calls.append(True),
            frame_observation_oracle=lambda: oracle,
            frame_identity_provider=self.frame_identity,
            **authority,
        )
        return adapter, oracle, gate_calls

    def test_confirmed_main_aliases_route_to_semantic_targets(self):
        adapter, oracle, gate_calls = self.make_adapter()

        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))
        receipt = adapter.click(NamedButton("MAIN_GOTO_FLEET"))

        self.assertEqual(
            oracle.enabled_calls,
            [
                "overlay/bulletin/close",
                "overlay/guild-message/close",
                "login/enter",
                "overlay/bulletin/close",
                "main/battle",
            ],
        )
        self.assertEqual(oracle.click_calls, ["main/formation"])
        self.assertEqual(receipt.semantic_id, "main/formation")
        self.assertEqual(len(gate_calls), 2)

    def test_operation_siren_order_owns_its_confirmation_popup(self):
        adapter, oracle, _ = self.make_adapter()

        order = adapter.click(NamedButton("ORDER_SCAN"))
        self.assertEqual(order.semantic_id, "os/order/scan")
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        confirmation = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(confirmation.semantic_id, "os/order/confirm")
        self.assertIsNone(adapter._operation_siren_pending_order)
        self.assertEqual(
            oracle.click_calls,
            ["os/order/scan", "os/order/confirm"],
        )

    def test_operation_siren_order_accepts_alas_scoped_confirmation_name(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        session.click(NamedButton("ORDER_SUBMARINE"))
        confirm = NamedButton("POPUP_CONFIRM_ORDER_SUBMARINE")
        self.assertTrue(adapter.appear(confirm))
        confirmation = session.click(confirm)

        self.assertEqual(confirmation.semantic_id, "os/order/confirm")
        self.assertIsNone(adapter._operation_siren_pending_order)
        self.assertEqual(
            oracle.click_calls,
            ["os/order/submarine", "os/order/confirm"],
        )

    def test_operation_siren_order_retries_only_endpoint_coherence(self):
        adapter, oracle, _ = self.make_adapter()
        receipt = oracle.click_receipt("os/order/submarine")
        oracle.click_operation_siren_order = Mock(
            side_effect=[
                SemanticGateClosed(
                    "operation siren order snapshots are not coherent"
                ),
                receipt,
            ]
        )

        with patch("alas_headless.alas_adapter.time.sleep") as sleep:
            returned = adapter.click(NamedButton("ORDER_SUBMARINE"))

        self.assertEqual(returned, receipt)
        self.assertEqual(adapter._operation_siren_pending_order, "submarine")
        self.assertEqual(oracle.click_operation_siren_order.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_operation_siren_storage_checkout_owns_exact_exit_confirmation(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_exit_prompt_visible = lambda: True

        self.assertTrue(adapter.operation_siren_storage_checkout_prompt_visible())
        receipt = adapter.click_operation_siren_storage_checkout_confirm()

        self.assertEqual(receipt.semantic_id, "os/exit/confirm")
        self.assertEqual(oracle.click_calls, ["os/exit/confirm"])
        self.assertGreater(adapter._operation_siren_entry_transition_until, 0.0)

        oracle.operation_siren_exit_prompt_visible = lambda: False
        with self.assertRaisesRegex(
            SemanticGateClosed,
            "operation siren exit prompt is absent",
        ):
            adapter.click_operation_siren_storage_checkout_confirm()

    def test_operation_siren_map_exit_owns_exact_exit_confirmation(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_exit_prompt_visible = lambda: True

        self.assertTrue(adapter.operation_siren_map_exit_prompt_visible())
        receipt = adapter.click_operation_siren_map_exit_confirm()

        self.assertEqual(receipt.semantic_id, "os/exit/confirm")
        self.assertEqual(oracle.click_calls, ["os/exit/confirm"])
        self.assertGreater(adapter._operation_siren_entry_transition_until, 0.0)

        oracle.operation_siren_exit_prompt_visible = lambda: False
        self.assertIsNone(
            adapter.try_click_operation_siren_map_exit_confirm()
        )
        with self.assertRaisesRegex(
            SemanticGateClosed,
            "operation siren exit prompt is absent",
        ):
            adapter.click_operation_siren_map_exit_confirm()

    def test_operation_siren_fleet_hp_retries_transient_missing_portraits(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_page_visible_value = True
        oracle.operation_siren_state = lambda: SimpleNamespace()
        calls = []

        def fleet_hp():
            calls.append(None)
            if len(calls) == 1:
                raise SemanticGateClosed(
                    "Operation Siren fleet portraits are absent or incomplete"
                )
            return (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)

        oracle.operation_siren_fleet_hp = fleet_hp

        self.assertEqual(
            adapter.campaign_fleet_hp(),
            (1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        )
        self.assertEqual(len(calls), 2)

    def test_operation_siren_fleet_hp_uses_local_shell_when_summary_is_incomplete(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_page_visible_value = True
        oracle.operation_siren_state = Mock(
            side_effect=SemanticGateClosed("operation siren fleet summary is malformed")
        )
        oracle.operation_siren_fleet_hp = lambda: (0.9, 0.8, 0.7, 0.6, 0.5, 0.4)

        self.assertEqual(
            adapter.campaign_fleet_hp(),
            (0.9, 0.8, 0.7, 0.6, 0.5, 0.4),
        )
        oracle.operation_siren_state.assert_not_called()

    def test_os_check_requires_unobstructed_local_map(self):
        adapter, oracle, _ = self.make_adapter()

        oracle.enabled_values["os/page/back"] = True
        oracle.operation_siren_local_map_visible_value = False
        self.assertFalse(adapter.appear(NamedButton("OS_CHECK")))

        oracle.operation_siren_local_map_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("OS_CHECK")))

        oracle.operation_siren_exit_prompt_visible = lambda: True
        self.assertFalse(adapter.appear(NamedButton("OS_CHECK")))

    def test_in_map_is_positive_on_exact_operation_siren_local_map(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_local_map_visible_value = True

        self.assertTrue(adapter.appear(NamedButton("IN_MAP")))

        oracle.operation_siren_local_map_visible_value = False
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))

    def test_typed_campaign_menu_hides_unrelated_pixel_page_checks(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_typed_main_or_reward_page_hides_exercise_page_check(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.main_page_visible_value = True
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

        oracle.main_page_visible_value = False
        oracle.enabled_values["reward/meta/enter"] = True
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_meta_landing_alias_uses_typed_entrance_state(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meta_entrance_state = Mock(return_value=SimpleNamespace())

        self.assertTrue(adapter.appear(NamedButton("ASH_SHOWDOWN")))
        self.assertEqual(adapter.semantic_id_for("ASH_SHOWDOWN"), "meta/page/back")

        oracle.meta_page_visible_value = True
        adapter.click(NamedButton("GOTO_MAIN"))
        self.assertEqual(oracle.click_calls, ["meta/home"])

    def test_meta_empty_beacon_page_maps_list_and_create_controls(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meta_current_empty_points = Mock(return_value=(200, 200))
        oracle.click_meta_current_create = Mock(
            return_value=oracle.click_receipt("meta/current/create")
        )

        self.assertTrue(adapter.appear(NamedButton("BEACON_LIST")))
        self.assertTrue(adapter.appear(NamedButton("META_BEGIN_ENTRANCE")))
        receipt = adapter.click(NamedButton("META_BEGIN_ENTRANCE"))

        self.assertEqual(receipt.semantic_id, "meta/current/create")
        oracle.click_meta_current_create.assert_called_once_with()

    def test_meta_assist_candidate_port_preserves_typed_expectations_through_session(self):
        adapter, oracle, gate_calls = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter

        state = session.meta_assist_state()
        receipt = session.click_meta_assist_next_candidate(
            expected_index=state.selected_candidate_index,
            expected_level=state.selected_level,
        )

        self.assertEqual(state, oracle.meta_assist_state_value)
        self.assertEqual(receipt.semantic_id, "meta/assist/candidate/3")
        self.assertEqual(oracle.click_calls, ["meta/assist/candidate/3"])
        self.assertEqual(gate_calls, [True, True])

    def test_meta_beacon_owner_keeps_generic_reward_probe_passive(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["reward/award-info/close"] = False
        oracle.enabled_values["reward/award-info1/close"] = False
        adapter.begin_meta_beacon()

        self.assertTrue(adapter._operation_siren_allows_passive_probe())
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))

        adapter.end_meta_beacon()
        self.assertFalse(adapter._meta_beacon_active)

    def test_meta_precombat_refuses_an_empty_saved_fleet(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meta_precombat_fleet_ready_value = False

        with self.assertRaisesRegex(SemanticGateClosed, "non-empty"):
            adapter.click_meta_precombat_start()

        self.assertEqual(oracle.click_calls, [])

    def test_meta_task_owner_survives_adapter_replacement(self):
        first, _, _ = self.make_adapter()
        replacement, replacement_oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = first
        session._meta_beacon_active = False
        session.open = lambda: session.adapter
        session.refresh_tactical_input_frame = lambda: None

        session.begin_meta_beacon()
        session.adapter = replacement
        receipt = session.click_daily_precombat_start()

        self.assertTrue(session.meta_beacon_active())
        self.assertTrue(replacement.meta_beacon_active())
        self.assertEqual(receipt.semantic_id, "daily/precombat/start")
        self.assertEqual(replacement_oracle.click_calls, ["daily/precombat/start"])

    def test_global_guild_overlay_hides_underlying_page_checks(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/guild-message/close"] = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))

    def test_meowfficer_check_color_only_matches_the_dock_page(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values.update(
            {
                "meowfficer/page/back": False,
                "meowfficer/get/result/close": False,
                "meowfficer/queue/close": False,
                "meowfficer/train/close": True,
                "meowfficer/fort/close": False,
            }
        )

        self.assertFalse(
            adapter.match_template_color(NamedButton("MEOWFFICER_CHECK"))
        )
        adapter.click(NamedButton("MEOWFFICER_CHECK"))

        self.assertEqual(oracle.click_calls, ["meowfficer/train/close"])
        self.assertEqual(len(gate_calls), 2)

    def test_original_login_handler_uses_exact_semantic_entry_context(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["login/enter"] = True

        adapter.begin_login()
        self.assertTrue(adapter.match_template_color(NamedButton("LOGIN_CHECK")))
        receipt = adapter.click(NamedButton("LOGIN_CHECK"))
        original_enabled = oracle.enabled

        def stale_login_probe(_semantic_id):
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = stale_login_probe
        self.assertFalse(adapter.match_template_color(NamedButton("LOGIN_CHECK")))
        oracle.enabled = original_enabled
        self.assertFalse(adapter.appear(NamedButton("ANDROID_NO_RESPOND")))
        adapter._login_flow._context.passive_transition_until = 0.0
        # A completed startup update can still be between Unity login surfaces.
        # This legacy Android-dialog probe stays a passive, no-input absence
        # result after the generic transition grace has elapsed.
        self.assertFalse(adapter.appear(NamedButton("ANDROID_NO_RESPOND")))
        bulletin = adapter.click(NamedButton("LOGIN_ANNOUNCE"))
        self.assertFalse(adapter.appear(NamedButton("LOGIN_RETURN_SIGN")))

        self.assertEqual(receipt.semantic_id, "login/enter")
        self.assertEqual(bulletin.semantic_id, "overlay/bulletin/close")
        self.assertEqual(
            oracle.click_calls, ["login/enter", "overlay/bulletin/close"]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "nested semantic"):
            adapter.begin_campaign_pre_sortie("12-4")

        adapter.end_login()
        oracle.enabled_values["login/enter"] = False
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("ANDROID_NO_RESPOND"))

    def test_login_closes_exact_post_sign_in_award_once(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["reward/award-info/close"] = True
        oracle.enabled_values["reward/award-info1/close"] = False
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_2")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])
        self.assertGreater(
            adapter._login_flow.snapshot().passive_transition_until,
            time.monotonic(),
        )

    def test_login_leaves_month_sign_page_through_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])

    def test_login_accepts_exact_main_identity_across_main_skins(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.main_page_visible_value = True
        oracle.enabled_values["main/formation"] = False
        oracle.enabled_values["main/battle"] = False
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_FLEET")))
        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))

    def test_login_closes_global_guild_message_overlay(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/guild-message/close"] = True
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))
        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(oracle.click_calls, ["overlay/guild-message/close"])

    def test_login_check_registry_route_preserves_frozen_read_contract(self):
        for expected in (False, True):
            with self.subTest(expected=expected):
                adapter, oracle, gate_calls = self.make_adapter()
                oracle.enabled_values["login/enter"] = expected

                registry_result = adapter._appear_once(NamedButton("LOGIN_CHECK"))

                self.assertEqual(registry_result, expected)
                self.assertEqual(oracle.enabled_calls, ["login/enter"])
                self.assertEqual(len(gate_calls), 1)

    def test_login_check_registry_route_preserves_frozen_exception_contract(self):
        adapter, oracle, gate_calls = self.make_adapter()

        def fail_closed(semantic_id):
            oracle.enabled_calls.append(semantic_id)
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = fail_closed
        with self.assertRaises(SemanticGateClosed) as routed:
            adapter._appear_once(NamedButton("LOGIN_CHECK"))

        self.assertEqual(str(routed.exception), "observer snapshot is stale")
        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(oracle.enabled_calls, ["login/enter"])

    def test_login_check_registry_route_preserves_frozen_package_gate_failure(self):
        oracle = FakeOracle()
        gate_calls = []

        def fail_closed():
            gate_calls.append(True)
            raise SemanticGateClosed("installed package fingerprint is not allowlisted")

        adapter = AlasSemanticAdapter(
            oracle,
            fail_closed,
            frame_observation_oracle=lambda: oracle,
            frame_identity_provider=self.frame_identity,
        )
        with self.assertRaises(SemanticGateClosed) as routed:
            adapter._appear_once(NamedButton("LOGIN_CHECK"))

        self.assertEqual(
            str(routed.exception),
            "installed package fingerprint is not allowlisted",
        )
        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(oracle.enabled_calls, [])

    def test_only_login_check_uses_registry_dispatch(self):
        adapter, oracle, _ = self.make_adapter()
        with patch.object(
            adapter._observation_registry,
            "dispatch",
            wraps=adapter._observation_registry.dispatch,
        ) as dispatch:
            self.assertEqual(
                tuple(
                    item.selector
                    for item in adapter._observation_registry.inventory()
                ),
                ("LOGIN_CHECK",),
            )
            self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN")))
            dispatch.assert_not_called()
            oracle.enabled_values["login/enter"] = True
            self.assertTrue(adapter.appear(NamedButton("LOGIN_CHECK")))
            self.assertEqual(dispatch.call_count, 1)

    def test_network_reconnect_popup_uses_only_exact_semantic_targets(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values.update(
            {
                "overlay/network-reconnect/cancel": True,
                "overlay/network-reconnect/confirm": True,
            }
        )

        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_UI_ADDITIONAL"))

        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(oracle.click_calls, ["overlay/network-reconnect/confirm"])

    def test_original_login_popup_handler_uses_exact_expired_data_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/login-data-expired/confirm"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = False
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM_WHITE")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_WHITE_LOGIN"))

        self.assertEqual(receipt.semantic_id, "overlay/login-data-expired/confirm")
        self.assertEqual(
            oracle.click_calls, ["overlay/login-data-expired/confirm"]
        )
        self.assertGreater(
            adapter._login_flow.snapshot().passive_transition_until,
            time.monotonic() + 50.0,
        )

    def test_main_dorm_and_research_menus_use_distinct_typed_buttons(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(
            adapter.semantic_id_for("MAIN_GOTO_DORMMENU"), "main/live"
        )
        self.assertEqual(
            adapter.semantic_id_for("MAIN_GOTO_RESHMENU_WHITE"), "main/tech"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORMMENU_GOTO_DORM"), "dorm-menu/dorm"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORMMENU_GOTO_ACADEMY"),
            "dorm-menu/academy",
        )

    def test_build_dorm_and_menu_page_checks_are_presence_only(self):
        cases = (
            ("build/page/start", "BUILD_CHECK"),
            ("dorm-menu/page/root", "DORMMENU_CHECK"),
            ("research-menu/page/back", "RESHMENU_CHECK"),
            ("research/page/back", "RESEARCH_CHECK"),
            ("dorm/page/manage", "DORM_CHECK"),
        )
        for semantic_id, resource in cases:
            with self.subTest(resource=resource):
                adapter, oracle, _ = self.make_adapter()
                oracle.exists_values[semantic_id] = True
                self.assertTrue(adapter.appear(NamedButton(resource)))
        self.assertEqual(
            adapter.semantic_id_for("DORM_GOTO_MAIN"), "dorm/page/back"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORM_INFO"), "dorm/statistics/confirm"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORM_FEED_CANCEL"),
            "dorm/empty-food/cancel",
        )
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BUILD_CHECK"))

    def test_research_page_check_rejects_selected_detail_panel(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_projects_visible_value = False
        oracle.enabled_values["research/detail/root"] = True

        self.assertFalse(adapter.appear(NamedButton("RESEARCH_CHECK")))

    def test_dorm_page_check_keeps_owned_page_visible_under_empty_food_modal(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = False
        oracle.dorm_empty_food_cancel_value = True

        self.assertTrue(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        receipt = adapter.click(NamedButton("DORM_FEED_CANCEL"))

        self.assertEqual(receipt.semantic_id, "dorm/empty-food/cancel")

    def test_dorm_page_check_treats_incomplete_empty_food_probe_as_absent(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = False

        def incomplete_empty_food_modal():
            raise SemanticGateClosed("dorm empty-food snapshots are incomplete")

        oracle.dorm_empty_food_cancel_available = incomplete_empty_food_modal

        self.assertTrue(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("DORM_FEED_CANCEL")))

    def test_dorm_page_check_yields_to_feed_panel_close(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = True

        self.assertFalse(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        receipt = adapter.click(NamedButton("DORM_FEED_CANCEL"))

        self.assertEqual(receipt.semantic_id, "dorm/feed/close")

    def test_dorm_feed_entry_suppresses_only_transition_close(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["dorm/feed/close"] = False

        entry = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertGreater(
            adapter._dorm_context.passive_transition_until,
            time.monotonic() + 40.0,
        )
        oracle.enabled_values["dorm/feed/close"] = True
        self.assertFalse(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        duplicate = adapter.click(NamedButton("DORM_FEED_ENTER"))

        self.assertEqual(duplicate, entry)
        self.assertEqual(oracle.click_calls, ["dorm/feed"])

        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CHECK")))
        close = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertEqual(close.semantic_id, "dorm/feed/close")
        self.assertEqual(oracle.click_calls, ["dorm/feed", "dorm/feed/close"])

    def test_dorm_empty_food_cancel_allows_a_fresh_entry(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["dorm/feed/close"] = False

        adapter.click(NamedButton("DORM_FEED_ENTER"))
        duplicate = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertEqual(duplicate.semantic_id, "dorm/feed")
        self.assertEqual(oracle.click_calls, ["dorm/feed"])

        oracle.dorm_empty_food_cancel_value = True
        adapter.click(NamedButton("DORM_FEED_CANCEL"))
        oracle.dorm_empty_food_cancel_value = False
        adapter.click(NamedButton("DORM_FEED_ENTER"))

        self.assertEqual(
            oracle.click_calls,
            ["dorm/feed", "dorm/empty-food/cancel", "dorm/feed"],
        )

    def test_build_and_dorm_typed_state_is_exposed_without_mutation(self):
        adapter, oracle, _ = self.make_adapter()

        self.assertEqual(adapter.build_selected_pool(), BuildPool.LIGHT)
        self.assertEqual(adapter.build_costs().cubes_owned, 10)
        self.assertEqual(adapter.dorm_state().occupied_slots, 2)
        self.assertEqual(oracle.click_calls, [])

    def test_research_decision_input_requires_complete_known_five_cards(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=slot,
                unity_index=slot,
                code="Q-{0:03d}".format(slot),
                series=9,
                duration_seconds=1800,
            )
            for slot in range(1, 6)
        ]

        class Project:
            def __init__(self, name, series):
                self.name = name
                self.series = series
                self.valid = name != "Q-003"

        with self.assertRaisesRegex(SemanticGateClosed, "unknown to pinned ALAS"):
            adapter.research_projects_for_alas(Project)
        self.assertEqual(oracle.click_calls, [])

        oracle.research_project_values[2].code = "Q-103"
        projects = adapter.research_projects_for_alas(Project)
        self.assertEqual([project.name for project in projects], [
            "Q-001", "Q-002", "Q-103", "Q-004", "Q-005"
        ])
        oracle.research_project_values[4].slot = 4
        with self.assertRaisesRegex(SemanticGateClosed, "slots are incomplete"):
            adapter.research_projects_for_alas(Project)
        self.assertEqual(oracle.click_calls, [])

    def test_research_page_stable_requires_two_identical_typed_snapshots(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=slot,
                unity_index=slot,
                code="Q-{0:03d}".format(slot),
                series=9,
                duration_seconds=1800,
                status=ResearchProjectStatus.DETAIL,
            )
            for slot in range(1, 6)
        ]

        adapter.research_page_stable()

        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(adapter.research_statuses(), ["detail"] * 5)

    def test_research_detail_stable_requires_two_identical_typed_snapshots(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_detail_value = SimpleNamespace(
            code="G-412",
            subtitle="small project",
            duration_seconds=5400,
            resource_id="gold",
            resource_owned=9000,
            resource_required=1500,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )

        adapter.research_detail_stable()

        self.assertEqual(oracle.click_calls, [])

    def test_research_code_selection_tracks_the_current_card_position(self):
        adapter, oracle, _ = self.make_adapter()
        refreshed = []
        adapter._input_frame_refresher = lambda: refreshed.append(True)
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=2,
                code="G-236-MI",
                status=ResearchProjectStatus.DETAIL,
            ),
            SimpleNamespace(
                slot=5,
                unity_index=1,
                code="D-381-MI",
                status=ResearchProjectStatus.DETAIL,
            ),
        ]

        receipt = adapter.click_research_project_code("G-236-MI")

        self.assertEqual(receipt.semantic_id, "research/project/1")
        self.assertEqual(adapter._research_context.selected_slot, 1)
        self.assertEqual(adapter._research_context.selected_code, "G-236-MI")
        self.assertEqual(oracle.click_calls, ["research/project/1"])
        self.assertEqual(refreshed, [True])

    def test_research_code_selection_uses_recent_decision_cache_then_rechecks(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="D-737-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        self.assertEqual(adapter.research_projects()[0].code, "D-737-MI")
        original_projects = oracle.research_projects
        reads = 0

        def transitional_projects():
            nonlocal reads
            reads += 1
            if reads == 1:
                raise SemanticGateClosed("research snapshots are not coherent")
            return original_projects()

        oracle.research_projects = transitional_projects
        receipt = adapter.click_research_project_code("D-737-MI")

        self.assertEqual(receipt.semantic_id, "research/project/1")
        self.assertEqual(reads, 1)
        self.assertEqual(oracle.click_calls, ["research/project/1"])

    def test_research_code_selection_uses_upstream_position_for_duplicates(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="C-153-MI",
                status=ResearchProjectStatus.DETAIL,
            ),
            SimpleNamespace(
                slot=5,
                unity_index=2,
                code="C-153-MI",
                status=ResearchProjectStatus.DETAIL,
            ),
        ]

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            adapter.click_research_project_code("C-153-MI")
        receipt = adapter.click_research_project_code(
            "C-153-MI", position=1
        )

        self.assertEqual(receipt.semantic_id, "research/project/5")
        self.assertEqual(adapter._research_context.selected_slot, 5)

        with self.assertRaisesRegex(SemanticGateClosed, "no longer matches"):
            adapter.click_research_project_code("G-236-MI", position=1)

    def test_research_queue_entry_retries_only_before_one_exact_input(self):
        adapter, oracle, _ = self.make_adapter()
        refreshed = []
        adapter._input_frame_refresher = lambda: refreshed.append(True)
        adapter.begin_research()
        original_click = oracle.click
        attempts = 0

        def transitional_click(semantic_id):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise SemanticGateClosed("semantic target is not actionable")
            return original_click(semantic_id)

        oracle.click = transitional_click
        with patch("alas_headless.alas_adapter.time.sleep") as sleep:
            receipt = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))

        self.assertEqual(receipt.semantic_id, "research/queue/enter")
        self.assertEqual(refreshed, [True, True])
        self.assertEqual(oracle.click_calls, ["research/queue/enter"])
        sleep.assert_called_once_with(0.25)

    def test_research_atomic_start_confirms_the_selected_exact_cost(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=3,
                code="G-236-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="G-236-MI",
            subtitle="small project",
            duration_seconds=9000,
            resource_id="gold",
            resource_owned=51507,
            resource_required=3000,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        oracle.research_prompt_cost = ("gold", 3000)
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "research/start/confirm":
                oracle.research_detail_value.is_running = True
                oracle.research_detail_value.can_start = False
            return receipt

        oracle.click = click
        original_prompt_cost = oracle.research_start_prompt_cost
        prompt_reads = 0

        def research_start_prompt_cost():
            nonlocal prompt_reads
            prompt_reads += 1
            if prompt_reads == 1:
                raise SemanticGateClosed("Msgbox snapshots are not coherent")
            return original_prompt_cost()

        oracle.research_start_prompt_cost = research_start_prompt_cost
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("G-236-MI"))

        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        self.assertGreaterEqual(prompt_reads, 2)
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/start",
                "research/start/confirm",
            ],
        )

    def test_research_atomic_start_preserves_running_project_for_queue_add(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=2,
                unity_index=4,
                code="G-412-MI",
                status=ResearchProjectStatus.RUNNING,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="G-412-MI",
            subtitle="small project",
            duration_seconds=5400,
            resource_id="",
            resource_owned=0,
            resource_required=0,
            requirement="",
            can_start=False,
            can_queue=True,
            is_running=True,
            is_finished=False,
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("G-412-MI"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
        self.assertEqual(oracle.click_calls, ["research/project/2"])

    def test_research_atomic_start_dispatches_resource_free_project_directly(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=4,
                unity_index=5,
                code="C-153-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="C-153-MI",
            subtitle="medium project",
            duration_seconds=21600,
            resource_id="",
            resource_owned=0,
            resource_required=0,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "research/detail/start":
                oracle.research_detail_value.is_running = True
                oracle.research_detail_value.can_start = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("C-153-MI"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        self.assertEqual(
            oracle.click_calls,
            ["research/project/4", "research/detail/start"],
        )

    def test_research_atomic_start_matches_normalized_part_prompt(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                unity_index=1,
                code="Q-289-MI",
                status=ResearchProjectStatus.DETAIL,
            )
        ]
        oracle.research_detail_value = SimpleNamespace(
            code="Q-289-MI",
            subtitle="small project",
            duration_seconds=7200,
            resource_id="research_part_t2",
            resource_owned=29300,
            resource_required=20,
            requirement="",
            can_start=True,
            can_queue=False,
            is_running=False,
            is_finished=False,
        )
        oracle.research_prompt_cost = ("research_part_t2", 20)
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "research/start/confirm":
                oracle.research_detail_value.is_running = True
                oracle.research_detail_value.can_start = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
        adapter.begin_research()

        self.assertTrue(adapter.start_research_project_code("Q-289-MI"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/start",
                "research/start/confirm",
            ],
        )

    def test_research_start_budget_is_spent_only_on_matching_final_confirm(self):
        oracle = FakeOracle()
        project = SimpleNamespace(
            slot=1,
            code="G-412",
            status=ResearchProjectStatus.DETAIL,
            button=SimpleNamespace(actionable=True),
        )
        oracle.research_project_values = [project]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        adapter.click(NamedButton("ENTRANCE_1"))
        adapter.click(NamedButton("RESEARCH_START"))
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_RESEARCH_START"))

        self.assertEqual(receipt.semantic_id, "research/start/confirm")
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/start",
                "research/start/confirm",
            ],
        )

    def test_research_start_budget_can_admit_one_existing_running_queue_add(self):
        oracle = FakeOracle()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                code="G-412",
                status=ResearchProjectStatus.RUNNING,
            )
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()
        adapter.click(NamedButton("ENTRANCE_1"))

        receipt = adapter.click(NamedButton("RESEARCH_QUEUE_ADD"))
        duplicate = adapter.click(NamedButton("RESEARCH_QUEUE_ADD"))

        self.assertEqual(receipt.semantic_id, "research/detail/queue")
        self.assertEqual(duplicate, receipt)
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 1)
        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        confirm = adapter.click(NamedButton("POPUP_CONFIRM_RESEARCH_QUEUE"))
        self.assertEqual(confirm.semantic_id, "research/queue/confirm")
        self.assertEqual(adapter._action_ledger.remaining("research.start"), 0)
        self.assertEqual(
            oracle.click_calls,
            [
                "research/project/1",
                "research/detail/queue",
                "research/queue/confirm",
            ],
        )

        gated = AlasSemanticAdapter(oracle, lambda: None)
        gated.begin_research()
        gated.click(NamedButton("ENTRANCE_1"))
        with self.assertRaisesRegex(SemanticGateClosed, "budgeted running project"):
            gated.click(NamedButton("RESEARCH_QUEUE_ADD"))

    def test_tactical_assignment_budget_is_spent_only_on_course_confirm(self):
        oracle = FakeOracle()
        oracle.tactical_book_values = [
            SimpleNamespace(position=1, selected=True, count=6)
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            tactical_assign_budget=1,
        )
        adapter.begin_tactical()

        adapter.click(NamedButton("TACTICAL_CLASS_START"))
        self.assertEqual(adapter._action_ledger.remaining("tactical.assign"), 1)
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_TACTICAL"))

        self.assertEqual(receipt.semantic_id, "tactical/course/confirm")
        self.assertEqual(adapter._action_ledger.remaining("tactical.assign"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM"))

    def test_dorm_feed_budget_requires_inventory_and_food_mutation_proof(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 1)

        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].semantic_id, "dorm/feed/item/50001")
        self.assertEqual(adapter._action_ledger.remaining("dorm.feed"), 0)
        self.assertEqual(oracle.dorm_feed_state_value.food, 1000)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 4)
        with self.assertRaises(SemanticGateClosed):
            adapter.dorm_feed_food(0, 1)

    def test_dorm_feed_refreshes_an_immutable_frame_for_each_card_boundary(self):
        oracle = FakeOracle()
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=2,
            frame_observation_oracle=lambda: oracle,
            input_frame_refresher=refresh,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 2)

        self.assertEqual(len(receipts), 2)
        self.assertEqual(refresh.call_count, 4)
        self.assertEqual(
            oracle.click_calls,
            ["dorm/feed/item/50001", "dorm/feed/item/50001"],
        )
        self.assertEqual(oracle.dorm_feed_state_value.food, 2000)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 3)

    def test_dorm_feed_postcondition_tolerates_transient_card_animation(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()
        original = oracle.dorm_feed_state
        transient = {"raised": False}

        def flaky_state():
            if oracle.click_calls and not transient["raised"]:
                transient["raised"] = True
                raise SemanticGateClosed("dorm feed item image is absent or ambiguous")
            return original()

        oracle.dorm_feed_state = flaky_state
        receipts = adapter.dorm_feed_food(0, 1)

        self.assertTrue(transient["raised"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.click_calls, ["dorm/feed/item/50001"])

    def test_dorm_feed_precondition_waits_for_stable_panel(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()
        original = oracle.dorm_feed_state
        transient = {"raised": False}

        def flaky_state():
            if not transient["raised"]:
                transient["raised"] = True
                raise SemanticGateClosed("dorm feed panel identity is not proven")
            return original()

        oracle.dorm_feed_state = flaky_state
        receipts = adapter.dorm_feed_food(0, 1)

        self.assertTrue(transient["raised"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.click_calls, ["dorm/feed/item/50001"])

    def test_dorm_feed_state_waits_for_complete_typed_panel(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        original = oracle.dorm_feed_state
        attempts = 0

        def flaky_state():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise SemanticGateClosed("dorm feed panel identity is not proven")
            return original()

        oracle.dorm_feed_state = flaky_state
        state = adapter.dorm_feed_state()

        self.assertEqual(state.food, 0)
        self.assertEqual(attempts, 3)

    def test_dorm_furniture_gold_purchase_uses_shop_authority(self):
        oracle = FakeOracle()
        oracle.dorm_furniture_purchase_state = lambda: SimpleNamespace(
            gold_price=150,
            quantity=1,
        )
        oracle.dorm_furniture_shop_balance = lambda: SimpleNamespace(
            dorm_coins=4512,
            gems=5422,
        )
        oracle.click_dorm_furniture_purchase = lambda currency: oracle.click_receipt(
            "dorm/furniture/purchase/" + currency
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.buy_dorm_furniture_with_gold()

        self.assertEqual(receipt.semantic_id, "dorm/furniture/purchase/gold")
        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.buy_dorm_furniture_with_gold()

    def test_operation_siren_shop_purchase_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"remaining": 3, "currency": 1200, "dialog": False}

        def items():
            return (
                SimpleNamespace(
                    index=7,
                    canonical_name="METARedBook",
                    display_name="META通用战术教材",
                    price=100,
                    remaining=state["remaining"],
                    currency="SpecialExchangeTicket",
                ),
            )

        oracle.operation_siren_shop_items = items
        oracle.operation_siren_shop_currency = lambda: state["currency"]
        oracle.click_operation_siren_shop_item = (
            lambda index, name, price: state.update(dialog=True)
        )
        oracle.shop_purchase_dialog_quantity = (
            lambda _name: 1 if state["dialog"] else None
        )

        def confirm(_name, _quantity):
            state["dialog"] = False
            state["remaining"] -= 1
            state["currency"] -= 100
            return oracle.click_receipt("shop/purchase/confirm")

        oracle.click_shop_purchase_confirm = confirm
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.purchase_operation_siren_shop_item_once(
            7, "METARedBook", 100
        )

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(state, {"remaining": 2, "currency": 1100, "dialog": False})
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_regular_shop_purchase_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"remaining": 4, "balance": 3626, "dialog": False}

        def items():
            return (
                SimpleNamespace(
                    index=6,
                    canonical_name="DR",
                    display_name="高级定向蓝图・八期",
                    amount=1,
                    cost="Medal",
                    price=20,
                    remaining=state["remaining"],
                    total=5,
                ),
            )

        oracle.general_shop_items = items
        oracle.shop_currency_balance = lambda _currency: state["balance"]
        oracle.click_shop_item = lambda _index: state.update(dialog=True)
        oracle.shop_purchase_dialog_quantity = (
            lambda _name: 1 if state["dialog"] else None
        )

        def confirm(_name, _quantity):
            state["dialog"] = False
            state["remaining"] -= 1
            state["balance"] -= 20
            return oracle.click_receipt("shop/purchase/confirm")

        oracle.click_shop_purchase_confirm = confirm
        adapter = AlasSemanticAdapter(oracle, lambda: None, shop_purchase_budget=1)

        receipt = adapter.purchase_shop_item_once(6, "DR", "Medal", 20)

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(state, {"remaining": 3, "balance": 3606, "dialog": False})
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_guild_shop_refresh_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"balance": 110600, "prompt": False, "refreshed": False}

        def items():
            name = "BookT3" if state["refreshed"] else "PlateT4"
            return (
                SimpleNamespace(
                    index=0,
                    display_name=name,
                    canonical_name=name,
                    amount=1,
                    cost="GuildCoins",
                    price=80 if state["refreshed"] else 60,
                    remaining=None,
                    total=None,
                ),
            )

        oracle.shop_selected_nav_label = lambda: "补给商店"
        oracle.shop_selected_tab_label = lambda: "舰队"
        oracle.general_shop_items = items
        oracle.shop_currency_balance = lambda _currency: state["balance"]
        oracle.shop_refresh_available = lambda: not state["refreshed"]
        oracle.click_shop_refresh = lambda: state.update(prompt=True)
        oracle.shop_refresh_prompt = (
            lambda: ("GuildCoins", 50) if state["prompt"] else None
        )

        def confirm(_currency, _price):
            state["prompt"] = False
            state["refreshed"] = True
            state["balance"] -= 50
            return oracle.click_receipt("shop/refresh/confirm")

        oracle.click_shop_refresh_confirm = confirm
        adapter = AlasSemanticAdapter(oracle, lambda: None, shop_purchase_budget=1)

        receipt = adapter.refresh_shop_once()

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(
            state, {"balance": 110550, "prompt": False, "refreshed": True}
        )
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_operation_siren_shop_purchase_refuses_insufficient_currency(self):
        oracle = FakeOracle()
        oracle.operation_siren_shop_items = lambda: (
            SimpleNamespace(
                index=7,
                canonical_name="METARedBook",
                display_name="META通用战术教材",
                price=100,
                remaining=3,
                currency="SpecialExchangeTicket",
            ),
        )
        oracle.operation_siren_shop_currency = lambda: 99
        oracle.click_operation_siren_shop_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "currency is insufficient"):
            adapter.purchase_operation_siren_shop_item_once(
                7, "METARedBook", 100
            )

        oracle.click_operation_siren_shop_item.assert_not_called()

    def test_operation_siren_voucher_exchange_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"remaining": 30, "currency": 21792, "dialog": False}

        def items():
            return (
                SimpleNamespace(
                    index=1,
                    canonical_name="HECombatPlan",
                    display_name="高效作战指令书",
                    icon_sprite="tebiezuozhan",
                    price=100,
                    remaining=state["remaining"],
                    currency="Voucher",
                    sold_out=False,
                ),
            )

        oracle.operation_siren_voucher_items = items
        oracle.operation_siren_voucher_currency = lambda: state["currency"]
        oracle.click_operation_siren_voucher_item = (
            lambda index, name, price, currency: state.update(dialog=True)
        )
        oracle.operation_siren_voucher_purchase_dialog_quantity = (
            lambda _name, _icon: 1 if state["dialog"] else None
        )

        def confirm(_name, _icon, _quantity):
            state["dialog"] = False
            state["remaining"] -= 1
            state["currency"] -= 100
            return oracle.click_receipt("os/voucher/purchase/confirm")

        oracle.click_operation_siren_voucher_purchase_confirm = confirm
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.purchase_operation_siren_voucher_item_once(
            1, "HECombatPlan", 100
        )

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(
            state, {"remaining": 29, "currency": 21692, "dialog": False}
        )
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_operation_siren_voucher_exchange_refuses_insufficient_currency(self):
        oracle = FakeOracle()
        oracle.operation_siren_voucher_items = lambda: (
            SimpleNamespace(
                index=1,
                canonical_name="HECombatPlan",
                display_name="高效作战指令书",
                icon_sprite="tebiezuozhan",
                price=100,
                remaining=30,
                currency="Voucher",
                sold_out=False,
            ),
        )
        oracle.operation_siren_voucher_currency = lambda: 99
        oracle.click_operation_siren_voucher_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "currency is insufficient"):
            adapter.purchase_operation_siren_voucher_item_once(
                1, "HECombatPlan", 100
            )

        oracle.click_operation_siren_voucher_item.assert_not_called()

    def test_operation_siren_voucher_exchange_refuses_identity_drift_and_oil(self):
        oracle = FakeOracle()
        oracle.operation_siren_voucher_items = lambda: (
            SimpleNamespace(
                index=1,
                canonical_name="HECombatPlan",
                display_name="高效作战指令书",
                icon_sprite="tebiezuozhan",
                price=101,
                remaining=30,
                currency="Voucher",
                sold_out=False,
            ),
        )
        oracle.click_operation_siren_voucher_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            adapter.purchase_operation_siren_voucher_item_once(
                1, "HECombatPlan", 100
            )
        with self.assertRaisesRegex(SemanticGateClosed, "Oil exchange"):
            adapter.purchase_operation_siren_voucher_item_once(
                0, "LoggerUnlockT2", 5000, "Oil"
            )

        oracle.click_operation_siren_voucher_item.assert_not_called()

    def test_operation_siren_voucher_exchange_refuses_sold_out_item(self):
        oracle = FakeOracle()
        oracle.operation_siren_voucher_items = lambda: (
            SimpleNamespace(
                index=10,
                canonical_name="Coin",
                display_name="物资",
                icon_sprite="gold",
                price=250,
                remaining=0,
                currency="Voucher",
                sold_out=True,
            ),
        )
        oracle.click_operation_siren_voucher_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "sold out"):
            adapter.purchase_operation_siren_voucher_item_once(10, "Coin", 250)

        oracle.click_operation_siren_voucher_item.assert_not_called()

    def test_dorm_furniture_theme_purchase_uses_shop_authority(self):
        oracle = FakeOracle()
        oracle.dorm_furniture_theme_purchase_state = lambda: SimpleNamespace(
            gold_price=1330,
        )
        oracle.dorm_furniture_shop_balance = lambda: SimpleNamespace(
            dorm_coins=4693,
            gems=5022,
        )
        oracle.click_dorm_furniture_theme_purchase_gold = lambda: oracle.click_receipt(
            "dorm/furniture/theme/purchase/gold"
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.buy_dorm_furniture_theme_with_gold()

        self.assertEqual(receipt.semantic_id, "dorm/furniture/theme/purchase/gold")
        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_dorm_furniture_flow_clears_exact_empty_food_popup_before_shop(self):
        oracle = FakeOracle()
        oracle.dorm_empty_food_cancel_value = True
        oracle.click_dorm_furniture_shop = Mock(
            side_effect=SemanticGateClosed("stop after proved popup recovery")
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None)

        with patch("alas_headless.alas_adapter.time.sleep"), self.assertRaises(
            SemanticGateClosed
        ):
            adapter.run_current_dorm_furniture_purchase("set")

        self.assertEqual(oracle.click_calls, ["dorm/empty-food/cancel"])
        oracle.click_dorm_furniture_shop.assert_called_once_with()

    def test_dorm_furniture_theme_flow_preserves_set_and_all_options(self):
        for buy_option in ("set", "all"):
            with self.subTest(buy_option=buy_option):
                oracle = FakeOracle()
                calls = []
                balances = iter((4693, 4693, 3363))
                oracle.dorm_empty_food_cancel_value = False
                oracle.click_dorm_furniture_shop = lambda: calls.append("shop")
                oracle.click_dorm_furniture_tag = lambda index: calls.append(
                    "tag:{0}".format(index)
                )
                oracle.click_dorm_furniture_theme = lambda index: calls.append(
                    "theme:{0}".format(index)
                )
                oracle.click_dorm_furniture_theme_details = lambda: calls.append(
                    "details"
                )
                oracle.dorm_furniture_theme_is_time_limited = lambda: True
                oracle.click_dorm_furniture_theme_purchase_option = (
                    lambda option: calls.append("option:" + option)
                )
                oracle.dorm_furniture_theme_purchase_state = lambda: SimpleNamespace(
                    gold_price=1330
                )
                oracle.dorm_state_value = SimpleNamespace(floor=1)
                oracle.dorm_furniture_shop_balance = lambda: SimpleNamespace(
                    dorm_coins=next(balances), gems=5022
                )
                oracle.click_dorm_furniture_theme_purchase_gold = (
                    lambda: oracle.click_receipt(
                        "dorm/furniture/theme/purchase/gold"
                    )
                )
                oracle.close_dorm_furniture_theme_details = lambda: calls.append(
                    "theme-back"
                )
                oracle.close_dorm_furniture_shop = lambda: calls.append("shop-back")
                oracle._retry_transition_read = lambda reader, **_: reader()
                adapter = AlasSemanticAdapter(
                    oracle,
                    lambda: None,
                    shop_purchase_budget=1,
                )

                with patch("alas_headless.alas_adapter.time.sleep"):
                    receipts = adapter.run_current_dorm_furniture_purchase(buy_option)

                self.assertEqual(len(receipts), 1)
                self.assertEqual(receipts[0].capability_id, "shop.purchase")
                self.assertIn("option:" + buy_option, calls)
                self.assertEqual(calls[-2:], ["theme-back", "shop-back"])

    def test_dorm_feed_proof_allows_only_bounded_ship_consumption(self):
        oracle = FakeOracle()
        original_click = oracle.click_dorm_food

        def click_with_one_consumption_tick(item_id):
            receipt = original_click(item_id)
            state = oracle.dorm_feed_state_value
            oracle.dorm_feed_state_value = SimpleNamespace(
                food=state.food - 18,
                capacity=state.capacity,
                items=state.items,
            )
            return receipt

        oracle.click_dorm_food = click_with_one_consumption_tick
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 1)

        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.dorm_feed_state_value.food, 982)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 4)

    def test_build_submit_budget_checks_coins_and_is_single_use(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        self.assertEqual(receipt.semantic_id, "build/prep/confirm")
        self.assertEqual(adapter._action_ledger.remaining("build.submit"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        insufficient = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        insufficient.begin_build()
        insufficient._build_context.coins_owned = 599
        with self.assertRaises(SemanticGateClosed):
            insufficient.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

    def test_build_set_count_proves_multi_order_and_split_submissions(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        count = 1

        def submit_state():
            return SimpleNamespace(
                count=count,
                cubes_owned=10,
                cubes_required=count,
                coins_required=600 * count,
            )

        original_click = oracle.click

        def click(semantic_id):
            nonlocal count
            if semantic_id == "build/prep/add":
                count += 1
            elif semantic_id == "build/prep/minus":
                count -= 1
            return original_click(semantic_id)

        oracle.build_submit_state = submit_state
        oracle.click = click
        refresh_input_frame = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=2,
            input_frame_refresher=refresh_input_frame,
        )
        adapter.begin_build()
        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))

        prepared = adapter.build_set_count(3)
        first = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        self.assertEqual(prepared.count, 3)
        self.assertEqual(refresh_input_frame.call_count, 2)
        self.assertEqual(first.semantic_id, "build/prep/confirm")
        self.assertEqual(
            oracle.click_calls,
            [
                "main/build",
                "build/page/start",
                "build/prep/add",
                "build/prep/add",
                "build/prep/confirm",
            ],
        )

        count = 1
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))
        self.assertEqual(adapter.build_set_count(2).count, 2)
        self.assertEqual(refresh_input_frame.call_count, 3)
        second = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        self.assertEqual(second.semantic_id, "build/prep/confirm")
        self.assertEqual(adapter._action_ledger.remaining("build.submit"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

    def test_official_retirement_budget_is_single_use_and_receipted(self):
        adapter, oracle, gate_calls = self.make_adapter(retirement_budget=1)

        retired = adapter.retire_ships_one_click(True)
        receipt = adapter.retirement_receipt()

        self.assertEqual(retired, 68)
        self.assertTrue(oracle.retirement_keep_limit_break)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(receipt.capability_id, "retirement.execute")
        self.assertEqual(len(receipt.policy_sha256), 64)
        self.assertEqual(adapter._action_ledger.remaining("retirement.execute"), 0)
        self.assertEqual(len(gate_calls), 1)
        with self.assertRaises(SemanticGateClosed):
            adapter.retire_ships_one_click(True)

    def test_official_no_candidate_result_is_receipted_and_not_retried(self):
        adapter, oracle, gate_calls = self.make_adapter(retirement_budget=1)
        oracle.retirement_receipt_value = RetirementNoCandidateReceipt(
            capacity_used=814,
            capacity_total=910,
            settings=RetirementSettingsState(
                generation=24,
                unique_ship_protection=True,
                priority=("R", "SR", "N"),
                full_star_policy="keep_none",
                no_full_star_policy="keep_needed",
            ),
            official_message="<color=white>没找到符合条件的舰船</color>",
            actions=(
                ActionReceipt(
                    semantic_id="retirement/one-click",
                    generation=23,
                    point=Point(725, 673),
                    bounds=Bounds(634, 639, 816, 707),
                    path="root/blur_panel/select_panel/quick_select",
                ),
            ),
        )

        retired = adapter.retire_ships_one_click(True)
        receipt = adapter.retirement_receipt()

        self.assertEqual(retired, 0)
        self.assertIsInstance(receipt, RetirementNoCandidateReceipt)
        assert isinstance(receipt, RetirementNoCandidateReceipt)
        self.assertEqual(receipt.capability_id, "retirement.execute")
        self.assertEqual(len(receipt.policy_sha256), 64)
        self.assertEqual(adapter._action_ledger.remaining("retirement.execute"), 0)
        self.assertEqual(len(gate_calls), 1)

    def test_official_retirement_is_default_denied(self):
        adapter, _, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "positive transaction budget"):
            adapter.retire_ships_one_click(True)

    def test_awaken_level120_honours_favourite_and_single_use_budget(self):
        adapter, oracle, gate_calls = self.make_adapter(awaken_budget=1)

        completed = adapter.awaken_task("level120", True)
        receipts = adapter.awaken_receipts()

        self.assertEqual(completed, 1)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].current_level, 115)
        self.assertEqual(receipts[0].target_level, 120)
        self.assertEqual(receipts[0].capability_id, "awaken.execute")
        self.assertEqual(len(receipts[0].policy_sha256), 64)
        self.assertEqual(
            oracle.awaken_calls,
            [
                ("favourite", True),
                ("filter", False),
                ("candidates", False),
                ("open", 100003),
                ("modal", 100003),
                ("commit", 100003),
                ("back", False),
                ("reset", None),
            ],
        )
        self.assertEqual(adapter._action_ledger.remaining("awaken.execute"), 0)
        self.assertEqual(len(gate_calls), 1)

    def test_awaken_level125_prefers_array_candidates(self):
        adapter, oracle, _ = self.make_adapter(awaken_budget=1)

        self.assertEqual(adapter.awaken_task("level125", False), 1)

        receipt = adapter.awaken_receipts()[0]
        self.assertEqual((receipt.current_level, receipt.target_level), (120, 125))
        self.assertTrue(receipt.cost.use_array)
        self.assertEqual(
            oracle.awaken_calls[:5],
            [
                ("favourite", False),
                ("filter", True),
                ("candidates", True),
                ("open", 100004),
                ("modal", 100004),
            ],
        )

    def test_awaken_is_default_denied_before_navigation(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "positive transaction budget"):
            adapter.awaken_task("level120", False)

        self.assertEqual(oracle.awaken_calls, [])

    def test_awaken_insufficient_modal_cancels_without_consuming_grant(self):
        adapter, oracle, gate_calls = self.make_adapter(awaken_budget=1)
        oracle.awaken_sufficient = False

        self.assertEqual(adapter.awaken_task("level120", False), 0)

        self.assertEqual(adapter.awaken_receipts(), ())
        self.assertEqual(len(adapter.awaken_cost_observations()), 1)
        self.assertFalse(adapter.awaken_cost_observations()[0].sufficient)
        self.assertIn(("cancel", 100003), oracle.awaken_calls)
        self.assertEqual(adapter._action_ledger.remaining("awaken.execute"), 1)
        self.assertEqual(gate_calls, [True])

    def test_enhancement_task_honours_favourite_filter_and_check_budget(self):
        adapter, oracle, gate_calls = self.make_adapter(enhancement_budget=2)

        consumed = adapter.enhance_ships("favourite", 3, "dd > cl")
        receipts = adapter.enhancement_receipts()

        self.assertEqual(consumed, 0)
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(item.capability_id == "enhancement.execute" for item in receipts))
        self.assertEqual(
            oracle.enhancement_calls,
            [
                ("favourite", True),
                ("filter", "dd"),
                ("candidates", "dd"),
                ("open", 100001),
                ("recommend", "dd"),
                ("back", "dd"),
                ("candidates", "dd"),
                ("filter", "cl"),
                ("candidates", "cl"),
                ("open", 100002),
                ("recommend", "cl"),
                ("back", "cl"),
                ("reset", None),
            ],
        )
        self.assertEqual(adapter._action_ledger.remaining("enhancement.execute"), 0)
        self.assertEqual(len(gate_calls), 1)

    def test_enhancement_task_is_default_denied_before_navigation(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "positive transaction budget"):
            adapter.enhance_ships("all", 5, None)

        self.assertEqual(oracle.enhancement_calls, [])

    def test_build_coin_count_falls_back_to_proven_build_resource_panel(self):
        oracle = FakeOracle()
        oracle.build_gold_value = 81908
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_build()

        self.assertEqual(adapter.build_coins_owned(), 81908)
        self.assertEqual(adapter._build_context.coins_owned, 81908)

    def test_build_warning_confirmation_waits_for_the_modal_to_close(self):
        oracle = FakeOracle()
        oracle.enabled_values["build/warning/confirm"] = True
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "build/warning/confirm":
                oracle.enabled_values["build/warning/confirm"] = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(receipt.semantic_id, "build/warning/confirm")
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))

    def test_build_warning_accepts_only_alas_gacha_prep_alias(self):
        oracle = FakeOracle()
        oracle.enabled_values["build/warning/confirm"] = True
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "build/warning/confirm":
                oracle.enabled_values["build/warning/confirm"] = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_PREP"))

        self.assertEqual(receipt.semantic_id, "build/warning/confirm")
        self.assertEqual(oracle.click_calls, ["build/warning/confirm"])

        oracle.enabled_values["build/warning/confirm"] = False
        oracle.enabled_values["build/prep/confirm"] = True
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM_GACHA_PREP")))
        with self.assertRaisesRegex(SemanticGateClosed, "exact warning"):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_PREP"))

    def test_build_generic_confirm_detects_open_order_dialog_before_alias_click(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()
        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))

        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))
        adapter.build_submit_state()
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))
        self.assertEqual(receipt.semantic_id, "build/prep/confirm")
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))

    def test_build_fast_finish_and_result_closure_use_typed_targets(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        oracle.enabled_values.update(
            {
                "reward/award-info/close": False,
                "reward/award-info1/close": False,
            }
        )
        oracle.build_queue_finish_prompt_value = (2, 9)

        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))

        def overlay_has_no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = overlay_has_no_queue_tab
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_FINISH_ORDERS"))
        self.assertEqual(receipt.semantic_id, "build/queue/finish-confirm")

        oracle.build_queue_finish_prompt_value = None
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        oracle.new_ship_reward_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("GET_SHIP")))
        self.assertTrue(adapter.appear(NamedButton("STORY_SKIP")))

        def result_page_has_no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = result_page_has_no_queue_tab
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        receipt = adapter.click(NamedButton("BUILD_FINISH_ORDERS"))
        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")

        oracle.new_ship_reward_visible_value = False
        oracle.award_info_page_visible_value = True
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        oracle.award_info_page_visible_value = False
        oracle.enabled_values["reward/award-info/close"] = True
        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_SHIP_1")))
        self.assertTrue(adapter.appear(NamedButton("BUILD_FINISH_RESULTS")))
        receipt = adapter.click(NamedButton("BUILD_FINISH_RESULTS"))
        self.assertEqual(receipt.semantic_id, "reward/award-info/close")

    def test_build_finish_transition_grace_precedes_slow_result_probes(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        assert adapter._build_context is not None
        adapter._build_context.queue_finish_transition_until = 11.0

        def no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = no_queue_tab
        slow_probe = Mock(side_effect=AssertionError("slow probe must not run"))
        oracle.build_queue_finish_prompt_cost = slow_probe

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
            self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

        slow_probe.assert_not_called()

    def test_build_result_overlay_blocks_queue_timer_and_launch_sentinels(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        oracle.toggle_selected = lambda _semantic_id: True
        oracle.new_ship_reward_page_visible_value = True
        page_hidden = SemanticGateClosed(
            "construction queue page identity is not proven"
        )
        oracle.build_queue_empty = Mock(side_effect=page_hidden)
        oracle.build_queue_all_launch_available = Mock(side_effect=page_hidden)

        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_new_ship_page_blocks_absent_queue_tab_sentinels(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        oracle.new_ship_reward_page_visible_value = True

        def no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = no_queue_tab

        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_side_navigation_retries_only_while_exact_toggle_is_blocked(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        blocked = SemanticGateClosed("semantic toggle action is blocked")
        oracle.click_toggle = Mock(
            side_effect=[blocked, oracle.click_receipt("build/nav/pools")]
        )

        with patch("alas_headless.alas_adapter.time.sleep"):
            receipt = adapter.click(NamedButton("GACHA_SIDE_NAVBAR_0_0"))

        self.assertEqual(receipt.semantic_id, "build/nav/pools")
        self.assertEqual(oracle.click_toggle.call_args_list[0].args, ("build/nav/pools",))
        self.assertEqual(oracle.click_toggle.call_count, 2)

    def test_build_finish_grace_covers_selected_background_queue_tab(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        assert adapter._build_context is not None
        adapter._build_context.queue_finish_transition_until = 11.0
        oracle.toggle_selected = lambda _semantic_id: True
        page_hidden = SemanticGateClosed(
            "construction queue page identity is not proven"
        )
        oracle.build_queue_empty = Mock(side_effect=page_hidden)
        oracle.build_queue_all_launch_available = Mock(side_effect=page_hidden)

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
            self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_navbars_and_queue_observations_feed_alas_primitives(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "reward/award-info/close": False,
                "reward/award-info1/close": False,
            }
        )
        oracle.build_queue_visible_value = True
        oracle.toggle_selected_values.update(
            {
                "build/nav/pools": False,
                "build/nav/queue": True,
                "build/nav/support": False,
                "build/nav/unseam": False,
                "build/pool/light": False,
                "build/pool/heavy": True,
                "build/pool/special": False,
            }
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None, build_submit_budget=1)
        adapter.begin_build()

        self.assertTrue(adapter.supports(NamedButton("GACHA_SIDE_NAVBAR_0_1")))
        self.assertTrue(adapter.supports(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0")))
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("GACHA_SIDE_NAVBAR_0_1"),
                color=(247, 255, 173),
                threshold=221,
                count=100,
            )
        )
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0"),
                color=(247, 227, 148),
                threshold=180,
                count=100,
            )
        )
        self.assertFalse(
            adapter.image_color_count(
                NamedButton("CONSTRUCT_BOTTOM_NAVBAR_0_0"),
                color=(189, 231, 247),
                threshold=180,
                count=50,
            )
        )
        self.assertTrue(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.click(NamedButton("GACHA_SIDE_NAVBAR_0_0"))
        session.click(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0"))
        self.assertEqual(
            oracle.click_calls,
            ["build/nav/pools", "build/pool/heavy"],
        )
        oracle.build_queue_empty_value = False
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("BUILD_QUEUE_EMPTY"))
        self.assertTrue(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        receipt = adapter.click(NamedButton("BUILD_FINISH_ORDERS"))
        self.assertEqual(receipt.semantic_id, "build/queue/all-launch")

        oracle.toggle_selected_values["build/nav/queue"] = False
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))

        oracle.toggle_selected_values["build/nav/queue"] = True

        def queue_switched_during_probe():
            raise SemanticGateClosed("construction queue tab is not selected")

        oracle.build_queue_empty = queue_switched_during_probe
        oracle.build_queue_all_launch_available = queue_switched_during_probe
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_queue_goto_main_uses_typed_queue_identity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.build_queue_visible_value = True
        oracle.enabled_values["build/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "build/page/back")
        self.assertEqual(oracle.click_calls, ["build/page/back"])

    def test_tactical_navigation_from_build_queue_has_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.build_queue_visible_value = True
        oracle.enabled_values["build/page/back"] = True

        adapter.click(NamedButton("GOTO_MAIN"))

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_tactical_back_has_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.enabled_values["tactical/dock/back"] = False
        oracle.enabled_values["tactical/page/back"] = True

        receipt = adapter.click(NamedButton("BACK_ARROW"))
        oracle.enabled_values.clear()
        oracle.enabled_values["tactical/dock/back"] = False
        oracle.enabled_values["tactical/page/back"] = False
        duplicate = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(receipt.semantic_id, "tactical/page/back")
        self.assertEqual(duplicate, receipt)
        self.assertEqual(oracle.click_calls, ["tactical/page/back"])
        self.assertFalse(adapter.appear(NamedButton("SP_CHECK")))

    def test_generic_back_leaves_exercise_page_through_exact_typed_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exercise_page_visible = lambda: True

        receipt = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(receipt.semantic_id, "exercise/page/back")
        self.assertEqual(oracle.click_calls, ["exercise/page/back"])

    def test_tactical_check_precedes_unrelated_global_page_classification(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.exists_values["tactical/page/back"] = True
        for target in (
            "tactical/dock/cancel",
            "tactical/skill/confirm",
            "tactical/book/start",
            "tactical/course/confirm",
            "tactical/course/cancel",
        ):
            oracle.enabled_values[target] = False
        oracle.war_archives_page_visible = lambda: (_ for _ in ()).throw(
            AssertionError("unrelated War Archives probe")
        )

        self.assertTrue(adapter.appear(NamedButton("TACTICAL_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM_WHITE")))
        self.assertFalse(adapter.appear(NamedButton("GET_MISSION")))
        oracle.enabled_values["tactical/course/confirm"] = True
        self.assertFalse(adapter.appear(NamedButton("TACTICAL_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("ADD_NEW_STUDENT")))

    def test_tactical_course_probe_treats_truncated_absent_msgbox_as_non_match(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.exists_values["tactical/page/back"] = True
        for target in (
            "tactical/dock/cancel",
            "tactical/skill/confirm",
            "tactical/book/start",
        ):
            oracle.enabled_values[target] = False
        enabled = oracle.enabled

        def truncated_course_probe(target):
            if target.startswith("tactical/course/"):
                raise SemanticGateClosed("toggle snapshot is truncated")
            return enabled(target)

        oracle.enabled = truncated_course_probe

        self.assertTrue(adapter.appear(NamedButton("TACTICAL_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))

    def test_build_goto_main_uses_exact_reviewed_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["build/page/start"] = True
        oracle.enabled_values["build/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "build/page/back")
        self.assertEqual(oracle.click_calls, ["build/page/back"])

    def test_campaign_menu_uses_presence_check_and_exact_navigation_targets(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))
        self.assertEqual(
            adapter.semantic_id_for("CAMPAIGN_MENU_GOTO_CAMPAIGN"),
            "campaign-menu/normal",
        )
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        self.assertEqual(oracle.click_calls, ["campaign-menu/page/back"])

    def test_campaign_menu_entry_has_bounded_transition_grace(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_error = SemanticGateClosed(
            "campaign page identity is not proven"
        )

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            receipt = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_CAMPAIGN"))
            duplicate = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_CAMPAIGN"))
            self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))

        self.assertEqual(duplicate, receipt)
        self.assertEqual(oracle.click_calls, ["campaign-menu/normal"])
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=31.0):
            with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
                adapter.appear(NamedButton("CAMPAIGN_CHECK"))
        adapter.end_campaign_pre_sortie()

    def test_resumed_map_does_not_impersonate_campaign_menu(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_in_map_value = True

        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))

    def test_campaign_chapter_check_and_back_require_typed_page_identity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True
        oracle.enabled_values["login/enter"] = False
        oracle.enabled_values["overlay/bulletin/close"] = False
        oracle.enabled_values["campaign-menu/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertEqual(adapter.campaign_page_state().chapter_name, "第一章")
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        self.assertEqual(oracle.click_calls, ["campaign-menu/page/back"])

    def test_campaign_check_short_circuits_restored_chapter_before_preparation(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        oracle.campaign_page_value = True
        oracle.campaign_preparation_error = AssertionError(
            "restored chapter must not probe campaign preparation"
        )

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))

        adapter.end_campaign_pre_sortie()

    def test_campaign_page_state_retries_only_generation_coherence(self):
        adapter, oracle, _ = self.make_adapter()
        expected = oracle.campaign_state_value
        attempts = []

        def transient_page_state():
            attempts.append(True)
            if len(attempts) < 3:
                raise SemanticGateClosed("campaign snapshots are not coherent")
            return expected

        oracle.campaign_page_state = transient_page_state

        self.assertIs(adapter.campaign_page_state(), expected)
        self.assertEqual(len(attempts), 3)

        def identity_failure():
            raise SemanticGateClosed("campaign page identity is not proven")

        oracle.campaign_page_state = identity_failure
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            adapter.campaign_page_state()

    def test_campaign_stage_entry_is_exact_and_spends_one_independent_budget(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云下",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.campaign_stage_entry_allowed())
        self.assertTrue(adapter.appear(button))
        receipt = adapter.click(button)

        self.assertEqual(receipt.semantic_id, "campaign/stage/12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        self.assertEqual(oracle.click_calls, ["campaign/stage/12-4"])
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.click(button)
        adapter.end_campaign_pre_sortie()

    def test_campaign_context_recovers_only_exact_network_reconnect_prompt(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        oracle.enabled_values["overlay/network-reconnect/cancel"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True

        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_CAMPAIGN_RECONNECT"))

        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(
            oracle.click_calls,
            ["overlay/network-reconnect/confirm"],
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_prioritizes_exact_network_reconnect_popup(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        oracle.enabled_values["overlay/network-reconnect/cancel"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._live_combat_visible = lambda: self.fail(
            "covered combat hierarchy must not be classified"
        )

        self.assertFalse(session.appear(NamedButton("BATTLE_PREPARATION")))
        self.assertTrue(session.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(session.appear(NamedButton("POPUP_CONFIRM")))
        receipt = session.click(NamedButton("POPUP_CONFIRM_COMBAT_STATUS"))

        self.assertEqual(
            receipt.semantic_id, "overlay/network-reconnect/confirm"
        )
        self.assertEqual(
            oracle.click_calls, ["overlay/network-reconnect/confirm"]
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_session_delegates_restored_chapter_check(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.campaign_combat_committed = lambda: True
        oracle.campaign_page_value = True
        oracle.campaign_preparation_error = AssertionError(
            "restored chapter must not enter combat or preparation probing"
        )
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._live_combat_visible = lambda: self.fail(
            "restored chapter must not be classified as combat"
        )

        self.assertTrue(session.appear(NamedButton("CAMPAIGN_CHECK")))

        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_session_tolerates_stale_snapshot_only_in_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.campaign_combat_committed = lambda: True
        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        def stale():
            raise SemanticGateClosed("observer snapshot is stale")

        session._live_combat_visible = stale

        self.assertFalse(session.appear(NamedButton("BATTLE_PREPARATION")))

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        self.assertFalse(
            session._campaign_combat_transition_error(
                SemanticGateClosed("observer snapshot is stale")
            )
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_map_mount_gap_is_bounded(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.campaign_combat_committed = lambda: True
        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter

        def mounting():
            raise SemanticGateClosed("campaign startup surface is not reviewed")

        oracle.campaign_is_in_map = mounting
        self.assertIsNone(session.campaign_is_in_map_after_combat())

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaisesRegex(SemanticGateClosed, "startup surface"):
            session.campaign_is_in_map_after_combat()
        adapter.end_campaign_pre_sortie()

    def test_campaign_result_ready_requires_committed_campaign_owner(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        oracle.daily_battle_result_visible = Mock(return_value=True)
        oracle.operation_siren_battle_result_visible = Mock(return_value=False)
        adapter.campaign_combat_committed = Mock(return_value=True)

        self.assertTrue(session.campaign_result_ready())
        adapter.campaign_combat_committed.return_value = False
        self.assertFalse(session.campaign_result_ready())

    def test_campaign_boss_stage_return_requires_committed_owner_and_closed_result(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.operation_siren_battle_result_visible = Mock(return_value=False)
        oracle.campaign_page_value = True
        adapter.campaign_combat_committed = Mock(return_value=True)

        self.assertTrue(session.campaign_boss_returned_to_stage())
        oracle.daily_battle_result_visible.return_value = True
        self.assertFalse(session.campaign_boss_returned_to_stage())
        oracle.daily_battle_result_visible.return_value = False
        adapter.campaign_combat_committed.return_value = False
        self.assertFalse(session.campaign_boss_returned_to_stage())

    def test_campaign_committed_map_departure_counts_as_combat_loading(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.daily_combat_visible = Mock(return_value=False)
        oracle.campaign_is_in_map = Mock(return_value=False)
        adapter.campaign_combat_committed = Mock(return_value=True)

        self.assertTrue(session.combat_is_loading())

    def test_orphan_campaign_result_accepts_reviewed_map_return(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.campaign_battle_reward_visible = Mock(return_value=False)
        oracle.campaign_is_in_map = Mock(return_value=True)
        oracle.operation_siren_page_visible = Mock(return_value=False)
        oracle.daily_page_visible = Mock(return_value=False)
        oracle.main_page_visible = Mock(return_value=False)

        self.assertEqual(session.recover_orphan_combat_result(), ())

    def test_orphan_event_result_accepts_reviewed_event_page_return(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.campaign_battle_reward_visible = Mock(return_value=False)
        oracle.event_campaign_page_visible_value = True
        oracle.operation_siren_page_visible = Mock(return_value=False)
        oracle.daily_page_visible = Mock(return_value=False)
        oracle.main_page_visible = Mock(return_value=False)

        self.assertEqual(session.recover_orphan_combat_result(), ())

    def test_orphan_campaign_result_tolerates_exact_map_mount_gap(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.campaign_battle_reward_visible = Mock(return_value=False)
        oracle.campaign_is_in_map = Mock(
            side_effect=(
                SemanticGateClosed("campaign startup surface is not reviewed"),
                True,
            )
        )
        oracle.operation_siren_page_visible = Mock(return_value=False)
        oracle.daily_page_visible = Mock(return_value=False)
        oracle.main_page_visible = Mock(return_value=False)

        with patch("alas_headless.alas_adapter.time.sleep", return_value=None):
            self.assertEqual(session.recover_orphan_combat_result(), ())

    def test_campaign_stage_probe_defers_to_exact_late_reconnect_prompt(self):
        adapter, oracle, _ = self.make_adapter()
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")

        def disconnected(_stage_code):
            raise SemanticGateClosed("campaign page identity is not proven")

        oracle.campaign_stage_actionable = disconnected
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True

        self.assertFalse(adapter.appear(button))
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_stage_entry_accepts_exact_preparation_transition(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            adapter.click(button)

            def identity_failure(_stage_code):
                raise SemanticGateClosed("campaign page identity is not proven")

            oracle.campaign_stage_actionable = identity_failure
            self.assertFalse(adapter.appear(button))

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=31.0):
            self.assertFalse(adapter.appear(button))
            oracle.campaign_preparation_value = None
            with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
                adapter.appear(button)

        adapter.end_campaign_pre_sortie()

    def test_campaign_stage_entry_defaults_closed_and_rejects_identity_change(self):
        adapter, oracle, _ = self.make_adapter()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云下",
            stages=(stage,),
        )
        button = NamedButton("12-3")
        button.semantic_campaign_stage_code = "12-3"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            adapter.appear(button)
        adapter.end_campaign_pre_sortie()

    def test_campaign_startup_in_map_probe_reuses_typed_non_map_gate(self):
        adapter, _, _ = self.make_adapter()

        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.appear(NamedButton("UNREVIEWED_PAGE_CHECK")))
        adapter.end_campaign_pre_sortie()

    def test_campaign_map_proof_allows_only_passive_unknown_probes(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        oracle.campaign_in_map_value = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("EXERCISE_CHECK"))
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_unknown_surface_keeps_passive_probe_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter._campaign_context.passive_transition_until = time.monotonic() - 1

        def unknown_surface():
            raise SemanticGateClosed("campaign startup surface is not reviewed")

        oracle.campaign_is_in_map = unknown_surface
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_event_list_back_uses_exact_typed_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("BACK_ARROW")))
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])

    def test_campaign_event_identity_is_hidden_after_back_commit(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        receipt = adapter.click(NamedButton("BACK_ARROW"))

        self.assertIs(adapter._campaign_context.event_page_back_receipt, receipt)
        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])
        adapter.end_campaign_pre_sortie()

    def test_campaign_event_identity_requires_actionable_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True
        oracle.campaign_preparation_value = None
        oracle.enabled_values["event-list/page/back"] = False
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")

        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))

        oracle.enabled_values["event-list/page/back"] = True
        self.assertTrue(adapter.appear(NamedButton("EVENT_CHECK")))
        adapter.end_campaign_pre_sortie()

    def test_campaign_startup_leaves_daily_page_through_exact_typed_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.daily_page_visible_value = True

        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(receipt.semantic_id, "daily/page/back")
        self.assertEqual(oracle.click_calls, ["daily/page/back"])

    def test_campaign_mode_switch_reports_exact_destination_without_input(self):
        adapter, oracle, _ = self.make_adapter()

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("SWITCH_1_HARD")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_1_NORMAL")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_2_HARD")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_2_EX")))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(oracle.click_calls, [])

    def test_campaign_oil_is_typed_for_global_alas_status_probe(self):
        adapter, _, _ = self.make_adapter()
        self.assertEqual(adapter.campaign_oil(), 9504)

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertEqual(adapter.campaign_oil(), 9504)
        adapter.end_campaign_pre_sortie()

    def test_campaign_stop_condition_observations_are_stage_bound(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        adapter.begin_campaign_pre_sortie("12-4")

        achievement = adapter.campaign_map_achievement_state()
        levels = adapter.campaign_fleet_levels()

        self.assertIs(achievement, oracle.campaign_achievement_value)
        self.assertEqual(levels, (118, 109, 117, 110, 118, 107))
        adapter.end_campaign_pre_sortie()

        with self.assertRaisesRegex(SemanticGateClosed, "outside"):
            adapter.campaign_map_achievement_state()
        with self.assertRaisesRegex(SemanticGateClosed, "outside"):
            adapter.campaign_fleet_levels()

    def test_campaign_auto_search_resources_feed_original_alas_switch(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = True
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)

        for name in (
            "AUTO_SEARCH_ON",
            "AUTO_SEARCH_ON2",
            "AUTO_SEARCH_ON3",
            "AUTO_SEARCH_ON4",
        ):
            self.assertTrue(adapter.appear(NamedButton(name)))
        for name in (
            "AUTO_SEARCH_OFF",
            "AUTO_SEARCH_OFF2",
            "AUTO_SEARCH_OFF3",
            "AUTO_SEARCH_OFF4",
        ):
            self.assertFalse(adapter.appear(NamedButton(name)))

        receipt = adapter.click(NamedButton("AUTO_SEARCH_ON"))
        self.assertEqual(
            receipt.semantic_id, "campaign/map-preparation/auto-search"
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = False
        self.assertTrue(adapter.appear(NamedButton("AUTO_SEARCH_OFF")))
        with self.assertRaisesRegex(SemanticGateClosed, "single-use"):
            adapter.click(NamedButton("AUTO_SEARCH_OFF"))

        self.assertEqual(
            oracle.click_calls,
            ["campaign/stage/12-4", "campaign/map-preparation/auto-search"],
        )

    def test_campaign_auto_search_state_has_single_typed_fast_path(self):
        oracle = FakeOracle()
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(
                SimpleNamespace(
                    stage_code="12-4",
                    button=SimpleNamespace(actionable=True),
                ),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = False
        adapter.begin_campaign_pre_sortie("12-4")
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.click(entrance)

        self.assertFalse(adapter.campaign_auto_search_selected())
        adapter.end_campaign_pre_sortie()

    def test_campaign_pre_sortie_reuses_prepare_and_cancel_states(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_map_preparation_committed())
        adapter.click(entrance)
        self.assertFalse(adapter.campaign_map_preparation_committed())
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation snapshots are not coherent"
        )
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.campaign_preparation_error = None
        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION")))
        with patch.object(
            adapter, "_campaign_preparation_kind", return_value=None
        ):
            adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.campaign_map_preparation_committed())
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation controls are not proven"
        )
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map preparation is transitioning away"
        )
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))
        oracle.campaign_preparation_error = None
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
        self.assertTrue(adapter.appear(NamedButton("FLEET_PREPARATION")))
        with self.assertRaisesRegex(SemanticGateClosed, "authorized budget"):
            adapter.click(NamedButton("FLEET_PREPARATION"))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign fleet preparation is transitioning away"
        )
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))
        oracle.campaign_preparation_error = None
        oracle.campaign_page_value = True
        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        proof = adapter.confirm_campaign_pre_sortie()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "12-4")
        self.assertEqual(proof.preparation_kind, "fleet")
        self.assertEqual(proof.entry_generation, 7)
        self.assertEqual(proof.cancel_generation, 9)
        self.assertEqual(proof.restored_generation, 12)
        self.assertEqual(
            oracle.click_calls,
            [
                "campaign/stage/12-4",
                "campaign/map-preparation/proceed",
                "campaign/fleet-preparation/cancel",
            ],
        )

    def test_campaign_stale_map_preparation_can_be_closed_before_fresh_entry(self):
        oracle = FakeOracle()
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION_CANCEL")))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))

        # Closing an inherited overlay must not consume the normal flow's
        # single cancel proof.  A fresh entry can still complete the original
        # ALAS preparation/cancel sequence in this same task run.
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))

        self.assertEqual(
            oracle.click_calls,
            [
                "campaign/map-preparation/cancel",
                "campaign/stage/12-4",
                "campaign/map-preparation/proceed",
                "campaign/fleet-preparation/cancel",
            ],
        )

    def test_campaign_map_to_fleet_transition_has_bounded_slow_adb_grace(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            adapter.click(entrance)
            adapter.click(NamedButton("MAP_PREPARATION"))

        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation controls are not proven"
        )
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=69.0):
            self.assertFalse(adapter.appear(NamedButton("FLEET_PREPARATION")))
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=71.0):
            with self.assertRaisesRegex(SemanticGateClosed, "controls are not proven"):
                adapter.appear(NamedButton("FLEET_PREPARATION"))

        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_defaults_closed_without_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        authorized = adapter.authorize_campaign_fleet_preparation(1, 2, 0)

        self.assertFalse(authorized)
        self.assertEqual(oracle.click_calls, [])
        with self.assertRaisesRegex(SemanticGateClosed, "remaining mutation"):
            adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preflight_rejects_insufficient_budget_before_input(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=2,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        with self.assertRaisesRegex(SemanticGateClosed, "2 < 3"):
            adapter.authorize_campaign_fleet_preparation(1, 2, 0)

        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preflight_uses_submarine_capacity_not_occupancy(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["fleet2"] = 0
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=2,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")

        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 1))
        receipt = adapter.click(NamedButton("FLEET_2_CLEAR"))
        self.assertEqual(
            receipt.semantic_id,
            "campaign/fleet-preparation/fleet/2/clear",
        )
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_skips_exact_normal_noop(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=1,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("SP")
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        prepared = adapter.confirm_campaign_fleet_selection()

        self.assertEqual(
            tuple(row.selected_fleet or 0 for row in prepared.rows),
            (1, 2, 0),
        )
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_requires_reconciliation_on_mismatch(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=3,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        self.assertTrue(adapter.campaign_fleet_preparation_required())
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_reuses_alas_sequence_and_cancels(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))

        # This is the input sequence emitted by ALAS FleetPreparation for the
        # fake initial state (1, 2, 1). Dropdown open/close remains ALAS-owned;
        # only the exact semantic endpoints replace screenshot coordinates.
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        self.assertTrue(adapter.campaign_fleet_row_allowed("fleet2"))
        self.assertFalse(adapter.campaign_fleet_operator_in_use("fleet2"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        self.assertEqual(adapter.campaign_fleet_selected_indices("fleet1"), [1])
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        prepared = adapter.confirm_campaign_fleet_selection()

        self.assertEqual(
            tuple(row.selected_fleet or 0 for row in prepared.rows),
            (1, 2, 0),
        )
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        oracle.campaign_page_value = True
        proof = adapter.confirm_campaign_fleet_preparation()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.initial_fleets, (1, 2, 1))
        self.assertEqual(proof.requested_fleets, (1, 2, 0))
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertEqual(
            proof.mutation_semantic_ids,
            (
                "campaign/fleet-preparation/fleet/2/clear",
                "campaign/fleet-preparation/submarine/1/clear",
                "campaign/fleet-preparation/option/2",
            ),
        )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)

    def test_campaign_fleet_dropdown_rollback_closes_empty_row_without_mutation(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=3,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))

        adapter.close_campaign_fleet_dropdown_for_rollback()

        self.assertIsNone(oracle.campaign_fleet_dropdown_state())
        self.assertEqual(oracle.campaign_fleets, {
            "fleet1": 1,
            "fleet2": 0,
            "submarine": 0,
        })
        adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_defaults_closed_after_fleet_proof(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        self.assertFalse(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        with self.assertRaisesRegex(SemanticGateClosed, "authorized budget"):
            adapter.click(NamedButton("FLEET_PREPARATION"))
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_reuses_exact_alas_click_and_proves_map_root(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        receipt = adapter.click(NamedButton("FLEET_PREPARATION"))
        self.assertEqual(receipt.semantic_id, "campaign/fleet-preparation/sortie")
        self.assertTrue(adapter.campaign_sortie_committed())
        self.assertTrue(adapter.appear(NamedButton("IN_MAP")))
        proof = adapter.confirm_campaign_sortie()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "12-4")
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertEqual(proof.oil_before_sortie, 9504)
        self.assertEqual(proof.required_oil, 97)
        self.assertGreater(proof.map_generation, proof.sortie_generation)
        self.assertEqual(
            proof.map_root_path, "LevelCamera/Canvas/UIMain/LevelGrid"
        )
        self.assertEqual(oracle.click_calls[-1], "campaign/fleet-preparation/sortie")

    def test_campaign_auto_search_proves_roles_and_passive_start(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
            input_frame_refresher=refresh,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )
        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))

        self.assertTrue(adapter.campaign_auto_search_running())
        proof = adapter.confirm_campaign_auto_search_started()
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertIn("CombatUIStandard", proof.map_root_path)
        self.assertEqual(
            oracle.click_calls[-1], "campaign/fleet-preparation/sortie"
        )

        oracle.enabled_values["reward/campaign-total/exit"] = True
        oracle.campaign_page_value = True
        oracle.campaign_official_combat_auto_state = Mock(
            return_value=(81, True)
        )
        oracle.read_state = Mock(
            return_value=SimpleNamespace(
                generation=82,
                buttons=(
                    SimpleNamespace(
                        name="ButtonExit",
                        path=(
                            "LevelStageTotalRewardPanel(Clone)/Window/Fixed/"
                            "ButtonExit"
                        ),
                        actionable=True,
                    ),
                ),
            )
        )
        refresh_before_result = refresh.call_count

        completion = adapter.wait_campaign_auto_search_completion(
            "12-4", timeout_seconds=60
        )

        self.assertEqual(completion.result_generation, 82)
        self.assertEqual(completion.combat_auto_generation, 81)
        self.assertEqual(
            oracle.click_calls[-1], "reward/campaign-total/exit"
        )
        self.assertEqual(refresh.call_count, refresh_before_result + 1)

    def test_campaign_auto_search_accepts_reversed_mob_boss_roles(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_boss_fleet2_mob"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("boss", "mob"))
        self.assertEqual(
            oracle.click_calls[-2:],
            [
                "campaign/fleet-preparation/roles/fleet1/boss",
                "campaign/fleet-preparation/roles/fleet2/mob",
            ],
        )

    def test_event_campaign_auto_search_uses_same_typed_role_contract(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("a1")
        entrance.semantic_campaign_stage_code = "a1"
        adapter.begin_campaign_pre_sortie("A1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )

    def test_event_hard_stage_uses_reviewed_shared_normal_entrance(self):
        oracle = FakeOracle()
        oracle.campaign_state_value.stages = (
            SimpleNamespace(
                stage_code="a1",
                button=SimpleNamespace(actionable=True),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("c1")
        entrance.semantic_campaign_stage_code = "a1"
        adapter.begin_campaign_pre_sortie("C1")

        self.assertTrue(adapter.appear(entrance))
        receipt = adapter.click(entrance)

        self.assertEqual(receipt.semantic_id, "campaign/stage/a1")
        self.assertEqual(oracle.click_calls[-1], "campaign/stage/a1")

    def test_event_hard_shared_entrance_does_not_hide_map_preparation(self):
        oracle = FakeOracle()
        oracle.event_campaign_page_visible_value = True
        oracle.campaign_state_value.stages = (
            SimpleNamespace(
                stage_code="a1",
                button=SimpleNamespace(actionable=True),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("c1")
        entrance.semantic_campaign_stage_code = "a1"
        adapter.begin_campaign_pre_sortie("C1")
        adapter.click(entrance)

        def preparation_state(stage_code):
            if stage_code == "c1":
                raise SemanticGateClosed("campaign preparation stage identity changed")
            self.assertEqual(stage_code, "a1")
            return SimpleNamespace(kind="map")

        oracle.campaign_preparation_state = Mock(side_effect=preparation_state)

        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION")))

    def test_event_hard_page_prefers_open_target_nodes_over_shared_normal_nodes(self):
        oracle = FakeOracle()
        oracle.campaign_page_value = True
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="a/c",
            stages=(
                SimpleNamespace(stage_code="a2"),
                SimpleNamespace(stage_code="a3"),
                SimpleNamespace(stage_code="c1"),
            ),
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("C1")

        state = adapter.campaign_page_state()

        self.assertEqual(state.chapter_name, "c")
        self.assertEqual([stage.stage_code for stage in state.stages], ["c1"])

    def test_event_sp_stage_code_is_canonical_without_numeric_suffix(self):
        adapter = AlasSemanticAdapter(FakeOracle(), lambda: None)

        adapter.begin_campaign_pre_sortie("SP")

        self.assertEqual(adapter.campaign_pre_sortie_stage_code(), "sp")

    def test_event_sp_uses_exact_interactable_auto_toggle_as_clear_proof(self):
        oracle = FakeOracle()
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        oracle.campaign_map_clear_percentage = Mock(
            side_effect=SemanticGateClosed(
                "campaign achievement progress is absent or ambiguous"
            )
        )
        oracle.toggle_state = Mock(
            return_value=SimpleNamespace(
                active_in_hierarchy=True,
                active_and_enabled=True,
                interactable=True,
                point=Point(50, 50),
                bounds=Bounds(0, 0, 100, 100),
            )
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("SP")

        self.assertEqual(adapter.campaign_map_clear_percentage(), 1.0)

    def test_event_hard_stage_normalizes_mode_and_clears_selected_submarine(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 1
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = True
        oracle.campaign_role_tab_selected = True
        oracle.campaign_roles = ["mob", "boss"]
        oracle.campaign_state_value.stages = (
            SimpleNamespace(
                stage_code="a1",
                button=SimpleNamespace(actionable=True),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("c1")
        entrance.semantic_campaign_stage_code = "a1"
        adapter.begin_campaign_pre_sortie("C1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))

        self.assertEqual(adapter._campaign_context.mode, "hard")
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.prepare_campaign_hard_fleets()
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        prepared = adapter.confirm_campaign_fleet_selection()
        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )

        self.assertEqual(
            tuple(row.selected_fleet or 0 for row in prepared.rows),
            (1, 2, 0),
        )
        self.assertEqual(
            tuple(
                receipt.semantic_id
                for receipt in adapter._campaign_context.fleet_mutation_receipts
            ),
            ("campaign/fleet-preparation/submarine/1/clear",),
        )
        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))

    def test_inherited_event_auto_search_closes_exact_total_reward(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/campaign-total/exit"] = True
        oracle.enabled_values["reward/campaign-total/exit"] = True
        oracle.campaign_page_value = True
        oracle.campaign_in_map_value = True
        oracle.campaign_official_combat_auto_state = Mock(
            return_value=(19, True)
        )
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            input_frame_refresher=refresh,
        )
        adapter.begin_campaign_pre_sortie("A1")

        self.assertTrue(adapter.campaign_inherited_auto_search_visible())
        proof = adapter.recover_inherited_campaign_auto_search(
            "a1",
            "fleet1_mob_fleet2_boss",
            timeout_seconds=60,
        )

        self.assertEqual(proof.stage_code, "a1")
        self.assertEqual((proof.fleet1_role, proof.fleet2_role), ("mob", "boss"))
        self.assertEqual(oracle.click_calls[-1], "reward/campaign-total/exit")
        refresh.assert_called_once_with()

    def test_hard_campaign_9710_uses_game_managed_roles_without_adjustment_click(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_all_fleet2_standby"
        )

        self.assertEqual(
            (roles.fleet1_role, roles.fleet2_role),
            ("game-managed", "game-managed"),
        )
        self.assertFalse(any("adjustment" in call for call in oracle.click_calls))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_all_fleet2_standby",
            )
        )
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_9710_rejects_unobservable_hardfleet_two(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "typed campaign duty tab"):
            adapter.ensure_campaign_auto_search_roles(
                "fleet1_standby_fleet2_all"
            )
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_97328_proves_hardfleet_two_reversed_duties(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_standby_fleet2_all"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("standby", "all"))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_standby_fleet2_all",
            )
        )
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_97328_reads_duty_tab_from_fresh_immutable_frames(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=2,
            campaign_sortie_budget=1,
            frame_observation_oracle=lambda: oracle,
            input_frame_refresher=refresh,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_all_fleet2_standby"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("all", "standby"))
        self.assertIn(
            "campaign/fleet-preparation/roles/tab", oracle.click_calls
        )
        self.assertGreaterEqual(refresh.call_count, 4)
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_97328_waits_for_duty_tab_postcondition(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        original_toggle_selected = oracle.toggle_selected
        probe_count = 0

        def delayed_toggle_selected(semantic_id):
            nonlocal probe_count
            probe_count += 1
            if (
                semantic_id == "campaign/fleet-preparation/roles/tab"
                and probe_count == 2
            ):
                return False
            return original_toggle_selected(semantic_id)

        oracle.toggle_selected = delayed_toggle_selected
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=2,
            campaign_sortie_budget=1,
            frame_observation_oracle=lambda: oracle,
            input_frame_refresher=lambda: None,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_all_fleet2_standby"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("all", "standby"))
        self.assertGreaterEqual(probe_count, 3)
        self.assertEqual(
            oracle.click_calls.count("campaign/fleet-preparation/roles/tab"), 1
        )
        adapter.end_campaign_pre_sortie()

    def test_hard_auto_search_is_qualified_only_for_11_4(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-1")
        entrance.semantic_campaign_stage_code = "11-1"
        adapter.begin_campaign_pre_sortie("11-1", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "only for 11-4"):
            adapter.ensure_campaign_auto_search_roles(
                "fleet1_all_fleet2_standby"
            )
        adapter.end_campaign_pre_sortie()

    def test_hard_11_4_accepts_only_exact_two_fleet_manual_clear_profile(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        adapter.end_campaign_pre_sortie()

        rejected = FakeOracle()
        rejected.campaign_hard_mode = True
        rejected.campaign_fleets["submarine"] = 0
        gated = AlasSemanticAdapter(
            rejected,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        gated.begin_campaign_pre_sortie("11-4", mode="hard")
        gated.click(entrance)
        gated.click(NamedButton("MAP_PREPARATION"))
        gated.authorize_campaign_fleet_preparation(1, 2, 0)
        gated.confirm_campaign_fleet_selection()
        with self.assertRaisesRegex(SemanticGateClosed, "two-fleet 11-4"):
            gated.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_boss_fleet2_mob",
            )
        gated.end_campaign_pre_sortie()

    def test_campaign_ambush_spends_one_campaign_grid_click_lease(self):
        oracle = FakeOracle()
        oracle.campaign_ambush_visible = lambda *, evade: True
        oracle.click_campaign_ambush = lambda *, evade: oracle.click_receipt(
            "campaign/ambush/evade" if evade else "campaign/ambush/fight"
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")

        self.assertTrue(adapter.handle_campaign_ambush(evade=True))
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.grid_click"), 0
        )
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.handle_campaign_ambush(evade=False)
        adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_accepts_typed_single_fleet_profile(self):
        oracle = FakeOracle()
        oracle.campaign_fleets.update(fleet2=0, submarine=0)
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("1-1")
        entrance.semantic_campaign_stage_code = "1-1"
        adapter.begin_campaign_pre_sortie("1-1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 0, 0))
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_all_fleet2_standby",
            )
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))
        proof = adapter.confirm_campaign_sortie()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "1-1")
        self.assertEqual(proof.prepared_fleets, (1, 0, 0))
        self.assertEqual(proof.mutation_semantic_ids, ())
        self.assertEqual(proof.required_oil, 97)

    def test_campaign_sortie_rejects_single_fleet_with_two_fleet_order(self):
        oracle = FakeOracle()
        oracle.campaign_fleets.update(fleet2=0, submarine=0)
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("1-1")
        entrance.semantic_campaign_stage_code = "1-1"
        adapter.begin_campaign_pre_sortie("1-1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 0, 0)
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "fleet order"):
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_preconditions_fail_before_input(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "auto search"):
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()

    def test_campaign_map_model_is_read_only_and_context_bound(self):
        oracle = FakeOracle()
        package_checks = []
        adapter = AlasSemanticAdapter(oracle, lambda: package_checks.append(True))
        adapter.begin_campaign_pre_sortie("12-4")

        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((5, 0), (6, 0)),
            expected_fleet_count=2,
        )

        self.assertIs(state, oracle.campaign_map_state_value)
        self.assertEqual(
            oracle.campaign_map_state_calls,
            [("12-4", 11, 8, ((5, 0), (6, 0)), 2)],
        )
        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(len(package_checks), 2)
        adapter.end_campaign_pre_sortie()

        with self.assertRaisesRegex(SemanticGateClosed, "pre-sortie flow"):
            adapter.campaign_map_state(
                columns=11,
                rows=8,
                land_cells=((5, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_map_reconnect_returns_to_same_logical_map(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        self.assertTrue(adapter.recover_campaign_map_network_reconnect())
        self.assertEqual(
            oracle.click_calls, ["overlay/network-reconnect/confirm"]
        )
        self.assertIs(state, oracle.campaign_map_state_value)
        self.assertEqual(len(oracle.campaign_map_state_calls), 2)

    def test_campaign_map_reconnect_is_noop_when_prompt_is_absent(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        oracle.enabled_values["overlay/network-reconnect/confirm"] = False
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        self.assertFalse(adapter.recover_campaign_map_network_reconnect())
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_combat_defaults_closed_after_alas_decision(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        self.assertIsNone(admission)
        self.assertEqual(oracle.click_calls, [])
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.click(CampaignGridButton((3, 5)))
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_binds_alas_grid_click_and_proves_post_state(self):
        oracle = FakeOracle()
        before = make_campaign_combat_state()
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        self.assertIsNotNone(admission)
        receipt = adapter.click(CampaignGridButton((3, 5)))
        self.assertEqual(receipt.semantic_id, "campaign/map/grid/D6")
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(SemanticGateClosed, "proven post-state"):
            adapter.click(CampaignGridButton((3, 5)))

        oracle.campaign_map_state_value = make_campaign_combat_state(
            generation=55, after=True
        )
        acknowledgement = adapter.click(CampaignGridButton((3, 5)))
        self.assertIs(acknowledgement, receipt)
        proof = adapter.confirm_campaign_combat(battle_count_after=1)
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.target_node, "D6")
        self.assertEqual(proof.enemy_object_id, 104)
        self.assertEqual((proof.ammo_before, proof.ammo_after), (5, 4))
        self.assertEqual((proof.battle_count_before, proof.battle_count_after), (0, 1))
        # ALAS's post-combat arrival acknowledgement is semantic-only; the
        # original target tap remains the sole physical mutation.
        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])

    def test_campaign_combat_budget_can_advance_to_the_next_alas_battle(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        self.assertIsNotNone(
            adapter.authorize_campaign_combat(
                make_campaign_combat_decision(), state
            )
        )
        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = make_campaign_combat_state(
            generation=55, after=True
        )

        proof = adapter.complete_campaign_combat_round(battle_count_after=1)

        self.assertIsNotNone(proof)
        self.assertFalse(adapter.campaign_combat_committed())
        self.assertEqual(adapter._action_ledger.remaining("campaign.grid_click"), 1)
        adapter.end_campaign_pre_sortie()

    def test_campaign_post_combat_refocus_consumes_bounded_cross_axis_swipes(self):
        oracle = FakeOracle()
        before = make_campaign_combat_state()
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = make_campaign_combat_state(
            generation=55, after=True
        )
        adapter.campaign_camera_state()
        self.assertTrue(adapter.campaign_post_combat_arrived((3, 5)))
        with self.assertRaisesRegex(SemanticGateClosed, "destination changed"):
            adapter.campaign_post_combat_arrived((4, 5))

        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.375,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        cross_axis_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 200.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-2",
            distance_check=True,
        )
        cross_axis_proof = adapter.swipe(
            (500, 400),
            (500, 600),
            duration=0.375,
            name="MAP_SWIPE_0_-2",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(cross_axis_intent)

        self.assertEqual(proof.target_node, "D6")
        self.assertEqual(cross_axis_proof.grid_vector, (0, -2))
        self.assertEqual(len(adapter._campaign_context.post_combat_viewport_proofs), 2)
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.viewport_swipe"), 0
        )
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.begin_campaign_map_swipe_vector(
                (200.0, 0.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_executes_alas_waypoint_then_enemy_input(self):
        oracle = FakeOracle()
        base = make_campaign_combat_state()
        nodes = ("D6", "C6", "C5", "C4", "C3", "D3")
        cells = tuple(
            replace(
                base.cells[0],
                row=int(node[1:]),
                column=ord(node[0]) - ord("A") + 1,
                node=node,
                button_path="root/DragLayer/plane/quads/" + node,
                point=Point(100 + index * 80, 200 + index * 20),
                bounds=Bounds(
                    70 + index * 80,
                    170 + index * 20,
                    130 + index * 80,
                    230 + index * 20,
                ),
            )
            for index, node in enumerate(nodes)
        )
        before = replace(
            base,
            cells=cells,
            fleets=(replace(base.fleets[0], node="D6"),),
            enemies=(replace(base.enemies[0], node="D3", fighting=False),),
        )
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        decision = replace(
            make_campaign_combat_decision(),
            origin_node="D6",
            target_node="D3",
            cost=5,
            route_nodes=nodes,
            goto_nodes=("C6", "D3"),
        )
        admission = adapter.authorize_campaign_combat(decision, state)

        self.assertEqual(admission.input_nodes, ("C6", "D3"))
        self.assertEqual(adapter.campaign_camera_target_node(), "C6")
        first = adapter.click(CampaignGridButton((2, 5)))
        self.assertEqual(first.semantic_id, "campaign/map/grid/C6")
        self.assertEqual(oracle.campaign_map_cell_click_calls, [("C6", False)])
        self.assertFalse(adapter.campaign_combat_committed())
        self.assertEqual(adapter.campaign_camera_target_node(), "D3")

        oracle.campaign_map_state_value = replace(
            before,
            generation=54,
            fleets=(replace(before.fleets[0], node="C5"),),
        )
        intermediate_state = adapter.campaign_camera_state()
        self.assertEqual(intermediate_state.fleets[0].node, "C5")

        oracle.campaign_map_state_value = replace(
            before,
            generation=55,
            fleets=(replace(before.fleets[0], node="C6"),),
        )
        waypoint_state = adapter.campaign_camera_state()
        self.assertEqual(waypoint_state.fleets[0].node, "C6")
        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.375,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)
        camera_state = adapter.campaign_camera_state()
        self.assertEqual(camera_state.fleets[0].node, "C6")
        recheck = adapter.recheck_campaign_combat_target_after_camera_view(
            camera_state
        )
        self.assertEqual(recheck.target_node, "D3")
        second = adapter.click(CampaignGridButton((3, 2)))
        self.assertEqual(second.semantic_id, "campaign/map/grid/D3")
        self.assertEqual(
            oracle.campaign_map_cell_click_calls,
            [("C6", False), ("D3", True)],
        )
        self.assertTrue(adapter.campaign_combat_committed())

        oracle.campaign_map_state_value = replace(
            before,
            generation=60,
            fleets=(replace(before.fleets[0], node="D3", ammo=4),),
            enemies=(),
        )
        post_camera = adapter.campaign_camera_state()
        self.assertEqual(post_camera.fleets[0].node, "D3")
        proof = adapter.confirm_campaign_combat(battle_count_after=1)
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.target_node, "D3")
        self.assertEqual(
            oracle.click_calls,
            ["campaign/map/grid/C6", "campaign/map/grid/D3"],
        )

    def test_campaign_combat_route_ignores_only_fleet_enumeration_order(self):
        oracle = FakeOracle()
        base = make_campaign_combat_state()
        nodes = ("D6", "C6", "C5", "C4", "C3", "D3")
        cells = tuple(
            replace(
                base.cells[0],
                row=int(node[1:]),
                column=ord(node[0]) - ord("A") + 1,
                node=node,
                button_path="root/DragLayer/plane/quads/" + node,
            )
            for node in nodes
        )
        selected = replace(base.fleets[0], node="D6")
        support = replace(
            base.fleets[0],
            marker="cell_fleet_support",
            node="A1",
        )
        before = replace(
            base,
            cells=cells,
            fleets=(selected, support),
            enemies=(replace(base.enemies[0], node="D3", fighting=False),),
        )
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=2,
        )
        decision = replace(
            make_campaign_combat_decision(),
            origin_node="D6",
            target_node="D3",
            cost=5,
            route_nodes=nodes,
            goto_nodes=("C6", "D3"),
        )
        adapter.authorize_campaign_combat(decision, state)
        adapter.click(CampaignGridButton((2, 5)))

        oracle.campaign_map_state_value = replace(
            before,
            generation=55,
            fleets=(support, replace(selected, node="C6")),
        )

        camera_state = adapter.campaign_camera_state()
        self.assertEqual(
            next(
                fleet.node
                for fleet in camera_state.fleets
                if fleet.marker == selected.marker
            ),
            "C6",
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_admits_alas_boss_over_a_long_orthogonal_route(self):
        oracle = FakeOracle()
        base = make_campaign_combat_state()
        nodes = ("D6", "E6", "F6", "G6", "H6")
        cells = tuple(
            replace(
                base.cells[0],
                column=index + 4,
                node=node,
                button_path="root/DragLayer/plane/quads/" + node,
            )
            for index, node in enumerate(nodes)
        )
        state = replace(
            base,
            cells=cells,
            enemies=(
                replace(
                    base.enemies[0],
                    column=8,
                    node="H6",
                    genre="Boss",
                    fighting=False,
                ),
            ),
        )
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        decision = replace(
            make_campaign_combat_decision(),
            target_node="H6",
            expected="combat_boss",
            cost=4,
            route_nodes=nodes,
            goto_nodes=("H6",),
        )

        admission = adapter.authorize_campaign_combat(decision, current)

        self.assertIsNotNone(admission)
        self.assertEqual(admission.target_node, "H6")
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_is_one_use_and_updates_exact_grid_geometry(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        self.assertIsNotNone(admission)

        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.157,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        self.assertTrue(adapter.campaign_map_viewport_swipe_committed())
        self.assertEqual(proof.target_before_point, Point(640, 360))
        self.assertEqual(proof.target_after_point, Point(840, 360))
        camera_state = adapter.campaign_camera_state()
        recheck = adapter.recheck_campaign_combat_target_after_camera_view(
            camera_state
        )
        self.assertEqual(recheck.target_node, "D6")
        self.assertEqual(recheck.camera_state_generation, 53)
        with self.assertRaisesRegex(SemanticGateClosed, "token changed"):
            adapter.recheck_campaign_combat_target_after_camera_view(
                replace(camera_state, generation=54)
            )
        receipt = adapter.click(CampaignGridButton((3, 5)))
        self.assertEqual(receipt.point, Point(840, 360))
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.begin_campaign_map_swipe_vector(
                (200.0, 0.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_rebases_exact_partial_hard_route(self):
        oracle = FakeOracle()
        cells = tuple(
            CampaignMapCellState(
                row=6,
                column=column,
                node=node,
                button_path=(
                    "root/DragLayer/plane/quads/chapter_cell_quad_6_" + str(column)
                ),
                point=Point(400 + column * 80, 360),
                bounds=Bounds(360 + column * 80, 320, 440 + column * 80, 400),
            )
            for column, node in ((3, "C6"), (4, "D6"), (5, "E6"))
        )
        enemy = CampaignMapEnemyState(
            row=6,
            column=5,
            node="E6",
            object_id=104,
            sprite="zl2",
            scale=2,
            genre="Main",
            level=114,
            fighting=False,
        )
        initial = CampaignMapState(
            generation=51,
            stage_code="12-4",
            rows=8,
            columns=11,
            cells=cells,
            land_nodes=("A1",),
            fleets=(CampaignMapFleetState("cell_fleet", "C6", 5, 5),),
            enemies=(enemy,),
            pickups=(),
            displayed_fleet_index=1,
            current_fleet_marker="cell_fleet",
            current_fleet_roster_sprites=("ship",),
        )
        decision = AlasCampaignDecisionPreview(
            generation=51,
            stage_code="12-4",
            battle_count=0,
            branch_name="battle_0",
            fleet_index=1,
            fleet_marker="cell_fleet",
            origin_node="C6",
            target_node="E6",
            target_kind="enemy",
            expected="combat",
            cost=2,
            weight=50.0,
            route_nodes=("C6", "D6", "E6"),
            goto_nodes=("E6",),
            step_optimize=False,
            turning_optimize=True,
        )
        oracle.campaign_map_state_value = initial
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
            campaign_viewport_swipe_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(decision, state)
        adapter.click(CampaignGridButton((4, 5)))
        oracle.campaign_map_state_value = replace(
            initial,
            generation=53,
            fleets=(CampaignMapFleetState("cell_fleet", "D6", 5, 5),),
        )
        adapter.campaign_camera_state()

        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )

        self.assertEqual(adapter._campaign_context.combat_admission.origin_node, "D6")
        self.assertEqual(
            adapter._campaign_context.combat_admission.route_nodes,
            ("D6", "E6"),
        )
        self.assertIsNone(adapter._campaign_context.combat_receipt)
        adapter.end_campaign_map_swipe_vector(intent)
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_rejects_timing_between_direct_and_adb(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "duration changed"):
            adapter.swipe(
                (500, 400),
                (700, 400),
                duration=0.225,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )

        adapter.end_campaign_map_swipe_vector(intent)
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_defaults_closed_and_raw_swipe_stays_rejected(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        oracle.campaign_map_target_raycast_top = False
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "viewport swipe budget"):
            adapter.authorize_campaign_combat(
                make_campaign_combat_decision(), state
            )
        with self.assertRaisesRegex(SemanticGateClosed, "raw ALAS input"):
            adapter.swipe(
                (500, 400),
                (700, 400),
                duration=0.375,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_accepts_alas_whitelist_fallback_only_in_padded_domain(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        intent = adapter.begin_campaign_map_swipe_vector(
            (14.0, -201.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=((900, 600, 1000, 650),),
            blacklist_area=None,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )
        proof = adapter.swipe(
            (772, 482),
            (786, 281),
            duration=0.3375,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        self.assertEqual(proof.end, (786, 281))
        self.assertEqual(len(oracle.campaign_map_swipe_calls), 1)
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_rejects_endpoint_outside_alas_padded_domain(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        intent = adapter.begin_campaign_map_swipe_vector(
            (14.0, -201.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "selection domain"):
            adapter.swipe(
                (126, 482),
                (140, 281),
                duration=0.3375,
                name="MAP_SWIPE_0_2",
                distance_check=True,
            )
        adapter.end_campaign_map_swipe_vector(intent)
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_camera_positioning_is_separate_one_use_empty_cell_contract(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        empty = CampaignMapCellState(
            row=3,
            column=6,
            node="F3",
            button_path="root/DragLayer/plane/quads/chapter_cell_quad_3_6",
            point=Point(640, 80),
            bounds=Bounds(600, 40, 680, 120),
        )
        state = replace(state, cells=state.cells + (empty,))
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_camera_positioning_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        admission = adapter.authorize_campaign_camera_positioning(
            "F3", current
        )
        self.assertEqual(admission.target_node, "F3")
        intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 200.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 300),
            (500, 500),
            duration=0.35,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)
        positioned_state = adapter.campaign_camera_state()
        completed = adapter.complete_campaign_camera_positioning(
            positioned_state
        )

        self.assertEqual(proof.target_node, "F3")
        self.assertEqual(completed, (proof,))
        self.assertTrue(adapter.campaign_camera_positioning_committed())
        self.assertIs(adapter.campaign_camera_positioning_proof(), proof)
        with self.assertRaisesRegex(SemanticGateClosed, "not proven"):
            adapter.campaign_map_viewport_swipe_proof()
        with self.assertRaisesRegex(SemanticGateClosed, "budget unit"):
            adapter.authorize_campaign_camera_positioning("F3", current)
        adapter.end_campaign_pre_sortie()

    def test_campaign_camera_positioning_rejects_enemy_or_default_zero_budget(self):
        state = make_campaign_combat_state()
        for budget, message in ((0, "budget"), (1, "empty sea cell")):
            oracle = FakeOracle()
            oracle.campaign_map_state_value = state
            adapter = AlasSemanticAdapter(
                oracle,
                lambda: None,
                campaign_camera_positioning_budget=budget,
            )
            adapter.begin_campaign_pre_sortie("12-4")
            current = adapter.campaign_map_state(
                columns=11,
                rows=8,
                land_cells=((0, 0),),
                expected_fleet_count=1,
            )
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.authorize_campaign_camera_positioning(
                        "D6", current
                    )
            adapter.end_campaign_pre_sortie()
        with self.assertRaisesRegex(ValueError, "at most two"):
            AlasSemanticAdapter(
                FakeOracle(),
                lambda: None,
                campaign_camera_positioning_budget=3,
            )
        with self.assertRaisesRegex(ValueError, "at most two"):
            AlasSemanticSession(
                "emulator-test",
                "be80ce591a481c12d60c50d6040d40c035b40a2b",
                campaign_camera_positioning_budget=3,
            )

    def test_campaign_camera_positioning_allows_two_original_focus_corrections_then_closes(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        empty = CampaignMapCellState(
            row=3,
            column=6,
            node="F3",
            button_path="root/DragLayer/plane/quads/chapter_cell_quad_3_6",
            point=Point(640, 80),
            bounds=Bounds(600, 40, 680, 120),
        )
        oracle.campaign_map_state_value = replace(
            state, cells=state.cells + (empty,)
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_camera_positioning_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_camera_positioning("F3", current)

        first_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 260.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        first = adapter.swipe(
            (500, 250),
            (500, 510),
            duration=0.35,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(first_intent)
        second_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 80.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-1",
            distance_check=True,
        )
        second = adapter.swipe(
            (500, 370),
            (500, 450),
            duration=0.35,
            name="MAP_SWIPE_0_-1",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(second_intent)
        positioned_state = adapter.campaign_camera_state()

        completed = adapter.complete_campaign_camera_positioning(
            positioned_state
        )

        self.assertEqual(completed, (first, second))
        self.assertEqual(
            adapter.campaign_camera_positioning_proofs(),
            (first, second),
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.begin_campaign_map_swipe_vector(
                (0.0, 80.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_0_-1",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_rejects_route_drift_before_input(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        decision = replace(
            make_campaign_combat_decision(),
            cost=1,
            route_nodes=("D6", "D5"),
        )

        with self.assertRaisesRegex(SemanticGateClosed, "exact orthogonal route"):
            adapter.authorize_campaign_combat(decision, current)

        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_rejects_failed_postcondition_without_replay(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), current
        )
        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = replace(state, generation=55)

        with self.assertRaisesRegex(SemanticGateClosed, "enemy still exists"):
            adapter.confirm_campaign_combat(battle_count_after=1)

        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_anomalous_receipt_cannot_replay_input(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), current
        )
        exact_click = oracle.click_campaign_map_cell

        def anomalous_click(
            map_state, node, *, allow_expected_enemy_coverage=False
        ):
            return replace(
                exact_click(
                    map_state,
                    node,
                    allow_expected_enemy_coverage=allow_expected_enemy_coverage,
                ),
                path="wrong/path",
            )

        oracle.click_campaign_map_cell = anomalous_click
        with self.assertRaisesRegex(SemanticGateClosed, "receipt changed"):
            adapter.click(CampaignGridButton((3, 5)))
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.click(CampaignGridButton((3, 5)))

        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])
        adapter.end_campaign_pre_sortie()

    def test_goto_main_from_mission_uses_exact_task_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.enabled_values["task/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "task/page/back")
        self.assertEqual(oracle.click_calls, ["task/page/back"])

    def test_research_menu_entries_use_exact_typed_buttons(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(
            adapter.semantic_id_for("RESHMENU_GOTO_RESEARCH"),
            "research-menu/research",
        )
        self.assertEqual(
            adapter.semantic_id_for("RESHMENU_GOTO_SHIPYARD"),
            "research-menu/shipyard",
        )
        self.assertEqual(
            adapter.semantic_id_for("ENTRANCE_3"), "research/project/3"
        )

    def test_research_ocr_companions_use_typed_project_model(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_project_values = [
            SimpleNamespace(
                slot=1,
                series=9,
                status=ResearchProjectStatus.DETAIL,
            ),
            SimpleNamespace(
                slot=2,
                series=8,
                status=ResearchProjectStatus.RUNNING,
            ),
        ]

        self.assertEqual(adapter.research_series(), [9, 8])
        self.assertEqual(adapter.research_statuses(), ["detail", "running"])
        self.assertIsNone(adapter.research_finished_index())

    def test_tactical_countdown_and_safe_continue_cancel_use_typed_state(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_tactical_rewards=True,
        )
        oracle.tactical_slot_values = [SimpleNamespace(slot=1)]
        oracle.tactical_remaining_values = (3723, 90)
        oracle.tactical_prompt_text = "「舰船」学习完成，「技能」技能获得450点经验是否继续学习该技能？"
        adapter.begin_tactical()

        self.assertEqual(len(adapter.tactical_slots()), 1)
        self.assertEqual(adapter.tactical_remaining_seconds(), (3723, 90))
        self.assertTrue(adapter.cancel_tactical_continue_if_present())
        self.assertFalse(adapter.cancel_tactical_continue_if_present())
        self.assertEqual(oracle.click_calls, ["tactical/continue/cancel"])
        adapter.end_commission()

    def test_tactical_continue_cancel_accepts_the_consumed_reward_receipt(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_tactical_rewards=True,
        )
        oracle.tactical_prompt_text = (
            "「舰船」学习完成，「技能」技能获得450点经验是否继续学习该技能？"
        )
        adapter.begin_tactical()
        reward_receipt = adapter._dispatch_mutation(
            "tactical.reward",
            lambda: oracle.click_receipt("reward/tactical/finish"),
        )
        adapter._commission_context.tactical_reward_receipt = reward_receipt

        self.assertEqual(adapter._action_ledger.remaining("tactical.reward"), 0)
        self.assertTrue(adapter.cancel_tactical_continue_if_present())
        self.assertEqual(oracle.click_calls, ["tactical/continue/cancel"])
        adapter.end_commission()

    def test_tactical_passive_continue_probe_is_false_without_prompt_or_opt_in(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_tactical()

        self.assertFalse(adapter.cancel_tactical_continue_if_present())

        oracle.tactical_prompt_text = "舰船学习完成，是否继续学习该技能？"
        with self.assertRaises(SemanticGateClosed):
            adapter.cancel_tactical_continue_if_present()

    def test_mail_page_identity_and_manage_use_exact_semantic_targets(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(adapter.semantic_id_for("MAIL_CHECK"), "mail/page/back")
        self.assertEqual(adapter.semantic_id_for("MAIL_MANAGE"), "mail/manage")

    def test_daily_page_makes_mail_escape_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.daily_page_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("GOTO_MAIN_WHITE")))
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_daily_check_distinguishes_overview_from_stage_detail(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.daily_page_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("DAILY_CHECK")))

        oracle.daily_detail_visible_value = True
        self.assertFalse(adapter.appear(NamedButton("DAILY_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DAILY_ENTER_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("BACK_ARROW")))

    def test_daily_expanded_stage_exposes_exact_run_choices(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._daily_kind = "fierce_assault"
        adapter._daily_stage = 1
        oracle.daily_page_visible_value = True
        oracle.daily_detail_visible_value = True
        oracle.daily_selected_stage_visible_value = True
        oracle.daily_run_choices = {"normal", "skip"}

        self.assertFalse(adapter.appear(NamedButton("DAILY_ENTER_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DAILY_NORMAL_RUN")))
        self.assertTrue(adapter.appear(NamedButton("DAILY_SKIP")))

    def test_campaign_menu_makes_exercise_page_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_daily_stage_transition_makes_in_map_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._daily_transition_until = time.monotonic() + 1.0
        oracle.campaign_page_error = SemanticGateClosed("not a campaign page")

        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))

    def test_mail_context_reuses_alas_state_machine_and_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["main/mail"] = True
        oracle.enabled_values["mail/page/back"] = True
        oracle.enabled_values["mail/manage/back"] = False
        oracle.enabled_values["mail/manage/claim"] = False
        oracle.enabled_values["mail/manage/delete"] = False
        adapter.begin_mail()

        adapter.click(NamedButton("MAIL_ENTER"))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN_WHITE")))
        self.assertFalse(adapter.appear(NamedButton("MAIL_BATCH_CLAIM")))
        self.assertFalse(adapter.appear(NamedButton("UNRELATED_MAIL_POPUP")))
        receipt = adapter.click(NamedButton("GOTO_MAIN_WHITE"))

        self.assertEqual(receipt.semantic_id, "mail/page/back")
        self.assertEqual(oracle.click_calls, ["main/mail", "mail/page/back"])
        self.assertFalse(adapter.appear(NamedButton("MAIL_CHECK")))
        oracle.main_page_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))
        adapter.end_mail()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("MAIL_BATCH_CLAIM"))

    def test_mail_reward_popup_uses_reviewed_award_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_mail()

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_2")))
        receipt = adapter.click(NamedButton("GET_ITEMS_2"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")

    def test_mail_claim_alias_closes_award_popup_without_spending_mutation_grant(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "reward/award-info/close": True,
                "reward/award-info1/close": False,
                "mail/manage/claim": False,
            }
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()

        receipt = adapter.click(NamedButton("MAIL_BATCH_CLAIM"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(adapter._action_ledger.remaining("mail.mutation"), 1)
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_mail_manager_close_and_filters_use_typed_controls(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.enabled_values["mail/manage/back"] = True
        oracle.mail_surface_kind_value = "manager"
        oracle.toggle_selected_values["mail/manage/merit"] = True

        self.assertTrue(
            adapter.image_color_count(
                NamedButton("MAIL_SELECT_MERIT"),
                color=(57, 56, 57),
                threshold=221,
                count=50,
            )
        )
        toggle = adapter.click(NamedButton("MAIL_SELECT_OIL"))
        close = adapter.click(NamedButton("MAIL_MANAGE"))

        self.assertEqual(toggle.semantic_id, "mail/manage/oil")
        self.assertEqual(close.semantic_id, "mail/manage/back")

    def test_mail_manager_overlay_preserves_page_identity_and_home_route(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.exists_values["mail/page/back"] = True
        oracle.enabled_values["mail/manage/back"] = True
        oracle.enabled_values["mail/page/back"] = False

        self.assertTrue(adapter.appear(NamedButton("MAIL_CHECK")))
        self.assertTrue(adapter._mail_context.recovered_existing_page)
        self.assertTrue(adapter.appear(NamedButton("MAIL_MANAGE")))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN_WHITE")))
        receipt = adapter.click(NamedButton("GOTO_MAIN_WHITE"))

        self.assertEqual(receipt.semantic_id, "mail/manage/back")
        self.assertEqual(oracle.click_calls, ["mail/manage/back"])

    def test_proven_mail_surface_short_circuits_unrelated_mapped_pages(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        adapter._mail_context.recovered_existing_page = True
        oracle.exists_values["mail/page/back"] = True
        oracle.enabled_values["mail/manage/back"] = True

        self.assertFalse(adapter.appear(NamedButton("MISSION_CHECK")))
        self.assertNotIn("task/page/back", oracle.enabled_calls)
        self.assertTrue(adapter.appear(NamedButton("MAIL_CHECK")))

    def test_mail_return_accepts_main_only_after_complete_page_identity(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.exists_values["main/battle"] = True
        oracle.enabled_values["mail/manage/back"] = False
        oracle.enabled_values["mail/page/back"] = False

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))

        oracle.main_page_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))

    def test_mail_flow_begins_with_read_only_page_discovery_grace(self):
        adapter, _, _ = self.make_adapter()
        adapter.begin_mail()

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_mail_startup_discovers_manager_before_generic_page_enumeration(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["mail/manage/back"] = True
        adapter.begin_mail()

        self.assertFalse(adapter.appear(NamedButton("MISSION_CHECK")))
        self.assertTrue(adapter._mail_context.initial_surface_probed)
        self.assertTrue(adapter._mail_context.recovered_existing_page)
        self.assertNotIn("task/page/back", oracle.enabled_calls)

    def test_mail_mutations_require_separate_opt_in(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.enabled_values["mail/manage/claim"] = True

        self.assertTrue(adapter.appear(NamedButton("MAIL_BATCH_CLAIM")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MAIL_BATCH_CLAIM"))

        opted_in = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        opted_in.begin_mail()
        receipt = opted_in.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertEqual(receipt.semantic_id, "mail/manage/claim")

    def test_mail_confirmation_routes_before_generic_network_popup_mapping(self):
        oracle = FakeOracle()
        oracle.enabled_values["mail/manage/claim"] = True
        oracle.mail_confirmation_kind_value = "claim"
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()

        adapter.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM_UI_ADDITIONAL")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_UI_ADDITIONAL"))

        self.assertEqual(receipt.semantic_id, "mail/confirm/claim")
        self.assertEqual(
            oracle.click_calls,
            ["mail/manage/claim", "mail/confirm/claim"],
        )
        self.assertIsNone(adapter._mail_context.pending_confirmation)

    def test_recovered_mail_confirmation_consumes_opt_in_at_confirm(self):
        oracle = FakeOracle()
        oracle.mail_confirmation_kind_value = "claim"
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_MAIL_CLAIM"))

        self.assertEqual(receipt.semantic_id, "mail/confirm/claim")
        self.assertEqual(oracle.click_calls, ["mail/confirm/claim"])
        self.assertFalse(adapter._action_ledger.allowed("mail.mutation"))

    def test_mail_empty_requires_mounted_page_and_never_uses_button_absence(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()

        oracle.mail_empty = True

        def fail_if_read_before_mail_page():
            raise AssertionError("empty-mail reader must not run before MailUI mounts")

        oracle.mail_is_empty = fail_if_read_before_mail_page
        self.assertFalse(adapter.appear(NamedButton("MAIL_WHITE_EMPTY")))

        oracle.mail_is_empty = lambda: oracle.mail_empty
        oracle.exists_values["mail/page/back"] = True
        oracle.mail_empty = True
        self.assertTrue(adapter.appear(NamedButton("MAIL_WHITE_EMPTY")))

    def test_commission_reward_and_navigation_are_distinct_alas_inputs(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()

        self.assertEqual(
            adapter.semantic_id_for("REWARD_1"), "reward/commission/finish"
        )
        self.assertEqual(
            adapter.semantic_id_for("REWARD_GOTO_COMMISSION"),
            "reward/commission/go",
        )
        self.assertEqual(
            adapter.semantic_id_for("AUTO_SEARCH_MENU_EXIT"),
            "reward/campaign-total/exit",
        )
        self.assertTrue(adapter.appear(NamedButton("REWARD_1")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("REWARD_1"))
        self.assertEqual(oracle.click_calls, [])

    def test_commission_reward_chain_uses_one_budget_and_typed_counter_proof(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values = {
            "reward/commission/finish": True,
            "reward/ship-exp/close": True,
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
            "commission/page/back": True,
        }
        oracle.reward_summary_values = [1, 1, 0]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        claim = adapter.click(NamedButton("REWARD_1"))
        duplicate = adapter.click(NamedButton("REWARD_1_WHITE"))
        self.assertTrue(adapter.appear(NamedButton("EXP_INFO_S_REWARD")))
        exp = adapter.click(NamedButton("REWARD_SAVE_CLICK"))
        exp_duplicate = adapter.click(NamedButton("EXP_INFO_S_REWARD"))
        award = adapter.click(NamedButton("GET_ITEMS_3"))
        award_duplicate = adapter.click(NamedButton("GET_ITEMS_1"))
        oracle.enabled_values["reward/award-info/close"] = False
        award_after_disappear = adapter.click(NamedButton("GET_ITEMS_2"))
        proof = adapter.confirm_commission_reward()

        self.assertEqual(claim, duplicate)
        self.assertEqual(exp.semantic_id, exp_duplicate.semantic_id)
        self.assertEqual(award.semantic_id, award_duplicate.semantic_id)
        self.assertEqual(award, award_after_disappear)
        self.assertEqual(exp.semantic_id, "reward/ship-exp/close")
        self.assertEqual(award.semantic_id, "reward/award-info/close")
        self.assertEqual(proof.before_finished_count, 1)
        self.assertEqual(proof.after_finished_count, 0)
        self.assertEqual(
            proof.close_semantic_ids,
            (
                "reward/ship-exp/close",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "reward/award-info/close",
            ),
        )
        self.assertEqual(
            oracle.click_calls,
            [
                "reward/commission/finish",
                "reward/ship-exp/close",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "reward/award-info/close",
                "commission/page/back",
            ],
        )

    def test_commission_reward_claims_multiple_finished_rows_with_one_input(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values["reward/commission/finish"] = True
        oracle.reward_summary_values = [2, 2, 0]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        adapter.click(NamedButton("REWARD_1"))
        adapter._commission_context.reward_close_receipts.append(
            SimpleNamespace(semantic_id="reward/award-info/close")
        )
        proof = adapter.confirm_commission_reward()
        self.assertEqual(proof.before_finished_count, 2)
        self.assertEqual(proof.after_finished_count, 0)
        self.assertEqual(
            oracle.click_calls,
            ["reward/commission/finish", "commission/page/back"],
        )

    def test_commission_reward_revalidates_larger_count_before_input(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values["reward/commission/finish"] = True
        oracle.reward_summary_values = [1, 2]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()

        self.assertTrue(adapter.commission_reward_pending())
        self.assertTrue(adapter.commission_reward_allowed())
        receipt = adapter.click(NamedButton("REWARD_1"))

        self.assertEqual(receipt.semantic_id, "reward/commission/finish")
        self.assertEqual(adapter._commission_context.reward_detected_count, 2)
        self.assertEqual(oracle.click_calls, ["reward/commission/finish"])

    def test_unknown_commission_presence_is_false_only_on_proven_surface(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("OIL_MAXED")))
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))

        oracle.exists_values.clear()
        adapter._commission_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("OIL_MAXED"))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("GUILD_POPUP_CONFIRM"))

    def test_commission_page_transition_has_bounded_passive_probe_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_commission()
        adapter.click(NamedButton("REWARD_GOTO_COMMISSION"))

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

        adapter._commission_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))

    def test_commission_scroll_delegates_only_inside_commission_context(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaises(SemanticGateClosed):
            adapter.commission_scroll_state()

        adapter.begin_commission()
        state = adapter.commission_scroll_state()
        next_proof = adapter.commission_scroll_next()
        top_proof = adapter.commission_scroll_to_top()

        self.assertTrue(state.scrollable)
        self.assertEqual(next_proof.direction, "next")
        self.assertEqual(top_proof.direction, "top")
        self.assertEqual(
            oracle.commission_scroll_calls,
            ["state", "next", "top"],
        )

    def test_commission_start_uses_exact_row_and_independent_one_input_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature

        adapter.click(row)
        self.assertTrue(adapter.appear(NamedButton("COMMISSION_ADVICE")))
        adapter.click(NamedButton("COMMISSION_ADVICE"))
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=0,
        )
        self.assertTrue(adapter.appear(NamedButton("COMMISSION_START")))
        first = adapter.click(NamedButton("COMMISSION_START"))
        duplicate = adapter.click(NamedButton("COMMISSION_START"))

        self.assertEqual(first, duplicate)
        self.assertFalse(adapter.commission_start_allowed())
        self.assertEqual(
            oracle.click_calls,
            [
                "commission/row/1",
                "commission/detail/recommend",
                "commission/detail/start",
            ],
        )

    def test_commission_start_accepts_nonzero_oil_with_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=10,
        )

        self.assertTrue(adapter.appear(NamedButton("COMMISSION_START")))
        adapter.click(NamedButton("COMMISSION_START"))
        self.assertEqual(
            oracle.click_calls,
            ["commission/row/1", "commission/detail/start"],
        )

    def test_commission_nonzero_oil_prompt_confirms_exact_recorded_cost(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=1200,
        )
        adapter.click(NamedButton("COMMISSION_START"))
        oracle.commission_start_prompt_cost_value = 1200

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(receipt.semantic_id, "commission/start/confirm")
        self.assertEqual(oracle.click_calls[-1], "commission/start/confirm")

    def test_commission_start_proof_precedes_exact_detail_close(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        signature = (
            1,
            "日常资源开发III",
            15,
            3600,
            "pending",
            "faxiankuangmai",
        )
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = signature
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=0,
        )
        adapter.click(NamedButton("COMMISSION_START"))

        proof = adapter.commission_start_proof()
        receipt = adapter.close_started_commission_detail()

        self.assertEqual(proof.after_status_sprite, "tag_ongoing")
        self.assertEqual(
            oracle.last_commission_transition_signature,
            signature,
        )
        self.assertEqual(receipt.semantic_id, "commission/detail/back")
        self.assertEqual(
            oracle.wait_calls[-1],
            ("reward/page/back", 12.0, receipt.generation),
        )

    def test_commission_start_defaults_closed(self):
        adapter, _, _ = self.make_adapter()
        adapter.begin_commission()
        self.assertFalse(adapter.commission_start_allowed())

    def test_unmapped_resource_fails_before_identity_or_input(self):
        adapter, oracle, gate_calls = self.make_adapter()

        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_entry_transition_makes_page_probes_passive(self):
        adapter, oracle, gate_calls = self.make_adapter()
        adapter._operation_siren_entry_transition_until = time.monotonic() + 1.0

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertEqual(gate_calls, [])

        adapter._operation_siren_entry_transition_until = 0.0
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 1.0
        )
        self.assertFalse(adapter.appear(NamedButton("RETIRE_APPEAR_1")))
        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_startup_recovery_owns_reward_and_clears_on_map(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }

        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        self.assertFalse(adapter.appear(NamedButton("IN_RETIREMENT_CHECK")))
        self.assertTrue(adapter._operation_siren_auto_search_active)
        self.assertGreater(
            adapter._operation_siren_entry_transition_until,
            time.monotonic(),
        )

        oracle.operation_siren_local_map_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("OS_CHECK")))
        self.assertEqual(adapter._operation_siren_entry_transition_until, 0.0)
        oracle.operation_siren_auto_search_state = Mock(return_value="off")
        self.assertEqual(adapter.operation_siren_auto_search_state(), "off")
        self.assertFalse(adapter.operation_siren_auto_search_completed_empty())
        self.assertEqual(gate_calls, [True, True, True, True])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_reward_popup_closes_without_mission_owner(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_operation_siren_page_remount_keeps_exact_reward_owner(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        oracle.operation_siren_local_map_visible_value = True

        adapter.begin_operation_siren_page_remount(timeout_seconds=60.0)
        self.assertTrue(adapter.appear(NamedButton("OS_CHECK")))
        self.assertGreater(
            adapter._operation_siren_page_remount_until,
            time.monotonic(),
        )
        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))
        adapter.end_operation_siren_page_remount()

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(adapter._operation_siren_page_remount_until, 0.0)

    def test_operation_siren_page_remount_timeout_is_bounded(self):
        adapter, _, _ = self.make_adapter()

        for value in (True, 0, -1, 601, float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    adapter.begin_operation_siren_page_remount(value)

    def test_operation_siren_startup_recovery_recognizes_campaign_menu(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.campaign_menu_value = True

        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertEqual(gate_calls, [True])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_startup_recovery_keeps_global_guild_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/guild-message/close"] = True
        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))
        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(oracle.click_calls, ["overlay/guild-message/close"])

    def test_operation_siren_campaign_entry_commit_is_idempotent(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_os_entrance_available = Mock(return_value=True)
        receipt = oracle.click_receipt("campaign-menu/os")
        oracle.click_campaign_os_entrance = Mock(return_value=receipt)

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_GOTO_OS")))
        first = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_OS"))
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_MENU_GOTO_OS")))
        duplicate = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_OS"))

        self.assertEqual(first, receipt)
        self.assertEqual(duplicate, receipt)
        oracle.click_campaign_os_entrance.assert_called_once_with()

    def test_operation_siren_globe_navigation_owns_loading_gap(self):
        adapter, oracle, _ = self.make_adapter()
        receipt = oracle.click_receipt("os/map/globe")
        oracle.click_operation_siren_globe = Mock(return_value=receipt)

        self.assertEqual(adapter.click(NamedButton("MAP_GOTO_GLOBE")), receipt)
        self.assertFalse(adapter.appear(NamedButton("GET_MISSION")))

        oracle.operation_siren_globe_visible = Mock(return_value=True)
        self.assertTrue(adapter.operation_siren_globe_visible())
        self.assertEqual(adapter._operation_siren_entry_transition_until, 0.0)

    def test_operation_siren_globe_return_commit_is_idempotent(self):
        adapter, oracle, _ = self.make_adapter()
        receipt = oracle.click_receipt("os/globe/map")
        oracle.click_operation_siren_globe_map = Mock(return_value=receipt)

        first = adapter.click(NamedButton("GLOBE_GOTO_MAP"))
        self.assertFalse(adapter.appear(NamedButton("GLOBE_GOTO_MAP")))
        duplicate = adapter.click(NamedButton("GLOBE_GOTO_MAP"))

        self.assertEqual(first, receipt)
        self.assertEqual(duplicate, receipt)
        oracle.click_operation_siren_globe_map.assert_called_once_with()

    def test_operation_siren_startup_recovery_timeout_is_bounded(self):
        adapter, _, _ = self.make_adapter()

        for value in (True, 0, -1, 601, float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    adapter.begin_operation_siren_startup_recovery(value)

    def test_operation_siren_map_rejects_passive_pixel_probes_before_build_scan(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_local_map_visible_value = True
        oracle.build_queue_timers = Mock(
            side_effect=AssertionError("construction probe must not run")
        )

        self.assertFalse(adapter.appear(NamedButton("WITHDRAW")))
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertEqual(gate_calls, [])

    def test_operation_siren_auto_search_commit_owns_loading_transition(self):
        adapter, oracle, gate_calls = self.make_adapter()
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 30.0
        )
        oracle.operation_siren_auto_search_state = Mock(
            side_effect=AssertionError("loading surface must not be queried")
        )

        self.assertEqual(adapter.operation_siren_auto_search_state(), "on")
        self.assertTrue(adapter.operation_siren_auto_search_transition_active())
        self.assertEqual(gate_calls, [True, True])

    def test_operation_siren_auto_search_records_natural_empty_completion(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_auto_search_active = True
        adapter._operation_siren_auto_search_transition_until = 0.0
        oracle.operation_siren_auto_search_state = Mock(return_value="off")

        self.assertEqual(adapter.operation_siren_auto_search_state(), "off")
        self.assertTrue(adapter.operation_siren_auto_search_completed_empty())

        oracle.enabled_values["os/map/auto-search/off"] = True
        adapter.click(NamedButton("AUTO_SEARCH_OS_MAP_OPTION_OFF"))
        self.assertFalse(adapter.operation_siren_auto_search_completed_empty())

        adapter._operation_siren_auto_search_active = False
        adapter.mark_operation_siren_auto_search_completed_empty()
        self.assertTrue(adapter.operation_siren_auto_search_completed_empty())

    def test_operation_siren_original_loop_can_close_settled_off_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_auto_search_active = True
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 30.0
        )
        oracle.operation_siren_auto_search_state = Mock(return_value="off")

        adapter.mark_operation_siren_auto_search_completed_empty()

        self.assertTrue(adapter.operation_siren_auto_search_completed_empty())
        self.assertFalse(adapter.operation_siren_auto_search_transition_active())
        self.assertFalse(adapter._operation_siren_auto_search_active)

        adapter._operation_siren_auto_search_active = True
        oracle.operation_siren_auto_search_state.return_value = "on"
        with self.assertRaisesRegex(
            SemanticGateClosed, "transition is active"
        ):
            adapter.mark_operation_siren_auto_search_completed_empty()

    def test_operation_siren_boss_combat_requires_exact_target_and_owns_result(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=())

        with self.assertRaisesRegex(
            SemanticGateClosed, "requires an exact boss target"
        ):
            adapter.begin_operation_siren_boss_combat()
        self.assertFalse(adapter.operation_siren_combat_committed())

        oracle.operation_siren_radar_targets.return_value = ((0, -2),)
        adapter.begin_operation_siren_boss_combat()

        self.assertTrue(adapter.operation_siren_combat_committed())
        self.assertEqual(gate_calls, [True, True])
        oracle.operation_siren_radar_targets.assert_called_with("boss")

    def test_operation_siren_combat_owner_releases_only_on_unobstructed_map(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.daily_battle_result_visible = Mock(return_value=True)
        oracle.award_info_page_visible = Mock(return_value=False)
        oracle.operation_siren_local_map_visible = Mock(return_value=True)

        self.assertFalse(adapter.complete_operation_siren_combat_if_map_restored())
        self.assertTrue(adapter.operation_siren_combat_committed())

        oracle.daily_battle_result_visible.return_value = False
        oracle.award_info_page_visible.return_value = True
        self.assertFalse(adapter.complete_operation_siren_combat_if_map_restored())
        self.assertTrue(adapter.operation_siren_combat_committed())

        oracle.award_info_page_visible.return_value = False
        self.assertTrue(adapter.complete_operation_siren_combat_if_map_restored())
        self.assertFalse(adapter.operation_siren_combat_committed())

    def test_operation_siren_combat_observer_gap_keeps_loading_and_execution(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.operation_siren_local_map_visible = Mock(return_value=False)
        oracle.enabled_values["reward/award-info/close"] = False
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        def incomplete():
            raise SemanticGateClosed(
                "combat fixture endpoint completeness changed"
            )

        session._live_combat_visible = incomplete

        self.assertTrue(session.combat_is_loading())
        self.assertTrue(session.combat_is_executing())
        self.assertFalse(session.appear(NamedButton("BATTLE_PREPARATION")))

        adapter._operation_siren_combat_active = False
        self.assertFalse(session.combat_is_loading())
        self.assertFalse(session.combat_is_executing())
        self.assertFalse(
            session._operation_siren_combat_observer_gap(
                SemanticGateClosed(
                    "combat fixture endpoint completeness changed"
                )
            )
        )

    def test_operation_siren_interrupt_advances_exact_pause_leave_confirm_steps(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter

        oracle.exercise_combat_quit_confirm_visible = Mock(return_value=False)
        oracle.exercise_combat_pause_menu_visible = Mock(return_value=False)
        oracle.combat_pause_visible = Mock(return_value=True)
        oracle.click_combat_pause = Mock()
        self.assertTrue(session.handle_operation_siren_combat_interrupt())
        oracle.click_combat_pause.assert_called_once_with()

        oracle.combat_pause_visible.return_value = False
        oracle.exercise_combat_pause_menu_visible.return_value = True
        oracle.click_exercise_combat_leave = Mock()
        self.assertTrue(session.handle_operation_siren_combat_interrupt())
        oracle.click_exercise_combat_leave.assert_called_once_with()

        oracle.exercise_combat_pause_menu_visible.return_value = False
        oracle.exercise_combat_quit_confirm_visible.return_value = True
        oracle.click_exercise_combat_quit_confirm = Mock()
        self.assertTrue(session.handle_operation_siren_combat_interrupt())
        oracle.click_exercise_combat_quit_confirm.assert_called_once_with()

    def test_operation_siren_low_resolve_cancel_remembers_defeated_fleet(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        receipt = oracle.click_receipt("os/combat/low-resolve/cancel")
        oracle.click_operation_siren_low_resolve_cancel = Mock(
            return_value=receipt
        )
        oracle.operation_siren_current_fleet_defeated = Mock(
            side_effect=AssertionError("remembered fleet must not be re-probed")
        )

        self.assertEqual(
            adapter.click_operation_siren_low_resolve_cancel(), receipt
        )
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())
        oracle.click_operation_siren_low_resolve_cancel.assert_called_once_with()

    def test_month_boss_d_rank_remembers_only_the_fighting_fleet(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=((0, -1),))
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        oracle.operation_siren_current_fleet_defeated = Mock(
            side_effect=AssertionError("map-chibi damage is not a skip signal")
        )

        adapter.begin_operation_siren_boss_combat()
        oracle.operation_siren_current_fleet = Mock(return_value=2)
        adapter.mark_operation_siren_combat_fleet_defeated()

        oracle.operation_siren_current_fleet = Mock(return_value=4)
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())
        self.assertTrue(adapter.operation_siren_fleet_already_defeated(4))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(2))
        oracle.operation_siren_current_fleet = Mock(return_value=2)
        self.assertFalse(adapter.operation_siren_current_fleet_defeated())

    def test_operation_siren_defeat_grade_is_not_s_rank(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.operation_siren_battle_result_visible = Mock(return_value=True)
        oracle.operation_siren_battle_result_grade = Mock(return_value="DEFEAT")
        receipt = oracle.click_receipt("operation-siren/battle/result")
        oracle.click_daily_battle_result = Mock(return_value=receipt)

        self.assertEqual(adapter.operation_siren_battle_result_grade(), "DEFEAT")
        self.assertEqual(adapter.click_operation_siren_battle_result(), receipt)
        oracle.click_daily_battle_result.assert_called_once_with()

        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._combat_result_observation = None
        session._combat_last_result_receipt = None
        session._arm_combat_result_transition = Mock()
        session._combat_result_action_oracle = lambda _adapter: oracle
        session._frame_clock = None

        self.assertTrue(session.appear(NamedButton("BATTLE_STATUS_D")))
        self.assertFalse(session.appear(NamedButton("BATTLE_STATUS_S")))
        self.assertEqual(
            session.click(NamedButton("BATTLE_STATUS_D")), receipt
        )

    def test_month_boss_skip_ignores_stacked_neighbour_hud(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=((0, -1),))
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        adapter.begin_operation_siren_boss_combat()
        adapter.mark_operation_siren_combat_fleet_defeated()

        oracle.operation_siren_current_fleet = Mock(return_value=4)
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(2))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(3))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(1))

    def test_low_resolve_cancel_remembers_hud_fleet_not_stale_combat_snapshot(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=((0, -1),))
        oracle.operation_siren_current_fleet = Mock(return_value=2)
        adapter.begin_operation_siren_boss_combat()
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        receipt = oracle.click_receipt("os/combat/low-resolve/cancel")
        oracle.click_operation_siren_low_resolve_cancel = Mock(
            return_value=receipt
        )

        self.assertEqual(
            adapter.click_operation_siren_low_resolve_cancel(), receipt
        )
        self.assertTrue(adapter.operation_siren_fleet_already_defeated(4))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(2))
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())

    def test_operation_siren_reward_close_requires_owner_and_exact_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.award_info_page_visible = Mock(return_value=True)
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }

        with self.assertRaisesRegex(SemanticGateClosed, "owner is absent"):
            adapter.click_operation_siren_reward_close()

        adapter._operation_siren_combat_active = True
        receipt = adapter.click_operation_siren_reward_close()

        self.assertEqual(receipt.semantic_id, "os/combat/reward/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_operation_siren_reward_close_rejects_ambiguous_targets(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.award_info_page_visible = Mock(return_value=True)
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": True,
        }

        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            adapter.click_operation_siren_reward_close()
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_globe_swipe_accepts_unobstructed_map_strip(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_globe_state = Mock(
            return_value=SimpleNamespace(zone_name="NA海域西南C")
        )
        oracle.operation_siren_globe_visible = Mock(return_value=True)

        intent = adapter.begin_operation_siren_globe_swipe_vector(
            (100, -100),
            box=(600, 220, 980, 620),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="GLOBE_SWIPE_100_-100",
            distance_check=True,
        )

        self.assertEqual(intent.box, (600, 220, 980, 620))
        self.assertEqual(gate_calls, [True])
        adapter.end_operation_siren_globe_swipe_vector(intent)

    def test_missing_stable_name_fails_closed(self):
        adapter, _, gate_calls = self.make_adapter()

        self.assertFalse(adapter.supports(object()))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(object())
        self.assertEqual(gate_calls, [])

    def test_raw_coordinate_input_is_always_rejected(self):
        adapter, oracle, gate_calls = self.make_adapter()

        with self.assertRaises(SemanticGateClosed):
            adapter.reject_raw_input("swipe")

        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_semantic_ocr_reads_typed_unity_text_and_strips_markup(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="<color=#fff>01:23:45</color>",
                    bounds=Bounds(100, 100, 200, 130),
                    truncated=False,
                ),
            ),
        )

        value = adapter.ocr_text([(90, 90, 210, 140)], alphabet="0123456789:")

        self.assertEqual(value, "01:23:45")
        self.assertEqual(oracle.last_text_bounds, (Bounds(90, 90, 210, 140),))
        self.assertEqual(len(gate_calls), 1)

    def test_tactical_book_progress_ocr_strips_only_the_selected_book_bonus(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_tactical()
        oracle.tactical_book_skill_progress_value = "900/3200"

        value = adapter.ocr_text(
            [(771, 191, 951, 209)], alphabet="0123456789/IDSB"
        )

        self.assertEqual(value, "900/3200")

    def test_semantic_ocr_rejects_missing_or_overlapping_text(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.text_groups = ((),)
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="123456", bounds=Bounds(100, 100, 180, 130), truncated=True
                ),
            ),
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

        oracle.text_groups = (
            (
                SimpleNamespace(
                    text="12", bounds=Bounds(100, 100, 180, 130), truncated=False
                ),
                SimpleNamespace(
                    text="34", bounds=Bounds(110, 100, 190, 130), truncated=False
                ),
            ),
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.ocr_text([(90, 90, 210, 140)])

    def test_alas_owned_state_machine_consumes_stable_semantic_inputs(self):
        oracle = FakeOracle()
        oracle.enabled_values = {
            "main/task": True,
            "task/page/back": True,
            "reward/award-info/close": False,
            "reward/award-info1/close": False,
        }
        oracle.exists_values["main/task"] = True
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL
        gate_calls = []
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: gate_calls.append(True),
            allow_mission_claim_once=True,
        )

        adapter.begin_mission_reward(daily=True, weekly=True)
        self.assertTrue(adapter.appear(NamedButton("MISSION_NOTICE")))
        adapter.click(NamedButton("MAIN_GOTO_MISSION"))
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_0"),
                color=(247, 255, 173),
                threshold=180,
                count=100,
            )
        )
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_1"),
                color=(140, 162, 181),
                threshold=180,
                count=50,
            )
        )
        self.assertFalse(adapter.appear(NamedButton("MISSION_MULTI")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_MULTI")))

        receipt = adapter.click(NamedButton("MISSION_MULTI"))

        self.assertEqual(receipt.semantic_id, "task/claim/all")
        self.assertEqual(
            oracle.click_calls,
            ["main/task", "task/claim/all"],
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))
        self.assertEqual(oracle.click_calls.count("task/claim/all"), 1)
        adapter.end_mission_reward()
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("MISSION_NOTICE"))
        self.assertGreaterEqual(len(gate_calls), 1)

    def test_alas_owned_claim_requires_separate_opt_in(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertFalse(adapter.mission_claim_allowed())
        self.assertFalse(adapter.appear(NamedButton("MISSION_MULTI")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_MULTI")))

        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))

        self.assertNotIn("task/claim/all", oracle.click_calls)

        opted_in = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mission_claim_once=True,
        )
        opted_in.begin_mission_reward(daily=True, weekly=False)
        self.assertTrue(opted_in.mission_claim_allowed())

    def test_alas_owned_reward_popup_alias_uses_exact_semantic_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_alas_owned_reward_popup_alias_rejects_ambiguity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": True,
        }
        adapter.begin_mission_reward(daily=True, weekly=False)

        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("GET_ITEMS_1"))
        self.assertEqual(oracle.click_calls, [])

    def test_alas_owned_guild_popup_cancel_alias_uses_reviewed_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {"overlay/guild-message/close": True}
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))
        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("GUILD_POPUP_CONFIRM"))

    def test_global_guild_popup_probe_and_cancel_use_reviewed_close(self):
        adapter, oracle, _ = self.make_adapter()

        oracle.enabled_values["overlay/guild-message/close"] = False
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        oracle.enabled_values["overlay/guild-message/close"] = True
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))

        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))
        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(oracle.click_calls, ["overlay/guild-message/close"])

    def test_weekly_only_and_numeric_row_paths_remain_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mission_reward(daily=False, weekly=True)

        self.assertFalse(adapter.appear(NamedButton("MISSION_NOTICE")))
        self.assertFalse(
            adapter.image_color_count(
                NamedButton("MISSION_WEEKLY_RED_DOT"),
                color=(206, 81, 66),
                threshold=221,
                count=20,
            )
        )
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW
        self.assertFalse(adapter.match_template_color(NamedButton("MISSION_SINGLE")))
        self.assertTrue(adapter.match_template_color(NamedButton("MISSION_SINGLE")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_SINGLE"))
        self.assertEqual(oracle.click_calls, [])

    def test_weekly_only_mission_notice_uses_exact_main_task_badge(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.main_red_dot_values["main/task"] = True
        adapter.begin_mission_reward(daily=False, weekly=True)

        self.assertTrue(adapter.appear(NamedButton("MISSION_NOTICE")))

    def test_weekly_progress_claim_uses_one_typed_input_and_acknowledgement(self):
        adapter, oracle, _ = self.make_adapter(allow_mission_claim_once=True)
        oracle.weekly_mission_progress_claim_available_value = True
        oracle.wait_any_results = [
            (
                "reward/award-info/close",
                SimpleNamespace(path="root/AwardInfoUI(Clone)/items/close"),
            ),
            SemanticGateClosed("semantic wait timed out"),
        ]
        adapter.begin_mission_reward(daily=False, weekly=True)

        receipt = adapter.claim_weekly_mission_progress_once()

        self.assertEqual(receipt.semantic_id, "task/weekly-progress/claim")
        self.assertEqual(
            oracle.click_calls,
            ["task/weekly-progress/claim", "reward/award-info/close"],
        )
        self.assertFalse(adapter.mission_claim_allowed())

    def test_weekly_progress_claim_closes_deferred_new_ship_reward(self):
        adapter, oracle, _ = self.make_adapter(allow_mission_claim_once=True)
        oracle.weekly_mission_progress_claim_available_value = True
        oracle.wait_any_results = [
            (
                "reward/award-info/close",
                SimpleNamespace(path="root/AwardInfoUI(Clone)/items/close"),
            ),
            (
                "reward/new-ship/continue",
                SimpleNamespace(path="root/NewShipUI(Clone)/shake_panel/click"),
            ),
            SemanticGateClosed("semantic wait timed out"),
        ]
        adapter.begin_mission_reward(daily=False, weekly=True)

        receipt = adapter.claim_weekly_mission_progress_once()

        self.assertEqual(receipt.semantic_id, "task/weekly-progress/claim")
        self.assertEqual(
            oracle.click_calls,
            [
                "task/weekly-progress/claim",
                "reward/award-info/close",
                "reward/new-ship/continue",
            ],
        )

    def test_weekly_badge_is_read_from_typed_mission_marker(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.mission_weekly_reward_available_value = True
        adapter.begin_mission_reward(daily=False, weekly=True)

        self.assertTrue(
            adapter.image_color_count(
                NamedButton("MISSION_WEEKLY_RED_DOT"),
                color=(206, 81, 66),
                threshold=221,
                count=20,
            )
        )

    def test_mission_ship_receipt_uses_exact_new_ship_continue(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.new_ship_reward_visible_value = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GET_SHIP")))
        receipt = adapter.click(NamedButton("GET_SHIP"))

        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(oracle.click_calls, ["reward/new-ship/continue"])

    def test_default_navbar_requires_exact_mission_entry_click(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        with self.assertRaises(SemanticGateClosed):
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_0"),
                color=(247, 255, 173),
                threshold=180,
                count=100,
            )

    def test_mission_navbar_reuses_alas_click_with_typed_image_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=True)
        adapter.click(NamedButton("MAIN_GOTO_MISSION"))

        receipt = adapter.click(NamedButton("REWARD_SIDE_NAVBAR_0_4"))

        self.assertEqual(receipt.semantic_id, "task/nav/weekly")
        self.assertEqual(oracle.click_calls, ["main/task", "task/nav/weekly"])

    def test_unknown_presence_is_false_only_on_proven_mission_surface(self):
        adapter, oracle, gate_calls = self.make_adapter()
        adapter.begin_mission_reward(daily=True, weekly=False)
        oracle.exists_values["main/task"] = True

        self.assertFalse(adapter.appear(NamedButton("UNRELATED_PAGE_CHECK")))

        oracle.exists_values.clear()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("UNRELATED_PAGE_CHECK"))
        self.assertGreaterEqual(len(gate_calls), 1)

    def test_reward_surface_keeps_passive_alas_page_scan_fail_closed(self):
        adapter, oracle, _ = self.make_adapter()

        self.assertFalse(adapter.mission_reward_active())
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertTrue(adapter.mission_reward_active())
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

        adapter.end_mission_reward()
        self.assertFalse(adapter.mission_reward_active())
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_exact_login_surface_defers_unrelated_page_scan_to_login_handler(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["login/enter"] = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("LOGIN_CHECK")))

        oracle.enabled_values.clear()
        oracle.enabled_values["overlay/bulletin/close"] = True
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("LOGIN_ANNOUNCE")))

    def test_render_transition_staleness_has_bounded_presence_grace(self):
        for message in (
            "observer snapshot is stale",
            "observer endpoints are not generation-coherent",
            "Msgbox snapshots are not coherent",
        ):
            with self.subTest(message=message):
                adapter, oracle, _ = self.make_adapter()

                def stale(_semantic_id):
                    raise SemanticGateClosed(message)

                oracle.enabled = stale
                self.assertFalse(adapter.appear(NamedButton("REWARD_CHECK")))
                adapter._observer_stale_since = time.monotonic() - 6.0
                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.appear(NamedButton("REWARD_CHECK"))

    def test_campaign_input_transition_extends_stale_presence_grace(self):
        adapter, oracle, _ = self.make_adapter()

        def stale(_semantic_id):
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = stale
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        adapter._observer_stale_since = time.monotonic() - 6

        self.assertFalse(adapter.appear(NamedButton("BATTLE_PREPARATION")))

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaisesRegex(SemanticGateClosed, "observer snapshot is stale"):
            adapter.appear(NamedButton("BATTLE_PREPARATION"))
        adapter.end_campaign_pre_sortie()

    def test_daily_result_owner_is_disabled_during_campaign_combat(self):
        adapter, _, _ = self.make_adapter()
        adapter._daily_kind = "tactical"
        self.assertTrue(adapter.daily_execution_active())

        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        self.assertFalse(adapter.daily_execution_active())
        adapter.end_campaign_pre_sortie()

    def test_login_activity_handoff_has_bounded_presence_grace(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        adapter.begin_login()
        self.assertFalse(adapter.appear(NamedButton("LOGIN_CHECK")))
        adapter._observer_stale_since = time.monotonic() - 6.0
        self.assertFalse(adapter.appear(NamedButton("LOGIN_CHECK")))
        adapter._login_flow._context.passive_transition_until = 0.0
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
            adapter.appear(NamedButton("LOGIN_CHECK"))

    def test_activity_handoff_outside_login_remains_fail_closed(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
            adapter.appear(NamedButton("REWARD_CHECK"))

    def test_operation_siren_startup_owns_passive_activity_handoff(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)
        self.assertFalse(adapter.appear(NamedButton("SP_CHECK")))

        adapter._operation_siren_auto_search_active = False
        adapter._operation_siren_entry_transition_until = 0.0
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
            adapter.appear(NamedButton("SP_CHECK"))

    def test_reviewed_mission_transition_has_bounded_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        adapter.click(NamedButton("GOTO_MAIN"))
        oracle.exists_values.clear()
        oracle.enabled_values.clear()

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        adapter._mission_context.passive_transition_until = time.monotonic() - 1.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))

    def test_bounded_task_flows_allow_passive_scan_on_proven_surface(self):
        cases = (
            ("begin_research", "reward/page/back"),
            ("begin_dorm", "dorm/page/back"),
            ("begin_build", "build/page/start"),
        )
        for begin_name, semantic_id in cases:
            with self.subTest(flow=begin_name):
                adapter, oracle, _ = self.make_adapter()
                getattr(adapter, begin_name)()
                oracle.exists_values[semantic_id] = True

                self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_proven_build_queue_allows_unrelated_page_scan_without_build_flow(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.build_queue_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("BUILD_CHECK")))

    def test_war_archives_page_check_claim_state_and_key_ocr_are_typed(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.war_archives_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("WAR_ARCHIVES_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("DATA_KEY_COLLECTED")))
        self.assertTrue(adapter.appear(NamedButton("DATA_KEY_COLLECT")))

        self.assertEqual(
            adapter.ocr_text([(133, 39, 250, 72)], alphabet="0123456789/IDSB"),
            "300/300",
        )

    def test_bounded_task_flows_begin_with_page_discovery_grace(self):
        for begin_name in (
            "begin_commission",
            "begin_tactical",
            "begin_research",
            "begin_dorm",
            "begin_build",
        ):
            with self.subTest(flow=begin_name):
                adapter, _, _ = self.make_adapter()
                getattr(adapter, begin_name)()
                self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_research_navigation_has_bounded_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        main_entry = adapter.click(NamedButton("MAIN_GOTO_RESHMENU"))
        main_duplicate = adapter.click(NamedButton("MAIN_GOTO_RESHMENU_WHITE"))
        research_entry = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        research_duplicate = adapter.click(NamedButton("RESHMENU_GOTO_RESEARCH"))
        queue_entry = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))
        queue_duplicate = adapter.click(NamedButton("RESEARCH_GOTO_QUEUE"))
        back = adapter.click(NamedButton("BACK_ARROW"))
        back_duplicate = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(main_duplicate, main_entry)
        self.assertEqual(research_duplicate, research_entry)
        self.assertEqual(queue_duplicate, queue_entry)
        self.assertEqual(back_duplicate, back)
        self.assertEqual(
            oracle.click_calls,
            [
                "main/tech",
                "research-menu/research",
                "research/queue/enter",
                "research/page/back",
            ],
        )
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        adapter._research_context.passive_transition_until = time.monotonic() - 1.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_research_goto_main_is_idempotent_during_page_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True
        oracle.enabled_values["research/page/back"] = True

        first = adapter.click(NamedButton("GOTO_MAIN"))
        duplicate = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(duplicate, first)
        self.assertEqual(oracle.click_calls, ["research/page/back"])

    def test_dorm_navigation_is_idempotent_during_page_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()

        main = adapter.click(NamedButton("MAIN_GOTO_DORMMENU"))
        main_duplicate = adapter.click(NamedButton("MAIN_GOTO_DORMMENU_WHITE"))
        entry = adapter.click(NamedButton("DORMMENU_GOTO_DORM"))
        entry_duplicate = adapter.click(NamedButton("DORMMENU_GOTO_DORM"))
        back = adapter.click(NamedButton("DORM_GOTO_MAIN"))
        back_duplicate = adapter.click(NamedButton("DORM_GOTO_MAIN"))

        self.assertEqual(main_duplicate, main)
        self.assertEqual(entry_duplicate, entry)
        self.assertEqual(back_duplicate, back)
        self.assertEqual(
            oracle.click_calls,
            ["main/live", "dorm-menu/dorm", "dorm/page/back"],
        )

    def test_dorm_page_discovery_grace_covers_slow_device_startup(self):
        adapter, _, _ = self.make_adapter()
        before = time.monotonic()

        adapter.begin_dorm()

        self.assertGreaterEqual(
            adapter._dorm_context.passive_transition_until - before,
            59.0,
        )
        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))

    def test_dorm_can_recover_prior_game_room_through_typed_home(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.game_room_page_visible_value = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "game-room/home")
        self.assertEqual(oracle.click_calls, ["game-room/home"])

    def test_dorm_menu_overlay_owns_page_discovery_over_mounted_main(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm-menu/page/root"] = True
        oracle.enabled_values["main/formation"] = True

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_FLEET")))
        self.assertTrue(adapter.appear(NamedButton("DORMMENU_CHECK")))

    def test_dorm_menu_overlay_owns_shared_page_discovery_without_flow_context(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["dorm-menu/page/root"] = True

        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORMMENU_CHECK")))

    def test_dorm_generic_reward_probe_requires_exact_award_popup(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["reward/award-info/close"] = False
        oracle.enabled_values["reward/award-info1/close"] = False

        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))
        oracle.enabled_values["reward/award-info/close"] = True
        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_dorm_recovers_server_rollover_activity_through_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])

    def test_cross_flow_virtual_probe_is_false_but_input_stays_forbidden(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("DOCK_CHECK"))

    def test_research_queue_snapshot_is_bounded_across_queue_exit(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        self.assertEqual(adapter.research_queue_empty_slots(), 5)
        oracle.research_queue_visible_value = False

        self.assertEqual(adapter.research_queue_empty_slots(), 5)
        adapter._research_context.last_queue_observed_at = time.monotonic() - 31.0
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            adapter.research_queue_empty_slots()

    def test_research_queue_exit_caches_the_last_typed_capacity(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.research_queue_visible_value = True

        adapter.click(NamedButton("BACK_ARROW"))
        oracle.research_queue_visible_value = False

        self.assertEqual(adapter.research_queue_empty_slots(), 5)

    def test_research_fill_slots_are_limited_by_current_run_budget(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()

        self.assertEqual(adapter.research_queue_fill_slots(), 5)
        gated = AlasSemanticAdapter(oracle, lambda: None)
        gated.begin_research()
        oracle.research_queue_visible_value = False
        self.assertEqual(gated.research_queue_fill_slots(), 0)

    def test_research_detail_availability_is_false_before_selection(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True

        def absent_detail():
            raise SemanticGateClosed("research detail identity is not proven")

        oracle.research_detail_state = absent_detail

        self.assertFalse(adapter.research_detail_available())

    def test_research_detail_availability_includes_current_run_budget(self):
        oracle = FakeOracle()
        gated = AlasSemanticAdapter(oracle, lambda: None)
        gated.begin_research()

        self.assertFalse(gated.research_detail_available())
        self.assertTrue(gated.appear(NamedButton("RESEARCH_UNAVAILABLE")))

        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            research_start_budget=1,
        )
        adapter.begin_research()
        self.assertTrue(adapter.research_detail_available())
        self.assertFalse(adapter.appear(NamedButton("RESEARCH_UNAVAILABLE")))

    def test_research_project_snapshot_has_short_render_grace(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_research()

        self.assertEqual(adapter.research_projects(), ())
        oracle.research_projects_visible_value = False

        self.assertEqual(adapter.research_projects(), ())
        adapter._research_context.last_projects_observed_at = time.monotonic() - 6.0
        with self.assertRaisesRegex(SemanticGateClosed, "page identity is not proven"):
            adapter.research_projects()

    def test_mission_entry_alias_cannot_double_click_during_transition(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["main/task"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        adapter.click(NamedButton("MAIN_GOTO_MISSION"))
        duplicate = adapter.click(NamedButton("MAIN_GOTO_MISSION_WHITE"))

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_MISSION_WHITE")))
        self.assertEqual(oracle.click_calls, ["main/task"])
        self.assertEqual(duplicate.semantic_id, "main/task")

    def test_reward_summary_entry_alias_is_idempotent(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mission_reward(daily=True, weekly=False)

        first = adapter.click(NamedButton("MAIN_GOTO_REWARD"))
        duplicate = adapter.click(NamedButton("MAIN_GOTO_REWARD_WHITE"))

        self.assertEqual(first, duplicate)
        self.assertEqual(oracle.click_calls, ["main/more"])

    def test_mission_no_claim_round_trip_enters_and_exits(self):
        adapter, oracle, gate_calls = self.make_adapter()

        receipt = adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(receipt.outcome, "nothing-claimable")
        self.assertFalse(receipt.claim_injected)
        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(
            [call[0] for call in oracle.wait_calls],
            ["task/page/back", "main/task"],
        )
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claimable_state_exits_then_fails_closed(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL

        with self.assertRaises(MissionClaimableDetected) as raised:
            adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(
            raised.exception.page.disposition,
            MissionDisposition.CLAIMABLE_ALL,
        )
        self.assertFalse(hasattr(raised.exception, "claim_receipt"))
        self.assertEqual(len(gate_calls), 1)

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_mission_dismisses_only_reviewed_overlay_close(self, _sleep):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values = {
            "main/task": False,
            "overlay/bulletin/close": False,
            "overlay/guild-message/close": True,
        }
        oracle.enable_main_after_overlay_click = True

        receipt = adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(
            receipt.dismissed_overlays,
            ("overlay/guild-message/close",),
        )
        self.assertEqual(
            oracle.click_calls,
            ["overlay/guild-message/close", "main/task", "task/page/back"],
        )
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claim_all_closes_popup_and_proves_unfinished(self):
        adapter, oracle, gate_calls = self.make_adapter(
            allow_mission_claim_once=True
        )
        oracle.mission_dispositions = [
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.UNFINISHED,
        ]

        receipt = adapter.claim_mission_rewards_once(timeout_seconds=12)

        self.assertEqual(receipt.outcome, "claimed-all-once")
        self.assertEqual(receipt.claim_input_count, 1)
        self.assertEqual(
            oracle.click_calls,
            [
                "main/task",
                "task/claim/all",
                "reward/award-info/close",
                "task/page/back",
            ],
        )
        self.assertEqual(
            oracle.wait_any_calls[0][0],
            (
                "reward/award-info/close",
                "reward/award-info1/close",
            ),
        )
        self.assertEqual(len(gate_calls), 1)

    def test_reward_hook_claim_requires_policy_and_call_opt_in(self):
        adapter, oracle, gate_calls = self.make_adapter(
            allow_mission_claim_once=True
        )
        oracle.mission_dispositions = [
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.UNFINISHED,
        ]

        receipt = adapter.run_mission_reward(
            timeout_seconds=12,
            allow_claim_once=True,
        )

        self.assertEqual(receipt.outcome, "claimed-all-once")
        self.assertEqual(receipt.claim_input_count, 1)
        self.assertIn("task/claim/all", oracle.click_calls)
        self.assertEqual(len(gate_calls), 1)

    def test_reward_hook_call_opt_in_cannot_bypass_zero_input_policy(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.mission_dispositions = [MissionDisposition.CLAIMABLE_ALL]

        with self.assertRaises(SemanticGateClosed):
            adapter.run_mission_reward(
                timeout_seconds=12,
                allow_claim_once=True,
            )

        self.assertEqual(oracle.click_calls, ["main/task"])

    def test_mission_claim_refuses_row_only_before_claim_input(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW

        with self.assertRaises(SemanticGateClosed):
            adapter.claim_mission_rewards_once(timeout_seconds=12)

        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(len(gate_calls), 1)

    def test_alas_owned_row_claim_uses_one_exact_typed_row(self):
        adapter, oracle, _ = self.make_adapter(allow_mission_claim_once=True)
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertFalse(adapter.appear(NamedButton("MISSION_SINGLE")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_SINGLE")))
        receipt = adapter.click(NamedButton("MISSION_SINGLE"))

        self.assertEqual(receipt.semantic_id, "task/claim/row/0")
        self.assertEqual(oracle.click_calls, ["task/claim/row/0"])
        self.assertFalse(adapter.mission_claim_allowed())

    def test_package_gate_verifies_once_per_bridge_pid(self):
        bridge = FakePackageBridge()
        gate = PinnedPackageGate(bridge)

        gate()
        gate()
        bridge.pid = 5678
        gate()

        self.assertEqual(
            bridge.calls,
            ["x86_64", "x86_64"],
        )

    def test_package_gate_requires_open_bridge(self):
        bridge = FakePackageBridge()
        bridge.pid = None

        with self.assertRaises(SemanticGateClosed):
            PinnedPackageGate(bridge)()

    def test_lazy_session_rejects_unmapped_before_opening_adb(self):
        session = AlasSemanticSession(
            "emulator-test", "be80ce591a481c12d60c50d6040d40c035b40a2b"
        )

        with self.assertRaises(AlasSemanticUnmapped):
            session.click(NamedButton("UNREVIEWED_CLICK"))

        self.assertIsNone(session.runtime_handle)

    def test_live_combat_manifest_rebinds_only_reviewed_capacity_successor(self):
        base_revision = "be80ce591a481c12d60c50d6040d40c035b40a2b"
        live_revision = "506b76f698b5089aaa29c4e7908b48edb8532a44"
        manifest = AlasCombatObserverManifest(
            package="com.bilibili.azurlane",
            driver_revision=base_revision,
            game_fingerprint="reviewed-game",
            resources=(),
        )
        session = AlasSemanticSession("emulator-test", live_revision)

        with patch(
            "alas_headless.alas_adapter.load_alas_combat_observer_manifest",
            return_value=manifest,
        ):
            rebound = session._live_combat_manifest()

        self.assertEqual(rebound.driver_revision, live_revision)
        self.assertEqual(manifest.driver_revision, base_revision)
        self.assertIs(session._live_combat_manifest(), rebound)

    def test_live_combat_manifest_rejects_unknown_driver_transition(self):
        manifest = AlasCombatObserverManifest(
            package="com.bilibili.azurlane",
            driver_revision="be80ce591a481c12d60c50d6040d40c035b40a2b",
            game_fingerprint="reviewed-game",
            resources=(),
        )
        session = AlasSemanticSession("emulator-test", "a" * 40)

        with patch(
            "alas_headless.alas_adapter.load_alas_combat_observer_manifest",
            return_value=manifest,
        ):
            with self.assertRaisesRegex(
                SemanticGateClosed,
                "not qualified",
            ):
                session._live_combat_manifest()

    def test_environment_factory_requires_explicit_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            )
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_captures_one_claim_budget_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertTrue(session.allow_mission_claim_once)

    def test_environment_factory_bounds_explicit_adb_timeout(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")
        self.assertEqual(
            session._runtime_handle_factory.command_timeout_seconds,
            30.0,
        )

        for malformed in ("030", "0", "121"):
            environment["ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS"] = malformed
            with self.subTest(value=malformed):
                with patch.dict("os.environ", environment, clear=True):
                    with self.assertRaises((SemanticGateClosed, ValueError)):
                        AlasSemanticSession.from_environment("emulator-test")

    def test_session_bounds_observer_freshness_and_process_lease_types(self):
        revision = "be80ce591a481c12d60c50d6040d40c035b40a2b"
        session = AlasSemanticSession(
            "emulator-test",
            revision,
            observer_max_age_ms=300000,
        )
        self.assertEqual(session.observer_max_age_ms, 300000)

        for malformed in (True, 0, 300001):
            with self.subTest(value=malformed):
                with self.assertRaisesRegex(ValueError, "observer max age"):
                    AlasSemanticSession(
                        "emulator-test",
                        revision,
                        observer_max_age_ms=malformed,
                    )
        with self.assertRaisesRegex(ValueError, "package lease"):
            AlasSemanticSession(
                "emulator-test",
                revision,
                package_process_lease=object(),
            )

    def test_environment_factory_parses_commission_reward_budget(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertEqual(session.commission_reward_budget, 1)

        environment["ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET"] = "01"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_rejects_removed_boolean_reward_opt_in(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_keeps_tactical_reward_opt_in_separate(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertTrue(session.allow_tactical_rewards)
        self.assertEqual(session.commission_reward_budget, 0)

    def test_environment_factory_parses_canonical_commission_start_budget(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_COMMISSION_START_BUDGET": "1",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")
        self.assertEqual(session.commission_start_budget, 1)

        environment["ALAS_SEMANTIC_COMMISSION_START_BUDGET"] = "01"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")

    def test_environment_factory_parses_new_bounded_mutation_budgets(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": (
                "be80ce591a481c12d60c50d6040d40c035b40a2b"
            ),
            "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET": "1",
            "ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET": "2",
            "ALAS_SEMANTIC_RESEARCH_START_BUDGET": "3",
            "ALAS_SEMANTIC_DORM_COLLECT_BUDGET": "4",
            "ALAS_SEMANTIC_DORM_FEED_BUDGET": "5",
            "ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET": "6",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "7",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": "8",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "9",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": "10",
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": "11",
        }
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("emulator-test")

        self.assertEqual(session.tactical_assign_budget, 1)
        self.assertEqual(session.research_reward_budget, 2)
        self.assertEqual(session.research_start_budget, 3)
        self.assertEqual(session.dorm_collect_budget, 4)
        self.assertEqual(session.dorm_feed_budget, 5)
        self.assertEqual(session.build_submit_budget, 6)
        self.assertEqual(session.campaign_stage_entry_budget, 7)
        self.assertEqual(session.campaign_fleet_mutation_budget, 8)
        self.assertEqual(session.campaign_sortie_budget, 9)
        self.assertEqual(session.campaign_combat_budget, 10)
        self.assertEqual(session.campaign_viewport_swipe_budget, 11)
        self.assertEqual(session.campaign_camera_positioning_budget, 0)

        environment["ALAS_SEMANTIC_DORM_FEED_BUDGET"] = "05"
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(SemanticGateClosed):
                AlasSemanticSession.from_environment("emulator-test")


class GuildSemanticAdapterTests(unittest.TestCase):
    def make_adapter(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            frame_observation_oracle=lambda: oracle,
            frame_identity_provider=AlasSemanticAdapterTests.frame_identity,
        )
        return adapter, oracle, []

    def test_exchange_filter_selects_highest_ranked_eligible_typed_item(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.guild_logistics_state = lambda: SimpleNamespace(
            exchange_items=(
                SimpleNamespace(
                    index=0,
                    icon_sprite="gold",
                    enough=True,
                    button=SimpleNamespace(interactable=True),
                ),
                SimpleNamespace(
                    index=1,
                    icon_sprite="17023",
                    enough=True,
                    button=SimpleNamespace(interactable=True),
                ),
                SimpleNamespace(
                    index=2,
                    icon_sprite="17003",
                    enough=True,
                    button=SimpleNamespace(interactable=True),
                ),
            )
        )

        selected = adapter.select_guild_exchange_item(
            "PlateGeneralT3 > PlateTorpedoT3 > Coin"
        )

        self.assertEqual(selected.index, 2)

    def test_exchange_filter_rejects_duplicate_priorities(self):
        adapter, _, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "duplicates"):
            adapter.select_guild_exchange_item("Coin > Coin")


class ScriptedAdbBridge(AdbObserverBridge):
    def __init__(self, outputs):
        super().__init__("emulator-test", "com.bilibili.azurlane")
        self.outputs = outputs
        self.calls = []

    def _run(self, arguments, timeout_seconds=None):
        self.calls.append((tuple(arguments), timeout_seconds))
        try:
            return self.outputs[tuple(arguments)]
        except KeyError as exc:
            raise AssertionError("unexpected ADB command: {0}".format(arguments)) from exc


class PackageFingerprintTests(unittest.TestCase):
    def test_swipe_uses_one_exact_adb_input_command(self):
        command = (
            "shell",
            "input",
            "swipe",
            "1257",
            "330",
            "1257",
            "390",
            "500",
        )
        bridge = ScriptedAdbBridge({command: ""})

        bridge.swipe(1257, 330, 1257, 390, 500)

    def test_reads_independent_version_abi_and_hash_identity(self):
        expected = AndroidPackageFingerprint(
            version_name="9.7.10",
            version_code=9710,
            primary_abi="x86_64",
            base_apk_sha256="a" * 64,
            il2cpp_sha256="b" * 64,
        )
        native_dir = "/data/app/~~token/pkg/lib/x86_64"
        base_apk = "/data/app/~~token/pkg/base.apk"
        il2cpp = native_dir + "/libil2cpp.so"
        bridge = ScriptedAdbBridge(
            {
                ("shell", "dumpsys", "package", bridge_package()): (
                    "versionCode=9710 minSdk=21\n"
                    "versionName=9.7.10\n"
                    "primaryCpuAbi=x86_64\n"
                    "legacyNativeLibraryDir={0}\n".format(native_dir)
                ),
                ("shell", "pm", "path", bridge_package()): "package:" + base_apk,
                (
                    "shell",
                    "find",
                    native_dir,
                    "-type",
                    "f",
                    "-name",
                    "libil2cpp.so",
                    "-print",
                ): il2cpp,
                ("shell", "sha256sum", base_apk): "{0}  {1}".format(
                    expected.base_apk_sha256, base_apk
                ),
                ("shell", "sha256sum", il2cpp): "{0}  {1}".format(
                    expected.il2cpp_sha256, il2cpp
                ),
            }
        )

        self.assertEqual(bridge.require_package_fingerprint(expected), expected)

    def test_compatibility_accepts_updated_split_package_without_hashing(self):
        native_dir = "/data/app/~~new-token/pkg/lib/x86_64"
        base_apk = "/data/app/~~new-token/pkg/base.apk"
        split_apk = "/data/app/~~new-token/pkg/split_config.x86_64.apk"
        il2cpp = native_dir + "/libil2cpp.so"
        bridge = ScriptedAdbBridge(
            {
                ("shell", "dumpsys", "package", bridge_package()): (
                    "versionCode=10000 minSdk=21\n"
                    "versionName=10.0.0\n"
                    "primaryCpuAbi=x86_64\n"
                    "legacyNativeLibraryDir={0}\n".format(native_dir)
                ),
                ("shell", "pm", "path", bridge_package()): (
                    "package:{0}\npackage:{1}".format(base_apk, split_apk)
                ),
                (
                    "shell",
                    "find",
                    native_dir,
                    "-type",
                    "f",
                    "-name",
                    "libil2cpp.so",
                    "-print",
                ): il2cpp,
            }
        )

        actual = bridge.require_package_compatibility("x86_64")

        self.assertEqual(actual["version_name"], "10.0.0")
        self.assertEqual(actual["version_code"], 10000)
        self.assertEqual(actual["base_apk_path"], base_apk)
        self.assertEqual(actual["il2cpp_path"], il2cpp)
        self.assertFalse(
            any(call[0][:2] == ("shell", "sha256sum") for call in bridge.calls)
        )

    def test_compatibility_rejects_only_concrete_unsupported_abi(self):
        native_dir = "/data/app/~~new-token/pkg/lib/arm64"
        bridge = ScriptedAdbBridge(
            {
                ("shell", "dumpsys", "package", bridge_package()): (
                    "versionCode=10000 minSdk=21\n"
                    "versionName=10.0.0\n"
                    "primaryCpuAbi=arm64-v8a\n"
                    "legacyNativeLibraryDir={0}\n".format(native_dir)
                ),
            }
        )

        with self.assertRaisesRegex(SemanticGateClosed, "ABI is unsupported"):
            bridge.require_package_compatibility("x86_64")

        self.assertEqual(len(bridge.calls), 1)

    def test_retries_exact_device_hash_once_after_cold_start_adb_failure(self):
        path = "/data/app/~~token/pkg/base.apk"
        testcase = self

        class HashRetryBridge(ScriptedAdbBridge):
            def __init__(self):
                super().__init__({})
                self.calls = 0

            def _run(self, arguments, timeout_seconds=None):
                testcase.assertEqual(
                    tuple(arguments), ("shell", "sha256sum", path)
                )
                testcase.assertEqual(timeout_seconds, 120.0)
                self.calls += 1
                if self.calls == 1:
                    raise ObserverTransportError("transient adb failure")
                return "{0}  {1}".format("a" * 64, path)

        bridge = HashRetryBridge()
        bridge._DEVICE_SHA256_RETRY_DELAY_SECONDS = 0.0

        self.assertEqual(bridge._device_sha256(path), "a" * 64)
        self.assertEqual(bridge.calls, 2)

    def test_rejects_non_allowlisted_fingerprint(self):
        expected = AndroidPackageFingerprint("1", 1, "x86_64", "a" * 64, "b" * 64)
        actual = AndroidPackageFingerprint("2", 2, "x86_64", "c" * 64, "d" * 64)

        class MismatchBridge(ScriptedAdbBridge):
            def package_fingerprint(self):
                return actual

        with self.assertRaises(SemanticGateClosed):
            MismatchBridge({}).require_package_fingerprint(expected)


def bridge_package():
    return "com.bilibili.azurlane"


if __name__ == "__main__":
    unittest.main()
