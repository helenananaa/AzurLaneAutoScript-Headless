"""Campaign for the typed ALAS boundary."""

from __future__ import annotations

import re
import time
from dataclasses import replace
from numbers import Real
from typing import Optional, Tuple
from ...alas_enemy_priority_config_contract import (
    AlasEnemyPriorityConfigSnapshot,
    validate_alas_enemy_priority_config,
)
from ...alas_hp_control_config_contract import (
    AlasHpControlConfigSnapshot,
    validate_alas_hp_control_config,
)
from ...alas_submarine_config_contract import (
    AlasSubmarineConfigSnapshot,
    validate_alas_submarine_config,
)
from ...semantic_oracle import (
    ActionReceipt,
    CampaignMapAchievementState,
    CampaignPageState,
    SemanticGateClosed,
    SemanticOracle,
    SemanticTargetMissing,
)
from .contracts import (
    AlasSemanticUnmapped,
    CampaignAutoSearchCompletionProof,
    CampaignAutoSearchEvidenceBundle,
    CampaignSortieProof,
    _CampaignFlowContext,
)
from .dispatch_result import UNHANDLED
from .campaign_health import CampaignHealthAdapterPorts
from ...oracle.errors import SemanticCampaignFleetIncomplete
from .resources import (
    CAMPAIGN_AUTO_SEARCH_ON_RESOURCES,
    CAMPAIGN_AUTO_SEARCH_RESOURCES,
    CAMPAIGN_FLEET_ROW_RESOURCES,
    CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES,
    CAMPAIGN_STRATEGY_FORMATION_RESOURCES,
    EVENT_CAMPAIGN_ASIDE_RESOURCES,
)


class CampaignAdapterPorts(CampaignHealthAdapterPorts):
    """Campaign ports on the shared adapter context."""

    def war_archives_campaign_visible(self) -> bool:
        """Expose the exact archive stage-page identity to original ALAS."""

        self._package_gate()
        return self.oracle.war_archives_campaign_page_visible()

    def _campaign_page_back_visible(self) -> bool:
        if self.oracle.war_archives_campaign_page_visible():
            return True
        try:
            self.oracle.campaign_page_state()
        except SemanticGateClosed:
            return False
        return True

    def war_archives_data_key_count(self) -> Tuple[int, int]:
        """Return the typed archive key inventory on the campaign page."""

        self._package_gate()
        return self.oracle.war_archives_campaign_data_key_count()

    def open_war_archives_campaign(self, event: str, category: str) -> ActionReceipt:
        """Perform the original archive search against typed card identities."""

        self._package_gate()
        expected_category, _sprite = self.oracle.war_archives_campaign_identity(event)
        if category != expected_category:
            raise SemanticGateClosed(
                "war archives category does not match configured campaign"
            )
        if not self.oracle.war_archives_page_visible():
            raise SemanticGateClosed("war archives campaign search requires landing page")
        if self.oracle.war_archives_category() != category:
            receipt = self._fresh_input_oracle().click_war_archives_category(category)
            deadline = time.monotonic() + 20.0
            while True:
                try:
                    if self.oracle.war_archives_category() == category:
                        break
                except SemanticGateClosed:
                    pass
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "war archives category did not reach postcondition"
                    )
                time.sleep(0.2)
            if receipt.semantic_id != "archive/category/" + category:
                raise SemanticGateClosed("war archives category receipt changed")

        for _ in range(32):
            position = self.oracle.war_archives_campaign_card_position(event)
            if position == "visible":
                settle_deadline = time.monotonic() + 10.0
                while True:
                    try:
                        receipt = self._fresh_input_oracle().click_war_archives_campaign(event)
                        break
                    except SemanticGateClosed as exc:
                        # Scrolling publishes button/image geometry across
                        # frames. This exact error is raised before any tap;
                        # wait for the unchanged strict input proof to succeed.
                        # Duplicate controls, blockers and dispatch errors are
                        # not a settling condition and propagate immediately.
                        if str(exc) != "war archives campaign control is not aligned":
                            raise
                        if time.monotonic() >= settle_deadline:
                            raise SemanticGateClosed(
                                "war archives campaign control did not stabilize"
                            ) from exc
                        time.sleep(0.2)
                deadline = time.monotonic() + 30.0
                while True:
                    if self.oracle.war_archives_campaign_page_visible():
                        state = self.oracle.campaign_page_state()
                        if state.generation <= receipt.generation:
                            raise SemanticGateClosed(
                                "war archives campaign postcondition predates input"
                            )
                        return receipt
                    if time.monotonic() >= deadline:
                        raise SemanticGateClosed(
                            "war archives campaign page did not open"
                        )
                    time.sleep(0.25)

            before_generation, before_bounds = (
                self.oracle.war_archives_campaign_card_geometry(event)
            )
            swipe = self._fresh_input_oracle().swipe_war_archives_campaign_toward(event)
            deadline = time.monotonic() + 10.0
            while True:
                generation, bounds = self.oracle.war_archives_campaign_card_geometry(
                    event
                )
                if generation > max(before_generation, swipe.generation) and bounds != before_bounds:
                    break
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "war archives campaign list did not advance"
                    )
                time.sleep(0.2)
        raise SemanticGateClosed("war archives campaign search exceeded list bounds")

    def bind_next_campaign_evidence_owner(self, owner: str) -> None:
        if self._campaign_context is not None:
            raise SemanticGateClosed(
                "campaign evidence owner cannot change during an active flow"
            )
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", owner) is None:
            raise ValueError("campaign evidence owner is malformed")
        self._campaign_evidence_bundle = None
        self._next_campaign_evidence_owner = owner

    def consume_campaign_auto_search_evidence(
        self,
        *,
        expected_owner: str,
        expected_stage_code: str,
        expected_mode: str,
    ) -> Optional[CampaignAutoSearchEvidenceBundle]:
        """Consume, clear, and integrity-check one transaction-bound bundle."""

        bundle = self._campaign_evidence_bundle
        self._campaign_evidence_bundle = None
        self._next_campaign_evidence_owner = None
        if bundle is None:
            return None
        errors = []
        if bundle.owner != expected_owner:
            errors.append("campaign_evidence.owner_mismatch")
        if bundle.stage_code != expected_stage_code.lower():
            errors.append("campaign_evidence.stage_mismatch")
        if bundle.mode != expected_mode:
            errors.append("campaign_evidence.mode_mismatch")
        sortie = bundle.sortie_proof
        completion = bundle.completion_proof
        if sortie is not None:
            if sortie.stage_code != bundle.stage_code:
                errors.append("campaign_evidence.sortie_stage_mismatch")
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in (sortie.sortie_generation, sortie.map_generation)
            ):
                errors.append("campaign_evidence.start_generation_malformed")
            elif sortie.map_generation <= sortie.sortie_generation:
                errors.append("campaign_evidence.start_generation_not_advanced")
        if completion is not None and completion.stage_code != bundle.stage_code:
            errors.append("campaign_evidence.completion_stage_mismatch")
        if completion is not None and completion.result_exit_receipt is None:
            errors.append("campaign_evidence.result_menu_retained")
        if sortie is not None and completion is not None and completion.result_exit_receipt is not None:
            chain = (
                sortie.map_generation,
                completion.combat_auto_generation,
                completion.result_generation,
                completion.result_exit_receipt.generation,
            )
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in chain
            ):
                errors.append("campaign_evidence.completion_generation_malformed")
            else:
                if completion.combat_auto_generation <= sortie.map_generation:
                    errors.append("campaign_evidence.combat_generation_not_advanced")
                if completion.result_generation <= completion.combat_auto_generation:
                    errors.append("campaign_evidence.result_generation_not_advanced")
                if (
                    completion.result_exit_receipt.generation
                    < completion.result_generation
                ):
                    errors.append("campaign_evidence.exit_receipt_stale")
        return replace(bundle, integrity_errors=tuple(errors))

    def last_campaign_auto_search_completion(
        self,
    ) -> Optional[CampaignAutoSearchCompletionProof]:
        return self._last_campaign_auto_search_completion

    def validate_campaign_hp_control_config(
        self, **values: object
    ) -> AlasHpControlConfigSnapshot:
        return validate_alas_hp_control_config(**values)

    def validate_campaign_enemy_priority_config(
        self, **values: object
    ) -> AlasEnemyPriorityConfigSnapshot:
        return validate_alas_enemy_priority_config(**values)

    def validate_campaign_submarine_config(
        self, **values: object
    ) -> AlasSubmarineConfigSnapshot:
        snapshot = validate_alas_submarine_config(**values)
        self._next_submarine_config = snapshot
        return snapshot

    def campaign_remaining_attempts(self):
        """Expose the game's reviewed stage counter to ALAS' stop decision."""
        self._require_campaign_context()
        return self.oracle.campaign_stage_state(
            self._campaign_resolved_entrance_stage()).remaining_attempts

    def campaign_stage_entry_allowed(self) -> bool:
        context = self._require_campaign_context()
        if (context.auto_search_completion is not None
                and context.auto_search_completion.result_exit_receipt is None
                and self.oracle.campaign_auto_search_reentry_available()):
            return self._action_ledger.allowed('campaign.sortie')
        return (
            self._action_ledger.allowed("campaign.stage_entry")
            and context.entry_receipt is None
        )

    def campaign_map_preparation_committed(self) -> bool:
        context = self._require_campaign_context()
        # This is a receipt query. Original ALAS owns waiting, recovery and
        # timeouts, including a retirement round trip before a fresh entry.
        return context.map_preparation_receipt is not None

    def dock_full_recovery_owned(self) -> bool:
        # The modal is account-wide. Original ALAS also calls Retirement
        # during Operation Siren search, with no campaign stage context.
        return (self._campaign_context is not None
                or self._build_context is not None
                or self._operation_siren_allows_passive_probe())

    def campaign_dock_full_visible(self) -> bool:
        if not self.dock_full_recovery_owned():
            return False
        context = self._campaign_context
        return self._frame_or_live_observation_oracle().campaign_dock_full_visible(
            (context.resolved_stage_code or context.stage_code) if context else ""
        )

    def click_campaign_dock_full_choice(self, choice: str) -> ActionReceipt:
        self._package_gate()
        if not self.dock_full_recovery_owned():
            raise SemanticGateClosed("dock-full recovery has no owned task surface")
        context = self._campaign_context
        return self.oracle.click_campaign_dock_full_choice(
            (context.resolved_stage_code or context.stage_code) if context else "",
            choice,
        )

    def arm_daemon_campaign_map_preparation(self) -> bool:
        """Record the exact inherited ALAS setting before Daemon advances it."""

        self._package_gate()
        context = self._require_campaign_context()
        if (
            context.entry_receipt is None
            or context.map_preparation_receipt is not None
            or context.daemon_auto_search_selected is not None
        ):
            raise SemanticGateClosed(
                "Daemon map preparation requires one owned stage entry"
            )
        if self._campaign_preparation_kind() != "map":
            raise SemanticGateClosed("Daemon map preparation layer is absent")
        selected = self.oracle.campaign_auto_search_selected()
        context.daemon_auto_search_selected = selected
        return selected

    def confirm_war_archives_entry_if_present(self) -> Optional[ActionReceipt]:
        """Confirm the bounded ordinary-key prompt after an archive sortie."""

        context = self._require_campaign_context()
        if context.sortie_receipt is None:
            return None
        oracle = self._fresh_input_oracle()
        cost = oracle.war_archives_entry_confirmation_cost()
        if cost is None:
            return None
        if context.archive_entry_confirm_receipt is not None:
            raise SemanticGateClosed("war archives entry confirmation is single-use")
        receipt = oracle.confirm_war_archives_entry()
        if receipt.generation <= context.sortie_receipt.generation:
            raise SemanticGateClosed("war archives entry prompt did not advance")
        context.archive_entry_confirm_receipt = receipt
        context.passive_transition_until = time.monotonic() + 60.0
        return receipt

    def campaign_auto_search_running(self) -> bool:
        context = self._require_campaign_context()
        if (
            context.sortie_receipt is None
            or context.auto_search_role_state is None
        ):
            return False
        if self.oracle.exists("reward/campaign-total/exit"):
            return False
        try:
            self.oracle.campaign_auto_search_active_state()
        except SemanticTargetMissing:
            retained = self.oracle.campaign_preparation_state(
                self._campaign_resolved_entrance_stage()
            )
            if retained is None:
                if (
                    isinstance(context.sortie_receipt.generation, bool)
                    or not isinstance(context.sortie_receipt.generation, int)
                ):
                    raise
                if time.monotonic() > context.passive_transition_until:
                    raise
                # After the exact sortie click, Unity can destroy the fleet
                # overlay before mounting LevelGrid/pre-combat/combat.  That
                # empty interval is a normal passive load, not evidence that
                # official auto-search was ignored.  Wait only inside the
                # 30-second deadline armed by the sortie receipt; the original
                # ALAS loop owns retry and no additional input is admitted.
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                return False
            if (
                getattr(retained, "kind", None) != "fleet"
                or getattr(retained, "stage_code", None) != context.stage_code
                or isinstance(getattr(retained, "generation", None), bool)
                or not isinstance(getattr(retained, "generation", None), int)
                or isinstance(context.sortie_receipt.generation, bool)
                or not isinstance(context.sortie_receipt.generation, int)
                or retained.generation <= context.sortie_receipt.generation
            ):
                raise
            if (
                context.retained_preparation_generation is not None
                and retained.generation < context.retained_preparation_generation
            ):
                raise SemanticGateClosed(
                    "retained campaign fleet-preparation generation moved backwards"
                )
            if retained.generation == context.retained_preparation_generation:
                context.retained_preparation_stable_reads += 1
            else:
                context.retained_preparation_generation = retained.generation
                context.retained_preparation_stable_reads = 1
            if context.retained_preparation_stable_reads >= 8:
                raise SemanticGateClosed(
                    "retained campaign fleet-preparation generation did not advance"
                )
            # A retained fleet-preparation root can briefly mask the passive
            # transition after the already-authorized sortie.  Refresh only;
            # the original ALAS loop owns waiting/retry and no second input is
            # admitted here.
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            return False
        return True

    def campaign_auto_search_owned(self) -> bool:
        """The accepted sortie owns official combat, without a manual grid tap."""
        context = self._campaign_context
        return bool(context is not None and context.sortie_receipt is not None
                    and context.sortie_proof is not None
                    and context.auto_search_role_state is not None)

    def campaign_auto_search_map_running(self) -> bool:
        """Supply ALAS' map-running probe; a CombatUI is not a moving map."""
        self._package_gate()
        if not self.campaign_auto_search_owned():
            return False
        oracle = self._frame_or_live_observation_oracle()
        if getattr(oracle, 'campaign_auto_search_map_transition_visible', lambda: False)():
            return False
        switch = oracle.campaign_map_auto_search_state()
        return switch is not None and switch[2]

    def campaign_auto_search_result_visible(self) -> bool:
        """Observe one native-loop frame and retain its exact result proof.

        ALAS owns waiting, popup recovery, combat handlers and result exit.
        This reader supplies only the map/combat/result observation boundary.
        """
        self._package_gate()
        oracle = self._frame_or_live_observation_oracle()
        context = self._campaign_context
        if (context is not None and context.mode == 'hard'
                and context.auto_search_completion is None
                and context.sortie_proof is None
                and context.sortie_receipt is not None
                and context.sortie_receipt.semantic_id in (
                    'reward/campaign-total/continue', 'reward/campaign-total/go')
                and time.monotonic() <= context.passive_transition_until
                and oracle.enabled('reward/campaign-total/exit')):
            # One accepted Continue is leaving this result. Its controls can
            # remain mounted for another native screenshot; they cannot offer
            # a second Continue before the new sortie's map proof exists.
            return False
        if not self.campaign_auto_search_owned():
            # Native startup/recovery can inherit a result from another run.
            # Its exact menu remains navigable without claiming completion.
            return oracle.enabled("reward/campaign-total/exit")
        context = self._campaign_context
        if not oracle.enabled("reward/campaign-total/exit"):
            combat_auto = oracle.campaign_official_combat_auto_state()
            if combat_auto is not None and combat_auto[1]:
                context.auto_search_combat_generation = combat_auto[0]
            return False
        if context.auto_search_completion is not None:
            return True
        state = oracle.read_state()
        combat_generation = context.auto_search_combat_generation
        if (combat_generation is None
                or combat_generation <= context.sortie_proof.map_generation
                or state.generation <= combat_generation):
            raise SemanticGateClosed("campaign auto-search result has no advancing combat proof")
        targets = tuple(button for button in state.buttons
                        if button.name == "ButtonExit" and button.actionable
                        and button.path.endswith(
                            "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"))
        if len(targets) != 1:
            raise SemanticGateClosed("campaign auto-search result target is ambiguous")
        roles = context.auto_search_role_state
        input_count = getattr(self.oracle, "input_dispatch_count", None)
        proof = CampaignAutoSearchCompletionProof(
            stage_code=context.stage_code, result_generation=state.generation,
            result_path=targets[0].path, fleet1_role=roles.fleet1_role,
            fleet2_role=roles.fleet2_role,
            waited_seconds=max(0.0, round(time.monotonic() - context.auto_search_started_at, 3)),
            combat_auto_generation=combat_generation, result_exit_receipt=None,
            passive_after_sortie=(context.auto_search_start_input_count is not None
                                  and input_count == context.auto_search_start_input_count),
        )
        context.auto_search_completion = proof
        self._last_campaign_auto_search_completion = proof
        if self._campaign_evidence_bundle is not None:
            self._campaign_evidence_bundle = replace(self._campaign_evidence_bundle, completion_proof=proof)
        return True

    def campaign_inherited_auto_search_visible(self) -> bool:
        """Recognize an official auto-search owned by an earlier process."""

        context = self._require_campaign_context()
        if any(
            item is not None
            for item in (
                context.entry_receipt,
                context.sortie_receipt,
                context.sortie_proof,
            )
        ):
            return False
        try:
            self.oracle.campaign_auto_search_active_state()
        except SemanticGateClosed:
            return False
        return True

    def recover_inherited_campaign_auto_search(
        self,
        stage_code: str,
        fleet_order: str,
        timeout_seconds: float = 1800.0,
    ) -> CampaignAutoSearchCompletionProof:
        """Passively finish one already-running official auto-search."""

        self._package_gate()
        context = self._require_campaign_context()
        if stage_code.lower() != context.stage_code:
            raise SemanticGateClosed(
                "inherited campaign auto-search stage identity changed"
            )
        roles = {
            "fleet1_mob_fleet2_boss": ("mob", "boss"),
            "fleet1_boss_fleet2_mob": ("boss", "mob"),
        }.get(fleet_order)
        if roles is None:
            raise SemanticGateClosed(
                "inherited campaign auto-search roles are not reviewed"
            )
        if not self.campaign_inherited_auto_search_visible():
            raise SemanticGateClosed("inherited campaign auto-search is absent")
        started = time.monotonic()
        deadline = started + float(timeout_seconds)
        combat_auto_generation: Optional[int] = None
        while time.monotonic() < deadline:
            self._package_gate()
            combat_auto = self.oracle.campaign_official_combat_auto_state()
            if combat_auto is not None:
                generation, enabled = combat_auto
                if isinstance(generation, bool) or not isinstance(generation, int):
                    raise SemanticGateClosed(
                        "inherited official combat generation is malformed"
                    )
                if not enabled:
                    raise SemanticGateClosed(
                        "official combat automation is disabled"
                    )
                combat_auto_generation = generation
            if self.oracle.enabled("reward/campaign-total/exit"):
                if combat_auto_generation is None:
                    raise SemanticGateClosed(
                        "inherited auto-search result has no active-run proof"
                    )
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                if not self.oracle.enabled("reward/campaign-total/exit"):
                    continue
                result_state = self.oracle.read_state()
                if isinstance(result_state.generation, bool) or not isinstance(
                    result_state.generation, int
                ):
                    raise SemanticGateClosed(
                        "inherited auto-search result generation is malformed"
                    )
                result_exit_receipt = self.oracle.click(
                    "reward/campaign-total/exit"
                )
                if isinstance(
                    result_exit_receipt.generation, bool
                ) or not isinstance(result_exit_receipt.generation, int):
                    raise SemanticGateClosed(
                        "inherited auto-search exit generation is malformed"
                    )
                if (
                    result_exit_receipt.semantic_id
                    != "reward/campaign-total/exit"
                    or result_exit_receipt.generation < result_state.generation
                    or not result_exit_receipt.path.endswith(
                        "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"
                    )
                ):
                    raise SemanticGateClosed(
                        "inherited auto-search result exit receipt is incoherent"
                    )
                stage_deadline = time.monotonic() + 30.0
                while time.monotonic() < stage_deadline:
                    try:
                        if self.oracle.campaign_page_is_normal():
                            proof = CampaignAutoSearchCompletionProof(
                                stage_code=context.stage_code,
                                result_generation=result_state.generation,
                                result_path=(
                                    "LevelStageTotalRewardPanel(Clone)/"
                                    "Window/Fixed/ButtonExit"
                                ),
                                fleet1_role=roles[0],
                                fleet2_role=roles[1],
                                waited_seconds=round(
                                    time.monotonic() - started,
                                    3,
                                ),
                                combat_auto_generation=combat_auto_generation,
                                result_exit_receipt=result_exit_receipt,
                            )
                            context.auto_search_completion = proof
                            self._last_campaign_auto_search_completion = proof
                            if self._campaign_evidence_bundle is not None:
                                self._campaign_evidence_bundle = replace(
                                    self._campaign_evidence_bundle,
                                    completion_proof=proof,
                                )
                            return proof
                    except SemanticGateClosed:
                        pass
                    time.sleep(0.5)
                raise SemanticGateClosed(
                    "inherited auto-search result did not return to stage"
                )
            time.sleep(1.0)
        raise SemanticGateClosed(
            "inherited campaign auto-search did not complete in time"
        )

    def confirm_campaign_auto_search_started(self) -> CampaignSortieProof:
        """Prove official auto-search took ownership after the sortie input."""

        context = self._require_campaign_context()
        if context.sortie_proof is not None:
            return context.sortie_proof
        if (
            not context.sortie_authorized
            or context.sortie_receipt is None
            or context.initial_fleet_state is None
            or context.prepared_fleet_state is None
            or context.requested_fleets is None
            or context.oil_before_sortie is None
            or context.auto_search_role_state is None
        ):
            raise SemanticGateClosed(
                "campaign auto-search start proof is incomplete"
            )
        active = self.oracle.campaign_auto_search_active_state()
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (active.generation, context.sortie_receipt.generation)
        ):
            raise SemanticGateClosed(
                "campaign auto-search start generation is malformed"
            )
        if active.generation <= context.sortie_receipt.generation:
            raise SemanticGateClosed(
                "campaign auto-search surface did not advance generation"
            )
        try:
            required_oil = context.prepared_fleet_state.required_sortie_oil
        except ValueError as exc:
            raise SemanticGateClosed(
                "campaign sortie oil requirement is not proven"
            ) from exc
        context.sortie_proof = CampaignSortieProof(
            stage_code=context.stage_code,
            initial_fleets=self._campaign_fleet_tuple(
                context.initial_fleet_state
            ),
            requested_fleets=context.requested_fleets,
            prepared_fleets=self._campaign_fleet_tuple(
                context.prepared_fleet_state
            ),
            mutation_semantic_ids=tuple(
                receipt.semantic_id
                for receipt in context.fleet_mutation_receipts
            ),
            oil_before_sortie=context.oil_before_sortie,
            required_oil=required_oil * (2 if context.use_2x_book else 1),
            sortie_generation=context.sortie_receipt.generation,
            map_generation=active.generation,
            map_root_path=active.root_path,
            oil_cost_source=context.prepared_fleet_state.oil_cost_source,
            submarine_auto_mode=context.submarine_auto_mode,
        )
        context.auto_search_started_at = time.monotonic()
        context.auto_search_start_input_count = getattr(self.oracle, "input_dispatch_count", None)
        if self._campaign_evidence_bundle is not None:
            self._campaign_evidence_bundle = replace(
                self._campaign_evidence_bundle,
                sortie_proof=context.sortie_proof,
            )
        return context.sortie_proof

    def _campaign_submarine_deployed(self):
        context = self._require_campaign_context()
        return bool((context.requested_fleets and context.requested_fleets[2]) or
                    (context.declared_submarine_fleet and getattr(context.map_state, 'submarine', None) is not None))

    def campaign_submarine_call_battle(self):
        self._package_gate()
        context = self._require_campaign_context()
        if not self._campaign_submarine_deployed():
            return None
        observed = self._frame_or_live_observation_oracle().campaign_submarine_call_state()
        return observed.battle_instance_id if observed is not None else None

    def campaign_submarine_grid(self, location):
        from ...alas_camera_view import build_alas_campaign_camera_view
        self._package_gate()
        context = self._require_campaign_context()
        if context.submarine_move_entry is None or context.map_columns is None:
            raise SemanticGateClosed('submarine grid requires original map and deployment entry')
        state = self.oracle.campaign_map_state(context.stage_code, columns=context.map_columns,
            rows=context.map_rows, land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count, allow_deployment=True)
        view = build_alas_campaign_camera_view(state, screen_center=(640, 360))
        key = tuple(location)
        if key not in view.grids:
            raise SemanticGateClosed('submarine destination is outside the observed map')
        grid = view.grids[key]
        grid.__str__ = grid.location
        context.map_state = state
        return grid

    def campaign_submarine_move_popup_appear(self, name):
        context = self._require_campaign_context()
        if context.submarine_move_confirm is None or context.submarine_move_oil is not None:
            return False
        observed = self._frame_or_live_observation_oracle().campaign_submarine_move_confirmation()
        if observed is None:
            return False
        expected = context.submarine_move_destination.semantic_id.rsplit('/',1)[1]
        if observed[2:4] != (context.map_state.submarine.node, expected):
            raise SemanticGateClosed('submarine oil prompt differs from planned movement')
        return name in ('POPUP_CONFIRM', 'POPUP_CANCEL')

    def click_campaign_submarine_grid(self, button):
        context = self._require_campaign_context()
        location = self._campaign_grid_location(button)
        grid = self.campaign_submarine_grid(location)
        node = chr(65+grid.location[0]) + str(grid.location[1]+1)
        if context.submarine_planned_destination is not None and node != context.submarine_planned_destination:
            raise SemanticGateClosed('submarine destination differs from original ALAS preview')
        if context.submarine_move_destination is not None:
            raise SemanticGateClosed('submarine destination already submitted; inspect before retry')
        receipt = self.oracle.click_campaign_submarine_destination(context.map_state, node, context.submarine_move_entry)
        context.submarine_move_destination = receipt
        return receipt

    def campaign_submarine_call_appear(self, name):
        self._package_gate()
        context = self._require_campaign_context()
        if not self._campaign_submarine_deployed():
            return False
        observed = self._frame_or_live_observation_oracle().campaign_submarine_call_state()
        if observed is None:
            return False
        receipt = context.submarine_call_receipts.get(observed.battle_instance_id)
        acknowledged = (receipt is not None and observed.generation > receipt.generation
                        and observed.button is None)
        if name == 'SUBMARINE_CALLED':
            # UI acknowledgment of our own call only; deployment/ammo is separate evidence.
            return acknowledged
        if name in ('SUBMARINE_AVAILABLE_CHECK_1', 'SUBMARINE_AVAILABLE_CHECK_2'):
            # While our submitted call is awaiting its UI acknowledgment,
            # neither called nor ready is proven. Keep the original handler
            # waiting instead of entering its unconditional fallback click.
            return (receipt is None and observed.button is not None) or acknowledged
        if name == 'SUBMARINE_READY':
            return receipt is None and observed.button is not None and observed.button.actionable
        raise SemanticGateClosed('unknown submarine call resource')

    def click_campaign_submarine_call(self):
        self._package_gate()
        context = self._require_campaign_context()
        call_mode = context.submarine_mode == 'every_combat' or (
            context.submarine_mode in ('boss_only', 'hunt_and_boss') and context.combat_admission is not None) or (
            context.submarine_mode == 'boss_only' and context.submarine_auto_mode == 'sub_standby'
            and context.auto_search_role_state is not None)
        if (not self._campaign_submarine_deployed()
                or (context.sortie_proof is None and context.combat_admission is None) or not call_mode):
            raise SemanticGateClosed('submarine call requires prepared sortie and original call mode')
        observed = self.oracle.campaign_submarine_call_state()
        if observed is None:
            raise SemanticGateClosed('submarine combat is absent')
        if observed.battle_instance_id in context.submarine_call_receipts:
            raise SemanticGateClosed('submarine call already submitted in this battle')
        receipt = self.oracle.click_campaign_submarine_call(observed.battle_instance_id)
        context.submarine_call_receipts[observed.battle_instance_id] = receipt
        return receipt

    def wait_campaign_auto_search_completion(
        self, stage_code: str, timeout_seconds: float = 1800.0,
        *, keep_result: bool = False, recovery_handler=None, submarine_handler=None,
    ) -> CampaignAutoSearchCompletionProof:
        """Passively wait for the official auto-search total-reward panel."""

        self._package_gate()
        context = self._require_campaign_context()
        manual_submarine = (context.requested_fleets and context.requested_fleets[2]
                            and context.submarine_auto_mode == 'sub_standby'
                            and context.submarine_mode in ('every_combat', 'boss_only'))
        if manual_submarine and submarine_handler is None:
            raise SemanticGateClosed('submarine standby requires original call handler')
        if type(keep_result) is not bool:
            raise TypeError("keep_result must be boolean")
        recovery_used = False
        if stage_code != context.stage_code:
            raise SemanticGateClosed(
                "campaign auto-search completion identity changed"
            )
        if (
            context.mode == "hard"
            and re.fullmatch(r"[1-9]\d*-[1-4]", stage_code) is None
            and re.fullmatch(r"[cd][1-3]", stage_code) is None
        ):
            raise SemanticGateClosed(
                "hard campaign auto-search completion is not qualified for "
                + stage_code
            )
        if context.sortie_proof is None or context.auto_search_role_state is None:
            raise SemanticGateClosed(
                "campaign auto-search completion requires sortie and role proof"
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, Real)
            or not 60 <= float(timeout_seconds) <= 3600
        ):
            raise ValueError("campaign auto-search timeout must be in [60, 3600]")
        started = time.monotonic()
        deadline = started + float(timeout_seconds)
        combat_auto_generation: Optional[int] = None
        while time.monotonic() < deadline:
            self._package_gate()
            if recovery_handler is not None:
                map_switch = getattr(self.oracle, 'campaign_map_auto_search_state', lambda: None)()
                if (self.oracle.campaign_dock_full_visible(context.stage_code)
                        or self.oracle.retirement_selection_visible()
                        or getattr(self.oracle, 'enhancement_dock_visible', lambda: False)()
                        or (map_switch is not None and not map_switch[2])):
                    if self._input_frame_refresher is not None:
                        self._input_frame_refresher()
                    recovery_used = True
                    recovery_handler()
                    continue
            combat_auto = self.oracle.campaign_official_combat_auto_state()
            if manual_submarine:
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                submarine_handler()
                recovery_used = recovery_used or bool(context.submarine_call_receipts)
            if combat_auto is not None:
                generation, enabled = combat_auto
                if isinstance(generation, bool) or not isinstance(generation, int):
                    raise SemanticGateClosed(
                        "official combat automation generation is malformed"
                    )
                if not enabled:
                    raise SemanticGateClosed(
                        "official combat automation is disabled"
                    )
                combat_auto_generation = generation
            if self.oracle.enabled("reward/campaign-total/exit"):
                if combat_auto_generation is None:
                    raise SemanticGateClosed(
                        "official combat automation was not proven"
                    )
                # Auto-search can run for minutes.  The result action must be
                # re-proved from a newly acquired immutable frame instead of
                # trying to reuse the input lease captured before sortie.
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                if not self.oracle.enabled("reward/campaign-total/exit"):
                    continue
                state = self.oracle.read_state()
                if isinstance(state.generation, bool) or not isinstance(
                    state.generation, int
                ):
                    raise SemanticGateClosed(
                        "campaign auto-search result generation is malformed"
                    )
                targets = tuple(
                    button
                    for button in state.buttons
                    if button.name == "ButtonExit"
                    and button.path.endswith(
                        "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"
                    )
                    and button.actionable
                )
                if len(targets) != 1:
                    raise SemanticGateClosed(
                        "campaign auto-search result target is ambiguous"
                    )
                if combat_auto_generation <= context.sortie_proof.map_generation:
                    raise SemanticGateClosed(
                        "official combat automation generation did not advance"
                    )
                if state.generation <= combat_auto_generation:
                    raise SemanticGateClosed(
                        "campaign auto-search result generation did not advance"
                    )
                if keep_result and self.oracle.campaign_auto_search_reentry_available():
                    roles = context.auto_search_role_state
                    proof = CampaignAutoSearchCompletionProof(
                        stage_code=stage_code, result_generation=state.generation,
                        result_path=targets[0].path, fleet1_role=roles.fleet1_role,
                        fleet2_role=roles.fleet2_role,
                        waited_seconds=round(time.monotonic() - started, 3),
                        combat_auto_generation=combat_auto_generation,
                        result_exit_receipt=None, passive_after_sortie=not recovery_used)
                    context.auto_search_completion = proof
                    self._last_campaign_auto_search_completion = proof
                    if self._campaign_evidence_bundle is not None:
                        self._campaign_evidence_bundle = replace(self._campaign_evidence_bundle, completion_proof=proof)
                    return proof
                result_exit_receipt = self.oracle.click(
                    "reward/campaign-total/exit"
                )
                if isinstance(
                    result_exit_receipt.generation, bool
                ) or not isinstance(result_exit_receipt.generation, int):
                    raise SemanticGateClosed(
                        "campaign auto-search result exit generation is malformed"
                    )
                if (
                    result_exit_receipt.semantic_id
                    != "reward/campaign-total/exit"
                    or result_exit_receipt.generation < state.generation
                    or result_exit_receipt.path != targets[0].path
                ):
                    raise SemanticGateClosed(
                        "campaign auto-search result exit receipt is incoherent"
                    )
                roles = context.auto_search_role_state
                proof = CampaignAutoSearchCompletionProof(
                    stage_code=stage_code,
                    result_generation=state.generation,
                    result_path=targets[0].path,
                    fleet1_role=roles.fleet1_role,
                    fleet2_role=roles.fleet2_role,
                    waited_seconds=round(time.monotonic() - started, 3),
                    combat_auto_generation=combat_auto_generation,
                    result_exit_receipt=result_exit_receipt,
                    passive_after_sortie=not recovery_used,
                )
                stage_deadline = time.monotonic() + 30.0
                while time.monotonic() < stage_deadline:
                    try:
                        if self.oracle.campaign_page_is_normal():
                            context.auto_search_completion = proof
                            self._last_campaign_auto_search_completion = proof
                            if self._campaign_evidence_bundle is not None:
                                self._campaign_evidence_bundle = replace(
                                    self._campaign_evidence_bundle,
                                    completion_proof=proof,
                                )
                            return proof
                    except SemanticGateClosed:
                        pass
                    time.sleep(0.5)
                raise SemanticGateClosed(
                    "campaign auto-search result did not return to stage"
                )
            time.sleep(1.0)
        raise SemanticGateClosed(
            "campaign auto-search did not reach the total-reward panel in time"
        )

    def close_orphan_campaign_auto_search_result(self) -> bool:
        """Close an unowned total-reward panel without claiming a task run."""

        self._package_gate()
        if self._input_frame_refresher is not None:
            self._input_frame_refresher()
        if not self.oracle.enabled("reward/campaign-total/exit"):
            return False
        self.oracle.click("reward/campaign-total/exit")
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                if self.oracle.campaign_page_is_normal():
                    return True
            except SemanticGateClosed:
                pass
            time.sleep(0.5)
        raise SemanticGateClosed(
            "orphan campaign auto-search result did not return to stage"
        )

    def authorize_campaign_auto_search_continue(self, *, use_2x_book: bool,
                                                fleet1: int, fleet2: int,
                                                fleet_order: str, submarine: int = 0,
                                                submarine_auto_mode: str = 'sub_standby') -> bool:
        """Authorize ALAS's next run using its retained game-owned menu."""
        self._package_gate()
        context = self._require_campaign_context()
        if context.mode == 'hard':
            return True  # Existing hard Continue owns its separate contract.
        if (context.auto_search_completion is None or context.sortie_proof is None
                or context.prepared_fleet_state is None or context.auto_search_role_state is None):
            raise SemanticGateClosed('campaign Continue requires a completed owned sortie and preparation')
        roles = {'fleet1_mob_fleet2_boss': ('mob', 'boss'),
                 'fleet1_boss_fleet2_mob': ('boss', 'mob'),
                 'fleet1_all_fleet2_standby': ('all', 'standby'),
                 'fleet1_standby_fleet2_all': ('standby', 'all')}
        observed_roles = (context.auto_search_role_state.fleet1_role, context.auto_search_role_state.fleet2_role)
        if context.requested_fleets != (fleet1, fleet2, submarine) or roles.get(fleet_order) != observed_roles:
            raise SemanticGateClosed('campaign Continue configuration differs from retained preparation')
        if submarine and context.submarine_auto_mode != submarine_auto_mode:
            raise SemanticGateClosed('campaign Continue submarine duty differs from retained preparation')
        if not self.oracle.campaign_auto_search_reentry_available():
            raise SemanticGateClosed('campaign Continue menu is unavailable')
        _, _, selected, count = self.oracle._campaign_2x_book_control('auto')
        if type(use_2x_book) is not bool or (selected is not use_2x_book and not (selected is None and not use_2x_book)):
            raise SemanticGateClosed('campaign Continue book selection is not proven')
        if use_2x_book and count < 1:
            raise SemanticGateClosed('campaign Continue book inventory is empty')
        oil = self.oracle.campaign_oil()
        required = context.prepared_fleet_state.required_sortie_oil * (2 if use_2x_book else 1)
        if oil < required:
            raise SemanticGateClosed('campaign Continue oil precondition failed')
        self._require_action_grant('campaign.sortie')
        context.oil_before_sortie = oil
        context.use_2x_book = use_2x_book
        context.sortie_budget_before = self._action_ledger.remaining('campaign.sortie')
        context.continuation_authorized = True
        return True

    def continue_campaign_normal_auto_search(self) -> ActionReceipt:
        self._package_gate()
        context = self._require_campaign_context()
        if (context.mode != 'normal' or not context.continuation_authorized
                or context.auto_search_completion is None
                or self._action_ledger.remaining('campaign.sortie') != context.sortie_budget_before):
            raise SemanticGateClosed('campaign Continue has no fresh authorization')
        selected = self.oracle.campaign_2x_book_selected(mode='auto')
        if selected is not context.use_2x_book and not (selected is None and not context.use_2x_book):
            raise SemanticGateClosed('campaign Continue book changed before input')
        context.continuation_authorized = False
        receipt = self._dispatch_mutation('campaign.sortie', self.oracle.click_campaign_auto_search_reentry)
        context.initial_fleet_state = context.prepared_fleet_state
        context.fleet_mutation_receipts = []
        context.sortie_receipt = receipt
        context.sortie_proof = None
        context.map_entry_state = None
        context.auto_search_completion = None
        context.auto_search_combat_generation = None
        context.book_confirmation_receipt = None
        context.passive_transition_until = time.monotonic() + 180.0
        if self._campaign_evidence_bundle is not None:
            self._campaign_evidence_bundle = replace(self._campaign_evidence_bundle, sortie_proof=None, completion_proof=None)
        return receipt

    def continue_campaign_hard_auto_search(self) -> ActionReceipt:
        """Spend one sortie lease on the reviewed official reentry control."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.mode != "hard":
            raise SemanticGateClosed(
                "campaign auto-search continue is qualified only for hard mode"
            )
        if re.fullmatch(r"[1-9]\d*-[1-4]", context.stage_code) is None:
            raise SemanticGateClosed(
                "campaign auto-search continue requires a main hard stage"
            )
        if context.auto_search_completion is None:
            raise SemanticGateClosed(
                "campaign auto-search continue requires a proven result"
            )
        def click_reentry():
            oracle = self._fresh_input_oracle()
            if oracle.campaign_auto_search_reentry_available():
                return oracle.click_campaign_auto_search_reentry()
            return oracle.click("reward/campaign-total/continue")

        receipt = self._dispatch_mutation("campaign.sortie", click_reentry)
        context.sortie_receipt = receipt
        context.sortie_proof = None
        context.map_entry_state = None
        context.auto_search_completion = None
        context.auto_search_combat_generation = None
        context.passive_transition_until = time.monotonic() + 60.0
        return receipt

    def _require_campaign_context(self) -> _CampaignFlowContext:
        if self._campaign_context is None:
            raise SemanticGateClosed(
                "campaign resource used outside ALAS pre-sortie flow"
            )
        return self._campaign_context

    def _known_campaign_surface_exists(self) -> bool:
        if self._campaign_context is not None:
            try:
                if self._campaign_preparation_kind() is not None:
                    return True
            except SemanticGateClosed:
                pass
        try:
            # Either result is a positive proof that the observer recognizes
            # the current campaign surface.  ``True`` means the exact map
            # root is present; ``False`` means one of the reviewed non-map
            # startup surfaces is present.  Only an exception is unknown.
            self.oracle.campaign_is_in_map()
        except SemanticGateClosed:
            return False
        return True

    def campaign_story_black(self) -> bool:
        """Reject the pixel-only black-story heuristic on proven campaign UI."""

        self._package_gate()
        if self._campaign_context is None:
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
                or self.oracle.daily_combat_visible()
                or self.oracle.daily_battle_result_visible()
                or time.monotonic() <= self._daily_transition_until
            ):
                return False
            if any(
                context is not None
                for context in (
                    self._mission_context,
                    self._mail_context,
                    self._commission_context,
                    self._research_context,
                    self._dorm_context,
                    self._minigame_context,
                    self._build_context,
                )
            ):
                return False
            if getattr(
                self.oracle, "operation_siren_local_map_visible", lambda: False
            )():
                return False
            for opsi_reader in (
                self.oracle.operation_siren_state,
                self.oracle.operation_siren_globe_state,
            ):
                try:
                    opsi_reader()
                except SemanticGateClosed:
                    continue
                return False
            # InfoHandler runs this heuristic on every UI transition.  A
            # proven non-campaign surface cannot be a campaign story frame.
            if any(
                checker()
                for checker in (
                    self._known_mission_surface_exists,
                    self._known_mail_surface_exists,
                    self._known_commission_surface_exists,
                    self._known_research_surface_exists,
                    self._known_dorm_surface_exists,
                    self._known_minigame_surface_exists,
                    self._known_build_surface_exists,
                )
            ):
                return False
            raise AlasSemanticUnmapped(
                "campaign story surface is not semantically mapped"
            )
        if self._known_campaign_surface_exists():
            return False
        raise AlasSemanticUnmapped(
            "campaign story surface is not semantically mapped"
        )

    def _record_event_story_transition(self, receipt: ActionReceipt) -> ActionReceipt:
        # A modern story choice/skip can unmount NewStoryUI before its owning
        # page is mounted again.  This deadline owns only passive appear()
        # scans; every later input still needs its normal semantic proof.
        self._event_story_transition_until = time.monotonic() + 12.0
        return receipt

    def click_event_story_skip_confirm(self) -> ActionReceipt:
        self._package_gate()
        return self._record_event_story_transition(
            self.oracle.click_event_story_skip_confirm()
        )

    def click_event_story_option(self, option_index: int) -> ActionReceipt:
        self._package_gate()
        return self._record_event_story_transition(
            self.oracle.click_event_story_option(option_index)
        )

    def click_event_story_skip(self) -> ActionReceipt:
        self._package_gate()
        return self._record_event_story_transition(
            self.oracle.click_event_story_skip()
        )

    def campaign_page_state(self) -> CampaignPageState:
        self._package_gate()
        last_error = None
        for _ in range(4):
            try:
                state = self.oracle.campaign_page_state()
                if self._campaign_context is not None:
                    self._campaign_context.passive_transition_until = (
                        time.monotonic() + 20.0
                    )
                    requested = self._campaign_context.stage_code
                    if re.fullmatch(r"[a-z]+[0-9]*", requested):
                        requested_chapter = SemanticOracle._campaign_stage_chapter(
                            requested
                        )
                        preferred = tuple(
                            stage
                            for stage in state.stages
                            if stage.stage_code == requested
                        )
                        shared_chapter = {"c": "a", "d": "b"}.get(
                            requested_chapter
                        )
                        if not preferred and shared_chapter is not None:
                            shared_stage = shared_chapter + requested[
                                len(requested_chapter) :
                            ]
                            preferred = tuple(
                                stage
                                for stage in state.stages
                                if stage.stage_code == shared_stage
                            )
                        if preferred:
                            state = CampaignPageState(
                                generation=state.generation,
                                chapter_name=SemanticOracle._campaign_stage_chapter(
                                    preferred[0].stage_code
                                ),
                                stages=preferred,
                            )
                return state
            except SemanticGateClosed as exc:
                if str(exc) not in (
                    "observer endpoints are not generation-coherent",
                    "campaign snapshots are not coherent",
                ):
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    def event_points(self) -> int:
        self._package_gate()
        return self.oracle.event_points()

    def event_coin(self) -> int:
        self._package_gate()
        context = self._campaign_context
        stage_code = (
            context.resolved_stage_code or context.stage_code
            if context is not None
            else None
        )
        return self._frame_or_live_observation_oracle().event_coin(stage_code)

    def campaign_oil(self) -> int:
        self._package_gate()
        return self._frame_or_live_observation_oracle().campaign_oil()

    def campaign_map_achievement_state(self) -> CampaignMapAchievementState:
        self._package_gate()
        state, stage_code = self._campaign_preparation_state_with_stage()
        if state is None or state.kind != "map":
            raise SemanticGateClosed(
                "campaign achievement requires the map-preparation layer"
            )
        return self.oracle.campaign_map_achievement_state(stage_code)

    def campaign_map_clear_percentage(self) -> float:
        self._package_gate()
        reader = self._frame_or_live_observation_oracle()
        state, stage_code = self._campaign_preparation_state_with_stage(reader=reader)
        if state is None or state.kind != "map":
            raise SemanticGateClosed(
                "campaign clear percentage requires the map-preparation layer"
            )
        try:
            return reader.campaign_map_clear_percentage(stage_code)
        except SemanticGateClosed as exc:
            if (
                stage_code != "sp"
                or str(exc)
                != "campaign achievement progress is absent or ambiguous"
            ):
                raise
            toggle = reader.toggle_state(
                "campaign/map-preparation/auto-search"
            )
            if (
                not toggle.active_in_hierarchy
                or not toggle.active_and_enabled
                or not toggle.interactable
                or toggle.point is None
                or toggle.bounds is None
                or not toggle.bounds.contains(toggle.point)
            ):
                raise SemanticGateClosed(
                    "SP auto-search unlock target is not proven"
                )
            return 1.0

    def campaign_auto_search_selected(self) -> bool:
        self._package_gate()
        self._require_campaign_context()
        if self._campaign_preparation_kind() != "map":
            raise SemanticGateClosed(
                "campaign auto-search state requires the map-preparation layer"
            )
        return self.oracle.campaign_auto_search_selected()

    def campaign_hard_remain(self) -> int:
        self._package_gate()
        context = self._require_campaign_context()
        if context.mode != "hard":
            raise SemanticGateClosed("hard quota used outside hard campaign flow")
        return self.oracle.campaign_hard_remain()

    def campaign_map_formation(self) -> str:
        self._package_gate()
        self._require_campaign_context()
        return self.oracle.campaign_map_formation()

    def _appear_campaign_stage(self, name, campaign_stage_code):
        if campaign_stage_code is not None:
            self._package_gate()
            context = self._require_campaign_context()
            shared_hard_entrance = CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES.get(
                context.stage_code
            )
            if (
                not isinstance(campaign_stage_code, str)
                or name != context.stage_code
                or campaign_stage_code
                not in (context.stage_code, shared_hard_entrance)
            ):
                raise SemanticGateClosed("campaign stage identity changed")
            if context.entry_receipt is not None:
                # This invocation has already spent its one-shot entrance.
                # A still-mounted chapter underlay cannot authorize a second
                # entry. Let ALAS take its next screenshot and inspect the
                # preparation instead of reparsing that obscured underlay.
                return False
            try:
                return self.oracle.campaign_stage_actionable(campaign_stage_code)
            except SemanticGateClosed:
                # NetworkDown can mount after enter_map() checked popups but
                # before this later stage-presence probe.  Treat that exact,
                # topmost reconnect prompt as a transient non-match; the next
                # ALAS loop iteration handles and confirms it before retrying
                # the stage.  Other identity failures remain fail-closed.
                if self.oracle.enabled("overlay/network-reconnect/confirm"):
                    return False
                if self.oracle.campaign_preparation_state(
                    campaign_stage_code
                ) is not None:
                    return False
                raise
        return UNHANDLED

    def _appear_campaign(self, name):
        if self._campaign_context is not None and name in ('AUTO_SEARCH_MAP_OPTION_OFF', 'AUTO_SEARCH_MAP_OPTION_ON'):
            switch = self.oracle.campaign_map_auto_search_state()
            return switch is not None and switch[2] == (name == 'AUTO_SEARCH_MAP_OPTION_ON')
        if self._campaign_context is not None and name in ('EMERGENCY_REPAIR_AVAILABLE', 'EMERGENCY_REPAIR_CONFIRM'):
            return self.campaign_repair_appear(name)
        if self._campaign_context is not None and name in ('WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM'):
            context = self._campaign_context
            confirm = name == 'CAMPAIGN_WITHDRAW_CONFIRM'
            if context.withdrawal_confirm_receipt is not None:
                return False
            if confirm and context.withdrawal_open_receipt is None:
                return False
            if not confirm and context.withdrawal_open_receipt is not None:
                return False
            return self.oracle.campaign_withdraw_control(confirm=confirm) is not None
        if (name == 'SP_CHECK' and self._campaign_context is not None
                and re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*', self._campaign_context.stage_code)):
            if self.oracle.campaign_is_in_map() or self.oracle.campaign_page_is_normal():
                return False
        if self._campaign_context is not None and name in ('SUBMARINE_MOVE_ENTER', 'SUBMARINE_MOVE_CONFIRM', 'SUBMARINE_MOVE_CANCEL'):
            if name == 'SUBMARINE_MOVE_ENTER':
                if self.oracle.campaign_deployment_controls() is not None:
                    return False
                context = self._campaign_context
                if context.submarine_move_confirm is not None:
                    from dataclasses import asdict
                    previous_marker = context.map_state.submarine.marker
                    # An appearance probe owns one immutable screenshot frame.
                    # Parse that complete frame; do not wait for two increasing
                    # generations inside it. Subsequent map input still re-proves
                    # the stable map at its existing mutation boundary.
                    state = self.oracle._campaign_map_state_once(
                        context.stage_code, columns=context.map_columns,
                        rows=context.map_rows,
                        land=tuple(sorted((r+1,c+1) for c,r in context.map_land_cells)),
                        expected_fleet_count=context.map_expected_fleet_count)
                    last_input = context.submarine_move_oil or context.submarine_move_confirm
                    if state.generation <= last_input.generation:
                        return False
                    expected = context.submarine_move_destination.semantic_id.rsplit('/',1)[1]
                    if state.submarine is None or state.submarine.node != expected or state.submarine.marker != previous_marker:
                        raise SemanticGateClosed('submarine deployment did not reach the selected node')
                    if context.combat_admission is not None:
                        self._validate_campaign_combat_route_state(context, state, for_next_input=True)
                        context.combat_admission = replace(context.combat_admission, map_signature=state.signature)
                    context.map_state = state
                    context.submarine_move_history.append(dict(
                        entry=asdict(context.submarine_move_entry), destination=asdict(context.submarine_move_destination),
                        confirm=asdict(context.submarine_move_confirm), post_generation=state.generation,
                        oil_confirmation=asdict(context.submarine_move_oil) if context.submarine_move_oil else None,
                        submarine=asdict(state.submarine)))
                    context.submarine_move_entry = context.submarine_move_destination = context.submarine_move_confirm = None
                    context.submarine_move_oil = None
                return self.oracle.campaign_submarine_strategy_state('move') is not None
            if name == 'SUBMARINE_MOVE_CONFIRM' and self._campaign_context.submarine_move_confirm is not None:
                return False
            return self._campaign_context.submarine_move_entry is not None and self.oracle.campaign_deployment_controls() is not None
        if self._campaign_context is not None and name in ('SUBMARINE_HUNT_ON', 'SUBMARINE_HUNT_OFF', 'SUBMARINE_VIEW_ON', 'SUBMARINE_VIEW_OFF'):
            context = self._campaign_context
            if not self._campaign_submarine_deployed():
                return False
            feature = 'hunt' if '_HUNT_' in name else 'view'
            state = self.oracle.campaign_submarine_strategy_state(feature)
            if state is not None and feature in context.submarine_strategy_pending and state is not context.submarine_strategy_pending[feature]:
                context.submarine_strategy_pending.pop(feature)
            return state is not None and state is name.endswith('_ON')
        if self._campaign_context is not None and name == 'AUTO_SEARCH_MENU_CONTINUE' and self._campaign_context.mode == 'normal':
            return (self._campaign_context.auto_search_completion is not None
                    and self.oracle.campaign_auto_search_reentry_available())
        if self._campaign_context is not None and name in ("MAP_AMBUSH_EVADE", "MAP_AMBUSH_ATTACK"):
            return self.oracle.campaign_ambush_visible(evade=name == "MAP_AMBUSH_EVADE")
        if self._campaign_context is not None and name in ("FLEET_LOCKED", "FLEET_UNLOCKED"):
            selected = self.oracle.campaign_fleet_lock_selected()
            return selected is not None and selected == (name == "FLEET_LOCKED")
        if self._campaign_context is not None and name in ("BOOK_CHECK_PREP", "BOOK_CHECK_AUTO"):
            return self.oracle.campaign_2x_book_selected(mode="auto" if name.endswith("AUTO") else "prep") is not None
        if self._campaign_context is not None and name in (
            "FAST_FORWARD_ON", "FAST_FORWARD_OFF",
        ):
            if self._campaign_preparation_kind() != "map":
                return False
            selected = self.oracle.campaign_clear_mode_selected()
            return selected is not None and selected == (name == "FAST_FORWARD_ON")
        if self._campaign_context is not None and name in (
            "FLEET_NUM_1",
            "FLEET_NUM_2",
        ):
            expected = 1 if name == "FLEET_NUM_1" else 2
            return self.oracle.campaign_map_displayed_fleet_index() == expected
        if self._campaign_context is not None and name == "STRATEGY_OPENED":
            return self.oracle.campaign_strategy_panel_visible()
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_STRATEGY_FORMATION_RESOURCES
        ):
            if not self.oracle.campaign_strategy_panel_visible():
                return False
            return self.oracle.campaign_strategy_formation() == (
                CAMPAIGN_STRATEGY_FORMATION_RESOURCES[name]
            )
        if self._campaign_context is not None and name == "SWITCH_OVER":
            context = self._require_campaign_context()
            admission = context.combat_admission
            if admission is None:
                return False
            displayed = self.oracle.campaign_map_displayed_fleet_index()
            if displayed == admission.fleet_index:
                return False
            return self.oracle.campaign_map_fleet_switch_available()
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_FLEET_ROW_RESOURCES
        ):
            row_key, action = CAMPAIGN_FLEET_ROW_RESOURCES[name]
            if action == "advice":
                return self.campaign_fleet_operator_is_hard(row_key)
            if action == "clear":
                return self.campaign_fleet_row_allowed(row_key)
            return not self.campaign_fleet_dropdown_opened()
        if self._campaign_context is not None and name == "EVENT_LIST_CHECK":
            return self.oracle.exists("event-list/page/back")
        if self._campaign_context is not None and name == "BACK_ARROW":
            if self._campaign_page_back_visible():
                return self.oracle.enabled("campaign-menu/page/back")
            return self.oracle.enabled("event-list/page/back")
        if self._campaign_context is not None and name in (
            "SWITCH_1_NORMAL",
            "SWITCH_1_HARD",
        ):
            expected = "normal" if name == "SWITCH_1_NORMAL" else "hard"
            return self.oracle.campaign_mode_switch_state() == expected
        if self._campaign_context is not None and name in (
            "SWITCH_2_HARD",
            "SWITCH_2_EX",
        ):
            # Main campaign chapters expose only the normal/hard switch.  The
            # second switch belongs to event EX pages and is presence-only in
            # ALAS' generic ModeSwitch probe.
            return False
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_AUTO_SEARCH_RESOURCES
        ):
            context = self._require_campaign_context()
            if context.map_preparation_receipt is not None:
                return False
            if self._campaign_preparation_kind() != "map":
                return False
            selected = self.oracle.toggle_selected(
                "campaign/map-preparation/auto-search"
            )
            return (
                selected
                if name in CAMPAIGN_AUTO_SEARCH_ON_RESOURCES
                else not selected
            )
        if self._campaign_context is not None and name in (
            "MAP_PREPARATION",
            "FLEET_PREPARATION",
            "MAP_PREPARATION_CANCEL",
        ):
            if (
                name == "MAP_PREPARATION"
                and self._campaign_context.map_preparation_receipt is not None
            ):
                return False
            if name == "FLEET_PREPARATION":
                context = self._require_campaign_context()
                try:
                    preparation, _resolved_stage_code = (
                        self._campaign_preparation_state_with_stage()
                    )
                except SemanticGateClosed:
                    if (
                        (
                            context.entry_receipt is not None
                            or context.map_preparation_receipt is not None
                            or context.cancel_receipt is not None
                            or context.sortie_receipt is not None
                        )
                        and time.monotonic() <= context.passive_transition_until
                    ):
                        return False
                    raise
                if preparation is None:
                    return False
                preparation_kind = getattr(preparation, "kind", None)
                owned_receipts = (
                    context.entry_receipt is not None,
                    context.map_preparation_receipt is not None,
                )
                if preparation_kind == "map":
                    # After ALAS clicks the stage, the map-detail layer is a
                    # normal intermediate state: the stage-entry receipt is
                    # present while the map-preparation receipt is not.  This
                    # is not a partial fleet-ownership claim, because no fleet
                    # overlay exists yet.
                    if owned_receipts == (False, True):
                        raise SemanticGateClosed(
                            "campaign map preparation ownership proof is partial"
                        )
                    # An inherited, exactly identified map-detail page also
                    # proves that no fleet overlay is present. This negative
                    # probe grants no fleet mutation or sortie authority.
                    return False
                if preparation_kind != "fleet":
                    raise SemanticGateClosed(
                        "campaign preparation kind is not reviewed"
                    )
                if all(owned_receipts):
                    # Both normal and hard panels load portraits after levels.
                    # Check the native screenshot once before ALAS enters its
                    # fleet operators; retrying an immutable reader cannot
                    # reveal a newly mounted portrait. Input reads stay strict.
                    oracle = self._frame_or_live_observation_oracle()
                    try:
                        oracle.campaign_fleet_selection_state(
                            _resolved_stage_code,
                            fallback_oil_cost=context.map_preparation_oil_cost)
                    except SemanticGateClosed as exc:
                        if (isinstance(exc, SemanticCampaignFleetIncomplete)
                                and time.monotonic() <= context.passive_transition_until):
                            return False
                        raise
                    return True
                if any(owned_receipts):
                    raise SemanticGateClosed(
                        "campaign fleet preparation ownership proof is partial"
                    )
                if not self._campaign_inherited_fleet_overlay_is_pristine(context):
                    raise SemanticGateClosed(
                        "inherited campaign fleet preparation requires pristine passive state"
                    )
                return True
            if name == "MAP_PREPARATION":
                context = self._require_campaign_context()
                if context.entry_receipt is None:
                    preparation, _resolved_stage_code = (
                        self._campaign_preparation_state_with_stage()
                    )
                    if preparation is None:
                        return False
                    kind = getattr(preparation, "kind", None)
                    if kind not in ("map", "fleet"):
                        raise SemanticGateClosed(
                            "inherited campaign preparation kind is invalid"
                        )
                    # Presence of an inherited map detail is observation-only.
                    # The cancel action independently revalidates the exact
                    # stage, root pair, raycast, and one-shot receipt.
                    return kind == "map"
            kind = self._campaign_preparation_kind()
            if name == "MAP_PREPARATION":
                return kind == "map"
            return kind in ("map", "fleet")
        return UNHANDLED

    def _click_campaign_confirmation(self, name):
        if name == 'POPUP_CONFIRM_CAMPAIGN_MAP' and self._campaign_context is not None:
            return self.oracle.click('campaign/urgent-notice/confirm')
        if name in ('POPUP_CONFIRM_SUBMARINE_MOVE', 'POPUP_CANCEL_SUBMARINE_MOVE'):
            if self._campaign_context is None or self._campaign_context.submarine_move_confirm is None:
                raise SemanticGateClosed('submarine movement popup has no pending deployment')
            name = 'POPUP_CONFIRM' if name.startswith('POPUP_CONFIRM_') else 'POPUP_CANCEL'
        if self._campaign_context is not None and name in ('POPUP_CONFIRM', 'POPUP_CANCEL') and self._campaign_context.submarine_move_confirm is not None:
            context = self._campaign_context
            if not self.campaign_submarine_move_popup_appear(name):
                raise SemanticGateClosed('submarine movement oil confirmation is unavailable')
            destination = context.submarine_move_destination.semantic_id.rsplit('/',1)[1]
            receipt = self.oracle.click_campaign_submarine_move_confirmation(context.map_state.submarine.node,
                destination, confirm=name == 'POPUP_CONFIRM')
            context.submarine_move_oil = receipt
            return receipt
        if (
            self._campaign_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                receipt = self.oracle.click(reconnect_target)
                self._campaign_context.passive_transition_until = (
                    time.monotonic() + 20.0
                )
                return receipt
        return UNHANDLED

    def _click_campaign_strategy(self, name):
        if name == 'AUTO_SEARCH_MAP_OPTION_OFF':
            self._require_campaign_context()
            self._package_gate()
            receipt = self._fresh_input_oracle().click_campaign_map_auto_search_on(
                post_input_foreground=self.oracle._foreground_component)
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                if (self.oracle.read_state().generation > receipt.generation
                        and self.oracle.campaign_dock_full_visible(self._campaign_context.stage_code)):
                    # The client can immediately pause a submitted map resume
                    # on its own dock-capacity check. Return to ALAS recovery.
                    return receipt
                switch = self.oracle.campaign_map_auto_search_state()
                if switch is not None and switch[0].generation > receipt.generation and switch[2]:
                    return receipt
                auto = self.oracle.campaign_official_combat_auto_state()
                if auto is not None and auto[0] > receipt.generation and auto[1]:
                    return receipt
                time.sleep(.1)
            raise SemanticGateClosed('map auto-search ON postcondition not observed; do not retry')
        if name in ('EMERGENCY_REPAIR_AVAILABLE', 'EMERGENCY_REPAIR_CONFIRM'):
            return self.click_campaign_repair(name)
        if name in ('WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM'):
            context = self._require_campaign_context()
            confirm = name == 'CAMPAIGN_WITHDRAW_CONFIRM'
            if (context.withdrawal_confirm_receipt is not None
                    or (confirm and context.withdrawal_open_receipt is None)
                    or (not confirm and context.withdrawal_open_receipt is not None)):
                raise SemanticGateClosed('campaign withdrawal input already submitted or unowned')
            receipt = self._fresh_input_oracle().click_campaign_withdraw(confirm=confirm)
            if confirm:
                context.withdrawal_confirm_receipt = receipt
            else:
                context.withdrawal_open_receipt = receipt
            context.passive_transition_until = time.monotonic() + 15.0
            return receipt
        if self._campaign_context is not None and name == 'SUBMARINE_MOVE_ENTER':
            context = self._campaign_context
            if not self._campaign_submarine_deployed() or (context.sortie_proof is None and context.combat_admission is None):
                raise SemanticGateClosed('submarine move requires prepared sortie')
            if context.submarine_move_entry is not None:
                raise SemanticGateClosed('submarine deployment already entered')
            receipt = self.oracle.click_campaign_submarine_strategy('move', False)
            context.submarine_move_entry = receipt
            context.submarine_move_destination = None
            context.submarine_move_confirm = None
            context.submarine_move_oil = None
            return receipt
        if self._campaign_context is not None and name == 'SUBMARINE_MOVE_CONFIRM':
            context = self._campaign_context
            if context.submarine_move_destination is None or context.submarine_move_confirm is not None:
                raise SemanticGateClosed('submarine deployment has no new destination to confirm')
            location = context.submarine_move_destination.semantic_id.rsplit('/',1)[1]
            self.campaign_submarine_grid((ord(location[0])-65,int(location[1:])-1))
            receipt = self.oracle.click_campaign_submarine_deployment_confirm(context.map_state, context.submarine_move_destination)
            context.submarine_move_confirm = receipt
            return receipt
        if self._campaign_context is not None and name == 'SUBMARINE_MOVE_CANCEL':
            receipt = self.oracle.click_campaign_deployment_cancel()
            self._campaign_context.submarine_move_entry = None
            self._campaign_context.submarine_move_destination = None
            self._campaign_context.submarine_move_confirm = None
            self._campaign_context.submarine_move_oil = None
            return receipt
        if self._campaign_context is not None and name in ('SUBMARINE_HUNT_ON', 'SUBMARINE_HUNT_OFF', 'SUBMARINE_VIEW_ON', 'SUBMARINE_VIEW_OFF'):
            context = self._campaign_context
            if not self._campaign_submarine_deployed():
                raise SemanticGateClosed('submarine strategy requires the prepared submarine')
            feature = 'hunt' if '_HUNT_' in name else 'view'
            expected = name.endswith('_ON')
            if feature in context.submarine_strategy_pending and context.submarine_strategy_pending[feature] is expected:
                raise SemanticGateClosed('submarine strategy state did not advance after input')
            receipt = self.oracle.click_campaign_submarine_strategy(feature, expected)
            context.submarine_strategy_pending[feature] = expected
            context.submarine_strategy_receipts.append(receipt)
            return receipt
        if self._campaign_context is not None and name == 'AUTO_SEARCH_MENU_EXIT':
            context = self._campaign_context
            if (context.auto_search_completion is not None
                    and context.auto_search_completion.result_exit_receipt is not None):
                return context.auto_search_completion.result_exit_receipt
            if context.manual_result_exit_receipt is not None:
                raise SemanticGateClosed('manual campaign result exit already submitted')
            receipt = self.oracle.click('reward/campaign-total/exit')
            if self.campaign_combat_committed() and not self.campaign_auto_search_owned():
                context.manual_result_exit_receipt = receipt
            if context.auto_search_completion is not None:
                proof = replace(context.auto_search_completion, result_exit_receipt=receipt)
                context.auto_search_completion = proof
                self._last_campaign_auto_search_completion = proof
                if self._campaign_evidence_bundle is not None:
                    self._campaign_evidence_bundle = replace(self._campaign_evidence_bundle, completion_proof=proof)
            return receipt
        if self._campaign_context is not None and name in ("MAP_AMBUSH_EVADE", "MAP_AMBUSH_ATTACK"):
            if not self.handle_campaign_ambush(evade=name == "MAP_AMBUSH_EVADE"):
                raise SemanticGateClosed("campaign ambush disappeared before input")
            return self._require_campaign_context().ambush_receipt
        if self._campaign_context is not None and name in ("FLEET_LOCKED", "FLEET_UNLOCKED"):
            context = self._require_campaign_context()
            previous = context.fleet_lock_receipt
            expected = name == "FLEET_LOCKED"
            if previous is not None and previous.semantic_id.endswith("/on" if expected else "/off"):
                raise SemanticGateClosed("fleet-lock state did not advance after its previous input")
            if previous is not None and self.oracle.read_state().generation <= previous.generation:
                raise SemanticGateClosed("fleet-lock input frame did not advance")
            receipt = self.oracle.click_campaign_fleet_lock(expected)
            context.fleet_lock_receipt = receipt
            return receipt
        if self._campaign_context is not None and name == "STRATEGY_OPEN":
            receipt = self.oracle.click_campaign_strategy_open()
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 5.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and name == "AUTO_SEARCH_MENU_CONTINUE"
        ):
            if self._campaign_context.mode == 'normal':
                return self.continue_campaign_normal_auto_search()
            return self.continue_campaign_hard_auto_search()
        if self._campaign_context is not None and name == "STRATEGY_OPENED":
            receipt = self.oracle.click_campaign_strategy_close()
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 5.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_STRATEGY_FORMATION_RESOURCES
        ):
            receipt = self.oracle.click_campaign_strategy_formation(
                CAMPAIGN_STRATEGY_FORMATION_RESOURCES[name]
            )
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 5.0
            )
            return receipt
        return UNHANDLED

    def _click_campaign_stage(self, name, campaign_stage_code):
        if campaign_stage_code is not None:
            context = self._require_campaign_context()
            shared_hard_entrance = CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES.get(
                context.stage_code
            )
            if (
                not isinstance(campaign_stage_code, str)
                or name != context.stage_code
                or campaign_stage_code
                not in (context.stage_code, shared_hard_entrance)
            ):
                raise SemanticGateClosed("campaign stage identity changed")
            if context.entry_receipt is not None:
                raise SemanticGateClosed(
                    "campaign stage entry was already submitted"
                )
            # Reuse the input frame prepared by Session.click for both the
            # wallet and exact stage proof. Serial live reads can outlive that
            # lease on WSL even while the stage remains unchanged.
            reader = self._fresh_input_oracle()
            context.oil_before_sortie = reader.campaign_oil()
            receipt = self._dispatch_mutation(
                "campaign.stage_entry",
                lambda: reader.click_campaign_stage(campaign_stage_code),
            )
            context.entry_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._campaign_context is not None and name in (
            "SWITCH_1_NORMAL",
            "SWITCH_1_HARD",
        ):
            destination = "normal" if name == "SWITCH_1_NORMAL" else "hard"
            receipt = self.oracle.click_campaign_mode_switch(destination)
            # CN 9.7.10 rebuilds the chapter list after a hard/normal switch.
            # The NULL swap observer produces no fresh ticks during that
            # rebuild, so keep a long enough window for refresh_frame to wait
            # for the next generation instead of treating the pause as fatal.
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 45.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and name in EVENT_CAMPAIGN_ASIDE_RESOURCES
        ):
            receipt = self.oracle.click_event_campaign_aside(
                EVENT_CAMPAIGN_ASIDE_RESOURCES[name]
            )
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 20.0
            )
            return receipt
        if self._campaign_context is not None and name in (
            "CHAPTER_PREV",
            "CHAPTER_NEXT",
        ):
            direction = "previous" if name == "CHAPTER_PREV" else "next"
            receipt = self.oracle.click_campaign_chapter(direction)
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 20.0
            )
            return receipt
        if self._campaign_context is not None and name == "SWITCH_OVER":
            context = self._require_campaign_context()
            admission = context.combat_admission
            if admission is None:
                raise SemanticGateClosed(
                    "campaign map fleet switch requires an ALAS combat decision"
                )
            displayed_fleet_index = (
                self.oracle.campaign_map_displayed_fleet_index()
            )
            if displayed_fleet_index == admission.fleet_index:
                raise SemanticGateClosed(
                    "campaign map fleet switch target is already displayed"
                )
            if len(context.map_fleet_switch_receipts) >= 1:
                raise SemanticGateClosed(
                    "campaign map fleet switch was already submitted for this combat decision"
                )
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                self.oracle.click_campaign_map_fleet_switch,
            )
            context.map_fleet_switch_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 5.0
            return receipt
        return UNHANDLED

    def _click_campaign_fleet(self, name, campaign_fleet_bar_match):
        if self._campaign_context is not None and name == "FLEET_PREPARATION":
            context = self._require_campaign_context()
            remaining_sorties = self._action_ledger.remaining("campaign.sortie")
            if (
                not context.sortie_authorized
                or not self._action_ledger.allowed("campaign.sortie")
                or remaining_sorties != context.sortie_budget_before
                or context.sortie_receipt is not None
                or context.prepared_fleet_state is None
            ):
                raise SemanticGateClosed(
                    "campaign sortie requires one authorized budget unit"
                )
            receipt = self._dispatch_mutation(
                "campaign.sortie",
                lambda: (
                    self.oracle.click_campaign_auto_search_sortie(
                        self._campaign_resolved_entrance_stage()
                    )
                    if (context.auto_search_role_state is not None or
                        (context.submarine_auto_mode is not None
                         and self.oracle.toggle_selected('campaign/fleet-preparation/roles/tab')))
                    else self.oracle.click_campaign_sortie(
                        self._campaign_resolved_entrance_stage(),
                        fallback_oil_cost=context.map_preparation_oil_cost,
                    )
                ),
            )
            if receipt.generation < context.prepared_fleet_state.generation:
                raise SemanticGateClosed(
                    "campaign sortie target predates prepared fleet state"
                )
            context.sortie_receipt = receipt
            # ANGLE NULL can spend more than a minute in the exact read-only
            # CombatLoadUI while assets stream.  The sortie budget is already
            # consumed, so this longer passive window admits no further input.
            context.passive_transition_until = time.monotonic() + 180.0
            return receipt
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_FLEET_ROW_RESOURCES
        ):
            context = self._require_campaign_context()
            row_key, action = CAMPAIGN_FLEET_ROW_RESOURCES[name]
            if action == "advice":
                raise SemanticGateClosed(
                    "campaign fleet advice is observation-only"
                )
            if action == "select":
                if (
                    context.initial_fleet_state is None
                    or context.requested_fleets is None
                ):
                    raise SemanticGateClosed(
                        "campaign fleet selection was not preflight-authorized"
                    )
                dropdown = self.oracle.campaign_fleet_dropdown_state()
                if dropdown is None:
                    row = self._campaign_fleet_row(row_key)
                    if row.select_button is None:
                        raise SemanticGateClosed(
                            "campaign fleet select row is unavailable: " + row_key
                        )
                    receipt = self.oracle.click_campaign_fleet_row(
                        row_key, "select"
                    )
                    context.fleet_dropdown_row = row_key
                    context.fleet_dropdown_previous_index = row.selected_fleet
                else:
                    close_index = context.fleet_dropdown_previous_index
                    if close_index not in dropdown.active_indices:
                        close_index = (
                            dropdown.active_indices[0]
                            if dropdown.active_indices
                            else None
                        )
                    if (
                        context.fleet_dropdown_row != row_key
                        or close_index not in range(1, 7)
                    ):
                        raise SemanticGateClosed(
                            "campaign fleet dropdown close identity changed"
                        )
                    receipt = self.oracle.click_campaign_fleet_option(
                        close_index
                    )
                    context.fleet_dropdown_row = None
                    context.fleet_dropdown_previous_index = None
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if (
                context.initial_fleet_state is None
                or context.requested_fleets is None
            ):
                raise SemanticGateClosed(
                    "campaign fleet clear was not preflight-authorized"
                )
            row = self._campaign_fleet_row(row_key)
            if not row.in_use:
                observed = self.oracle.campaign_fleet_selection_state(
                    self._campaign_resolved_entrance_stage(),
                    fallback_oil_cost=context.map_preparation_oil_cost,
                )
                matches = tuple(
                    candidate
                    for candidate in observed.rows
                    if candidate.row_key == row_key
                )
                if len(matches) != 1 or matches[0].in_use:
                    raise SemanticGateClosed(
                        "campaign fleet empty-row identity changed"
                    )
                row = matches[0]
                clear_button = row.clear_button
                if (
                    clear_button is None
                    or clear_button.point is None
                    or clear_button.bounds is None
                ):
                    raise SemanticGateClosed(
                        "campaign fleet empty-row clear identity is incomplete"
                    )
                # ALAS sometimes emits an idempotent clear while reconciling
                # partially prepared rows. Preserve that state-machine edge as
                # an observation-only success: no ADB input and no mutation
                # budget are consumed.
                return ActionReceipt(
                    semantic_id={
                        "fleet1": "campaign/fleet-preparation/fleet/1/clear",
                        "fleet2": "campaign/fleet-preparation/fleet/2/clear",
                        "submarine": (
                            "campaign/fleet-preparation/submarine/1/clear"
                        ),
                    }[row_key],
                    generation=observed.generation,
                    point=clear_button.point,
                    bounds=clear_button.bounds,
                    path=clear_button.path,
                )
            if (
                len(context.fleet_mutation_receipts)
                >= context.required_fleet_mutations
            ):
                raise SemanticGateClosed(
                    "campaign fleet clear exceeds the preflight mutation plan"
                )
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                lambda: self.oracle.click_campaign_fleet_row(row_key, "clear"),
            )
            context.fleet_mutation_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if (
            self._campaign_context is not None
            and campaign_fleet_bar_match is not None
        ):
            context = self._require_campaign_context()
            row_key = {
                "FLEET_1": "fleet1",
                "FLEET_2": "fleet2",
                "SUBMARINE": "submarine",
            }[campaign_fleet_bar_match.group(1)]
            index = int(campaign_fleet_bar_match.group(2))
            dropdown = self.oracle.campaign_fleet_dropdown_state()
            if (
                dropdown is None
                or context.fleet_dropdown_row != row_key
                or index in dropdown.active_indices
            ):
                raise SemanticGateClosed(
                    "campaign fleet option is absent or already selected"
                )
            if (
                len(context.fleet_mutation_receipts)
                >= context.required_fleet_mutations
            ):
                raise SemanticGateClosed(
                    "campaign fleet selection exceeds the preflight mutation plan"
                )
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                lambda: self.oracle.click_campaign_fleet_option(index),
            )
            context.fleet_mutation_receipts.append(receipt)
            context.fleet_dropdown_row = None
            context.fleet_dropdown_previous_index = None
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        return UNHANDLED

    def _click_campaign_preparation(self, name, semantic_id):
        if self._campaign_context is not None and name == "BOOK_BOX_AUTO":
            # Configuring the checkbox spends no book or oil. Inherited
            # result menus can be configured too; Continue retains its own
            # independent sortie/resource authorization.
            if not self.oracle.enabled("reward/campaign-total/exit"):
                raise SemanticGateClosed("AUTO book input requires the exact result menu")
            return self._click_campaign_book("auto")
        if self._campaign_context is not None and name == "BOOK_BOX_PREP":
            self._require_campaign_context()
            if self._campaign_preparation_kind() != "fleet":
                raise SemanticGateClosed("2x-book input requires fleet preparation")
            return self._click_campaign_book("prep")
        if self._campaign_context is not None and name in (
            "FAST_FORWARD_ON", "FAST_FORWARD_OFF",
        ):
            context = self._require_campaign_context()
            if context.entry_receipt is None or context.map_preparation_receipt is not None:
                raise SemanticGateClosed("clear-mode input requires owned map preparation")
            if self._campaign_preparation_kind() != "map":
                raise SemanticGateClosed("clear-mode input requires map preparation")
            return self.oracle.click_campaign_clear_mode(name == "FAST_FORWARD_ON")
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_AUTO_SEARCH_RESOURCES
        ):
            context = self._require_campaign_context()
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle requires proven stage entry"
                )
            if context.map_preparation_receipt is not None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle is only valid before map preparation"
                )
            if self._campaign_preparation_kind() != "map":
                raise SemanticGateClosed(
                    "campaign auto-search toggle requires the map-preparation layer"
                )
            reader = self._fresh_input_oracle()
            selected = reader.toggle_selected(
                "campaign/map-preparation/auto-search"
            )
            previous = context.auto_search_toggle_receipt
            if previous is not None and (
                context.auto_search_toggle_previous_state is None
                or selected == context.auto_search_toggle_previous_state
                or reader.read_state().generation <= previous.generation
            ):
                raise SemanticGateClosed(
                    "campaign auto-search toggle has no fresh state-change postcondition"
                )
            if selected != (name in CAMPAIGN_AUTO_SEARCH_ON_RESOURCES):
                raise SemanticGateClosed(
                    "campaign auto-search resource state changed before input"
                )
            # Original ALAS can turn this off, enable clear mode, then turn it
            # back on. Retain its switch semantics while refusing to replay an
            # input whose previous state change has not been observed.
            receipt = reader.click_toggle(
                "campaign/map-preparation/auto-search"
            )
            context.auto_search_toggle_receipt = receipt
            context.auto_search_toggle_previous_state = selected
            context.passive_transition_until = time.monotonic() + 5.0
            return receipt
        if self._campaign_context is not None and name == "MAP_PREPARATION":
            context = self._require_campaign_context()
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign map preparation requires proven stage entry"
                )
            if context.map_preparation_receipt is not None:
                raise SemanticGateClosed(
                    "campaign map-preparation transition is single-use"
                )
            preparation_kind = self._campaign_preparation_kind()
            if preparation_kind not in (None, "map"):
                raise SemanticGateClosed(
                    "campaign map preparation is not the active layer"
                )
            # `appear(MAP_PREPARATION)` and this input call are separate ALAS
            # operations.  During the bounded post-entry transition the
            # adapter may get one incoherent read here and report no kind.
            # The oracle action below performs a fresh, exact page/stage/
            # raycast proof immediately before input, so let that final proof
            # decide rather than failing on the advisory pre-read.
            observed_preparation, stage_code = (
                self._campaign_preparation_state_with_stage()
            )
            if (
                observed_preparation is not None
                and observed_preparation.kind == "map"
            ):
                context.map_preparation_oil_cost = getattr(
                    observed_preparation, "oil_cost", None
                )
            receipt = self.oracle.click_campaign_map_preparation(stage_code)
            context.resolved_stage_code = stage_code
            context.map_preparation_receipt = receipt
            context.passive_transition_until = time.monotonic() + 60.0
            return receipt
        if self._campaign_context is not None and name == "MAP_PREPARATION_CANCEL":
            context = self._require_campaign_context()
            if context.cancel_receipt is not None:
                raise SemanticGateClosed(
                    "campaign preparation cancel is not currently allowed"
                )
            if (
                context.entry_receipt is None
                and context.inherited_cancel_receipt is not None
            ):
                previous = context.inherited_cancel_receipt
                self._package_gate()
                if (self.oracle.read_state().generation > previous.generation
                        and not self.oracle.observation_target_present('campaign/map-preparation/cancel')
                        and not self.oracle.observation_target_present('campaign/fleet-preparation/cancel')
                        and self.oracle.campaign_page_is_normal()
                        and not self.oracle._blocking_rules(self.oracle.read_state(), 'ui/absence-probe')):
                    return previous
                raise SemanticGateClosed(
                    "inherited campaign preparation cancel is single-use"
                )
            if context.entry_receipt is None:
                preparation, resolved_stage_code = (
                    self._campaign_preparation_state_with_stage()
                )
                kind = getattr(preparation, "kind", None)
                if preparation is not None and kind not in ("map", "fleet"):
                    raise SemanticGateClosed(
                        "inherited campaign preparation kind is invalid"
                    )
            else:
                kind, resolved_stage_code = self._campaign_preparation_kind_with_stage()
            if kind in ("map", "fleet") and context.entry_receipt is None:
                # ALAS deliberately closes an already-open stage detail while
                # discovering the current page.  A new process has no local
                # entry receipt for that inherited overlay, but the observer's
                # exact stage/page/raycast proof still makes this reversible
                # cancel safe.  Do not consume the flow's later cancel receipt:
                # the normal pre-sortie proof must still perform its own
                # entry -> preparation -> cancel sequence.
                if kind == "fleet":
                    receipt = self.oracle.cancel_campaign_fleet_preparation(
                        resolved_stage_code
                    )
                else:
                    receipt = self.oracle.cancel_campaign_map_preparation(
                        resolved_stage_code
                    )
                context.inherited_cancel_receipt = receipt
                context.inherited_cancel_kind = kind
                context.inherited_cancel_stage_code = resolved_stage_code
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign preparation cancel requires proven stage entry"
                )
            if kind == "fleet":
                if context.map_preparation_receipt is None:
                    raise SemanticGateClosed(
                        "campaign fleet cancel requires proven map transition"
                    )
                receipt = self.oracle.cancel_campaign_fleet_preparation(
                    resolved_stage_code
                )
            elif kind == "map":
                receipt = self.oracle.cancel_campaign_map_preparation(
                    resolved_stage_code
                )
            else:
                raise SemanticGateClosed(
                    "campaign preparation cancel layer is absent"
                )
            context.preparation_kind = kind
            context.cancel_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._campaign_context is not None and name == "BACK_ARROW":
            if self.oracle.daily_precombat_visible():
                receipt = self.oracle.click_daily_precombat_back()
            elif self.oracle.daily_page_visible():
                receipt = self.oracle.click_daily_control("daily/page/back")
            elif self._campaign_page_back_visible():
                receipt = self.oracle.click("campaign-menu/page/back")
            else:
                receipt = self.oracle.click("event-list/page/back")
                self._campaign_context.event_page_back_receipt = receipt
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 20.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and semantic_id == "campaign-menu/normal"
        ):
            context = self._require_campaign_context()
            if (
                context.menu_entry_receipt is not None
                and time.monotonic() <= context.passive_transition_until
            ):
                return context.menu_entry_receipt
            if semantic_id in ("os/map/fleet-lock/on", "os/map/fleet-lock/off"):
                receipt = self.oracle.click_operation_siren_fleet_lock(
                    semantic_id.rsplit("/", 1)[-1]
                )
            else:
                receipt = self.oracle.click(semantic_id)
            context.menu_entry_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        return UNHANDLED
