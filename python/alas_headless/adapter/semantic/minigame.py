"""Minigame for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import SemanticGateClosed, SemanticTargetMissing
from .contracts import _MinigameFlowContext
from .dispatch_result import UNHANDLED
from .resources import MINIGAME_VIRTUAL_RESOURCES


class MinigameAdapterPorts:
    """Minigame ports on the shared adapter context."""

    def begin_minigame(self) -> None:
        self._package_gate()
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._supply_pack_context,
                self._minigame_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._minigame_context = _MinigameFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_minigame(self) -> None:
        self._minigame_context = None

    def minigame_active(self) -> bool:
        return self._minigame_context is not None

    def minigame_play_allowed(self) -> bool:
        context = self._require_minigame_context()
        if context.play_receipt is not None:
            oracle = self._frame_or_live_observation_oracle()
            state = oracle.read_state()
            if (state.generation > context.play_receipt.generation
                    and oracle.game_room_page_visible()
                    and not oracle.game_room_list_visible()
                    and not oracle._blocking_rules(state, 'ui/absence-probe')
                    and not any(b.active_in_hierarchy and b.active_and_enabled
                                and '/GameRoomFushun2UI(Clone)/' in b.path for b in state.buttons)):
                # Native exit_game completed this play. Release only its input
                # lease; original ALAS still owns play_count and the next run.
                context.play_receipt = None
                context.selected_tickets = None
        return (
            context.play_receipt is None
            and self._action_ledger.allowed("minigame.play")
        )

    def minigame_prepare_default_ticket(self) -> int:
        """Read Fushun's default selection for ALAS' use_coin decision."""

        self._package_gate()
        context = self._require_minigame_context()
        if not self._action_ledger.allowed("minigame.play"):
            raise SemanticGateClosed("minigame play requires a positive budget")
        selected, counter_owned = self.oracle.new_year_challenge_ticket_count()
        observed_owned = context.coins_owned
        if observed_owned is None:
            raise SemanticGateClosed(
                "new-year challenge ticket inventory was not proven before entry"
            )
        if (
            selected not in (0, 1)
            or counter_owned != observed_owned
            or observed_owned < selected
        ):
            raise SemanticGateClosed(
                "new-year challenge default ticket state is inconsistent"
            )
        context.selected_tickets = selected
        # The game can leave the selection at zero when monthly rewards are
        # exhausted. Returning zero lets original ALAS skip this play normally.
        return selected

    def _require_minigame_context(self) -> _MinigameFlowContext:
        if self._minigame_context is None:
            raise SemanticGateClosed(
                "minigame resource used outside ALAS minigame flow"
            )
        return self._minigame_context

    def minigame_prepare_selected_tickets(self) -> int:
        """Bind the native ALAS coin selection to this play's typed inventory."""
        self._package_gate()
        context = self._require_minigame_context()
        if not self._action_ledger.allowed('minigame.play'):
            raise SemanticGateClosed('minigame play requires a positive budget')
        selected, owned = self.oracle.new_year_challenge_ticket_count()
        if context.coins_owned != owned or not 0 <= selected <= owned:
            raise SemanticGateClosed('native minigame ticket selection does not match inventory')
        context.selected_tickets = selected
        return selected

    def _known_minigame_surface_exists(self) -> bool:
        if self._minigame_context is None:
            return False
        oracle = self._frame_or_live_observation_oracle()
        try:
            return bool(
                oracle.game_room_page_visible()
                or oracle.game_room_list_visible()
                or getattr(oracle, 'poke_minigame_prepare_visible', lambda: False)()
                or getattr(oracle, 'shooting_minigame_prepare_visible', lambda: False)()
                or oracle.academy_page_visible()
                or oracle.exists("dorm-menu/page/root")
                or oracle.minigame_ticket_prompt_visible()
                or oracle.new_year_challenge_help_visible()
                or oracle.new_year_challenge_result() is not None
                or self._new_year_challenge_surface_visible()
            )
        except SemanticGateClosed:
            return False

    def minigame_scroll_visible(self) -> bool:
        self._package_gate()
        if self._minigame_context is None:
            raise SemanticGateClosed("minigame scroll used outside minigame flow")
        return self.oracle.game_room_list_visible()

    def minigame_scroll_set(self, position: float) -> bool:
        self._package_gate()
        if self._minigame_context is None:
            raise SemanticGateClosed("minigame scroll used outside minigame flow")
        return self.oracle.minigame_scroll_to(position)

    def _appear_minigame(self, name, button):
        if name in MINIGAME_VIRTUAL_RESOURCES and self._minigame_context is not None:
            if name == "GAME_ROOM_CHECK":
                return self.oracle.game_room_page_visible()
            if name == "GOTO_CHOOSE_GAME":
                return self.oracle.game_room_page_visible() and not self.oracle.game_room_list_visible()
            if name == "MINIGAME_SCROLL_AREA":
                return self.oracle.game_room_list_visible()
            if name == "NEW_YEAR_CHALLENGE_ENTRANCE":
                try:
                    self.oracle.new_year_challenge_entry_target()
                except SemanticTargetMissing:
                    return False
                return True
            if name == "NEW_YEAR_CHALLENGE_FIRST_TIME":
                # The reviewed current surface is the normal Fushun prepare
                # page (help/start pair), not the one-time tutorial overlay.
                return False
            if name in (
                "NEW_YEAR_CHALLENGE_ADD_COIN",
                "NEW_YEAR_CHALLENGE_DEC_COIN",
            ):
                try:
                    selected, owned = self.oracle.new_year_challenge_ticket_count()
                except SemanticGateClosed:
                    return False
                if name == "NEW_YEAR_CHALLENGE_ADD_COIN":
                    return (
                        self._minigame_context.play_receipt is not None
                        or self._action_ledger.allowed("minigame.play")
                    )
                return selected > 0
            if name == "NEW_YEAR_CHALLENGE_START":
                try:
                    state = self.oracle.read_state()
                except SemanticGateClosed:
                    return False
                starts = tuple(
                    button
                    for button in state.buttons
                    if button.name == "btn_start"
                    and button.path.endswith(
                        "GameRoomFushun2UI(Clone)/btn_start"
                    )
                    and button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.interactable
                    and button.bounds is not None
                )
                helps = tuple(
                    button
                    for button in state.buttons
                    if button.name == "btn_help"
                    and button.path.endswith(
                        "GameRoomFushun2UI(Clone)/btn_help"
                    )
                    and button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.bounds is not None
                )
                return len(starts) == 1 and len(helps) == 1
            if name == "NEW_YEAR_CHALLENGE_END":
                try:
                    if self.oracle._blocking_rules(self.oracle.read_state(), 'minigame/new-year/result-close'):
                        return False
                    return self.oracle.new_year_challenge_result() is not None
                except SemanticGateClosed:
                    return False
            if name == "NEW_YEAR_CHALLENGE_EXIT":
                return False
            if name == "RESET_TICKET_POPUP":
                return False
            if name == "BACK":
                if self.oracle.new_year_challenge_result() is not None:
                    return False
                if self.oracle.new_year_challenge_home_visible():
                    return True
                try:
                    self.oracle.new_year_challenge_ticket_count()
                    return True
                except SemanticGateClosed:
                    return self.oracle.game_room_page_visible()
            if name == "COIN_POPUP":
                return False
            if name in ("POPUP_CANCEL", "POPUP_CONFIRM"):
                return True if self.oracle.minigame_ticket_prompt_visible() else UNHANDLED
        return UNHANDLED

    def _click_minigame(self, name):
        if self._minigame_context is not None:
            context = self._minigame_context
            if name == "GOTO_CHOOSE_GAME":
                receipt = self.oracle.click("game-room/list")
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name == "NEW_YEAR_CHALLENGE_ENTRANCE":
                context.coins_owned = self.oracle.minigame_coin_amount()
                receipt = self.oracle.click_new_year_challenge_entry()
                context.entry_receipt = receipt
                context.passive_transition_until = time.monotonic() + 12.0
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    if self.oracle.new_year_challenge_prepare_visible():
                        return receipt
                    time.sleep(0.1)
                raise SemanticGateClosed('new-year entry did not reach its exact prepare page')
            if name == "NEW_YEAR_CHALLENGE_ADD_COIN":
                if context.play_receipt is not None or not self._action_ledger.allowed('minigame.play'):
                    raise SemanticGateClosed('minigame coin selection requires an unstarted budgeted play')
                oracle = self._fresh_input_oracle()
                selected, owned = oracle.new_year_challenge_ticket_count()
                if context.coins_owned != owned or not 0 < selected < owned:
                    raise SemanticGateClosed('minigame coin addition exceeds proven inventory')
                receipt = oracle.click_new_year_challenge_prepare_control('add')
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    try:
                        if (self.oracle.read_state().generation > receipt.generation
                                and self.oracle.new_year_challenge_ticket_count() == (selected + 1, owned)):
                            return receipt
                    except SemanticGateClosed:
                        pass
                    time.sleep(.1)
                raise SemanticGateClosed('minigame coin selection did not advance; inspect before retry')
            if name == "NEW_YEAR_CHALLENGE_DEC_COIN":
                raise SemanticGateClosed(
                    "qualification play does not permit deselecting its consumed lease"
                )
            if name == "NEW_YEAR_CHALLENGE_START":
                if context.selected_tickets < 1 or context.play_receipt is not None:
                    raise SemanticGateClosed(
                        "new-year challenge start requires an admitted ticket selection"
                    )
                selected, owned = self._frame_or_live_observation_oracle().new_year_challenge_ticket_count()
                if selected != context.selected_tickets or owned != context.coins_owned:
                    raise SemanticGateClosed('new-year challenge selected ticket cost changed before start')
                receipt = self._dispatch_mutation(
                    "minigame.play",
                    lambda: self.oracle.click_new_year_challenge_prepare_control(
                        "start"
                    ),
                )
                context.play_receipt = receipt
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name == "NEW_YEAR_CHALLENGE_END":
                receipt = self._fresh_input_oracle().click_new_year_challenge_result_close()
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name == "NEW_YEAR_CHALLENGE_EXIT":
                raise SemanticGateClosed(
                    "current Fushun result closes directly to its prepare page"
                )
            if name == "BACK":
                if self.oracle.new_year_challenge_result() is not None:
                    raise SemanticGateClosed(
                        "new-year challenge result must close before back"
                    )
                if self.oracle.new_year_challenge_home_visible():
                    return self._fresh_input_oracle().click_new_year_challenge_prepare_control('back')
                try:
                    self.oracle.new_year_challenge_ticket_count()
                except SemanticGateClosed:
                    if self.oracle.game_room_list_visible():
                        receipt = self._fresh_input_oracle().click("game-room/back")
                        deadline = time.monotonic() + 5.0
                        while time.monotonic() < deadline:
                            if (self.oracle.game_room_page_visible()
                                    and not self.oracle.game_room_list_visible()):
                                return receipt
                            time.sleep(0.1)
                        raise SemanticGateClosed('game-room back did not close its list')
                    return self._fresh_input_oracle().click("game-room/back")
                receipt = self.oracle.click_new_year_challenge_prepare_control(
                    "back"
                )
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name in ("POPUP_CANCEL", "POPUP_CONFIRM"):
                ticket_visible = self.oracle.minigame_ticket_prompt_visible()
                if not ticket_visible and self.oracle.observation_prompt_kind() is not None:
                    return UNHANDLED
                if (
                    name == "POPUP_CONFIRM"
                    and context.ticket_confirm_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                    and not ticket_visible
                    and self.oracle.read_state().generation
                    > context.ticket_confirm_receipt.generation
                ):
                    return context.ticket_confirm_receipt
                if not ticket_visible:
                    return UNHANDLED
                target = (
                    "minigame/tickets/cancel"
                    if name == "POPUP_CANCEL"
                    else "minigame/tickets/confirm"
                )
                receipt = self.oracle.click(target)
                if name == "POPUP_CONFIRM":
                    context.ticket_prompt_confirmed = True
                    context.ticket_confirm_receipt = receipt
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
        return UNHANDLED
