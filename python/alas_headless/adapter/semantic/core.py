"""Core for the typed ALAS boundary."""

from __future__ import annotations

from contextlib import contextmanager

import time
import sys
from ...oracle.errors import SemanticSnapshotStale
from dataclasses import replace
from typing import Any, Callable, List, Mapping, Optional, Set, Tuple, Union
from ...adapter import (
    ActionGrantExhausted,
    ActionLedger,
    ActionNotDispatched,
    DEFAULT_CAPABILITY_INVENTORY,
    ObservationRegistry,
    ObserveRequest,
    RecoveryPolicy,
    SemanticFrameIdentity,
    StaleFrameError,
    compatibility_policy_sha256,
    compatibility_profile,
)
from ...adapter.flows import LoginFlow, register_login_observations
from ...semantic_oracle import (
    ActionReceipt,
    AwakenCostState,
    AwakenExecutionReceipt,
    EnhancementExecutionReceipt,
    EnhancementNoMaterialReceipt,
    EnhancementRejectedReceipt,
    RetirementExecutionReceipt,
    RetirementNoCandidateReceipt,
    SemanticGateClosed,
    SemanticOracle,
)
from .contracts import (
    AlasSemanticActionDeferred,
    AlasSemanticUnmapped,
    CampaignAutoSearchCompletionProof,
    CampaignAutoSearchEvidenceBundle,
    _BattlePassFlowContext,
    _BuildFlowContext,
    _CampaignFlowContext,
    _CommissionFlowContext,
    _DataKeyFlowContext,
    _DormFlowContext,
    _MailFlowContext,
    _MinigameFlowContext,
    _MissionFlowContext,
    _OperationSirenGlobeSwipeIntent,
    _ResearchFlowContext,
    _SupplyPackFlowContext,
)
from .legacy import _legacy_action_grants
from .resources import (
    BATTLE_PASS_VIRTUAL_RESOURCES,
    BUILD_POOL_NAVBAR_PATTERN,
    BUILD_SIDE_NAVBAR_PATTERN,
    BUILD_VIRTUAL_RESOURCES,
    CAMPAIGN_CLICK_RESOURCES,
    CAMPAIGN_FLEET_BAR_PATTERN,
    CAMPAIGN_VIRTUAL_RESOURCES,
    COMMISSION_CLICK_RESOURCES,
    COMMISSION_ROW_PATTERN,
    COMMISSION_VIRTUAL_RESOURCES,
    DATA_KEY_VIRTUAL_RESOURCES,
    DEFAULT_ALAS_BUTTON_TARGETS,
    DORM_VIRTUAL_RESOURCES,
    MAIL_CLICK_RESOURCES,
    MAIL_VIRTUAL_RESOURCES,
    MINIGAME_VIRTUAL_RESOURCES,
    MISSION_NAVBAR_PATTERN,
    MISSION_VIRTUAL_RESOURCES,
    PAGE_VIRTUAL_RESOURCES,
    RESEARCH_VIRTUAL_RESOURCES,
    SUPPLY_PACK_VIRTUAL_RESOURCES,
    TACTICAL_VIRTUAL_RESOURCES,
)


class CoreAdapterPorts:
    """Core ports on the shared adapter context."""

    def __init__(
        self,
        oracle: SemanticOracle,
        package_gate: Callable[[], None],
        mappings: Mapping[str, str] = DEFAULT_ALAS_BUTTON_TARGETS,
        allow_mission_claim_once: bool = False,
        allow_mail_mutations: bool = False,
        mail_mutation_budget: int = 0,
        minigame_play_budget: int = 0,
        meta_assist_budget: int = 0,
        operation_siren_coordinate_checkout_budget: int = 0,
        allow_tactical_rewards: bool = False,
        tactical_assign_budget: int = 0,
        commission_reward_budget: int = 0,
        commission_start_budget: int = 0,
        daily_execute_budget: int = 0,
        exercise_execute_budget: int = 0,
        exercise_refresh_budget: int = 0,
        research_reward_budget: int = 0,
        research_start_budget: int = 0,
        dorm_collect_budget: int = 0,
        dorm_feed_budget: int = 0,
        awaken_budget: int = 0,
        enhancement_budget: int = 0,
        build_submit_budget: int = 0,
        retirement_budget: int = 0,
        shop_purchase_budget: int = 0,
        campaign_stage_entry_budget: int = 0,
        campaign_fleet_mutation_budget: int = 0,
        campaign_sortie_budget: int = 0,
        campaign_combat_budget: int = 0,
        campaign_viewport_swipe_budget: int = 0,
        campaign_camera_positioning_budget: int = 0,
        frame_observation_oracle: Optional[Callable[[], Any]] = None,
        frame_identity_provider: Optional[
            Callable[[], SemanticFrameIdentity]
        ] = None,
        input_frame_refresher: Optional[Callable[[], Any]] = None,
        tactical_input_frame_refresher: Optional[Callable[[], Any]] = None,
        action_ledger: Optional[ActionLedger] = None,
    ) -> None:
        if package_gate is None:
            raise ValueError("semantic ALAS mode requires a package identity gate")
        self._live_oracle = oracle
        self._observation_oracle_override = None
        self._package_gate = package_gate
        self._mappings = dict(mappings)
        if not self._mappings or any(
            not name or not semantic_id
            for name, semantic_id in self._mappings.items()
        ):
            raise ValueError("ALAS semantic mappings must be non-empty")
        for label, budget in (
            ("mail mutation", mail_mutation_budget),
            ("minigame play", minigame_play_budget),
            ("META assist", meta_assist_budget),
            (
                "Operation Siren coordinate checkout",
                operation_siren_coordinate_checkout_budget,
            ),
            ("tactical assign", tactical_assign_budget),
            ("commission reward", commission_reward_budget),
            ("commission start", commission_start_budget),
            ("daily execute", daily_execute_budget),
            ("exercise execute", exercise_execute_budget),
            ("exercise refresh", exercise_refresh_budget),
            ("research reward", research_reward_budget),
            ("research start", research_start_budget),
            ("dorm collect", dorm_collect_budget),
            ("dorm feed", dorm_feed_budget),
            ("awaken", awaken_budget),
            ("enhancement", enhancement_budget),
            ("build submit", build_submit_budget),
            ("retirement", retirement_budget),
            ("shop purchase", shop_purchase_budget),
            ("campaign stage entry", campaign_stage_entry_budget),
            ("campaign fleet mutation", campaign_fleet_mutation_budget),
            ("campaign sortie", campaign_sortie_budget),
            ("campaign combat", campaign_combat_budget),
            ("campaign viewport swipe", campaign_viewport_swipe_budget),
            ("campaign camera positioning", campaign_camera_positioning_budget),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or budget < 0
            ):
                raise ValueError(
                    "{0} budget must be a non-negative integer".format(label)
                )
        if action_ledger is None:
            grants = _legacy_action_grants(
                allow_mission_claim_once=allow_mission_claim_once,
                allow_mail_mutations=allow_mail_mutations,
                mail_mutation_budget=mail_mutation_budget,
                minigame_play_budget=minigame_play_budget,
                meta_assist_budget=meta_assist_budget,
                operation_siren_coordinate_checkout_budget=(
                    operation_siren_coordinate_checkout_budget
                ),
                allow_tactical_rewards=allow_tactical_rewards,
                tactical_assign_budget=tactical_assign_budget,
                commission_reward_budget=commission_reward_budget,
                commission_start_budget=commission_start_budget,
                daily_execute_budget=daily_execute_budget,
                exercise_execute_budget=exercise_execute_budget,
                exercise_refresh_budget=exercise_refresh_budget,
                research_reward_budget=research_reward_budget,
                research_start_budget=research_start_budget,
                dorm_collect_budget=dorm_collect_budget,
                dorm_feed_budget=dorm_feed_budget,
                awaken_budget=awaken_budget,
                enhancement_budget=enhancement_budget,
                build_submit_budget=build_submit_budget,
                retirement_budget=retirement_budget,
                shop_purchase_budget=shop_purchase_budget,
                campaign_stage_entry_budget=campaign_stage_entry_budget,
                campaign_fleet_mutation_budget=campaign_fleet_mutation_budget,
                campaign_sortie_budget=campaign_sortie_budget,
                campaign_combat_budget=campaign_combat_budget,
                campaign_viewport_swipe_budget=campaign_viewport_swipe_budget,
                campaign_camera_positioning_budget=(
                    campaign_camera_positioning_budget
                ),
            )
            profile = compatibility_profile("legacy-adapter", grants)
            action_ledger = ActionLedger(
                profile=profile,
                inventory=DEFAULT_CAPABILITY_INVENTORY,
                grants=grants,
                recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
                policy_sha256=compatibility_policy_sha256(
                    profile.profile_id,
                    grants,
                ),
            )
        elif not isinstance(action_ledger, ActionLedger):
            raise TypeError("semantic action ledger is invalid")
        action_ledger.require_preflight()
        self._action_ledger = action_ledger
        self._campaign_evidence_sequence = 0
        # Completed audit records have no input authority. Keep them readable
        # after ALAS.run returns; task cleanup discards pending intents only.
        self._daily_execution_receipts: List[ActionReceipt] = []
        self._last_retirement_receipt: Optional[
            Union[RetirementExecutionReceipt, RetirementNoCandidateReceipt]
        ] = None
        self._awaken_receipts: List[AwakenExecutionReceipt] = []
        self._awaken_cost_observations: List[AwakenCostState] = []
        self._enhancement_receipts: List[
            Union[EnhancementExecutionReceipt, EnhancementNoMaterialReceipt, EnhancementRejectedReceipt]
        ] = []
        self._frame_observation_oracle = frame_observation_oracle
        self._frame_identity_provider = frame_identity_provider
        if input_frame_refresher is not None and not callable(input_frame_refresher):
            raise TypeError("semantic input frame refresher is invalid")
        self._input_frame_refresher = input_frame_refresher
        if (
            tactical_input_frame_refresher is not None
            and not callable(tactical_input_frame_refresher)
        ):
            raise TypeError("semantic Tactical input frame refresher is invalid")
        self._tactical_input_frame_refresher = tactical_input_frame_refresher
        self._compat_observation_ordinal = 0
        self._observation_registry = ObservationRegistry()
        register_login_observations(
            self._observation_registry,
            enabled=lambda semantic_id: (
                self._require_frame_observation_oracle().enabled(semantic_id)
            ),
            frame_identity=self._frame_identity_for_request,
        )
        self._login_flow = LoginFlow(
            lambda: self._package_gate(),
            observation_oracle=self._require_frame_observation_oracle,
            monotonic=lambda: time.monotonic(),
            entry_observer=self._dispatch_login_check_registry,
        )

        self.reset_task_state()

    @property
    def oracle(self) -> Any:
        """Route one legacy ``appear`` traversal through its leased frame."""

        if self._observation_oracle_override is not None:
            return self._observation_oracle_override
        return self._live_oracle

    def reset_task_state(self) -> None:
        """Discard task-owned contexts and proofs, retaining grants and runtime."""

        self._prepared_input_oracle = None
        self._storage_box_candidate = None
        self._storage_box_use_receipt = None
        self._storage_box_use_quantity = None
        self._storage_box_equipment_receipt = None
        self._storage_box_destroy_receipt = None
        self._mission_context: Optional[_MissionFlowContext] = None
        self._mail_context: Optional[_MailFlowContext] = None
        self._commission_context: Optional[_CommissionFlowContext] = None
        self._research_context: Optional[_ResearchFlowContext] = None
        self._dorm_context: Optional[_DormFlowContext] = None
        self._dorm_parent_commission: Optional[_CommissionFlowContext] = None
        self._build_context: Optional[_BuildFlowContext] = None
        self._supply_pack_context: Optional[_SupplyPackFlowContext] = None
        self._battle_pass_context: Optional[_BattlePassFlowContext] = None
        self._data_key_context: Optional[_DataKeyFlowContext] = None
        self._minigame_context: Optional[_MinigameFlowContext] = None
        self._campaign_context: Optional[_CampaignFlowContext] = None
        self._gems_farming_hard_profile: Optional[
            Tuple[str, int, str, str]
        ] = None
        self._daily_kind: Optional[str] = None
        self._daily_stage: Optional[int] = None
        self._daily_pending_receipt: Optional[ActionReceipt] = None
        self._daily_quick_reward_closed = False
        self._daily_pending_stage_receipt: Optional[ActionReceipt] = None
        self._daily_stage_confirmed = False
        self._daily_transition_until = 0.0
        self._current_raid_result_event: Optional[str] = None
        self._network_reconnect_transition_until = 0.0
        self._main_battle_transition_receipt: Optional[ActionReceipt] = None
        self._main_shop_transition_receipt: Optional[ActionReceipt] = None
        self._main_shop_transition_until = 0.0
        self._main_dock_transition_receipt: Optional[ActionReceipt] = None
        self._main_dock_transition_until = 0.0
        self._event_story_transition_until = 0.0
        self._campaign_event_entry_transition_until = 0.0
        self._operation_siren_entry_transition_until = 0.0
        self._operation_siren_exit_receipt: Optional[ActionReceipt] = None
        self._operation_siren_exit_handoff = None
        self._operation_siren_abyssal_entry_receipt: Optional[ActionReceipt] = None
        self._operation_siren_abyssal_entry_input_count: Optional[int] = None
        self._operation_siren_page_remount_until = 0.0
        self._operation_siren_entry_receipt: Optional[ActionReceipt] = None
        self._campaign_archive_entry_receipt: Optional[ActionReceipt] = None
        self._campaign_archive_entry_transition_until = 0.0
        self._operation_siren_globe_map_receipt: Optional[ActionReceipt] = None
        self._operation_siren_order_entry_receipt: Optional[ActionReceipt] = None
        self._operation_siren_adaptability_info_receipt: Optional[ActionReceipt] = None
        self._operation_siren_auto_search_transition_until = 0.0
        self._operation_siren_auto_search_active = False
        self._operation_siren_startup_search_provisional = False
        self._operation_siren_auto_search_completed_empty = False
        self._operation_siren_combat_active = False
        self._operation_siren_combat_fleet: Optional[int] = None
        self._operation_siren_defeated_fleets: set[int] = set()
        self._meta_beacon_active = False
        self._meta_assist_active = False
        self._meta_precombat_start_receipt = None
        self._meta_precombat_start_until = 0.0
        self._meta_precombat_back_receipt = None
        self._meta_precombat_back_until = 0.0
        self._meta_assist_entry_receipt = None
        self._meta_assist_entry_until = 0.0
        self._main_more_entry_receipt = None
        self._main_more_entry_until = 0.0
        self._commission_return_transition_until = 0.0
        self._mission_page_return_transition_until = 0.0
        self._meowfficer_return_transition_until = 0.0
        self._build_return_transition_until = 0.0
        self._guild_return_transition_until = 0.0
        self._guild_message_close_receipt = None
        self._dorm_return_transition_until = 0.0
        self._main_guild_entry_receipt = None
        self._main_guild_entry_until = 0.0
        self._guild_logistics_transition_until = 0.0
        self._shipyard_entry_receipt = None
        self._meta_entry_receipt = None
        self._meta_current_create_handoff = None
        self._orphan_tactical_prompt_probe = None
        self._meta_home_receipt = None
        self._research_back_receipt = None
        self._inherited_home_return_receipt = None
        self._inherited_home_return_until = 0.0
        self._shop_home_handoff = None
        self._commission_navigation_handoff = None
        self._inherited_withdraw_open_receipt = None
        self._inherited_withdraw_confirm_receipt = None
        self._research_progress_close_receipt = None
        self._research_progress_close_until = 0.0
        self._meta_current_entry_receipt = None
        self._meta_dossier_entry_receipt = None
        self._meta_reward_close_receipt = None
        self._operation_siren_reward_close_receipt = None
        self._meta_character_entry_receipt = None
        self._daily_entry_receipt = None
        self._daily_entry_transition_until = 0.0
        self._main_tech_entry_receipt = None
        self._main_storage_entry_receipt = None
        self._main_live_entry_receipt = None
        self._private_quarters_entry_receipt = None
        self._private_quarters_dialogue_receipt = None
        self._private_quarters_transition_until = 0.0
        self._private_quarters_home_transition_until = 0.0
        self._private_quarters_entry_transition_until = 0.0
        self._research_menu_return_transition_until = 0.0
        self._operation_siren_pending_order: Optional[str] = None
        self._exercise_pending = False
        self._exercise_execution_active = False
        self._exercise_chapter_back_transition_until = 0.0
        self._exercise_entry_transition_until = 0.0
        self._exercise_entry_receipt: Optional[ActionReceipt] = None
        self._exercise_page_back_transition_until = 0.0
        self._exercise_chapter_entry_transition_until = 0.0
        self._last_campaign_auto_search_completion: Optional[
            CampaignAutoSearchCompletionProof
        ] = None
        self._campaign_evidence_bundle: Optional[
            CampaignAutoSearchEvidenceBundle
        ] = None
        self._next_campaign_evidence_owner: Optional[str] = None
        self._operation_siren_globe_swipe_intent: Optional[
            _OperationSirenGlobeSwipeIntent
        ] = None
        self._operation_siren_camera_geometry = None
        self._operation_siren_map_swipe_intent = None
        self._awaken_flow_active = False
        self._enhancement_flow_active = False
        self._enhancement_current_candidate = None
        self._enhancement_no_material_cards: Set[Tuple[int, int, str, int]] = set()
        self._observer_stale_since: Optional[float] = None
        self._login_flow.end()

    def _require_action_grant(self, capability: str) -> None:
        try:
            self._action_ledger.require_available(capability)
        except ActionGrantExhausted as exc:
            raise AlasSemanticActionDeferred(
                "{0}: task action grant is exhausted".format(capability)
            ) from exc

    def _dispatch_mutation(
        self,
        capability: str,
        operation: Callable[[], Any],
    ) -> Any:
        # Only a refusal before entering the backend is task-local. Do not
        # translate backend errors based on a grant already burned by input.
        self._require_action_grant(capability)
        if isinstance(self.oracle, SemanticOracle):
            dispatch_count = self.oracle.input_dispatch_count
            backend_operation = operation

            def tracked_operation() -> Any:
                try:
                    return backend_operation()
                except Exception as exc:
                    if self.oracle.input_dispatch_count == dispatch_count:
                        raise ActionNotDispatched(exc) from exc
                    if isinstance(exc, SemanticSnapshotStale):
                        exc.input_outcome_uncertain = True
                    raise

            operation = tracked_operation
        dispatch = self._action_ledger.dispatch(capability, operation)
        if isinstance(
            dispatch.value,
            (
                ActionReceipt,
                AwakenExecutionReceipt,
                EnhancementExecutionReceipt,
                EnhancementNoMaterialReceipt,
                EnhancementRejectedReceipt,
                RetirementExecutionReceipt,
                RetirementNoCandidateReceipt,
            ),
        ):
            return replace(
                dispatch.value,
                policy_sha256=dispatch.policy_sha256,
                capability_id=dispatch.capability,
            )
        return dispatch.value

    def _require_frame_observation_oracle(self) -> Any:
        provider = self._frame_observation_oracle
        if provider is None:
            raise StaleFrameError()
        reader = provider()
        if reader is None:
            raise StaleFrameError()
        # The retry limit belongs to the game session, while each ALAS
        # screenshot boundary creates a new immutable observation reader.
        reader._login_update_retry_attempted = (
            getattr(self.oracle, "_login_update_retry_attempted", False)
        )
        return reader

    @contextmanager
    def prepared_input_frame(self, provider: Callable[[], Any]):
        """Offer the session's fresh frame to one nested input preparation."""
        previous = self._prepared_input_oracle
        self._prepared_input_oracle = provider
        try:
            yield
        finally:
            self._prepared_input_oracle = previous

    def _fresh_input_oracle(self) -> Any:
        """Bind a mutation's final semantic proof to one fresh ALAS frame."""

        prepared = self._prepared_input_oracle
        self._prepared_input_oracle = None
        if prepared is not None:
            try:
                return prepared()
            except StaleFrameError:
                # A wait, input, refresh or runtime change can invalidate the
                # offered frame. The usual acquisition owns recovery.
                pass
        if (
            self._input_frame_refresher is not None
            and self._frame_observation_oracle is not None
        ):
            self._input_frame_refresher()
            return self._require_frame_observation_oracle()
        return self.oracle

    def _frame_or_live_observation_oracle(self) -> Any:
        """Use ALAS' immutable screenshot frame when one is currently leased."""

        try:
            return self._require_frame_observation_oracle()
        except StaleFrameError:
            # Direct runner probes can occur just after an exact click has
            # invalidated the screenshot lease. They remain read-only and use
            # the live oracle's unchanged coherence and structural checks.
            return self.oracle

    def _current_frame_identity(self) -> SemanticFrameIdentity:
        provider = self._frame_identity_provider
        if provider is None:
            raise StaleFrameError()
        identity = provider()
        if not isinstance(identity, SemanticFrameIdentity):
            raise StaleFrameError()
        return identity

    def _frame_identity_for_request(
        self, request: ObserveRequest
    ) -> SemanticFrameIdentity:
        identity = self._current_frame_identity()
        if identity.frame_id != request.frame_id:
            raise StaleFrameError()
        return identity

    @staticmethod
    def _button_name(button: Any) -> str:
        name = button if isinstance(button, str) else getattr(button, "name", None)
        if not isinstance(name, str) or not name:
            raise AlasSemanticUnmapped("ALAS resource has no stable name")
        # Native InfoHandler annotates these shared objects for logging. Their
        # object identity, not the caller's arbitrary suffix, identifies the
        # reviewed base resource. Do not import assets here (which could load
        # pixel dependencies), or normalize an unrelated object/string merely
        # because its name has the same prefix. Context and typed prompt checks
        # remain in the normal observation/input dispatch below this seam.
        if not isinstance(button, str):
            assets = sys.modules.get("module.handler.assets")
            if assets is not None:
                for base in ("POPUP_CONFIRM", "POPUP_CONFIRM_WHITE", "POPUP_CANCEL"):
                    if getattr(assets, base, None) is button:
                        if base == "POPUP_CONFIRM" and name in (
                            "POPUP_CONFIRM_GACHA_PREP", "POPUP_CONFIRM_GACHA_ORDER"
                        ):
                            # These reviewed native aliases distinguish warning
                            # dismissal from resource-consuming order submission.
                            return name
                        return base
        # InfoHandler temporarily annotates this reviewed shared asset between
        # its presence probe and click. Keep legacy string aliases for existing
        # callers; newly annotated real shared assets use object identity above.
        if name in (
            "POPUP_CONFIRM_RESEARCH_START",
            "POPUP_CONFIRM_RESEARCH_QUEUE",
            "POPUP_CONFIRM_RESEARCH_CANCEL",
            "POPUP_CONFIRM_LOGIN",
            "POPUP_CONFIRM_CAMPAIGN_RECONNECT",
            "POPUP_CONFIRM_COMBAT_EXECUTE",
            "POPUP_CONFIRM_COMBAT_STATUS",
            "POPUP_CONFIRM_WHITE_LOGIN",
            "POPUP_CONFIRM_WHITE_UI_ADDITIONAL",
            "POPUP_CONFIRM_WHITE_CAMPAIGN_RECONNECT",
            "POPUP_CONFIRM_UI_ADDITIONAL",
            "POPUP_CONFIRM_MAIL_CLAIM",
            "POPUP_CONFIRM_MAIL_QUIT",
            "POPUP_CONFIRM_TICKETS_FULL",
            "POPUP_CONFIRM_MINIGAME_ENTER",
            "POPUP_CONFIRM_FINISH_ORDERS",
            "POPUP_CONFIRM_TACTICAL",
            "POPUP_CONFIRM_MISSION_REWARD",
            "POPUP_CONFIRM_COMMISSION_START",
        ):
            return (
                "POPUP_CONFIRM_WHITE"
                if name in ("POPUP_CONFIRM_WHITE_LOGIN", "POPUP_CONFIRM_WHITE_UI_ADDITIONAL",
                            "POPUP_CONFIRM_WHITE_CAMPAIGN_RECONNECT")
                else "POPUP_CONFIRM"
            )
        return name

    def semantic_id_for(self, button: Any) -> str:
        name = self._button_name(button)
        try:
            return self._mappings[name]
        except KeyError as exc:
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(name)
            ) from exc

    def supports(self, button: Any) -> bool:
        try:
            name = self._button_name(button)
        except AlasSemanticUnmapped:
            return False
        return bool(
            name in self._mappings
            or name in MISSION_VIRTUAL_RESOURCES
            or name in MAIL_VIRTUAL_RESOURCES
            or name in MAIL_CLICK_RESOURCES
            or name in COMMISSION_VIRTUAL_RESOURCES
            or name in COMMISSION_CLICK_RESOURCES
            or name in CAMPAIGN_VIRTUAL_RESOURCES
            or name in CAMPAIGN_CLICK_RESOURCES
            or name in PAGE_VIRTUAL_RESOURCES
            or name in RESEARCH_VIRTUAL_RESOURCES
            or name in DORM_VIRTUAL_RESOURCES
            or name in MINIGAME_VIRTUAL_RESOURCES
            or name in BUILD_VIRTUAL_RESOURCES
            or name in TACTICAL_VIRTUAL_RESOURCES
            or name in BATTLE_PASS_VIRTUAL_RESOURCES
            or name in SUPPLY_PACK_VIRTUAL_RESOURCES
            or name in DATA_KEY_VIRTUAL_RESOURCES
            or CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name)
            or MISSION_NAVBAR_PATTERN.fullmatch(name)
            or COMMISSION_ROW_PATTERN.fullmatch(name)
            or BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
            or BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        )

    @staticmethod
    def reject_raw_input(operation: str) -> None:
        raise SemanticGateClosed(
            "raw ALAS input is disabled in semantic mode: {0}".format(operation)
        )
