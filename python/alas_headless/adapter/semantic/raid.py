"""Raid for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Optional
from ...semantic_oracle import (
    ActionReceipt,
    RaidMultipleSortieState,
    SemanticGateClosed,
)


class RaidAdapterPorts:
    """Raid ports on the shared adapter context."""

    def supports_raid_layout(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().supports_raid_layout(event)

    def current_raid_result_active(self) -> bool:
        """Return whether an exact current-Raid sortie owns the result stack."""

        return self._current_raid_result_event is not None

    def raid_remain(self, event: str, mode: str) -> int:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_remain(
            event=event, mode=mode
        )

    def raid_page_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_page_visible(
            event=event
        )

    def click_raid_stage(self, event: str, mode: str) -> ActionReceipt:
        self._package_gate()
        deadline = time.monotonic() + 10.0
        while True:
            try:
                return self._fresh_input_oracle().click_raid_stage(
                    event=event, mode=mode
                )
            except SemanticGateClosed as exc:
                if str(exc) != "Raid stage input is blocked":
                    raise
                # The current Raid cards fan into their final positions after
                # the page identity is already complete.  A geometric overlap
                # rejects the input before dispatch; keep observing until the
                # exact target is unobscured, without clicking again.
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "current Raid stage did not become actionable"
                    ) from exc
                time.sleep(0.25)

    def click_raid_advanced_challenge(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_advanced_challenge(event=event)

    def enter_raid_page(self, event: str) -> ActionReceipt:
        self._package_gate()
        input_oracle = self._fresh_input_oracle()
        if not input_oracle.supports_raid_layout(event) or not input_oracle.main_page_visible():
            raise SemanticGateClosed("current Raid entry requires the reviewed main page")
        receipt = input_oracle.click("main/raid")
        deadline = time.monotonic() + 10.0
        last_transition_error: Optional[SemanticGateClosed] = None
        while True:
            try:
                if self.oracle.raid_page_visible(event=event):
                    break
            except SemanticGateClosed as exc:
                # The stage cards animate independently while the exact Raid
                # root is opening.  A temporary geometry mismatch is not an
                # input authorization; keep observing without another click.
                last_transition_error = exc
            if time.monotonic() >= deadline:
                if last_transition_error is not None:
                    raise SemanticGateClosed(
                        "current Raid page did not stabilize: {0}".format(
                            last_transition_error
                        )
                    ) from last_transition_error
                raise SemanticGateClosed("current Raid page did not open")
            time.sleep(0.25)
        return receipt

    def click_raid_home(self, event: str) -> ActionReceipt:
        self._package_gate()
        # The current Raid page carries a large UI projection.  Acquire it once
        # as the immutable screenshot-equivalent, then run the full page,
        # image, blocker and raycast proof against that same fresh frame.  This
        # preserves the input-age gate without extending its threshold.
        receipt = self._fresh_input_oracle().click_raid_home(event=event)
        deadline = time.monotonic() + 10.0
        while not self.oracle.main_page_visible():
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("main page did not open from current Raid")
            time.sleep(0.25)
        return receipt

    def raid_fleet_selection_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_fleet_selection_visible(
            event=event
        )

    def raid_fleet_ready(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_fleet_ready(event=event)

    def click_raid_fleet_back(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_fleet_back(event=event)

    def click_raid_fleet_start(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_fleet_start(event=event)

    def click_raid_fleet_recommend(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._dispatch_mutation(
            "campaign.fleet_mutation",
            lambda: self._fresh_input_oracle().click_raid_fleet_recommend(
                event=event
            ),
        )

    def raid_precombat_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_precombat_visible(
            event=event
        )

    def raid_precombat_multiple_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_precombat_multiple_visible(
            event=event
        )

    def click_raid_precombat_multiple(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_precombat_multiple(event=event)

    def raid_multiple_sortie_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_multiple_sortie_visible(
            event=event
        )

    def raid_multiple_sortie_state(self, event: str) -> RaidMultipleSortieState:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_multiple_sortie_state(
            event=event
        )

    def click_raid_multiple_sortie_back(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_multiple_sortie_back(
            event=event
        )

    def raid_precombat_notice_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_precombat_notice_visible(
            event=event
        )

    def click_raid_precombat_notice(self, event: str) -> ActionReceipt:
        self._package_gate()
        receipt = self._fresh_input_oracle().click_raid_precombat_notice(event=event)
        deadline = time.monotonic() + 10.0
        last_transition_error: Optional[SemanticGateClosed] = None
        while True:
            try:
                if not self.oracle.raid_precombat_notice_visible(event=event):
                    return receipt
            except SemanticGateClosed as exc:
                # The information box tears down its text and image children
                # before the root button.  No further input is authorized
                # during that one-way transition.
                last_transition_error = exc
            if time.monotonic() >= deadline:
                if last_transition_error is not None:
                    raise SemanticGateClosed(
                        "Raid precombat notice did not close: {0}".format(
                            last_transition_error
                        )
                    ) from last_transition_error
                raise SemanticGateClosed("Raid precombat notice did not close")
            time.sleep(0.25)

    def click_raid_precombat_start(self, event: str) -> ActionReceipt:
        self._package_gate()
        receipt = self._dispatch_mutation(
            "campaign.sortie",
            lambda: self._fresh_input_oracle().click_raid_precombat_start(
                event=event
            ),
        )
        self._current_raid_result_event = event
        return receipt

    def click_raid_precombat_back(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_precombat_back(event=event)
