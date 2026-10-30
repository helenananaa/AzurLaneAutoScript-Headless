"""Commission for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Optional, Tuple
from ...semantic_oracle import (
    ActionReceipt,
    CommissionDetailState,
    CommissionRewardProof,
    CommissionRowState,
    CommissionScrollProof,
    CommissionScrollState,
    CommissionStartProof,
    SemanticGateClosed,
    SemanticTargetMissing,
)
from .contracts import _CommissionFlowContext, AlasSemanticCommissionStartUnproven
from .dispatch_result import UNHANDLED
from .resources import COMMISSION_CLICK_RESOURCES, COMMISSION_TAB_TARGETS
from ...oracle.errors import SemanticSnapshotStale
from ...oracle.input_outcome import input_result_scope


class CommissionAdapterPorts:
    """Commission ports on the shared adapter context."""

    def begin_commission(self) -> None:
        """Open one ALAS-owned commission state-machine invocation."""

        self._package_gate()
        if (
            self._commission_context is not None
            or self._login_flow.active
            or self._mail_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._supply_pack_context is not None
            or self._minigame_context is not None
            or self._build_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._commission_context = _CommissionFlowContext(
            flow_kind="commission",
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_commission(self) -> None:
        self._commission_context = None

    def _require_commission_context(self) -> _CommissionFlowContext:
        if self._commission_context is None:
            raise SemanticGateClosed(
                "commission resource used outside ALAS commission flow"
            )
        return self._commission_context

    def _known_commission_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/more",
                "reward/page/back",
                "reward/commission/finish",
                "reward/commission/go",
                "commission/page/back",
                "commission/detail/back",
                "commission/detail/recommend",
                "commission/detail/start",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "reward/award-info1/close",
                "tactical/page/back",
                "tactical/continue/cancel",
            )
        )

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        self._package_gate()
        self._require_commission_context()
        return self._frame_or_live_observation_oracle().commission_rows()

    def commission_is_empty(self) -> bool:
        self._package_gate()
        self._require_commission_context()
        return self._frame_or_live_observation_oracle().commission_is_empty()

    def commission_scroll_state(self) -> CommissionScrollState:
        self._package_gate()
        self._require_commission_context()
        # Native ALAS inspects the scrollbar after detecting this screenshot's
        # rows. Reuse its immutable projection instead of splitting a new live
        # Button/UI pair. The actual swipe still acquires a fresh input frame
        # and proves movement against live postconditions below.
        return self._frame_or_live_observation_oracle().commission_scroll_state()

    def commission_scroll_next(self) -> Optional[CommissionScrollProof]:
        self._package_gate()
        self._require_commission_context()
        source = self._fresh_input_oracle()
        return self._live_oracle.commission_scroll_next(precondition_oracle=source)

    def commission_scroll_to_top(self) -> Optional[CommissionScrollProof]:
        self._package_gate()
        self._require_commission_context()
        return self._live_oracle.commission_scroll_to_top(precondition_oracle_factory=self._fresh_input_oracle)

    def commission_reward_pending(self) -> bool:
        """Detect a finished commission only from the typed reward summary."""

        context = self._require_commission_context()
        if context.flow_kind != "commission":
            raise SemanticGateClosed(
                "commission reward state used outside commission flow"
            )
        self._package_gate()
        # Native page arrival and this pending check share the screenshot
        # frame. Split live reads can cross a sidebar transition; the actual
        # claim still prepares and validates its own fresh input frame.
        source = self._frame_or_live_observation_oracle()
        if not source.exists("reward/commission/finish"):
            context.reward_detected_count = None
            return False
        if not source.enabled("reward/commission/finish"):
            raise SemanticGateClosed("commission reward finish input is blocked")
        count = source.reward_summary_count("commission", "finished")
        if count <= 0:
            raise SemanticGateClosed(
                "commission reward button contradicts the finished counter"
            )
        context.reward_detected_count = count
        return True

    def commission_reward_allowed(self) -> bool:
        context = self._require_commission_context()
        return (
            context.flow_kind == "commission"
            and self._action_ledger.allowed("commission.reward")
            and context.reward_detected_count is not None
            and context.reward_detected_count > 0
            and context.reward_claim_receipt is None
        )

    def _commission_next_reward_cycle_ready(self) -> bool:
        context = self._require_commission_context()
        claim = context.reward_claim_receipt
        if claim is None:
            return False
        previous_generation = claim.generation
        if context.reward_close_receipts:
            close = context.reward_close_receipts[-1]
            if not hasattr(close, 'generation') or close.generation <= claim.generation:
                return False
            previous_generation = close.generation
        # ALAS owns the receive loop and click interval. A fresh, uncovered
        # sidebar may still offer a finished commission when the last input
        # produced no popup, or after a previous popup chain closed. Recheck
        # that actual surface and consume a new grant instead of pretending
        # the old receipt represents another input.
        state = self.oracle.read_state()
        return (state.generation > previous_generation
                and self._reward_sidebar_ready(self.oracle)
                and self.oracle.enabled('reward/commission/finish')
                and self._award_close_target() is None
                and not self.oracle.enabled('reward/ship-exp/close')
                and not self.oracle.new_ship_reward_page_visible())

    def commission_reward_claimed(self) -> bool:
        context = self._require_commission_context()
        return context.reward_claim_receipt is not None

    def confirm_commission_reward(self) -> CommissionRewardProof:
        """Prove the final native claim drained its observed finished rows."""

        context = self._require_commission_context()
        if context.flow_kind != "commission":
            raise SemanticGateClosed(
                "commission reward proof used outside commission flow"
            )
        if context.reward_proof is not None:
            return context.reward_proof
        if context.reward_claim_receipt is None:
            raise SemanticGateClosed("commission reward input was not recorded")
        if context.reward_detected_count is None or context.reward_detected_count <= 0:
            raise SemanticGateClosed(
                "commission reward proof requires a positive observed finished count"
            )
        if not context.reward_close_receipts:
            raise SemanticGateClosed(
                "commission reward popup chain has no reviewed close input"
            )
        self._package_gate()
        if not self.oracle.enabled("commission/page/back"):
            raise SemanticGateClosed(
                "commission page is absent after reward popup closure"
            )
        back = self.oracle.click("commission/page/back")
        context.passive_transition_until = time.monotonic() + 12.0
        self.oracle.wait_for(
            "reward/page/back",
            timeout_seconds=12.0,
            minimum_generation=back.generation,
        )
        after = self.oracle.reward_summary_count("commission", "finished")
        if after != 0:
            raise SemanticGateClosed(
                "commission reward finished counter did not reach zero"
            )
        generation = self.oracle.read_state().generation
        context.reward_proof = CommissionRewardProof(
            before_finished_count=context.reward_detected_count,
            after_finished_count=after,
            claim_generation=context.reward_claim_receipt.generation,
            close_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.reward_close_receipts
            ),
            generation=generation,
        )
        return context.reward_proof

    def commission_start_allowed(self) -> bool:
        context = self._require_commission_context()
        return (
            context.flow_kind == "commission"
            and self._action_ledger.allowed("commission.start")
        )

    def commission_selection_active(self) -> bool:
        context = self._require_commission_context()
        return (context.selected_signature is not None
                and not self._commission_selected_row_still_on_list())

    def _commission_selected_row_still_on_list(self) -> bool:
        """A row click owns an intent, not proof that its detail has opened."""
        context = self._require_commission_context()
        if context.selected_signature is None or context.start_receipt is not None:
            return False
        self._package_gate()
        oracle = self._frame_or_live_observation_oracle()
        if (oracle.observation_target_present('commission/detail/back')
                or not oracle.enabled('commission/page/back')):
            return False
        rows = oracle.commission_rows()
        matches = tuple(row for row in rows if row.signature == context.selected_signature)
        return len(matches) == 1

    def commission_detail_state(self) -> CommissionDetailState:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_detail_state()

    def commission_start_confirmed(self) -> bool:
        context = self._require_commission_context()
        if context.start_receipt is None or context.selected_signature is None:
            return False
        if context.start_proof is not None:
            return True
        with input_result_scope():
            prompt_cost = self.oracle.commission_start_prompt_cost()
            if prompt_cost is not None:
                if context.selected_oil_cost != prompt_cost:
                    raise SemanticGateClosed("commission start oil cost changed")
                return False
            try:
                context.start_proof = self.oracle.commission_start_transition(
                    context.selected_signature
                )
            except SemanticSnapshotStale:
                raise
            except SemanticGateClosed:
                rejected = self.oracle.commission_start_oil_rejection_generation(
                    context.selected_signature, context.selected_oil_cost,
                    context.start_receipt.generation)
                if rejected is not None:
                    raise AlasSemanticCommissionStartUnproven(
                        context.start_receipt, rejected, context.selected_signature,
                        rejection='client oil capacity')
                if time.monotonic() - context.start_clicked_at <= 15.0:
                    return False
                pending_generation = self.oracle.commission_start_pending_generation(
                    context.selected_signature, context.selected_oil_cost)
                if (pending_generation is not None
                        and pending_generation > context.start_receipt.generation):
                    # ALAS keeps its failure interval and later reselects from a
                    # fresh queue. Preserve the consumed grant and stop this start;
                    # do not acknowledge success or replay the accepted input.
                    raise AlasSemanticCommissionStartUnproven(
                        context.start_receipt, pending_generation,
                        context.selected_signature)
                raise
        return True

    def commission_start_proof(self) -> CommissionStartProof:
        """Return the cached typed proof after the exact row entered running state."""

        context = self._require_commission_context()
        if not self.commission_start_confirmed() or context.start_proof is None:
            raise SemanticGateClosed("commission start transition is not proven")
        return context.start_proof

    def close_started_commission_detail(self) -> ActionReceipt:
        """Leave the proven running detail without touching its cancel action."""

        context = self._require_commission_context()
        if context.start_proof is None:
            raise SemanticGateClosed(
                "commission running detail cannot close before start proof"
            )
        self._package_gate()
        if not self.oracle.enabled("commission/detail/back"):
            raise SemanticGateClosed("proven commission detail back is absent")
        receipt = self.oracle.click("commission/detail/back")
        context.passive_transition_until = time.monotonic() + 12.0
        self.oracle.wait_for(
            "reward/page/back",
            timeout_seconds=12.0,
            minimum_generation=receipt.generation,
        )
        context.selected_signature = None
        context.selected_at = 0.0
        context.start_receipt = None
        context.start_clicked_at = 0.0
        context.start_proof = None
        context.selected_oil_cost = None
        context.start_confirm_receipt = None
        return receipt

    def _close_commission_award(self, target):
        """Let the original receive loop observe the next popup after one close."""
        oracle = self.oracle
        receipt = self._fresh_input_oracle().click(target)
        for attempt in range(20):
            state = oracle.read_state()
            if state.generation > receipt.generation and not any(
                button.active_in_hierarchy and any(root in button.path for root in (
                    '/AwardInfoUI(Clone)/', '/AwardInfoUI1(Clone)/'))
                for button in state.buttons
            ):
                return receipt
            if (state.generation > receipt.generation
                    and oracle.reward_item_info_visible()):
                # The accepted award input exposed its typed item description.
                # Return to ALAS' existing popup handler without another input
                # or claiming that the covered award has finished closing.
                return receipt
            if attempt < 19:
                time.sleep(0.1)
        raise SemanticGateClosed('commission reward did not close after one input')

    def _commission_ship_exp_completed_transition(self, *, wait=False):
        """Acknowledge an observed EXP page already closed by our last input."""
        context = self._require_commission_context()
        observed = context.ship_exp_observation_generation
        if (context.flow_kind != 'commission' or observed is None
                or context.reward_claim_receipt is None
                or not context.reward_close_receipts
                or time.monotonic() > context.passive_transition_until):
            return None
        previous = context.reward_close_receipts[-1]
        if (previous.semantic_id != 'reward/ship-exp/close'
                or observed < previous.generation):
            return None
        while True:
            state = self.oracle.read_state()
            awards = tuple(button for target in ('reward/award-info/close', 'reward/award-info1/close')
                           for button in self.oracle._matches(state, target)
                           if button.active_in_hierarchy and button.active_and_enabled)
            if len(awards) > 1:
                raise SemanticGateClosed('commission EXP return award is ambiguous')
            blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
            if any(rule.blocker_id not in ('award-info', 'award-info1', 'commission-page', 'reward-page', 'loading', 'ship-exp')
                   for rule in blockers):
                return None
            sidebar = self.oracle._matches(state, 'reward/page/back')
            if len(sidebar) > 1:
                raise SemanticGateClosed('commission EXP return sidebar is ambiguous')
            returned_sidebar = bool(
                len(sidebar) == 1 and sidebar[0].actionable
                and not self.oracle._blocking_rules(state, 'reward/page/back')
            )
            if (state.generation > observed and (len(awards) == 1 or returned_sidebar)
                    and not any(button.active_in_hierarchy and '/ShipExpUI(Clone)/' in button.path
                                for button in state.buttons)
                    and not any(rule.blocker_id in ('loading', 'ship-exp') for rule in blockers)):
                # This acknowledges the already accepted EXP close. The next
                # award can still be fading in, or the final EXP can return
                # directly to the actual reward sidebar. Native ALAS owns
                # the next reward/page edge; no new close input is sent.
                context.ship_exp_observation_generation = None
                return previous
            if not wait or time.monotonic() >= context.passive_transition_until:
                return None
            # Only the no-input refusal caller waits, within the existing
            # accepted-close transition window. No additional input is sent.
            time.sleep(.1)

    def _click_commission(self, name, button, semantic_id, commission_row_match):
        if (
            self._commission_context is not None
            and name in COMMISSION_CLICK_RESOURCES
        ):
            tab_target = COMMISSION_TAB_TARGETS.get(name)
            if tab_target is not None:
                receipt = self._fresh_input_oracle().click_image(tab_target)
                self._commission_context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name in ("COMMISSION_ADVICE", "COMMISSION_START"):
                context = self._commission_context
                if context.selected_signature is None:
                    raise SemanticGateClosed("commission row selection is not proven")
                if name == "COMMISSION_ADVICE":
                    return self._fresh_input_oracle().click_commission_recommend(
                        context.selected_signature
                    )
                if context.start_receipt is not None:
                    return context.start_receipt
                self._require_action_grant("commission.start")
                input_oracle = self._fresh_input_oracle()
                detail = input_oracle.commission_detail_state()
                expected = context.selected_signature
                if detail.signature != (expected[1], expected[2], expected[3]):
                    raise SemanticGateClosed(
                        "selected commission detail identity changed"
                    )
                if detail.selected_ship_count < 3:
                    raise SemanticGateClosed(
                        "commission start requires at least three assigned ships"
                    )
                context.selected_oil_cost = detail.oil_cost
                receipt = self._dispatch_mutation(
                    "commission.start",
                    lambda: input_oracle.click_commission_start(
                        context.selected_signature
                    ),
                )
                context.start_receipt = receipt
                context.start_clicked_at = time.monotonic()
                return receipt
            if name == "BACK_ARROW":
                input_oracle = self._fresh_input_oracle()
                targets = tuple(
                    semantic_id
                    for semantic_id in (
                        "tactical/book/cancel",
                        "tactical/page/back",
                        "commission/page/back",
                    )
                    if input_oracle.enabled(semantic_id)
                )
                previous = self._commission_context.navigation_back_receipt
                if (not targets and previous is not None
                        and time.monotonic() <= self._commission_context.passive_transition_until
                        and input_oracle.read_state().generation > previous.generation
                        and not input_oracle.observation_target_present(previous.semantic_id)):
                    return previous
                if len(targets) != 1:
                    raise SemanticGateClosed(
                        "contextual ALAS back target is absent or ambiguous"
                    )
                receipt = self._record_mission_transition(input_oracle.click(targets[0]))
                self._commission_context.navigation_back_receipt = receipt
                return receipt
            if name in ("EXP_INFO_S_REWARD", "REWARD_SAVE_CLICK"):
                context = self._commission_context
                if context.flow_kind == "commission":
                    pass
                elif context.tactical_reward_receipt is None:
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                if (context.flow_kind == 'commission'
                        and not self.oracle.observation_target_present('reward/ship-exp/close')):
                    completed = self._commission_ship_exp_completed_transition()
                    if completed is not None:
                        return completed
                input_count = getattr(self.oracle, 'input_dispatch_count', None)
                try:
                    receipt = self.oracle.click("reward/ship-exp/close")
                except SemanticTargetMissing:
                    # EXP can disappear between the presence read and the
                    # guarded click. Reuse only the already recorded close
                    # whose next native award is freshly proven, before any
                    # new input. ALAS will handle that award on its next loop.
                    if (context.flow_kind == 'commission'
                            and type(input_count) is int
                            and self.oracle.input_dispatch_count == input_count):
                        completed = self._commission_ship_exp_completed_transition(wait=True)
                        if (completed is not None
                                and self.oracle.input_dispatch_count == input_count):
                            return completed
                    raise
                context.ship_exp_observation_generation = None
                if context.flow_kind == "commission":
                    context.reward_close_receipts.append(receipt)
                return self._record_mission_transition(receipt)
            if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                context = self._commission_context
                if (name == 'GET_ITEMS_1'
                        and context.flow_kind == 'commission'
                        and context.reward_claim_receipt is None
                        and self.oracle.enabled('reward/ship-exp/close')):
                    receipt = self.oracle.click('reward/ship-exp/close')
                    context.reward_close_receipts.append(receipt)
                    return self._record_mission_transition(receipt)
                if (
                    context.flow_kind != "commission"
                    and context.tactical_reward_receipt is None
                ):
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                target = self._award_close_target()
                if target is None:
                    if context.flow_kind == "commission":
                        previous = (context.reward_close_receipts[-1]
                                    if context.reward_close_receipts else None)
                        if (context.reward_claim_receipt is not None
                                and previous is not None
                                and previous.semantic_id == 'reward/ship-exp/close'
                                and time.monotonic() <= context.passive_transition_until):
                            oracle = self._frame_or_live_observation_oracle()
                            state = oracle.read_state()
                            award_roots = {
                                b.path.split(root, 1)[0] + root
                                for b in state.buttons
                                if b.active_in_hierarchy and b.active_and_enabled
                                for root in ('/AwardInfoUI(Clone)/', '/AwardInfoUI1(Clone)/')
                                if root in b.path
                            }
                            if (state.generation > previous.generation
                                    and len(award_roots) == 1
                                    and not any(b.active_in_hierarchy and '/ShipExpUI(Clone)/' in b.path
                                                for b in state.buttons)
                                    and all(rule.blocker_id in ('award-info', 'award-info1', 'reward-page')
                                            for rule in oracle._blocking_rules(state, 'ui/absence-probe'))):
                                # EXP has already closed. AwardInfo's hierarchy
                                # can mount before its close Button is ready.
                                # Let ALAS acquire its next screenshot; no input
                                # or synthetic close receipt is needed here.
                                return None
                            if (state.generation > previous.generation
                                    and self._reward_sidebar_ready(oracle)
                                    and not oracle._blocking_rules(state, 'reward/page/back')
                                    and not any(b.active_in_hierarchy and any(root in b.path for root in (
                                        '/ShipExpUI(Clone)/', '/AwardInfoUI(Clone)/', '/AwardInfoUI1(Clone)/'))
                                        for b in state.buttons)):
                                # The last EXP can return directly to the hub.
                                # Native ALAS still checks award aliases from
                                # its preceding screenshot in this iteration.
                                # Give its next screenshot the page: no input
                                # and no fabricated award-close receipt.
                                return None
                        recorded_awards = tuple(
                            recorded
                            for recorded in context.reward_close_receipts
                            if recorded.semantic_id in (
                                "reward/award-info/close",
                                "reward/award-info1/close",
                            )
                        )
                        if recorded_awards:
                            # ALAS can decide a cached popup asset still appears
                            # immediately after the Unity object has gone away.
                            # Reuse the last exact receipt instead of turning
                            # that observation race into another ADB input.
                            return recorded_awards[-1]
                    raise SemanticGateClosed("reviewed commission reward popup is absent")
                receipt = (self._close_commission_award(target)
                           if context.flow_kind == 'commission'
                           else self.oracle.click(target))
                if (
                    context.flow_kind == "commission"
                    and context.reward_claim_receipt is not None
                ):
                    context.reward_close_receipts.append(receipt)
                return self._record_mission_transition(receipt)

        if self._commission_context is not None and commission_row_match is not None:
            signature = getattr(button, "semantic_commission_signature", None)
            if not isinstance(signature, tuple) or len(signature) != 6:
                raise SemanticGateClosed("ALAS commission row identity is malformed")
            receipt = self._fresh_input_oracle().click_commission_row(signature)
            context = self._commission_context
            context.selected_signature = signature
            context.selected_at = time.monotonic()
            context.start_receipt = None
            context.start_clicked_at = 0.0
            context.start_proof = None
            return receipt
        return UNHANDLED
