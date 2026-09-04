"""Build for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import (
    BuildCostState,
    BuildPool,
    BuildSubmitState,
    SemanticGateClosed,
)
from .contracts import _BuildFlowContext
from .dispatch_result import UNHANDLED
from .resources import (
    BUILD_POOL_NAVBAR_TARGETS,
    BUILD_SIDE_NAVBAR_TARGETS,
    BUILD_VIRTUAL_RESOURCES,
)


class BuildAdapterPorts:
    """Build ports on the shared adapter context."""

    def begin_build(self) -> None:
        self._package_gate()
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._supply_pack_context,
                self._minigame_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._build_context = _BuildFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_build(self) -> None:
        self._build_context = None

    def _known_build_surface_exists(self) -> bool:
        if any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/build",
            )
        ):
            return True
        return self._current_build_surface_exists()

    def _current_build_surface_exists(self) -> bool:
        if any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "build/page/start",
                "build/page/back",
                "build/prep/confirm",
            )
        ):
            return True
        try:
            self.oracle.build_queue_timers()
        except SemanticGateClosed:
            return False
        return True

    def build_selected_pool(self) -> BuildPool:
        self._package_gate()
        return self.oracle.build_selected_pool()

    def build_costs(self) -> BuildCostState:
        self._package_gate()
        return self.oracle.build_costs()

    def build_submit_state(self) -> BuildSubmitState:
        self._package_gate()
        state = self.oracle.build_submit_state()
        if self._build_context is not None:
            self._build_context.prep_validated = True
        return state

    def build_set_count(self, target: int) -> BuildSubmitState:
        """Set and prove the exact pending construction quantity (1..10)."""

        self._package_gate()
        if self._build_context is None:
            raise SemanticGateClosed(
                "construction count used outside ALAS build flow"
            )
        if type(target) is not int or not 1 <= target <= 10:
            raise SemanticGateClosed(
                "construction count must be an integer from 1 to 10"
            )
        state = self.build_submit_state()
        for _ in range(10):
            if state.count == target:
                return state
            control = "build/prep/add" if state.count < target else "build/prep/minus"
            # The complete typed construction dialog can take longer to read
            # than one immutable frame lease.  Refresh immediately before
            # each exact quantity mutation; SemanticOracle then re-reads the
            # target and the runtime still invalidates that fresh lease at the
            # final tap boundary.
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            self.oracle.click(control)
            state = self.build_submit_state()
        raise SemanticGateClosed("construction count did not reach requested value")

    def build_coins_owned(self) -> int:
        if self._build_context is None:
            raise SemanticGateClosed(
                "construction coin count used outside ALAS build flow"
            )
        if self._build_context.coins_owned is None:
            # A task may legitimately start while ALAS is already on page_build,
            # so MAIN_GOTO_BUILD is not guaranteed to run.  The proven Build
            # resource panel supplies the same owned-coin value in that case.
            self._build_context.coins_owned = self.oracle.build_coins_owned()
        return self._build_context.coins_owned

    def _appear_build(self, name):
        if name in BUILD_VIRTUAL_RESOURCES and self._build_context is not None:
            if name == "BUILD_SUBMIT_ORDERS":
                return self.oracle.enabled("build/page/start")
            if name in ("BUILD_SUBMIT_WW_ORDERS", "BUILD_WW_CHECK", "SHOP_MEDAL_CHECK"):
                return False
            if name in ("GET_SHIP", "STORY_SKIP"):
                return self.oracle.new_ship_reward_visible()
            if name in ("GET_ITEMS_SHIP_1", "BUILD_FINISH_RESULTS"):
                return self._award_close_target() is not None
            if name == "BUILD_QUEUE_EMPTY":
                try:
                    queue_selected = self.oracle.toggle_selected("build/nav/queue")
                except SemanticGateClosed as exc:
                    if (
                        str(exc)
                        == "semantic toggle target is absent or ambiguous: build/nav/queue"
                        and (
                            # Evaluate the monotonic transition window before
                            # inspecting other transient result surfaces.  Each
                            # typed inspection is itself a device round-trip;
                            # doing those first can consume the whole window
                            # immediately after the batch-finish tap.
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.build_queue_finish_prompt_cost() is not None
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        return False
                    raise
                if not queue_selected:
                    return False
                try:
                    empty = self.oracle.build_queue_empty()
                except SemanticGateClosed as exc:
                    if str(exc) == "construction queue tab is not selected":
                        # ALAS polls this queue sentinel immediately after a
                        # successful tab change. A new coherent frame may
                        # already be on pools, where the sentinel is absent.
                        return False
                    if (
                        str(exc) == "construction queue page identity is not proven"
                        and (
                            # A selected background queue tab can be observed
                            # before the foreground NewShip/AwardInfo page has
                            # finished publishing its own typed identity.
                            # Preserve the same bounded post-finish grace used
                            # when the queue toggle itself is absent.
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        # The selected queue tab remains in the background
                        # while a typed construction result page owns the
                        # foreground.  It is not valid to read queue timers
                        # through that page; let the result aliases close it.
                        return False
                    raise
                if not empty and self._build_context.submit_receipt is None:
                    raise SemanticGateClosed(
                        "construction queue must be empty before a bounded submit"
                    )
                return empty
            if name == "BUILD_FINISH_ORDERS":
                # Gacha polls the batch-finish sentinel after it returns from
                # the queue to a pool.  A pool frame has no queue control; it
                # is an ordinary negative probe, not an invalid queue state.
                try:
                    queue_selected = self.oracle.toggle_selected("build/nav/queue")
                except SemanticGateClosed as exc:
                    if (
                        str(exc)
                        == "semantic toggle target is absent or ambiguous: build/nav/queue"
                        and (
                            # See BUILD_QUEUE_EMPTY above.  Keep the bounded
                            # post-tap grace before any slow typed state probe.
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.build_queue_finish_prompt_cost() is not None
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        return False
                    raise
                if not queue_selected:
                    return False
                try:
                    return self.oracle.build_queue_all_launch_available()
                except SemanticGateClosed as exc:
                    if str(exc) == "construction queue tab is not selected":
                        return False
                    if (
                        str(exc) == "construction queue page identity is not proven"
                        and (
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        return False
                    raise
            if name == "BUILD_MINUS":
                return self.oracle.enabled("build/prep/minus")
            if name == "BUILD_PLUS":
                return self.oracle.enabled("build/prep/add")
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_PREP"):
                if self.oracle.enabled("build/warning/confirm"):
                    return not self._build_context.warning_confirmed
                if (
                    name == "POPUP_CONFIRM"
                    and self.oracle.build_queue_finish_prompt_cost() is not None
                ):
                    return True
                if name == "POPUP_CONFIRM":
                    return bool(
                        self._build_context.prep_validated
                        and self.oracle.enabled("build/prep/confirm")
                        and self._build_context.prep_opened
                    )
                return False
            if name == "POPUP_CONFIRM_GACHA_ORDER":
                return bool(
                    self.oracle.enabled("build/prep/confirm")
                    and self._build_context.prep_opened
                )
            if name == "POPUP_CANCEL":
                return bool(
                    self.oracle.enabled("build/warning/cancel")
                    or self.oracle.enabled("build/prep/cancel")
                    or self.oracle.build_queue_finish_prompt_cost() is not None
                )
        return UNHANDLED

    def _click_build_nav(self, build_side_navbar_match, build_pool_navbar_match):
        if self._build_context is not None and build_side_navbar_match is not None:
            index = int(build_side_navbar_match.group(1))
            if index not in (0, 1):
                raise SemanticGateClosed(
                    "construction side navigation input is outside build/queue"
                )
            target = BUILD_SIDE_NAVBAR_TARGETS[index]
            # The native queue-cleanup loop can request this exact navigation
            # immediately after a stable queue sentinel.  On the CN client a
            # short-lived foreground layer can still be published between
            # those two observer turns.  Re-read only this same typed toggle
            # while it is blocked; click_toggle remains the sole input gate
            # and will not tap until the blocker is gone.
            deadline = time.monotonic() + 8.0
            while True:
                try:
                    return self.oracle.click_toggle(target)
                except SemanticGateClosed as exc:
                    if (
                        str(exc) != "semantic toggle action is blocked"
                        or time.monotonic() >= deadline
                    ):
                        raise
                    time.sleep(0.25)
        if self._build_context is not None and build_pool_navbar_match is not None:
            index = int(build_pool_navbar_match.group(1))
            target = BUILD_POOL_NAVBAR_TARGETS.get(index)
            if target is None:
                raise SemanticGateClosed("construction pool index is not qualified")
            return self.oracle.click_toggle(target)
        return UNHANDLED

    def _click_build(self, name):
        if self._build_context is not None and name in BUILD_VIRTUAL_RESOURCES:
            context = self._build_context
            if name == "BUILD_SUBMIT_ORDERS":
                receipt = self.oracle.click("build/page/start")
                context.prep_opened = True
                context.prep_validated = False
                context.warning_confirmed = False
                return receipt
            if name == "BUILD_MINUS":
                return self.oracle.click("build/prep/minus")
            if name == "BUILD_PLUS":
                return self.oracle.click("build/prep/add")
            if name in (
                "BUILD_QUEUE_EMPTY",
                "BUILD_SUBMIT_WW_ORDERS",
                "BUILD_WW_CHECK",
                "SHOP_MEDAL_CHECK",
            ):
                raise SemanticGateClosed(
                    "construction observation resource is not an admitted input"
                )
            if name in ("GET_SHIP", "STORY_SKIP"):
                if not self.oracle.new_ship_reward_visible():
                    raise SemanticGateClosed("construction ship reward is absent")
                return self.oracle.click("reward/new-ship/continue")
            if name in ("GET_ITEMS_SHIP_1", "BUILD_FINISH_RESULTS"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("construction reward popup is absent")
                return self.oracle.click(target)
            if name == "BUILD_FINISH_ORDERS":
                if self.oracle.new_ship_reward_visible():
                    return self.oracle.click("reward/new-ship/continue")
                target = self._award_close_target()
                if target is not None:
                    return self.oracle.click(target)
                return self._dispatch_mutation(
                    "build.submit",
                    self.oracle.click_build_queue_all_launch,
                )
            if name == "POPUP_CANCEL":
                if self.oracle.build_queue_finish_prompt_cost() is not None:
                    return self.oracle.click("build/queue/finish-cancel")
                target = (
                    "build/warning/cancel"
                    if self.oracle.enabled("build/warning/cancel")
                    else "build/prep/cancel"
                )
                return self.oracle.click(target)
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_PREP"):
                if (
                    name == "POPUP_CONFIRM"
                    and self.oracle.build_queue_finish_prompt_cost() is not None
                ):
                    receipt = self.oracle.click("build/queue/finish-confirm")
                    context.queue_finish_transition_until = time.monotonic() + 15.0
                    return receipt
                if (
                    not self.oracle.enabled("build/warning/confirm")
                    or context.warning_confirmed
                ):
                    raise SemanticGateClosed(
                        "construction preparation alias requires the exact warning"
                    )
                receipt = self.oracle.click("build/warning/confirm")
                deadline = time.monotonic() + 8.0
                while self.oracle.enabled("build/warning/confirm"):
                    if time.monotonic() >= deadline:
                        raise SemanticGateClosed(
                            "construction warning did not close after confirmation"
                        )
                    time.sleep(0.25)
                context.warning_confirmed = True
                return receipt
            if name == "POPUP_CONFIRM_GACHA_ORDER":
                if self.oracle.enabled("build/warning/confirm"):
                    raise SemanticGateClosed(
                        "construction order alias cannot confirm a warning"
                    )
                submit = self.oracle.build_submit_state()
                if (
                    not self._action_ledger.allowed("build.submit")
                    or not 1 <= submit.count <= 10
                    or submit.cubes_owned < submit.cubes_required
                    or context.coins_owned is None
                    or context.coins_owned < submit.coins_required
                    or not context.prep_opened
                ):
                    raise SemanticGateClosed(
                        "construction submit requires 1..10 builds, sufficient resources, and a positive budget"
                    )
                receipt = self._dispatch_mutation(
                    "build.submit",
                    lambda: self.oracle.click("build/prep/confirm"),
                )
                context.submit_receipt = receipt
                context.prep_opened = False
                context.prep_validated = False
                return receipt
        return UNHANDLED
