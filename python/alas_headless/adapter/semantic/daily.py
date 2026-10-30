"""Daily for the typed ALAS boundary."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import List, Tuple
from ...adapter import StaleFrameError
from ...semantic_oracle import ActionReceipt, SemanticGateClosed
from .dispatch_result import UNHANDLED


class DailyAdapterPorts:
    """Daily ports on the shared adapter context."""

    def daily_current_active(self) -> bool:
        self._package_gate()
        return self.oracle.daily_current_active()

    def daily_current_kind(self) -> str:
        self._package_gate()
        return self.oracle.daily_current_kind()

    def daily_current_remain(self) -> int:
        self._package_gate()
        return self.oracle.daily_current_remain()

    def daily_detail_visible(self) -> bool:
        self._package_gate()
        return self.oracle.daily_detail_visible()

    def daily_precombat_visible(self) -> bool:
        self._package_gate()
        return self.oracle.daily_precombat_visible()

    def daily_fleet_index(self) -> int:
        self._package_gate()
        return self.oracle.daily_fleet_index()

    def click_daily_current_card(self) -> ActionReceipt:
        self._package_gate()
        kind = self.oracle.daily_current_kind()
        receipt = self.oracle.click_daily_current_card()
        self._daily_kind = kind
        self._daily_stage = None
        self._daily_pending_stage_receipt = None
        self._daily_stage_confirmed = False
        self._daily_quick_reward_closed = False
        return receipt

    def click_daily_stage(self, index: int) -> ActionReceipt:
        self._package_gate()
        if self._daily_kind is None:
            raise SemanticGateClosed("daily challenge identity was not admitted")
        if (
            self._daily_stage == index
            and self._daily_pending_stage_receipt is not None
            and time.monotonic() <= self._daily_transition_until
        ):
            return self._daily_pending_stage_receipt
        receipt = self.oracle.click_daily_stage(index)
        self._daily_stage = index
        self._daily_pending_receipt = None
        self._daily_pending_stage_receipt = receipt
        self._daily_stage_confirmed = False
        self._daily_quick_reward_closed = False
        self._daily_transition_until = time.monotonic() + 45.0
        return receipt

    def click_daily_fleet(self, direction: str) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_fleet(direction)

    def click_daily_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        if self._daily_kind is None or self._daily_stage not in (1, 2, 3):
            raise SemanticGateClosed("daily execution intent is incomplete")
        if self._daily_pending_receipt is not None:
            return self._daily_pending_receipt
        fleet = self.oracle.daily_fleet_index()
        receipt = self._dispatch_mutation(
            "daily.execute", self.oracle.click_daily_precombat_start
        )
        receipt = replace(
            receipt,
            semantic_id="daily/execute/{0}/stage/{1}/fleet/{2}".format(
                self._daily_kind, self._daily_stage, fleet
            ),
        )
        self._daily_execution_receipts.append(receipt)
        self._daily_pending_receipt = receipt
        self._daily_transition_until = time.monotonic() + 20.0
        return receipt

    def exercise_execute_allowed(self) -> bool:
        self._package_gate()
        return self._action_ledger.allowed("exercise.execute")

    def exercise_refresh_allowed(self) -> bool:
        self._package_gate()
        return self._action_ledger.allowed("exercise.refresh")

    def click_exercise_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        if not (self._exercise_pending or self._exercise_execution_active):
            raise SemanticGateClosed("exercise execution intent is incomplete")
        receipt = self._dispatch_mutation(
            "exercise.execute", self.oracle.click_daily_precombat_start
        )
        self._exercise_pending = False
        self._exercise_execution_active = True
        return replace(receipt, semantic_id="exercise/execute")

    def complete_daily_battle_result(self, timeout_seconds: float = 30.0) -> Tuple[ActionReceipt, ...]:
        """Drain a typed Daily-compatible result stack to its owning page."""

        self._package_gate()
        deadline = time.monotonic() + timeout_seconds
        receipts: List[ActionReceipt] = []
        while time.monotonic() < deadline:
            if self._current_raid_result_event is not None:
                try:
                    raid_page_visible = self.oracle.raid_page_visible(
                        event=self._current_raid_result_event
                    )
                except SemanticGateClosed as exc:
                    if str(exc) not in (
                        "current Raid stage identity is absent or ambiguous",
                        "current Raid stage sprites are absent or ambiguous",
                        "current Raid stage sprite does not cover its button",
                    ):
                        raise
                    # The Raid page remounts behind the final result transition
                    # before its five cards finish their layout.  No input is
                    # authorized by an incomplete page; keep observing the
                    # already-dispatched one-way return instead.
                    time.sleep(0.25)
                    continue
                if raid_page_visible:
                    self._current_raid_result_event = None
                    return tuple(receipts)
            elif self.oracle.daily_page_visible():
                return tuple(receipts)
            if getattr(self.oracle, 'campaign_battle_fail_tip_visible', lambda: False)():
                try:
                    self._refresh_tactical_input_frame()
                except StaleFrameError:
                    time.sleep(0.25)
                    continue
                if self.oracle.close_campaign_battle_fail_tip_if_present():
                    time.sleep(0.25)
                    continue
            if self.oracle.daily_battle_result_visible():
                try:
                    self._refresh_tactical_input_frame()
                except StaleFrameError:
                    # Unity can invalidate the result frame while changing
                    # grade -> statistics -> reward.  No input occurred, so
                    # wait for the next typed frame and retry observation.
                    time.sleep(0.25)
                    continue
                try:
                    receipts.append(self.oracle.click_daily_battle_result())
                except SemanticGateClosed:
                    # The grade/statistics pages can advance while the
                    # button-only frame is being refreshed.  Re-observe the
                    # typed stack instead of treating that proven transition
                    # as a failed click.
                    continue
                time.sleep(1.0)
                continue
            if self.oracle.campaign_battle_reward_visible():
                target = (
                    "reward/award-info/close"
                    if self.oracle.enabled("reward/award-info/close")
                    else "reward/award-info1/close"
                )
                try:
                    self._refresh_tactical_input_frame()
                except StaleFrameError:
                    time.sleep(0.25)
                    continue
                try:
                    receipts.append(self.oracle.click(target))
                except SemanticGateClosed:
                    # AwardInfo can close as its fresh input frame arrives.
                    continue
                time.sleep(1.0)
                continue
            time.sleep(0.25)
        if self._current_raid_result_event is not None:
            raise SemanticGateClosed(
                "current Raid battle result did not return to Raid page"
            )
        raise SemanticGateClosed("daily battle result did not return to Daily page")

    def daily_execution_receipts(self) -> Tuple[ActionReceipt, ...]:
        return tuple(self._daily_execution_receipts)

    def daily_quick_consumed(self) -> bool:
        """Prove this session's skip spent the selected card's final count."""
        self._package_gate()
        receipt = self._daily_pending_receipt
        kind = self._daily_kind
        if (
            receipt is None
            or kind is None
            or receipt.semantic_id != "daily/execute/{0}/stage/{1}/quick/all".format(
                kind, self._daily_stage
            )
        ):
            return False
        state = self.oracle.read_state()
        return bool(
            state.generation > receipt.generation
            and self.oracle.daily_page_visible()
            and self.oracle.daily_remaining_for_kind(kind) == 0
        )

    def daily_quick_complete(self) -> bool:
        """Release ALAS' loop only after the correlated reward was closed."""
        return bool(
            self.daily_quick_consumed()
            and self._daily_quick_reward_closed
            and self._award_close_target() is None
        )

    def daily_execution_active(self) -> bool:
        """Return whether the result owner is the bounded Daily flow."""

        return self._daily_kind is not None and self._campaign_context is None

    def click_daily_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_control("daily/page/back")

    def click_daily_precombat_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_precombat_back()

    def _click_daily(self, name):
        if name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3') and self.daily_execution_active():
            target = self._award_close_target()
            if target is not None:
                receipt = self.oracle.click(target)
                pending = self._daily_pending_receipt
                if (
                    pending is not None
                    and pending.semantic_id.endswith('/quick/all')
                    and receipt.generation > pending.generation
                ):
                    self._daily_quick_reward_closed = True
                return receipt
        if name == "DAILY_ENTER":
            return self.click_daily_current_card()
        if name.startswith("DAILY_MISSION_"):
            return self.click_daily_stage(int(name.rsplit("_", 1)[1]))
        if name == "DAILY_NORMAL_RUN":
            receipt = self.oracle.click_daily_run_choice("normal")
            self._daily_transition_until = time.monotonic() + 45.0
            return receipt
        if name == "DAILY_SKIP":
            if self._daily_kind is None or self._daily_stage not in (1, 2, 3):
                raise SemanticGateClosed("daily execution intent is incomplete")
            receipt = self._dispatch_mutation(
                "daily.execute", lambda: self.oracle.click_daily_run_choice("skip")
            )
            receipt = replace(
                receipt,
                semantic_id="daily/execute/{0}/stage/{1}/quick/all".format(
                    self._daily_kind, self._daily_stage
                ),
            )
            self._daily_execution_receipts.append(receipt)
            self._daily_pending_receipt = receipt
            self._daily_transition_until = time.monotonic() + 45.0
            return receipt
        return UNHANDLED
