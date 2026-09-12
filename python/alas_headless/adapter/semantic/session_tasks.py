"""Session tasks for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Any, Callable, List, Optional, Sequence, Tuple, Union
from ...adapter import SemanticFrame
from ...alas_enemy_priority_config_contract import AlasEnemyPriorityConfigSnapshot
from ...alas_fleet_config_contract import AlasFleetConfigSnapshot
from ...alas_hp_control_config_contract import AlasHpControlConfigSnapshot
from ...alas_mail_config_contract import AlasMailConfigSnapshot
from ...alas_submarine_config_contract import AlasSubmarineConfigSnapshot
from ...semantic_oracle import (
    ActionReceipt,
    AwakenCostState,
    AwakenExecutionReceipt,
    Bounds,
    BuildCostState,
    BuildPool,
    BuildSubmitState,
    CampaignAutoSearchRoleState,
    CampaignFleetSelectionState,
    CampaignMapAchievementState,
    CampaignMapState,
    CampaignMapViewportSwipeIntent,
    CampaignMapViewportSwipeProof,
    CampaignPageState,
    CommissionDetailState,
    CommissionRewardProof,
    CommissionRowState,
    CommissionScrollProof,
    CommissionScrollState,
    CommissionStartProof,
    DormFeedState,
    DormFurniturePurchaseState,
    DormFurnitureShopBalance,
    DormFurnitureThemePurchaseState,
    DormState,
    EnhancementExecutionReceipt,
    EnhancementNoMaterialReceipt,
    GemsFarmingDockCandidate,
    GemsFarmingEquipmentLoadout,
    GeneralShopItemState,
    MeowfficerAcquisitionState,
    MeowfficerDockState,
    MeowfficerPurchaseState,
    MeowfficerQueueState,
    MeowfficerTrainingState,
    MetaAssistState,
    MetaCurrentDetailState,
    MetaEntranceState,
    ObserverTransportError,
    OperationSirenGlobeSwipeReceipt,
    RaidMultipleSortieState,
    ResearchDetailState,
    ResearchProjectState,
    ResearchQueueState,
    RetirementExecutionReceipt,
    RetirementNoCandidateReceipt,
    SemanticGateClosed,
    SemanticTargetMissing,
    ShipyardState,
    TacticalBookState,
    TacticalCandidateShipState,
    TacticalSkillState,
    TacticalSlotState,
)
from .adapter import AlasSemanticAdapter
from .contracts import (
    AlasSemanticUnmapped,
    CampaignAutoSearchCompletionProof,
    CampaignAutoSearchEvidenceBundle,
    CampaignCameraPositioningAdmission,
    CampaignFleetPreparationProof,
    CampaignPreSortieProof,
    CampaignSortieProof,
    MissionClaimReceipt,
    MissionRunReceipt,
)
from .resources import DEFAULT_ALAS_BUTTON_TARGETS


class SessionTasksPorts:
    """Session tasks on the shared immutable frame."""

    def refresh_tactical_input_frame(self) -> SemanticFrame:
        """Acquire the Dock action lease without requiring its truncated UI tree."""

        return self.refresh_frame(include_ui=False)

    def refresh_gems_farming_dock_input_frame(self) -> SemanticFrame:
        """Acquire a Gems Dock lease before its focused typed projections."""

        return self.refresh_frame(include_ui=False)

    def __enter__(self) -> AlasSemanticAdapter:
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def semantic_id_for(self, button: Any) -> str:
        # Name validation is cheap and happens before the bridge is opened, so
        # unmapped ALAS calls fail without touching ADB or the game.
        if self.adapter is None:
            name = AlasSemanticAdapter._button_name(button)
            try:
                return DEFAULT_ALAS_BUTTON_TARGETS[name]
            except KeyError as exc:
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                ) from exc
        return self.adapter.semantic_id_for(button)

    def campaign_result_ready(self) -> bool:
        """Report an exact campaign result that arrived before ALAS polled it."""

        adapter = self.open()
        oracle = adapter.oracle
        return bool(
            adapter.campaign_combat_committed()
            and oracle.daily_battle_result_visible()
            and not oracle.operation_siren_battle_result_visible()
        )

    def campaign_boss_returned_to_stage(self) -> bool:
        """Report the typed stage page reached after a committed boss combat."""

        adapter = self.open()
        oracle = adapter.oracle
        returned = bool(
            adapter._campaign_context is not None
            and adapter._campaign_context.combat_receipt is not None
            and not oracle.daily_battle_result_visible()
            and not oracle.operation_siren_battle_result_visible()
            and oracle.campaign_page_is_normal()
        )
        if returned:
            # This is the same typed result that the original CampaignBase
            # uses to raise CampaignEnd. Retain it for its next outer run;
            # do not infer completion from an arbitrary map disappearance.
            adapter._campaign_context.manual_completion_proven = True
        return returned

    def close_campaign_battle_fail_tip_if_present(self) -> bool:
        self.refresh_frame()
        return self.open().oracle.close_campaign_battle_fail_tip_if_present()

    def bounds(self, button: Any) -> Bounds:
        self.semantic_id_for(button)
        return self.open().bounds(button)

    def ocr_text(
        self,
        areas: Sequence[Any],
        alphabet: Optional[str] = None,
    ) -> Union[str, List[str]]:
        return self.open().ocr_text(areas, alphabet=alphabet)

    def general_shop_items(self) -> Tuple[GeneralShopItemState, ...]:
        return self.open().oracle.general_shop_items()

    def shop_purchase_allowed(self) -> bool:
        return self.open()._action_ledger.allowed("shop.purchase")

    def refresh_shop_once(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().refresh_shop_once()

    def retirement_allowed(self) -> bool:
        return self.open().retirement_allowed()

    def awaken_allowed(self) -> bool:
        return self.open().awaken_allowed()

    def begin_awaken_task(self, favourite: bool) -> None:
        self.refresh_frame()
        self.open().begin_awaken_task(favourite)

    def prepare_awaken_phase(self, use_array: bool) -> None:
        self.refresh_frame()
        self.open().prepare_awaken_phase(use_array)

    def awaken_next(self, use_array: bool) -> str:
        self.refresh_frame()
        return self.open().awaken_next(use_array)

    def finish_awaken_task(self) -> None:
        self.refresh_frame()
        self.open().finish_awaken_task()

    def awaken_receipts(self) -> Tuple[AwakenExecutionReceipt, ...]:
        return self.open().awaken_receipts()

    def awaken_cost_observations(self) -> Tuple[AwakenCostState, ...]:
        return self.open().awaken_cost_observations()

    def enhancement_allowed(self) -> bool:
        return self.open().enhancement_allowed()

    def gems_farming_admit_live_mode(
        self,
        stage_code: str,
        campaign_mode: str,
        change_flagship: str,
        change_vanguard: str,
        attacking_fleet: int,
    ) -> None:
        self.open().gems_farming_admit_live_mode(
            stage_code,
            campaign_mode,
            change_flagship,
            change_vanguard,
            attacking_fleet,
        )

    def gems_farming_select_fleet_index(self, fleet_index: int) -> int:
        self.refresh_frame()
        return self.open().gems_farming_select_fleet_index(fleet_index)

    def gems_farming_open_slot(self, role: str) -> ActionReceipt:
        self.refresh_frame()
        return self.open().gems_farming_open_slot(role)

    def gems_farming_hard_slot_occupied(
        self, stage_code: str, fleet_index: int, role: str
    ) -> bool:
        self.refresh_frame()
        return self.open().gems_farming_hard_slot_occupied(
            stage_code, fleet_index, role
        )

    def gems_farming_hard_fleet_preparation_visible(self, stage_code: str) -> bool:
        self.refresh_frame(include_ui=False)
        return self.open().gems_farming_hard_fleet_preparation_visible(stage_code)

    def gems_farming_hard_unmount(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().gems_farming_hard_unmount(
            stage_code, fleet_index, role
        )

    def gems_farming_hard_open_slot(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().gems_farming_hard_open_slot(
            stage_code, fleet_index, role
        )

    def gems_farming_equipment_take_off(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        self.refresh_frame()
        return self.open().gems_farming_equipment_take_off(role)

    def gems_farming_equipment_take_on(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        self.refresh_frame()
        return self.open().gems_farming_equipment_take_on(role)

    def gems_farming_candidates(
        self,
        *,
        role: str,
        selector: str,
        max_level: int,
        min_emotion: int,
        fleet_index: int,
    ) -> Tuple[GemsFarmingDockCandidate, ...]:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_candidates(
            role=role,
            selector=selector,
            max_level=max_level,
            min_emotion=min_emotion,
            fleet_index=fleet_index,
        )

    def gems_farming_select_candidate(
        self, candidate: GemsFarmingDockCandidate
    ) -> ActionReceipt:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_select_candidate(candidate)

    def gems_farming_cancel_candidate_selection(self) -> ActionReceipt:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_cancel_candidate_selection()

    def gems_farming_confirm_candidate_selection(
        self, candidate: GemsFarmingDockCandidate, role: str
    ) -> ActionReceipt:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_confirm_candidate_selection(candidate, role)

    def begin_enhancement_task(
        self,
        ship_to_enhance: str,
        check_per_category: int,
        filter_expression: Optional[str],
    ) -> None:
        self.refresh_frame()
        self.open().begin_enhancement_task(
            ship_to_enhance, check_per_category, filter_expression
        )

    def enhancement_enter(
        self, favourite: bool, ship_type: Optional[str]
    ) -> bool:
        self.refresh_frame()
        return self.open().enhancement_enter(favourite, ship_type)

    def enhancement_choose(self, ship_count: int) -> Tuple[bool, int]:
        self.refresh_frame()
        return self.open().enhancement_choose(ship_count)

    def enhancement_leave_category(self) -> None:
        self.refresh_frame()
        self.open().enhancement_leave_category()

    def finish_enhancement_task(self) -> None:
        self.refresh_frame()
        self.open().finish_enhancement_task()

    def enhancement_receipts(
        self,
    ) -> Tuple[Union[EnhancementExecutionReceipt, EnhancementNoMaterialReceipt], ...]:
        return self.open().enhancement_receipts()

    def retire_ships_one_click(self, keep_limit_break: bool) -> int:
        return self.open().retire_ships_one_click(keep_limit_break)

    def retirement_receipt(
        self,
    ) -> Optional[Union[RetirementExecutionReceipt, RetirementNoCandidateReceipt]]:
        return self.open().retirement_receipt()

    def purchase_shop_item_once(
        self,
        index: int,
        expected_name: str,
        expected_cost: str,
        expected_price: int,
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().purchase_shop_item_once(
            index, expected_name, expected_cost, expected_price
        )

    def shop_refresh_available(self) -> bool:
        return self.open().oracle.shop_refresh_available()

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        return self.open().research_projects()

    def research_projects_for_alas(
        self, project_factory: Callable[..., object]
    ) -> Tuple[object, ...]:
        return self.open().research_projects_for_alas(project_factory)

    def click_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> ActionReceipt:
        return self.open().click_research_project_code(code, position=position)

    def start_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> bool:
        return self.open().start_research_project_code(code, position=position)

    def validate_research_filter(self, filter_: object, value: str) -> None:
        self.open().validate_research_filter(filter_, value)

    def shipyard_select_series(self, series: int) -> ActionReceipt:
        return self.open().shipyard_select_series(series)

    def shipyard_select_ship(self, index: int) -> ShipyardState:
        return self.open().shipyard_select_ship(index)

    def shipyard_state(self, index: int) -> ShipyardState:
        return self.open().shipyard_state(index)

    def research_detail_state(self) -> ResearchDetailState:
        return self.open().research_detail_state()

    def research_detail_available(self) -> bool:
        return self.open().research_detail_available()

    def research_detail_is_running(self) -> bool:
        return self.open().research_detail_is_running()

    def research_detail_can_queue(self) -> bool:
        return self.open().research_detail_can_queue()

    def research_queue_state(self) -> ResearchQueueState:
        return self.open().research_queue_state()

    def research_queue_empty_slots(self) -> int:
        return self.open().research_queue_empty_slots()

    def research_queue_fill_slots(self) -> int:
        return self.open().research_queue_fill_slots()

    def research_queue_remaining_seconds(self) -> int:
        return self.open().research_queue_remaining_seconds()

    def build_selected_pool(self) -> BuildPool:
        return self.open().build_selected_pool()

    def build_costs(self) -> BuildCostState:
        return self.open().build_costs()

    def dorm_state(self) -> DormState:
        return self.open().dorm_state()

    def meowfficer_dock_state(self) -> MeowfficerDockState:
        return self.open().meowfficer_dock_state()

    def meowfficer_purchase_state(self) -> MeowfficerPurchaseState:
        return self.open().meowfficer_purchase_state()

    def buy_meowfficer_boxes(
        self, count: int, *, timeout_seconds: float = 45.0
    ) -> MeowfficerDockState:
        return self.open().buy_meowfficer_boxes(
            count, timeout_seconds=timeout_seconds
        )

    def meowfficer_fort_chore_available(self) -> bool:
        return self.open().meowfficer_fort_chore_available()

    def run_meowfficer_fort_chores(
        self, *, timeout_seconds: float = 30.0
    ) -> Tuple[ActionReceipt, ...]:
        return self.open().run_meowfficer_fort_chores(
            timeout_seconds=timeout_seconds
        )

    def admit_meowfficer_training_plan(self, *, mode: str, sunday: bool) -> None:
        self.open().admit_meowfficer_training_plan(mode=mode, sunday=sunday)

    def enhance_meowfficer(
        self,
        *,
        index: int,
        max_feed_level: int,
        timeout_seconds: float = 90.0,
    ) -> str:
        return self.open().enhance_meowfficer(
            index=index,
            max_feed_level=max_feed_level,
            timeout_seconds=timeout_seconds,
        )

    def meowfficer_acquisition_state(self) -> MeowfficerAcquisitionState:
        return self.open().meowfficer_acquisition_state()

    def finish_meowfficer_acquisition(
        self,
        *,
        retain_talented_gold: bool,
        retain_talented_purple: bool,
        timeout_seconds: float = 45.0,
    ) -> int:
        return self.open().finish_meowfficer_acquisition(
            retain_talented_gold=retain_talented_gold,
            retain_talented_purple=retain_talented_purple,
            timeout_seconds=timeout_seconds,
        )

    def meowfficer_training_state(self) -> MeowfficerTrainingState:
        return self.open().meowfficer_training_state()

    def meowfficer_queue_state(self) -> MeowfficerQueueState:
        return self.open().meowfficer_queue_state()

    def dorm_furniture_purchase_state(self) -> DormFurniturePurchaseState:
        return self.open().dorm_furniture_purchase_state()

    def dorm_furniture_shop_balance(self) -> DormFurnitureShopBalance:
        return self.open().dorm_furniture_shop_balance()

    def dorm_furniture_theme_purchase_state(
        self,
    ) -> DormFurnitureThemePurchaseState:
        return self.open().dorm_furniture_theme_purchase_state()

    def buy_dorm_furniture_with_gold(self) -> ActionReceipt:
        return self.open().buy_dorm_furniture_with_gold()

    def buy_dorm_furniture_theme_with_gold(self) -> ActionReceipt:
        return self.open().buy_dorm_furniture_theme_with_gold()

    def run_current_dorm_furniture_purchase(
        self, buy_option: str
    ) -> Tuple[ActionReceipt, ...]:
        return self.open().run_current_dorm_furniture_purchase(buy_option)

    def begin_meta_beacon(self) -> None:
        self._meta_beacon_active = True
        self.open().begin_meta_beacon()

    def begin_meta_assist(self) -> None:
        self._meta_assist_active = True
        self.open().begin_meta_assist()

    def end_meta_assist(self) -> None:
        self._meta_assist_active = False
        if self.adapter is not None:
            self.adapter.end_meta_assist()

    def end_meta_beacon(self) -> None:
        self._meta_beacon_active = False
        if self.adapter is not None:
            self.adapter.end_meta_beacon()

    def meta_beacon_active(self) -> bool:
        return self._meta_beacon_active

    def click_meta_beacon_sortie_confirm(self) -> ActionReceipt:
        self.refresh_tactical_input_frame()
        adapter = self.open()
        if not self._meta_beacon_active:
            raise SemanticGateClosed("META beacon task owner is absent")
        if not adapter.meta_beacon_active():
            adapter.begin_meta_beacon()
        return adapter.click_meta_beacon_sortie_confirm()

    def meta_entrance_state(self) -> MetaEntranceState:
        return self.open().meta_entrance_state()

    def meta_page_visible(self) -> bool:
        return self.open().meta_page_visible()

    def private_quarters_daily_count(self) -> int:
        return self.open()._frame_or_live_observation_oracle().private_quarters_overview().remaining

    def meta_assist_state(self) -> MetaAssistState:
        return self.open().meta_assist_state()

    def click_meta_assist_next_candidate(
        self, *, expected_index: int, expected_level: int
    ) -> ActionReceipt:
        self.refresh_tactical_input_frame()
        return self.open().click_meta_assist_next_candidate(
            expected_index=expected_index,
            expected_level=expected_level,
        )

    def meta_current_empty_points(self) -> Tuple[int, int]:
        return self.open().meta_current_empty_points()

    def meta_current_detail_state(self) -> MetaCurrentDetailState:
        return self.open().meta_current_detail_state()

    def dorm_feed_state(self) -> DormFeedState:
        return self.open().dorm_feed_state()

    def dorm_food_counts(self) -> Tuple[int, ...]:
        return self.open().dorm_food_counts()

    def dorm_feed_food(self, item_index: int, count: int) -> Tuple[ActionReceipt, ...]:
        # ALAS can spend a long time waiting for BackYardFeedUI's typed text
        # after its last screenshot. Acquire a new immutable frame at the
        # exact mutation boundary instead of allowing that observation to
        # expire before the oracle re-proves the selected food card.
        self.refresh_frame()
        return self.open().dorm_feed_food(item_index, count)

    def build_submit_state(self) -> BuildSubmitState:
        return self.open().build_submit_state()

    def build_set_count(self, target: int) -> BuildSubmitState:
        return self.open().build_set_count(target)

    def build_coins_owned(self) -> int:
        return self.open().build_coins_owned()

    def campaign_page_state(self) -> CampaignPageState:
        return self.open().campaign_page_state()

    def event_points(self) -> int:
        return self.open().event_points()

    def event_coin(self) -> int:
        return self.open().event_coin()

    def campaign_oil(self) -> int:
        return self.open().campaign_oil()

    def campaign_map_achievement_state(self) -> CampaignMapAchievementState:
        return self.open().campaign_map_achievement_state()

    def campaign_map_clear_percentage(self) -> float:
        return self.open().campaign_map_clear_percentage()

    def campaign_map_preparation_mode_state(self) -> str:
        return self.open().campaign_map_preparation_mode_state()

    def set_campaign_map_preparation_mode(
        self, destination: str
    ) -> ActionReceipt:
        return self.open().set_campaign_map_preparation_mode(destination)

    def campaign_auto_search_selected(self) -> bool:
        return self.open().campaign_auto_search_selected()

    def campaign_map_formation(self) -> str:
        return self.open().campaign_map_formation()

    def campaign_fleet_hp(self) -> Tuple[float, ...]:
        return self.open().campaign_fleet_hp()

    def campaign_hp_control_snapshot(self, fleet_index: int):
        return self.open().campaign_hp_control_snapshot(fleet_index)

    def wait_campaign_repair_ready(self):
        return self.open().wait_campaign_repair_ready()

    def campaign_repair_postcondition(self):
        return self.open().campaign_repair_postcondition()

    def change_campaign_scout_position(self, source_slot, destination_slot):
        return self.open().change_campaign_scout_position(source_slot, destination_slot)

    def campaign_fleet_levels(self) -> Tuple[int, ...]:
        return self.open().campaign_fleet_levels()

    def campaign_map_state(
        self,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        return self.open().campaign_map_state(
            columns=columns,
            rows=rows,
            land_cells=land_cells,
            expected_fleet_count=expected_fleet_count,
        )

    def authorize_campaign_camera_positioning(
        self, target_node: str, state: CampaignMapState
    ) -> CampaignCameraPositioningAdmission:
        return self.open().authorize_campaign_camera_positioning(
            target_node, state
        )

    def begin_campaign_map_swipe_vector(
        self, vector: Any, **kwargs: Any
    ) -> CampaignMapViewportSwipeIntent:
        return self.open().begin_campaign_map_swipe_vector(vector, **kwargs)

    def recover_campaign_map_network_reconnect(self) -> bool:
        return self.open().recover_campaign_map_network_reconnect()

    def end_campaign_map_swipe_vector(
        self, intent: CampaignMapViewportSwipeIntent
    ) -> None:
        self.open().end_campaign_map_swipe_vector(intent)

    def swipe(
        self,
        p1: Any,
        p2: Any,
        *,
        duration: Any,
        name: Any,
        distance_check: Any,
    ) -> Union[CampaignMapViewportSwipeProof, OperationSirenGlobeSwipeReceipt]:
        return self.open().swipe(
            p1,
            p2,
            duration=duration,
            name=name,
            distance_check=distance_check,
        )

    def campaign_map_viewport_swipe_committed(self) -> bool:
        return self.open().campaign_map_viewport_swipe_committed()

    def campaign_map_viewport_swipe_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        return self.open().campaign_map_viewport_swipe_proof()

    def campaign_camera_positioning_committed(self) -> bool:
        return self.open().campaign_camera_positioning_committed()

    def complete_campaign_camera_positioning(
        self, state: CampaignMapState
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        return self.open().complete_campaign_camera_positioning(state)

    def campaign_camera_positioning_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        return self.open().campaign_camera_positioning_proof()

    def campaign_camera_positioning_proofs(
        self,
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        return self.open().campaign_camera_positioning_proofs()

    def campaign_camera_state(self) -> CampaignMapState:
        return self.open().campaign_camera_state()

    def campaign_camera_target_node(self) -> Optional[str]:
        return self.open().campaign_camera_target_node()

    def handle_campaign_ambush(self, *, evade: bool) -> bool:
        return self.open().handle_campaign_ambush(evade=evade)

    def campaign_ambush_present(self) -> bool:
        return self.open().campaign_ambush_present()

    def campaign_ambush_outcome(self) -> Optional[str]:
        return self.open().campaign_ambush_outcome()

    def finish_campaign_ambush(self) -> None:
        self.open().finish_campaign_ambush()

    def campaign_ambush_info_count(self) -> int:
        adapter = self.open()
        if adapter._campaign_context is None:
            return 0
        notice = adapter._frame_or_live_observation_oracle().campaign_ambush_notice()
        return int(notice in ("success", "failed"))

    def campaign_stage_entry_allowed(self) -> bool:
        return self.open().campaign_stage_entry_allowed()

    def campaign_map_preparation_committed(self) -> bool:
        return self.open().campaign_map_preparation_committed()

    def confirm_campaign_pre_sortie(self) -> CampaignPreSortieProof:
        return self.open().confirm_campaign_pre_sortie()

    def authorize_campaign_fleet_preparation(
        self, fleet1: int, fleet2: int, submarine: int
    ) -> bool:
        return self.open().authorize_campaign_fleet_preparation(
            fleet1, fleet2, submarine
        )

    def campaign_fleet_preparation_required(self) -> bool:
        return self.open().campaign_fleet_preparation_required()

    def campaign_fleet_row_allowed(self, row_key: str) -> bool:
        return self.open().campaign_fleet_row_allowed(row_key)

    def prepare_campaign_hard_fleets(self) -> CampaignFleetSelectionState:
        return self.open().prepare_campaign_hard_fleets()

    def campaign_fleet_operator_is_hard(self, row_key: str) -> bool:
        return self.open().campaign_fleet_operator_is_hard(row_key)

    def campaign_fleet_operator_hard_satisfied(
        self, row_key: str
    ) -> Optional[bool]:
        return self.open().campaign_fleet_operator_hard_satisfied(row_key)

    def campaign_fleet_operator_in_use(self, row_key: str) -> bool:
        return self.open().campaign_fleet_operator_in_use(row_key)

    def campaign_fleet_operator_selected_fleet(
        self, row_key: str
    ) -> Optional[int]:
        return self.open().campaign_fleet_operator_selected_fleet(row_key)

    def campaign_fleet_dropdown_opened(self) -> bool:
        return self.open().campaign_fleet_dropdown_opened()

    def campaign_fleet_selected_indices(self, row_key: str) -> List[int]:
        return self.open().campaign_fleet_selected_indices(row_key)

    def confirm_campaign_fleet_selection(self) -> CampaignFleetSelectionState:
        return self.open().confirm_campaign_fleet_selection()

    def ensure_campaign_auto_search_roles(
        self, fleet_order: str
    ) -> CampaignAutoSearchRoleState:
        return self.open().ensure_campaign_auto_search_roles(fleet_order)

    def campaign_auto_search_running(self) -> bool:
        return self.open().campaign_auto_search_running()

    def campaign_inherited_auto_search_visible(self) -> bool:
        return self.open().campaign_inherited_auto_search_visible()

    def recover_inherited_campaign_auto_search(
        self,
        stage_code: str,
        fleet_order: str,
        timeout_seconds: float = 1800.0,
    ) -> CampaignAutoSearchCompletionProof:
        return self.open().recover_inherited_campaign_auto_search(
            stage_code,
            fleet_order,
            timeout_seconds=timeout_seconds,
        )

    def close_orphan_campaign_auto_search_result(self) -> bool:
        return self.open().close_orphan_campaign_auto_search_result()

    def confirm_campaign_auto_search_started(self) -> CampaignSortieProof:
        return self.open().confirm_campaign_auto_search_started()

    def wait_campaign_auto_search_completion(
        self, stage_code: str, timeout_seconds: float = 1800.0,
        *, keep_result: bool = False, recovery_handler=None, submarine_handler=None,
    ) -> CampaignAutoSearchCompletionProof:
        return self.open().wait_campaign_auto_search_completion(
            stage_code, timeout_seconds=timeout_seconds, keep_result=keep_result,
            recovery_handler=recovery_handler, submarine_handler=submarine_handler,
        )

    def campaign_submarine_call_battle(self):
        adapter = self.open()
        if adapter._campaign_context is None:
            return False  # Not a Campaign task; leave its original handler untouched.
        return adapter.campaign_submarine_call_battle()

    def campaign_submarine_grid(self, location):
        return self.open().campaign_submarine_grid(location)

    def authorize_campaign_auto_search_continue(self, **values) -> bool:
        return self.open().authorize_campaign_auto_search_continue(**values)

    def ensure_campaign_submarine_auto_mode(self, desired: str) -> str:
        return self.open().ensure_campaign_submarine_auto_mode(desired)

    def campaign_retirement_visible(self) -> bool:
        return self.open().oracle.retirement_selection_visible()

    def last_campaign_auto_search_completion(
        self,
    ) -> Optional[CampaignAutoSearchCompletionProof]:
        return self.open().last_campaign_auto_search_completion()

    def bind_next_campaign_evidence_owner(self, owner: str) -> None:
        self.open().bind_next_campaign_evidence_owner(owner)

    def consume_campaign_auto_search_evidence(
        self,
        *,
        expected_owner: str,
        expected_stage_code: str,
        expected_mode: str,
    ) -> Optional[CampaignAutoSearchEvidenceBundle]:
        return self.open().consume_campaign_auto_search_evidence(
            expected_owner=expected_owner,
            expected_stage_code=expected_stage_code,
            expected_mode=expected_mode,
        )

    def close_campaign_fleet_dropdown_for_rollback(self) -> None:
        self.open().close_campaign_fleet_dropdown_for_rollback()

    def confirm_campaign_fleet_preparation(
        self,
    ) -> CampaignFleetPreparationProof:
        return self.open().confirm_campaign_fleet_preparation()

    def authorize_campaign_sortie(
        self,
        *,
        use_auto_search: bool,
        use_2x_book: bool,
        submarine_mode: str,
        fleet_order: str,
    ) -> bool:
        return self.open().authorize_campaign_sortie(
            use_auto_search=use_auto_search,
            use_2x_book=use_2x_book,
            submarine_mode=submarine_mode,
            fleet_order=fleet_order,
        )

    def campaign_clear_mode_available(self) -> bool:
        return self.open().campaign_clear_mode_available()

    def campaign_2x_book_selected(self) -> bool:
        return self.open().campaign_2x_book_selected()

    def handle_campaign_2x_book_popup(self) -> bool:
        return self.open().handle_campaign_2x_book_popup()

    def campaign_sortie_committed(self) -> bool:
        return self.open().campaign_sortie_committed()

    def campaign_dock_full_visible(self) -> bool:
        return self.open().campaign_dock_full_visible()

    def campaign_precombat_visible(self) -> bool:
        adapter = self.open()
        adapter._require_campaign_context()
        return adapter._frame_or_live_observation_oracle().campaign_precombat_visible()

    def click_campaign_precombat_back(self) -> ActionReceipt:
        adapter = self.open()
        context = adapter._require_campaign_context()
        oracle = adapter._fresh_input_oracle()
        # Optional recovery evidence must not prevent full-fleet back navigation.
        # A failed correlation leaves the existing six-slot requirement intact.
        try:
            index, identity = oracle.campaign_precombat_fleet_identity()
        except SemanticGateClosed:
            index, identity = None, None
        receipt = oracle.click_campaign_precombat_back()
        context.inherited_fleet_identity = identity
        context.inherited_fleet_index = index
        return receipt

    def click_campaign_dock_full_choice(self, choice: str) -> ActionReceipt:
        return self.open().click_campaign_dock_full_choice(choice)

    def arm_daemon_campaign_map_preparation(self) -> bool:
        return self.open().arm_daemon_campaign_map_preparation()

    def authorize_daemon_campaign_sortie(
        self,
        *,
        fleet1: int,
        fleet2: int,
        submarine: int,
        use_auto_search: bool,
        use_2x_book: bool,
        submarine_mode: str,
        fleet_order: str,
    ) -> bool:
        return self.open().authorize_daemon_campaign_sortie(
            fleet1=fleet1,
            fleet2=fleet2,
            submarine=submarine,
            use_auto_search=use_auto_search,
            use_2x_book=use_2x_book,
            submarine_mode=submarine_mode,
            fleet_order=fleet_order,
        )

    def confirm_daemon_campaign_sortie(self) -> CampaignSortieProof:
        return self.open().confirm_daemon_campaign_sortie()

    def confirm_war_archives_entry_if_present(self) -> Optional[ActionReceipt]:
        return self.open().confirm_war_archives_entry_if_present()

    def confirm_campaign_sortie(self) -> CampaignSortieProof:
        return self.open().confirm_campaign_sortie()

    def research_series(self) -> List[int]:
        return self.open().research_series()

    def research_statuses(self) -> List[str]:
        return self.open().research_statuses()

    def research_detail_stable(self) -> None:
        self.open().research_detail_stable()

    def research_page_stable(self) -> None:
        self.open().research_page_stable()

    def research_finished_index(self) -> Optional[int]:
        return self.open().research_finished_index()

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        return self.open().tactical_slots()

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        return self.open().tactical_remaining_seconds()

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        return self.open().tactical_candidate_ships()

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        return self.open().tactical_skills()

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        return self.open().tactical_books()

    def tactical_select_book(self, position: int) -> ActionReceipt:
        return self.open().tactical_select_book(position)

    def tactical_book_selected(self, position: int) -> bool:
        return self.open().tactical_book_selected(position)

    def tactical_select_suitable_ship(
        self, favourite: bool, min_level: int, start_index: int
    ) -> bool:
        return self.open().tactical_select_suitable_ship(
            favourite, min_level, start_index
        )

    def tactical_select_first_trainable_skill(self) -> bool:
        return self.open().tactical_select_first_trainable_skill()

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        return self.open().commission_rows()

    def commission_is_empty(self) -> bool:
        return self.open().commission_is_empty()

    def commission_scroll_state(self) -> CommissionScrollState:
        return self.open().commission_scroll_state()

    def commission_scroll_next(self) -> Optional[CommissionScrollProof]:
        return self.open().commission_scroll_next()

    def commission_scroll_to_top(self) -> Optional[CommissionScrollProof]:
        return self.open().commission_scroll_to_top()

    def minigame_scroll_visible(self) -> bool:
        return self.open().minigame_scroll_visible()

    def minigame_scroll_set(self, position: float) -> bool:
        self.refresh_frame()
        return self.open().minigame_scroll_set(position)

    def commission_reward_pending(self) -> bool:
        return self.open().commission_reward_pending()

    def commission_reward_allowed(self) -> bool:
        return self.open().commission_reward_allowed()

    def commission_reward_claimed(self) -> bool:
        return self.open().commission_reward_claimed()

    def confirm_commission_reward(self) -> CommissionRewardProof:
        return self.open().confirm_commission_reward()

    def commission_start_allowed(self) -> bool:
        return self.open().commission_start_allowed()

    def commission_selection_active(self) -> bool:
        return self.open().commission_selection_active()

    def commission_detail_state(self) -> CommissionDetailState:
        return self.open().commission_detail_state()

    def commission_start_confirmed(self) -> bool:
        return self.open().commission_start_confirmed()

    def commission_start_proof(self) -> CommissionStartProof:
        return self.open().commission_start_proof()

    def close_started_commission_detail(self) -> ActionReceipt:
        return self.open().close_started_commission_detail()

    def cancel_tactical_continue_if_present(self) -> bool:
        return self.open().cancel_tactical_continue_if_present()

    def click_if_present(self, button: Any) -> Optional[ActionReceipt]:
        """Dispatch a presence-driven ALAS click only if its target remains."""

        try:
            return self.click(button)
        except SemanticTargetMissing:
            return None

    def campaign_story_black(self) -> bool:
        oracle = self.open().oracle
        if oracle.daily_combat_visible():
            self._daily_combat_seen_at = time.monotonic()
            return False
        if oracle.daily_battle_result_visible():
            return False
        if time.monotonic() - getattr(
            self, "_daily_combat_seen_at", float("-inf")
        ) <= 20.0:
            return False
        return self.open().campaign_story_black()

    def daily_current_active(self) -> bool:
        return self.open().daily_current_active()

    def daily_current_kind(self) -> str:
        return self.open().daily_current_kind()

    def daily_current_remain(self) -> int:
        return self.open().daily_current_remain()

    def daily_detail_visible(self) -> bool:
        return self.open().daily_detail_visible()

    def daily_fleet_index(self) -> int:
        return self.open().daily_fleet_index()

    def click_daily_fleet(self, direction: str) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_daily_fleet(direction)

    def daily_execution_receipts(self) -> Tuple[ActionReceipt, ...]:
        return self.open().daily_execution_receipts()

    def complete_daily_battle_result(self) -> Tuple[ActionReceipt, ...]:
        return self.open().complete_daily_battle_result()

    def daily_execution_active(self) -> bool:
        return self.open().daily_execution_active()

    def current_raid_result_active(self) -> bool:
        return self.open().current_raid_result_active()

    def exercise_execute_allowed(self) -> bool:
        return self.open().exercise_execute_allowed()

    def exercise_refresh_allowed(self) -> bool:
        return self.open().exercise_refresh_allowed()

    def exercise_duel_hp(self) -> Tuple[float, float]:
        return self.open().oracle.exercise_duel_hp()

    def exercise_quit_low_hp(self) -> Tuple[ActionReceipt, ...]:
        """Quit an Exercise duel through the exact official pause flow."""

        oracle = self.open().oracle
        receipts = []
        if not oracle.exercise_combat_pause_menu_visible():
            receipts.append(oracle.click_exercise_combat_pause())
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if oracle.exercise_combat_pause_menu_visible():
                break
            time.sleep(0.2)
        else:
            raise SemanticGateClosed("Exercise pause menu did not appear")
        receipts.append(oracle.click_exercise_combat_leave())
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if oracle.exercise_combat_quit_confirm_visible():
                break
            time.sleep(0.2)
        else:
            raise SemanticGateClosed("Exercise quit confirmation did not appear")
        receipts.append(oracle.click_exercise_combat_quit_confirm())
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if oracle.daily_precombat_visible() and oracle.exercise_page_visible():
                return tuple(receipts)
            time.sleep(0.25)
        raise SemanticGateClosed("Exercise quit did not return to preparation")

    def exercise_wait_overview(self, timeout_seconds: float = 15.0) -> None:
        """Wait for Exercise ownership after its preparation overlay is gone."""

        oracle = self.open().oracle
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if (
                oracle.exercise_page_visible()
                and not oracle.daily_precombat_visible()
                and not oracle.exercise_opponent_detail_visible()
            ):
                return
            time.sleep(0.25)
        raise SemanticGateClosed("Exercise overview did not stabilize")

    def exercise_opponents(self) -> Tuple[Tuple[Tuple[int, int], Tuple[int, ...]], ...]:
        """Inspect all four rivals with a fresh, closed-loop detail transition."""

        adapter = self.open()
        oracle = adapter.oracle
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                powers = tuple(
                    oracle.exercise_opponent_power(index) for index in range(1, 5)
                )
                break
            except SemanticGateClosed:
                time.sleep(0.25)
        else:
            raise SemanticGateClosed("Exercise rival powers did not stabilize")
        result = []
        for index, power in enumerate(powers, start=1):
            self.refresh_frame()
            receipt = self.open().oracle.click("exercise/opponent/{0}".format(index))
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                try:
                    if oracle.exercise_opponent_detail_visible():
                        levels = oracle.exercise_opponent_levels()
                        break
                except SemanticGateClosed:
                    pass
                time.sleep(0.25)
            else:
                raise SemanticGateClosed("Exercise rival detail did not appear")
            if receipt.generation > oracle.read_ui_state().generation:
                raise SemanticGateClosed("Exercise rival detail predates its selection")
            oracle.click_exercise_opponent_back()
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                if oracle.exercise_page_visible():
                    break
                time.sleep(0.25)
            else:
                raise SemanticGateClosed("Exercise rival detail did not close")
            result.append((power, levels))
        return tuple(result)

    def complete_exercise_battle_result(self, timeout_seconds: float = 60.0) -> Tuple[ActionReceipt, ...]:
        """Drain the exact Exercise grade/reward/statistics stack to its page."""

        deadline = time.monotonic() + timeout_seconds
        receipts: List[ActionReceipt] = []
        while time.monotonic() < deadline:
            oracle = self.open().oracle
            if oracle.exercise_page_visible():
                return tuple(receipts)
            if oracle.exercise_merit_shop_visible():
                receipts.append(oracle.click_exercise_merit_shop_close())
            elif oracle.exercise_reward_item_info_visible():
                receipts.append(oracle.click_exercise_reward_item_info_cancel())
            elif oracle.award_info_page_visible():
                receipts.append(oracle.click_exercise_award_info_close())
            elif oracle.daily_battle_result_visible():
                receipts.append(oracle.click_daily_battle_result())
            else:
                time.sleep(0.25)
                continue
            time.sleep(1.0)
        raise SemanticGateClosed("Exercise result stack did not return to overview")

    def click_daily_back(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_daily_back()

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        self.open().begin_mission_reward(daily=daily, weekly=weekly)

    def begin_login(self) -> None:
        adapter = self.open()
        adapter.begin_login()
        if self._game_manager_restart_pending:
            adapter._login_flow.extend_passive_transition(120.0)
            self._game_manager_restart_pending = False

    def end_login(self) -> None:
        if self.adapter is not None:
            self.adapter.end_login()

    def end_mission_reward(self) -> None:
        if self.adapter is not None:
            self.adapter.end_mission_reward()

    def mission_reward_active(self) -> bool:
        return bool(
            self.adapter is not None and self.adapter.mission_reward_active()
        )

    def mail_reward_active(self) -> bool:
        return bool(self.adapter is not None and self.adapter.mail_reward_active())

    def validate_mail_config(self, **values: object) -> AlasMailConfigSnapshot:
        return self.open().validate_mail_config(**values)

    def mission_claim_allowed(self) -> bool:
        return self.open().mission_claim_allowed()

    def claim_weekly_mission_progress_once(self) -> Optional[ActionReceipt]:
        return self.open().claim_weekly_mission_progress_once()

    def begin_mail(self) -> None:
        self.open().begin_mail()

    def end_mail(self) -> None:
        if self.adapter is not None:
            self.adapter.end_mail()

    def begin_supply_pack(self) -> None:
        self.open().begin_supply_pack()

    def begin_battle_pass(self) -> None:
        self.open().begin_battle_pass()

    def end_battle_pass(self) -> None:
        if self.adapter is not None:
            self.adapter.end_battle_pass()

    def battle_pass_active(self) -> bool:
        return bool(
            self.adapter is not None and self.adapter.battle_pass_active()
        )

    def begin_data_key(self, *, force_collect: bool) -> None:
        self.open().begin_data_key(force_collect=force_collect)

    def end_data_key(self) -> None:
        if self.adapter is not None:
            self.adapter.end_data_key()

    def war_archives_campaign_visible(self) -> bool:
        self.refresh_frame()
        return self.open().war_archives_campaign_visible()

    def war_archives_data_key_count(self) -> Tuple[int, int]:
        self.refresh_frame()
        return self.open().war_archives_data_key_count()

    def open_war_archives_campaign(
        self, event: str, category: str
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().open_war_archives_campaign(event, category)

    def end_supply_pack(self) -> None:
        if self.adapter is not None:
            self.adapter.end_supply_pack()

    def supply_pack_active(self) -> bool:
        return bool(
            self.adapter is not None and self.adapter.supply_pack_active()
        )

    def begin_minigame(self) -> None:
        self.open().begin_minigame()

    def end_minigame(self) -> None:
        if self.adapter is not None:
            self.adapter.end_minigame()

    def minigame_active(self) -> bool:
        return bool(self.adapter is not None and self.adapter.minigame_active())

    def minigame_play_allowed(self) -> bool:
        return self.open().minigame_play_allowed()

    def minigame_prepare_default_ticket(self) -> int:
        self.refresh_frame()
        return self.open().minigame_prepare_default_ticket()

    def minigame_help_visible(self) -> bool:
        self.refresh_frame()
        return self.open().oracle.new_year_challenge_help_visible()

    def minigame_close_help(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().oracle.click_new_year_challenge_help()

    def minigame_result(self) -> Optional[Tuple[int, int]]:
        self.refresh_frame()
        return self.open().oracle.new_year_challenge_result()

    def minigame_attack_state(self) -> Tuple[int, int, bool]:
        self.refresh_frame()
        return self.open().oracle.new_year_challenge_attack_state()

    def minigame_attack(self, key: str) -> Optional[ActionReceipt]:
        self.refresh_frame()
        context = self.open()._require_minigame_context()
        if context.play_receipt is None:
            raise SemanticGateClosed("minigame attack used before admitted start")
        return self.open().oracle.click_new_year_challenge_attack_key(key)

    def minigame_attack_combo(
        self, first_key: str
    ) -> Tuple[ActionReceipt, ...]:
        self.refresh_frame()
        context = self.open()._require_minigame_context()
        if context.play_receipt is None:
            raise SemanticGateClosed("minigame combo used before admitted start")
        return self.open().oracle.click_new_year_challenge_attack_combo(first_key)

    def minigame_tick(
        self, first_key: str
    ) -> Tuple[Optional[Tuple[int, int]], int, Tuple[ActionReceipt, ...]]:
        self.refresh_frame()
        context = self.open()._require_minigame_context()
        if context.play_receipt is None:
            raise SemanticGateClosed("minigame tick used before admitted start")
        return self.open().oracle.new_year_challenge_tick(first_key)

    def minigame_exit_new_year(self) -> Tuple[ActionReceipt, ...]:
        """Return from Fushun prepare/list to the stable game-room page."""

        self.refresh_frame()
        adapter = self.open()
        context = adapter._require_minigame_context()
        receipts = []
        if adapter.oracle.new_year_challenge_result() is not None:
            receipts.append(adapter.oracle.click_new_year_challenge_result_close())
            context.passive_transition_until = time.monotonic() + 12.0
            time.sleep(0.5)
            self.refresh_frame()
        try:
            adapter.oracle.new_year_challenge_ticket_count()
        except SemanticGateClosed:
            pass
        else:
            receipts.append(
                adapter.oracle.click_new_year_challenge_prepare_control("back")
            )
            context.passive_transition_until = time.monotonic() + 12.0
            time.sleep(0.75)
            self.refresh_frame()
        if not adapter.oracle.game_room_page_visible():
            raise SemanticGateClosed(
                "new-year challenge exit did not restore the game room"
            )
        return tuple(receipts)

    def begin_commission(self) -> None:
        self.open().begin_commission()

    def end_commission(self) -> None:
        if self.adapter is not None:
            self.adapter.end_commission()

    def begin_tactical(self) -> None:
        self.open().begin_tactical()

    def end_tactical(self) -> None:
        if self.adapter is not None:
            self.adapter.end_commission()

    def begin_research(self) -> None:
        self.open().begin_research()

    def end_research(self) -> None:
        if self.adapter is not None:
            self.adapter.end_research()

    def begin_dorm(self) -> None:
        self.open().begin_dorm()

    def end_dorm(self) -> None:
        if self.adapter is not None:
            self.adapter.end_dorm()

    def begin_build(self) -> None:
        self.open().begin_build()

    def end_build(self) -> None:
        if self.adapter is not None:
            self.adapter.end_build()

    def begin_campaign_pre_sortie(
        self, stage_code: str, mode: str = "normal"
    ) -> None:
        self.open().begin_campaign_pre_sortie(stage_code, mode=mode)

    def prepare_campaign_run(self) -> None:
        self.open().prepare_campaign_run()

    def campaign_pre_sortie_stage_code(self) -> str:
        return self.open().campaign_pre_sortie_stage_code()

    def end_campaign_pre_sortie(self) -> None:
        if self.adapter is not None:
            self.adapter.end_campaign_pre_sortie()

    def campaign_pre_sortie_active(self) -> bool:
        return bool(
            self.adapter is not None
            and self.adapter.campaign_pre_sortie_active()
        )

    def validate_campaign_fleet_config(
        self, **values: object
    ) -> AlasFleetConfigSnapshot:
        return self.open().validate_campaign_fleet_config(**values)

    def validate_campaign_hp_control_config(
        self, **values: object
    ) -> AlasHpControlConfigSnapshot:
        return self.open().validate_campaign_hp_control_config(**values)

    def validate_campaign_enemy_priority_config(
        self, **values: object
    ) -> AlasEnemyPriorityConfigSnapshot:
        return self.open().validate_campaign_enemy_priority_config(**values)

    def validate_campaign_submarine_config(
        self, **values: object
    ) -> AlasSubmarineConfigSnapshot:
        return self.open().validate_campaign_submarine_config(**values)

    def campaign_hard_remain(self) -> int:
        return self.open().campaign_hard_remain()

    def raid_remain(self, event: str, mode: str) -> int:
        return self.open().raid_remain(event=event, mode=mode)

    def raid_page_visible(self, event: str) -> bool:
        return self.open().raid_page_visible(event=event)

    def click_event_story_skip_confirm(self) -> ActionReceipt:
        return self.open().click_event_story_skip_confirm()

    def click_event_story_option(self, option_index: int) -> ActionReceipt:
        return self.open().click_event_story_option(option_index)

    def click_event_story_skip(self) -> ActionReceipt:
        return self.open().click_event_story_skip()

    def click_raid_stage(self, event: str, mode: str) -> ActionReceipt:
        return self.open().click_raid_stage(event=event, mode=mode)

    def click_raid_advanced_challenge(self, event: str) -> ActionReceipt:
        return self.open().click_raid_advanced_challenge(event=event)

    def enter_raid_page(self, event: str) -> ActionReceipt:
        return self.open().enter_raid_page(event=event)

    def click_raid_home(self, event: str) -> ActionReceipt:
        return self.open().click_raid_home(event=event)

    def raid_fleet_selection_visible(self, event: str) -> bool:
        return self.open().raid_fleet_selection_visible(event=event)

    def raid_fleet_ready(self, event: str) -> bool:
        return self.open().raid_fleet_ready(event=event)

    def click_raid_fleet_back(self, event: str) -> ActionReceipt:
        return self.open().click_raid_fleet_back(event=event)

    def click_raid_fleet_start(self, event: str) -> ActionReceipt:
        return self.open().click_raid_fleet_start(event=event)

    def click_raid_fleet_recommend(self, event: str) -> ActionReceipt:
        return self.open().click_raid_fleet_recommend(event=event)

    def raid_multiple_sortie_visible(self, event: str) -> bool:
        return self.open().raid_multiple_sortie_visible(event=event)

    def raid_multiple_sortie_state(self, event: str) -> RaidMultipleSortieState:
        return self.open().raid_multiple_sortie_state(event=event)

    def click_raid_multiple_sortie_back(self, event: str) -> ActionReceipt:
        return self.open().click_raid_multiple_sortie_back(event=event)

    @staticmethod
    def _login_probe_is_transient(adapter: AlasSemanticAdapter, exc: Exception) -> bool:
        snapshot = adapter._login_flow.snapshot()
        return bool(
            snapshot.active
            and time.monotonic() <= snapshot.passive_transition_until
            and (
                isinstance(exc, ObserverTransportError)
                or str(exc)
                in (
                    "observer snapshot is stale",
                    "observer endpoints are not generation-coherent",
                    "Msgbox snapshots are not coherent",
                    "game activity is not top-resumed",
                )
            )
        )

    def server_maintenance_visible(self) -> bool:
        adapter = self.open()
        if adapter.oracle.enabled("overlay/network-reconnect/confirm"):
            # ui_additional owns NetworkDown immediately after the maintenance
            # and update probes.  Do not make a different Msgbox reader race
            # the already-proven global reconnect owner.
            return False
        try:
            return adapter.server_maintenance_visible()
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise

    def login_update_in_progress(self) -> bool:
        adapter = self.open()
        try:
            return adapter.login_update_in_progress()
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise

    def _login_update_restart_required_on_frame(
        self, adapter: AlasSemanticAdapter
    ) -> bool:
        """Evaluate update completion from one coherent immutable frame."""

        live_oracle = adapter.oracle
        self.refresh_frame()
        frame_oracle = adapter._require_frame_observation_oracle()
        # The update-progress latch belongs to this game process, not to an
        # individual frame reader. Preserve it while the immutable oracle
        # evaluates the completion text/opening transition.
        frame_oracle._login_update_seen = live_oracle._login_update_seen
        frame_oracle._login_update_restart_consumed = (
            live_oracle._login_update_restart_consumed
        )
        required = frame_oracle.login_update_restart_required()
        if frame_oracle._login_update_restart_consumed:
            live_oracle._login_update_restart_consumed = True
        return required

    def restart_game_for_manager(self) -> bool:
        """Cold-restart the configured game for ALAS GameManager ownership."""

        factory = self._runtime_handle_factory
        if factory is None or self.package_process_lease is not None:
            raise SemanticGateClosed(
                "game-manager restart requires an owned ADB runtime"
            )
        if self.adapter is not None:
            self.adapter.end_login()
        self.adapter = None
        self._release_owned_runtime_handle()
        factory.restart_game(self.component)
        # GameManager's LoginHandler owns the next login-flow boundary.  Mark
        # the freshly restarted process so that boundary receives the same
        # boot grace as an in-flow post-update restart without nesting flows.
        self._game_manager_restart_pending = True
        if self.trace is not None:
            self.trace.emit("semantic.game_manager.restart")
        return True

    def run_mission_reward(
        self,
        daily: bool = True,
        weekly: bool = True,
        timeout_seconds: float = 30.0,
        allow_claim_once: bool = False,
    ) -> Union[MissionRunReceipt, MissionClaimReceipt]:
        return self.open().run_mission_reward(
            daily=daily,
            weekly=weekly,
            timeout_seconds=timeout_seconds,
            allow_claim_once=allow_claim_once,
        )

    def claim_mission_rewards_once(
        self,
        timeout_seconds: float = 30.0,
    ) -> MissionClaimReceipt:
        return self.open().claim_mission_rewards_once(
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def reject_raw_input(operation: str) -> None:
        AlasSemanticAdapter.reject_raw_input(operation)
