"""Mission for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Optional, Tuple, Union
from ...semantic_oracle import (
    ActionReceipt,
    MissionDisposition,
    MissionPageState,
    SemanticGateClosed,
)
from .contracts import (
    AlasSemanticUnmapped,
    MissionClaimReceipt,
    MissionClaimableDetected,
    MissionRunReceipt,
    _MissionFlowContext,
)


class MissionAdapterPorts:
    """Mission ports on the shared adapter context."""

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        """Open one ALAS-owned mission state-machine invocation."""

        self._package_gate()
        if self._mission_context is not None:
            raise SemanticGateClosed("nested ALAS mission flow is not allowed")
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._research_context,
                self._dorm_context,
                self._supply_pack_context,
                self._minigame_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._mission_context = _MissionFlowContext(
            daily=bool(daily),
            weekly=bool(weekly),
        )

    def end_mission_reward(self) -> None:
        """Close the ALAS-owned mission invocation and discard all cached state."""

        self._mission_context = None

    def mission_reward_active(self) -> bool:
        """Return whether ALAS currently owns the mission/reward flow."""

        return self._mission_context is not None

    def mission_claim_allowed(self) -> bool:
        """Expose the remaining input budget without weakening the click gate."""

        self._require_mission_context()
        return self._action_ledger.allowed("mission.claim")

    def claim_weekly_mission_progress_once(self) -> Optional[ActionReceipt]:
        """Claim one proven weekly progress reward and close its receipt popup."""

        context = self._require_mission_context()
        if not context.weekly:
            raise SemanticGateClosed("weekly mission claim is not configured")
        if not self.oracle.weekly_mission_progress_claim_available():
            return None
        if not self._action_ledger.allowed("mission.claim"):
            raise SemanticGateClosed(
                "mission claim input requires the separate one-claim opt-in"
            )
        receipt = self._dispatch_mutation(
            "mission.claim", self.oracle.click_weekly_mission_progress_claim
        )
        acknowledgement_targets = (
            "reward/award-info/close",
            "reward/award-info1/close",
            "reward/new-ship/continue",
        )
        minimum_generation = receipt.generation
        dismissed = 0
        # The current client can queue a NewShipUI after the ordinary AwardInfo
        # receipt.  Consume only this typed acknowledgement chain, then return
        # control to the ALAS task state machine.
        while dismissed < 3:
            try:
                semantic_id, _ = self.oracle.wait_for_any(
                    acknowledgement_targets,
                    3.0,
                    minimum_generation=minimum_generation,
                )
            except SemanticGateClosed as exc:
                if (
                    dismissed
                    and str(exc) == "semantic wait timed out"
                    and exc.__cause__ is None
                ):
                    return receipt
                if not dismissed:
                    raise SemanticGateClosed(
                        "weekly mission claim acknowledgement is absent"
                    ) from exc
                raise
            acknowledgement = self.oracle.click(semantic_id)
            minimum_generation = acknowledgement.generation
            dismissed += 1
        raise SemanticGateClosed("weekly mission claim acknowledgement chain is excessive")

    def _require_mission_context(self) -> _MissionFlowContext:
        if self._mission_context is None:
            raise SemanticGateClosed("mission resource used outside ALAS mission flow")
        return self._mission_context

    def _known_mission_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/task",
                "main/more",
                "reward/page/back",
                "task/page/back",
                "reward/award-info/close",
                "reward/award-info1/close",
                "overlay/bulletin/close",
                "overlay/guild-message/close",
                "event-list/page/back",
            )
        )

    def _record_mission_transition(self, receipt: ActionReceipt) -> ActionReceipt:
        context = self._mission_context
        if context is not None and receipt.semantic_id in (
            "main/more",
            "reward/page/back",
            "main/task",
            "task/page/back",
        ):
            context.passive_transition_until = time.monotonic() + 12.0
        commission_context = self._commission_context
        if commission_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "reward/commission/finish",
            "reward/commission/go",
            "reward/ship-exp/close",
            "reward/award-info/close",
            "reward/award-info1/close",
            "commission/page/back",
            "commission/detail/back",
            "build/page/back",
            "tactical/page/back",
        ):
            commission_context.passive_transition_until = time.monotonic() + 12.0
        research_context = self._research_context
        if research_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/tech",
            "research-menu/research",
            "research-menu/page/back",
            "research/page/back",
            "research/queue/enter",
            "research/detail/queue",
        ):
            research_context.passive_transition_until = time.monotonic() + 12.0
        dorm_context = self._dorm_context
        if dorm_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/live",
            "dorm-menu/dorm",
            "dorm/page/back",
            "dorm/feed",
            "dorm/feed/close",
        ):
            dorm_context.passive_transition_until = time.monotonic() + 12.0
        build_context = self._build_context
        if build_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/build",
            "build/page/back",
        ):
            build_context.passive_transition_until = time.monotonic() + 12.0
        return receipt

    def _stable_mission_state(self) -> Optional[MissionPageState]:
        context = self._require_mission_context()
        candidate = self.oracle.mission_page_state()

        if candidate.disposition == MissionDisposition.UNKNOWN:
            context.last_signature = None
            context.last_generation = -1
            context.stable_generations = 0
            context.stable_state = None
            return None

        if candidate.signature != context.last_signature:
            context.last_signature = candidate.signature
            context.last_generation = candidate.generation
            context.stable_generations = 1
            context.stable_state = None
            return None

        if candidate.generation > context.last_generation:
            context.last_generation = candidate.generation
            context.stable_generations += 1
            if context.stable_generations >= 2:
                context.stable_state = candidate
        return context.stable_state

    def _mission_notice_appears(self) -> bool:
        context = self._require_mission_context()
        if context.daily and self.oracle.exists("main/task"):
            return True
        return bool(
            context.weekly and self.oracle.main_red_dot("main/task")
        )

    def _mission_resource_appears(self, name: str) -> bool:
        self._require_mission_context()
        if name in ("MISSION_NOTICE", "MISSION_NOTICE_WHITE"):
            return self._mission_notice_appears()
        if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
            return self._award_close_target() is not None
        if name in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"):
            return self.oracle.enabled("overlay/guild-message/close")
        if name == "GET_SHIP":
            return self.oracle.new_ship_reward_visible()
        if name == "MISSION_WEEKLY_RED_DOT":
            return self.oracle.mission_weekly_reward_available()

        state = self._stable_mission_state()
        if state is None:
            return False
        if name == "MISSION_MULTI":
            return state.disposition == MissionDisposition.CLAIMABLE_ALL
        if name == "MISSION_SINGLE":
            return state.disposition == MissionDisposition.CLAIMABLE_ROW
        if name == "MISSION_UNFINISH":
            return state.disposition == MissionDisposition.UNFINISHED
        if name == "MISSION_EMPTY":
            return state.disposition == MissionDisposition.EMPTY
        raise AlasSemanticUnmapped(
            "ALAS mission resource is not semantically mapped: {0}".format(name)
        )

    def _enter_mission_page(
        self, timeout_seconds: float
    ) -> Tuple[ActionReceipt, MissionPageState, Tuple[str, ...]]:
        dismissed_overlays = []
        deadline = time.monotonic() + timeout_seconds
        while not self.oracle.enabled("main/task"):
            dismissed = False
            for semantic_id in (
                "overlay/bulletin/close",
                "overlay/guild-message/close",
            ):
                if self.oracle.enabled(semantic_id):
                    self.oracle.click(semantic_id)
                    dismissed_overlays.append(semantic_id)
                    dismissed = True
                    time.sleep(0.75)
                    break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("unobstructed main task target did not appear")
            if not dismissed:
                time.sleep(0.5)

        entry = self.oracle.click("main/task")
        self.oracle.wait_for(
            "task/page/back",
            timeout_seconds,
            minimum_generation=entry.generation,
        )
        page = self.oracle.wait_for_mission_state(timeout_seconds)
        return entry, page, tuple(dismissed_overlays)

    def _return_from_mission(self, timeout_seconds: float) -> ActionReceipt:
        exit_receipt = self.oracle.click("task/page/back")
        self.oracle.wait_for(
            "main/task",
            timeout_seconds,
            minimum_generation=exit_receipt.generation,
        )
        return exit_receipt

    def run_mission_reward(
        self,
        daily: bool = True,
        weekly: bool = True,
        timeout_seconds: float = 30.0,
        allow_claim_once: bool = False,
    ) -> Union[MissionRunReceipt, MissionClaimReceipt]:
        """Run the reviewed no-claim TaskScene branch.

        Claim Buttons are detected, but deliberately not clicked until their
        reward-popup and post-claim contracts have separate live evidence.
        """

        self._package_gate()
        if not daily and not weekly:
            return MissionRunReceipt("disabled", 0, "", "")

        entry, page, dismissed_overlays = self._enter_mission_page(timeout_seconds)

        if page.disposition in (
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.CLAIMABLE_ROW,
        ):
            if allow_claim_once and page.disposition == MissionDisposition.CLAIMABLE_ALL:
                return self._claim_open_mission(
                    entry,
                    page,
                    dismissed_overlays,
                    timeout_seconds,
                )
            exit_receipt = self._return_from_mission(timeout_seconds)
            raise MissionClaimableDetected(
                page=page,
                entry=entry,
                exit_receipt=exit_receipt,
                dismissed_overlays=tuple(dismissed_overlays),
            )
        if page.disposition not in (
            MissionDisposition.UNFINISHED,
            MissionDisposition.EMPTY,
        ):
            self._return_from_mission(timeout_seconds)
            raise SemanticGateClosed("mission state is not proven")
        exit_receipt = self._return_from_mission(timeout_seconds)
        return MissionRunReceipt(
            outcome="nothing-claimable",
            page_generation=page.generation,
            entry_path=entry.path,
            exit_path=exit_receipt.path,
            claim_injected=False,
            claim_all_present=page.claim_all is not None,
            claim_row_count=len(page.claim_rows),
            unfinished_row_count=len(page.unfinished_rows),
            dismissed_overlays=tuple(dismissed_overlays),
        )

    def _claim_open_mission(
        self,
        entry: ActionReceipt,
        page: MissionPageState,
        dismissed_overlays: Tuple[str, ...],
        timeout_seconds: float,
    ) -> MissionClaimReceipt:
        if (
            page.disposition != MissionDisposition.CLAIMABLE_ALL
            or page.claim_all is None
        ):
            raise SemanticGateClosed("unique actionable mission claim-all is absent")

        claim_receipt = self._dispatch_mutation(
            "mission.claim",
            lambda: self.oracle.click("task/claim/all"),
        )
        popup_semantic_id, _ = self.oracle.wait_for_any(
            (
                "reward/award-info/close",
                "reward/award-info1/close",
            ),
            timeout_seconds,
            minimum_generation=claim_receipt.generation,
        )
        popup_close_receipt = self.oracle.click(popup_semantic_id)
        self.oracle.wait_for(
            "task/page/back",
            timeout_seconds,
            minimum_generation=popup_close_receipt.generation,
        )
        post_page = self.oracle.wait_for_mission_state(timeout_seconds)
        if post_page.disposition != MissionDisposition.UNFINISHED:
            raise SemanticGateClosed("post-claim mission state is not proven unfinished")
        exit_receipt = self._return_from_mission(timeout_seconds)
        if claim_receipt.policy_sha256 is None or claim_receipt.capability_id is None:
            raise SemanticGateClosed("mission claim receipt authority is incomplete")
        return MissionClaimReceipt(
            outcome="claimed-all-once",
            pre_claim_generation=page.generation,
            post_claim_generation=post_page.generation,
            entry_path=entry.path,
            claim_path=claim_receipt.path,
            popup_close_path=popup_close_receipt.path,
            exit_path=exit_receipt.path,
            pre_claim_row_count=len(page.claim_rows),
            post_claim_row_count=len(post_page.claim_rows),
            unfinished_row_count=len(post_page.unfinished_rows),
            policy_sha256=claim_receipt.policy_sha256,
            capability_id=claim_receipt.capability_id,
            claim_input_count=1,
            dismissed_overlays=dismissed_overlays,
        )

    def claim_mission_rewards_once(
        self,
        timeout_seconds: float = 30.0,
    ) -> MissionClaimReceipt:
        """Inject one reviewed GetAllButton claim and prove its full closure."""

        self._package_gate()
        entry, page, dismissed_overlays = self._enter_mission_page(timeout_seconds)
        if (
            page.disposition != MissionDisposition.CLAIMABLE_ALL
            or page.claim_all is None
        ):
            self._return_from_mission(timeout_seconds)
            raise SemanticGateClosed("unique actionable mission claim-all is absent")
        return self._claim_open_mission(
            entry,
            page,
            dismissed_overlays,
            timeout_seconds,
        )
