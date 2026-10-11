"""Tactical for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Tuple
from ...semantic_oracle import (
    ActionReceipt,
    Point,
    SemanticGateClosed,
    TacticalBookState,
    TacticalCandidateShipState,
    TacticalSkillState,
    TacticalSlotState,
)
from .contracts import AlasSemanticUnmapped, _CommissionFlowContext
from .dispatch_result import UNHANDLED
from .resources import TACTICAL_VIRTUAL_RESOURCES


class TacticalAdapterPorts:
    """Tactical ports on the shared adapter context."""

    def begin_tactical(self) -> None:
        """Open the shared reward/tactical context without commission budgets."""

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
            flow_kind="tactical",
            passive_transition_until=time.monotonic() + 20.0,
        )

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        self._package_gate()
        return self.oracle.tactical_slots()

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        self._package_gate()
        return self._frame_or_live_observation_oracle().tactical_remaining_seconds()

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        self._package_gate()
        return self.oracle.tactical_candidate_ships()

    def _refresh_tactical_input_frame(self) -> None:
        refresher = self._tactical_input_frame_refresher or self._input_frame_refresher
        if refresher is not None:
            refresher()

    def _tactical_course_target_enabled(self, target: str) -> bool:
        try:
            return self.oracle.enabled(target)
        except SemanticGateClosed:
            return False

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        self._package_gate()
        return self.oracle.tactical_skills()

    def tactical_select_suitable_ship(
        self, favourite: bool, min_level: int, start_index: int
    ) -> bool:
        context = self._require_commission_context()
        if context.flow_kind != "tactical":
            raise SemanticGateClosed("tactical ship selection requires the tactical flow")
        if (
            type(favourite) is not bool
            or type(min_level) is not int
            or not 1 <= min_level <= 125
            or type(start_index) is not int
            or start_index < 0
        ):
            raise ValueError("tactical ship selection bounds are invalid")
        self._require_action_grant("tactical.assign")
        # Tactical and enhancement share the exact Dock favourite toggle.
        # The original ALAS Dock scan can wait for cards for longer than a
        # frame lease, while the favourite toggle itself may be an input.
        # Acquire a current immutable frame for each precise Dock mutation.
        self._refresh_tactical_input_frame()
        self.oracle.set_enhancement_dock_favourite(favourite)
        candidates = self.oracle.tactical_candidate_ships()
        selected = next(
            (
                candidate
                for candidate in candidates[start_index:]
                if candidate.level >= min_level
            ),
            None,
        )
        if selected is None:
            return False
        self._refresh_tactical_input_frame()
        receipt = self.oracle.click_tactical_ship(selected.ship_id)
        self.oracle.wait_for(
            "tactical/dock/confirm",
            timeout_seconds=5.0,
            minimum_generation=receipt.generation,
        )
        self._refresh_tactical_input_frame()
        confirm = self.oracle.click("tactical/dock/confirm")
        self.oracle.wait_for(
            "tactical/skill/confirm",
            timeout_seconds=8.0,
            minimum_generation=confirm.generation,
        )
        return True

    def tactical_select_first_trainable_skill(self) -> bool:
        context = self._require_commission_context()
        if context.flow_kind != "tactical":
            raise SemanticGateClosed("tactical skill selection requires the tactical flow")
        prior = context.tactical_skill_confirm_receipt
        if (prior is not None
                and self.oracle.enabled('tactical/book/start')
                and self.oracle.read_state().generation > prior.generation):
            # ALAS' positive skill screenshot can outlive the accepted confirm.
            # The exact newer book page proves arrival; do not select again.
            return True
        skill = next(
            (skill for skill in self.oracle.tactical_skills() if not skill.max_level),
            None,
        )
        if skill is None:
            return False
        self._require_action_grant("tactical.assign")
        self._refresh_tactical_input_frame()
        receipt = self.oracle.click_tactical_skill(skill.position)
        self.oracle.wait_for(
            "tactical/skill/confirm",
            timeout_seconds=5.0,
            minimum_generation=receipt.generation,
        )
        self._refresh_tactical_input_frame()
        context.tactical_skill_confirm_receipt = self._record_mission_transition(
            self.oracle.click("tactical/skill/confirm"))
        return True

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        context = self._require_commission_context()
        if context.flow_kind != "tactical":
            raise SemanticGateClosed("tactical books require the tactical flow")
        return self._frame_or_live_observation_oracle().tactical_books()

    def tactical_select_book(self, position: int) -> ActionReceipt:
        context = self._require_commission_context()
        if context.flow_kind != "tactical":
            raise SemanticGateClosed("tactical book selection requires the tactical flow")
        before = self.oracle.tactical_books()
        matches = tuple(book for book in before if book.position == position)
        if len(matches) != 1 or matches[0].count <= 0:
            raise SemanticGateClosed("selected tactical book is unavailable")
        if matches[0].selected:
            image = matches[0].image
            assert image.bounds is not None
            return ActionReceipt(
                semantic_id="tactical/book/{0}".format(position),
                generation=self.oracle.read_state().generation,
                point=Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                ),
                bounds=image.bounds,
                path=image.path,
            )
        self._require_action_grant("tactical.assign")
        self._refresh_tactical_input_frame()
        receipt = self.oracle.click_tactical_book(position)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                current = self.oracle.tactical_books()
            except SemanticGateClosed:
                time.sleep(0.1)
                continue
            if any(book.position == position and book.selected for book in current):
                return receipt
            time.sleep(0.1)
        raise SemanticGateClosed("tactical book selection was not observed")

    def tactical_book_selected(self, position: int) -> bool:
        return any(
            book.position == position and book.selected
            for book in self.tactical_books()
        )

    def cancel_tactical_continue_if_present(self) -> bool:
        self._package_gate()
        if self._commission_context is None:
            raise SemanticGateClosed("tactical popup used outside ALAS tactical flow")
        prompt = self.oracle.tactical_continue_prompt_text()
        if prompt is None:
            return False
        if self._commission_context.flow_kind != "tactical":
            raise SemanticGateClosed("tactical continue cancellation requires the tactical flow")
        if prompt in self._commission_context.cancelled_tactical_prompts:
            return False
        self.oracle.click("tactical/continue/cancel")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                current_prompt = self.oracle.tactical_continue_prompt_text()
            except SemanticGateClosed:
                time.sleep(0.1)
                continue
            if current_prompt != prompt:
                self._commission_context.cancelled_tactical_prompts.add(prompt)
                return True
            time.sleep(0.1)
        raise SemanticGateClosed("tactical continue cancellation was not observed")

    def _appear_tactical(self, name, semantic_id):
        if name == 'LOGIN_CHECK':
            # Original UI.ui_additional() owns returning from an inherited
            # login page. Its canonical login probe must run before the
            # Tactical context suppresses unrelated unmapped resources.
            return UNHANDLED
        if (name in ("POPUP_CONFIRM", "POPUP_CANCEL")
                and self.oracle.observation_prompt_kind() == "opsi-exit"
                and self.oracle.operation_siren_exit_prompt_visible()):
            # Native navigation can inherit an OpSi exit before classroom
            # entry. Its existing shared confirmation owns this prompt.
            return UNHANDLED
        if (
            self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
        ):
            if (semantic_id in ('reward/tactical/finish', 'reward/tactical/go')
                    and self.oracle.reward_sidebar_control_offscreen(semantic_id)):
                # The original receive loop requests this exact control. Its
                # first click only brings it into view; no reward is claimed.
                return True
            if name == "GET_MISSION":
                return ((self._commission_context.tactical_reward_receipt is not None
                         or self._action_ledger.allowed("tactical.reward"))
                        and self.oracle.enabled("tactical/completion/ack"))
            if name == "GOTO_MAIN":
                # Another task can leave a detail panel that page enumeration
                # deliberately rejects. Preserve ALAS' reviewed recovery edge
                # before suppressing unrelated presence probes.
                return self._goto_main_target() is not None
            if name == "TACTICAL_CHECK":
                return bool(
                    self.oracle.exists("tactical/page/back")
                    and not self.oracle.enabled("tactical/dock/cancel")
                    and not self.oracle.enabled("tactical/skill/confirm")
                    and not self.oracle.enabled("tactical/book/start")
                    and not self._tactical_course_target_enabled(
                        "tactical/course/confirm"
                    )
                    and not self._tactical_course_target_enabled(
                        "tactical/course/cancel"
                    )
                )
            if name in ("POPUP_CONFIRM_WHITE", "POPUP_CANCEL_WHITE"):
                return False
            if name in TACTICAL_VIRTUAL_RESOURCES:
                if name == "ADD_NEW_STUDENT":
                    if self._commission_context.tactical_empty_slot_receipt is not None:
                        if (self.oracle.exists('tactical/dock/back')
                                or time.monotonic() <= self._commission_context.passive_transition_until):
                            return False
                        raise SemanticGateClosed("tactical empty-slot destination was not observed")
                    try:
                        if any(
                            self.oracle.enabled(target)
                            for target in (
                                "tactical/book/start",
                                "tactical/book/cancel",
                            )
                        ) or self._tactical_course_target_enabled(
                            "tactical/course/confirm"
                        ) or self._tactical_course_target_enabled("tactical/course/cancel"):
                            return False
                        return (
                            len(self.oracle.tactical_slots()) < 4
                            and self.oracle.tactical_empty_slots_ready()
                        )
                    except SemanticGateClosed:
                        return False
                if name == "DOCK_CHECK":
                    try:
                        visible = bool(self.oracle.tactical_candidate_ships())
                        prior = self._commission_context.tactical_empty_slot_receipt
                        if visible and prior is not None and self.oracle.read_state().generation > prior.generation:
                            self._commission_context.tactical_empty_slot_receipt = None
                        return visible
                    except SemanticGateClosed:
                        return False
                if name == "SKILL_CONFIRM":
                    try:
                        return bool(self.oracle.tactical_skills())
                    except SemanticGateClosed:
                        return False
                if name == "BACK_ARROW":
                    return any(
                        self.oracle.enabled(target)
                        for target in (
                            "tactical/dock/back",
                            "tactical/page/back",
                        )
                    )
                if name in ("TACTICAL_CLASS_START", "TACTICAL_CLASS_CANCEL"):
                    target = (
                        "tactical/book/start"
                        if name == "TACTICAL_CLASS_START"
                        else "tactical/book/cancel"
                    )
                    return self.oracle.enabled(target)
                if name == "POPUP_CONFIRM":
                    return (
                        self._action_ledger.allowed("tactical.assign")
                        and self._tactical_course_target_enabled(
                            "tactical/course/confirm"
                        )
                    )
                if name == "POPUP_CANCEL":
                    return self._tactical_course_target_enabled("tactical/course/cancel")
            if semantic_id is None:
                return False
        return UNHANDLED

    def _click_tactical(self, name):
        sidebar_target = self._mappings.get(name)
        if (self._commission_context is not None
                and self._commission_context.flow_kind == 'tactical'
                and sidebar_target in ('reward/tactical/finish', 'reward/tactical/go')
                and self.oracle.reward_sidebar_control_offscreen(sidebar_target)):
            return self.oracle.scroll_reward_sidebar_control(sidebar_target)
        if (name in ("POPUP_CONFIRM", "POPUP_CANCEL")
                and self.oracle.observation_prompt_kind() == "opsi-exit"
                and self.oracle.operation_siren_exit_prompt_visible()):
            return UNHANDLED
        if (name == "GET_MISSION" and self._commission_context is not None
                and self._commission_context.flow_kind == "tactical"):
            if self._commission_context.tactical_reward_receipt is None:
                self._require_action_grant("tactical.reward")
            return self.oracle.click_tactical_completion_ack()
        if (
            self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
            and name in TACTICAL_VIRTUAL_RESOURCES
        ):
            context = self._commission_context
            if name == "ADD_NEW_STUDENT":
                prior = context.tactical_empty_slot_receipt
                if (prior is not None
                        and self.oracle.enabled('tactical/dock/back')
                        and self.oracle.tactical_candidate_ships()
                        and self.oracle.read_state().generation > prior.generation):
                    # A successful slot entry can leave one old classroom
                    # probe in flight. The exact Dock destination proves the
                    # original input completed; never tap the covered slot.
                    context.tactical_empty_slot_receipt = None
                    return prior
                if prior is not None:
                    if time.monotonic() <= context.passive_transition_until:
                        return None
                    raise SemanticGateClosed("tactical empty-slot destination was not observed")
                self._require_action_grant("tactical.assign")
                receipt = self.oracle.click_tactical_first_empty_slot()
                context.tactical_skill_confirm_receipt = None
                context.tactical_empty_slot_receipt = self._record_mission_transition(receipt)
                return receipt
            if name == "BACK_ARROW":
                targets = tuple(
                    target
                    for target in ("tactical/dock/back", "tactical/page/back")
                    if self.oracle.enabled(target)
                )
                if (
                    not targets
                    and context.tactical_back_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.tactical_back_receipt
                if len(targets) != 1:
                    raise SemanticGateClosed("tactical back target is ambiguous")
                receipt = self._record_mission_transition(
                    self.oracle.click(targets[0])
                )
                if receipt.semantic_id == "tactical/page/back":
                    context.tactical_back_receipt = receipt
                return receipt
            if name == "TACTICAL_CLASS_START":
                self._require_action_grant("tactical.assign")
                books = self.oracle.tactical_books()
                selected = tuple(book for book in books if book.selected)
                if len(selected) != 1 or selected[0].count <= 0:
                    raise SemanticGateClosed(
                        "tactical course start requires one available selected book"
                    )
                receipt = self._record_mission_transition(self.oracle.click("tactical/book/start"))
                return receipt
            if name == "TACTICAL_CLASS_CANCEL":
                return self.oracle.click("tactical/book/cancel")
            if name == "POPUP_CONFIRM":
                prior = context.tactical_confirm_receipt
                if (prior is not None
                        and time.monotonic() - context.tactical_confirmed_at <= 12.0
                        and not self._tactical_course_target_enabled("tactical/course/confirm")):
                    if context.tactical_confirm_before_slots is None:
                        raise SemanticGateClosed('prior tactical course slot observation is unavailable')
                    # The modal can disappear before its new student card
                    # mounts. Wait read-only for the prior input's exact
                    # running-slot postcondition instead of clicking again.
                    deadline = min(context.tactical_confirmed_at + 12.0,
                                   time.monotonic() + 4.0)
                    while True:
                        state = self.oracle.read_state()
                        slots = self.oracle.tactical_slots()
                        if (state.generation > prior.generation and any(
                                (slot.slot, slot.ship_id) not in context.tactical_confirm_before_slots
                                and getattr(slot.status, 'value', slot.status) == 'running'
                                for slot in slots)):
                            return prior
                        if time.monotonic() >= deadline:
                            raise SemanticGateClosed('confirmed tactical course has no new running slot')
                        time.sleep(.1)
                self._require_action_grant("tactical.assign")
                input_reader = self._fresh_input_oracle()
                try:
                    before_slots = {(slot.slot, slot.ship_id)
                                    for slot in input_reader.tactical_slots()
                                    if getattr(slot.status, 'value', slot.status) == 'running'}
                except SemanticGateClosed:
                    # An unavailable observation is not an empty classroom;
                    # it cannot later prove that an existing course is new.
                    before_slots = None
                receipt = self._dispatch_mutation(
                    "tactical.assign",
                    lambda: input_reader.click("tactical/course/confirm"),
                )
                context.tactical_confirm_before_slots = before_slots
                context.tactical_confirm_receipt = receipt
                context.tactical_confirmed_at = time.monotonic()
                return receipt
            raise AlasSemanticUnmapped(
                "tactical resource requires a typed workflow helper: {0}".format(name)
            )
        return UNHANDLED
