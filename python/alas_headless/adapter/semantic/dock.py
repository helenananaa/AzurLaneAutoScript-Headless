"""Dock for the typed ALAS boundary."""

from __future__ import annotations

from typing import Any, Optional, Tuple, Union
from .contracts import AlasSemanticActionDeferred
from ...semantic_oracle import (
    AwakenCostState,
    AwakenExecutionReceipt,
    EnhancementExecutionReceipt,
    EnhancementNoMaterialReceipt,
    EnhancementRejectedReceipt,
    RetirementExecutionReceipt,
    RetirementNoCandidateReceipt,
    SemanticGateClosed,
    enhancement_config_policy,
)


class DockAdapterPorts:
    """Dock ports on the shared adapter context."""

    def retirement_allowed(self) -> bool:
        return self._action_ledger.allowed("retirement.execute")

    def awaken_allowed(self) -> bool:
        return self._action_ledger.allowed("awaken.execute")

    def awaken_receipts(self) -> Tuple[AwakenExecutionReceipt, ...]:
        return tuple(self._awaken_receipts)

    def awaken_cost_observations(self) -> Tuple[AwakenCostState, ...]:
        return tuple(self._awaken_cost_observations)

    def begin_awaken_task(self, favourite: bool) -> None:
        """Open the typed Dock boundary; ALAS retains the task state machine."""

        if not isinstance(favourite, bool):
            raise TypeError("awaken favourite must be boolean")
        if self._awaken_flow_active:
            raise SemanticGateClosed("awaken flow is already active")
        self._require_action_grant('awaken.execute')
        self._package_gate()
        self._awaken_receipts = []
        self._awaken_cost_observations = []
        try:
            self.oracle._enhancement_dock_records()
        except SemanticGateClosed:
            if not self.oracle.main_page_visible():
                raise SemanticGateClosed(
                    "awaken task must start on main or the official Dock"
                )
            self.oracle.click("main/dock")
            self.oracle._retry_transition_read(
                self.oracle._enhancement_dock_records,
                attempts=50,
                interval_seconds=0.1,
            )
        self.oracle.set_enhancement_dock_favourite(favourite)
        self._awaken_flow_active = True

    def prepare_awaken_phase(self, use_array: bool) -> None:
        if not self._awaken_flow_active or not isinstance(use_array, bool):
            raise SemanticGateClosed("awaken phase is not active")
        self.oracle.set_awaken_dock_filter(use_array)

    def awaken_next(self, use_array: bool) -> str:
        """Execute at most one reviewed ship transaction for ALAS's loop."""

        if not self._awaken_flow_active or not isinstance(use_array, bool):
            raise SemanticGateClosed("awaken phase is not active")
        candidates = self.oracle.awaken_dock_candidates()
        if not candidates:
            return "finish"
        try:
            self._require_action_grant('awaken.execute')
        except AlasSemanticActionDeferred as exc:
            raise AlasSemanticActionDeferred(
                'awaken execution budget exhausted with remaining candidates; task completion is unproven'
            ) from exc
        candidate = candidates[0]
        detail, _ = self.oracle.open_awaken_dock_candidate(
            candidate.position,
            candidate.ship_id,
            candidate.ship_name,
            candidate.level,
        )
        cost, _ = self.oracle.open_awaken_confirmation(detail)
        self._awaken_cost_observations.append(cost)
        if cost.use_array != use_array:
            self.oracle.cancel_awaken_confirmation(cost)
            raise SemanticGateClosed(
                "awaken modal resource mode differs from configuration"
            )
        if not cost.sufficient:
            self.oracle.cancel_awaken_confirmation(cost)
            self.oracle.return_from_awaken_detail_to_dock()
            return "insufficient"
        receipt = self._dispatch_mutation(
            "awaken.execute",
            lambda: self.oracle.commit_awaken_confirmation(cost),
        )
        self._awaken_receipts.append(receipt)
        self.oracle.return_from_awaken_detail_to_dock()
        return "continue"

    def finish_awaken_task(self) -> None:
        if not self._awaken_flow_active:
            raise SemanticGateClosed("awaken flow is not active")
        self.oracle.reset_enhancement_dock()
        self._awaken_flow_active = False

    def enhancement_allowed(self) -> bool:
        return self._action_ledger.allowed("enhancement.execute")

    def begin_enhancement_task(
        self,
        ship_to_enhance: str,
        check_per_category: int,
        filter_expression: Optional[str],
    ) -> None:
        """Validate the ALAS-owned flow and open its semantic boundary."""

        enhancement_config_policy(
            ship_to_enhance, check_per_category, filter_expression
        )
        self._require_action_grant('enhancement.execute')
        self._package_gate()
        self.oracle._enhancement_dock_records()
        self._enhancement_receipts = []
        self._enhancement_current_candidate = None
        self._enhancement_no_material_cards = set()
        self._enhancement_flow_active = True

    @staticmethod
    def _enhancement_candidate_key(candidate: Any) -> Tuple[int, int, str, int]:
        return (
            candidate.position,
            candidate.ship_id,
            candidate.ship_name,
            candidate.level,
        )

    def _open_next_enhancement_candidate(self) -> bool:
        candidates = tuple(
            item
            for item in self.oracle.enhancement_dock_candidates()
            if self._enhancement_candidate_key(item)
            not in self._enhancement_no_material_cards
        )
        if not candidates:
            self._enhancement_current_candidate = None
            return False
        candidate = candidates[0]
        self.oracle.open_enhancement_dock_candidate(
            candidate.position,
            candidate.ship_id,
            candidate.ship_name,
            candidate.level,
        )
        self._enhancement_current_candidate = candidate
        return True

    def enhancement_enter(self, favourite: bool, ship_type: Optional[str]) -> bool:
        """Apply one ALAS-selected category and open its first reviewed card."""

        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        if not isinstance(favourite, bool):
            raise TypeError("enhancement favourite policy must be boolean")
        self.oracle.set_enhancement_dock_favourite(favourite)
        self.oracle.set_enhancement_dock_filter(ship_type)
        self._enhancement_no_material_cards = set()
        self._enhancement_current_candidate = None
        return self._open_next_enhancement_candidate()

    def enhancement_choose(self, ship_count: int) -> Tuple[bool, int]:
        """Execute at most one successful ALAS enhancement selection."""

        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        if isinstance(ship_count, bool) or not isinstance(ship_count, int):
            raise TypeError("enhancement ship count must be an integer")
        while ship_count > 0 and self.enhancement_allowed():
            candidate = self._enhancement_current_candidate
            if candidate is None:
                return False, ship_count
            receipt = self._dispatch_mutation(
                "enhancement.execute",
                self.oracle.enhance_with_official_recommendation,
            )
            self._enhancement_receipts.append(receipt)
            if isinstance(receipt, EnhancementExecutionReceipt):
                return True, ship_count
            self._enhancement_no_material_cards.add(
                self._enhancement_candidate_key(candidate)
            )
            # Native ALAS skips a target in battle without consuming its
            # candidate-check count. The rejected action still burns its grant.
            if not isinstance(receipt, EnhancementRejectedReceipt):
                ship_count -= 1
            self.oracle.return_to_enhancement_dock()
            self._enhancement_current_candidate = None
            if not self.enhancement_allowed():
                return False, ship_count
            if not self._open_next_enhancement_candidate():
                return False, ship_count
        return False, ship_count

    def enhancement_leave_category(self) -> None:
        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        if self._enhancement_current_candidate is not None:
            self.oracle.return_to_enhancement_dock()
        self._enhancement_current_candidate = None
        self._enhancement_no_material_cards = set()

    def finish_enhancement_task(self) -> None:
        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        self.enhancement_leave_category()
        self.oracle.reset_enhancement_dock()
        self._enhancement_flow_active = False

    def enhancement_receipts(
        self,
    ) -> Tuple[Union[EnhancementExecutionReceipt, EnhancementNoMaterialReceipt, EnhancementRejectedReceipt], ...]:
        return tuple(self._enhancement_receipts)

    def retire_ships_one_click(self, keep_limit_break: bool) -> int:
        """Run one official retirement transaction and return its real count."""

        if not isinstance(keep_limit_break, bool):
            raise TypeError("retirement limit-break policy must be boolean")
        self._require_action_grant('retirement.execute')
        self._package_gate()
        receipt = self._dispatch_mutation(
            "retirement.execute",
            lambda: self.oracle.retire_ships_one_click(keep_limit_break),
        )
        self._last_retirement_receipt = receipt
        if isinstance(receipt, RetirementNoCandidateReceipt):
            return 0
        return receipt.retired_count

    def retirement_receipt(
        self,
    ) -> Optional[Union[RetirementExecutionReceipt, RetirementNoCandidateReceipt]]:
        return self._last_retirement_receipt
