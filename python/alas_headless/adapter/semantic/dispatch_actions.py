"""Dispatch actions for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...oracle.surfaces import ObservationSurface
from ...semantic_oracle import (
    MissionDisposition,
    ResearchProjectStatus,
    SemanticGateClosed,
    SemanticTargetMissing,
)
from ...oracle.errors import SemanticTargetNotActionable
from .contracts import AlasSemanticActionDeferred, AlasSemanticUnmapped
from .dispatch_result import UNHANDLED
from .resources import (
    BUILD_VIRTUAL_RESOURCES,
    CAMPAIGN_CLICK_RESOURCES,
    CAMPAIGN_FLEET_BAR_PATTERN,
    COMMISSION_CLICK_RESOURCES,
    DORM_VIRTUAL_RESOURCES,
    MAIL_CLICK_RESOURCES,
    MISSION_CLICK_RESOURCES,
    RESEARCH_CLICK_RESOURCES,
    REWARD_RESOURCE_FIELDS,
    TACTICAL_VIRTUAL_RESOURCES,
)


class DispatchActionsPorts:
    """Dispatch actions ports on the shared adapter context."""

    def click_network_reconnect(self, confirm):
        """Submit only the exact reviewed reconnect target, then retain its transition."""
        self._package_gate()
        target = ('overlay/network-reconnect/confirm' if confirm
                  else 'overlay/network-reconnect/cancel')
        receipt = self.oracle.click(target)
        self._network_reconnect_transition_until = time.monotonic() + 20.0
        if self._campaign_context is not None:
            self._campaign_context.passive_transition_until = time.monotonic() + 20.0
        return receipt

    def _click_main_tech(self):
        return self._click_main_ready('main/tech')

    def _main_tech_entry_completed(self, *, wait=False):
        receipt = self._main_tech_entry_receipt
        if receipt is None:
            return None
        deadline = time.monotonic() + (12.0 if wait else 0.0)
        while True:
            if (self.oracle.observation_target_present('research-menu/page/back')
                    and self.oracle.enabled('research-menu/page/back')
                    and self.oracle.read_state().generation > receipt.generation):
                return receipt
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.2)

    def _main_storage_entry_completed(self, *, wait=False):
        receipt = self._main_storage_entry_receipt
        if receipt is None:
            return None
        deadline = time.monotonic() + (12.0 if wait else 0.0)
        while True:
            # ALAS can retain the departing main screenshot after entry. Its
            # completed receipt belongs to a fresh destination observation.
            oracle = self._live_oracle
            reader = getattr(oracle, '_storage_page_snapshot', None)
            if reader is not None:
                state, tabs = reader()
                if tabs is not None and state.generation > receipt.generation:
                    return receipt
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.2)

    def _click_main_ready(self, semantic_id):
        before_input = getattr(self.oracle, 'input_dispatch_count', 0)
        try:
            return self._fresh_input_oracle().click(semantic_id)
        except SemanticGateClosed as exc:
            if semantic_id == 'main/storage' and self._main_storage_entry_receipt is not None:
                completed = self._main_storage_entry_completed(wait=True)
                if completed is not None:
                    return completed
            if semantic_id == 'main/tech' and self._main_tech_entry_receipt is not None:
                # Its accepted entry owns destination mounting, not another
                # attempt to make the departing Main source actionable.
                raise
            if semantic_id == 'main/live' and self._main_live_entry_receipt is not None:
                # Existing live-menu submission owns its destination checks.
                # Do not wait for or resubmit the departing source control.
                raise
            if (semantic_id == 'main/more' and self._main_more_entry_receipt is not None
                    and time.monotonic() <= self._main_more_entry_until):
                # A submitted sidebar entry has its own destination receipt
                # checks below. Waiting for the covered source again would
                # consume that transition window and risk another toggle.
                raise
            if (str(exc) != 'semantic target is not actionable'
                    or getattr(self.oracle, 'input_dispatch_count', 0) != before_input
                    or not self.oracle.main_page_visible()):
                raise
            # The home return can expose Main before its bottom controls regain
            # raycasts. Await fresh actionability; the ordinary click still owns
            # every input check, and no input is repeated after dispatch.
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline:
                if not self.oracle.main_page_visible():
                    raise exc
                if self.oracle.enabled(semantic_id):
                    # Mounting may outlive the offered screenshot. Reacquire
                    # before final proof; never reuse an expired input lease.
                    return self._fresh_input_oracle().click(semantic_id)
                time.sleep(0.2)
            raise

    def _click_priority(self, name):
        if (name in ('POPUP_CONFIRM', 'POPUP_CANCEL')
                and (self._commission_context is None
                     or self._commission_context.flow_kind != 'tactical')):
            prior = self._orphan_tactical_prompt_probe
            self._orphan_tactical_prompt_probe = None
            reader = self._frame_or_live_observation_oracle()
            if getattr(reader, 'tactical_continue_prompt_text', lambda: None)() is not None:
                # The shared native popup handler is an acknowledgement alias.
                # This exact inherited prompt always uses its reviewed Cancel.
                fresh = self._fresh_input_oracle()
                if fresh.tactical_continue_prompt_text() is None:
                    return None
                return fresh.click('tactical/continue/cancel')
            if (prior is not None and self.oracle.input_dispatch_count == prior[1]
                    and reader.read_state().generation >= prior[0]):
                # A queued replacement can mount between the native positive
                # probe and click. Consume that one probe without any input;
                # never reinterpret it as an unrelated Msgbox confirmation.
                return None
        if name in ('POPUP_CONFIRM', 'POPUP_CONFIRM_UI_ADDITIONAL',
                    'POPUP_CONFIRM_WHITE', 'POPUP_CONFIRM_WHITE_UI_ADDITIONAL'):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'operation_siren_adaptability_info_visible', lambda: False)():
                receipt = self._fresh_input_oracle().click_operation_siren_adaptability_info()
                self._operation_siren_adaptability_info_receipt = receipt
                return receipt
            previous = self._operation_siren_adaptability_info_receipt
            if (previous is not None and oracle.read_state().generation > previous.generation
                    and oracle.operation_siren_local_map_visible()
                    and not oracle._blocking_rules(oracle.read_state(), 'os/page/back')):
                # The source screenshot can outlive its accepted dismissal.
                # Consume this handoff once, without reinterpreting the shared
                # confirmation alias as a login or unrelated popup action.
                self._operation_siren_adaptability_info_receipt = None
                return None
        if name == 'GOTO_MAIN' and getattr(
                self._frame_or_live_observation_oracle(), 'operation_siren_order_panel_visible', lambda: False)():
            return self._fresh_input_oracle().click_operation_siren_order_back()
        if getattr(self, '_storage_box_use_receipt', None) is not None:
            if name == 'MATERIAL_ENTER' and self._frame_or_live_observation_oracle().enabled('reward/award-info/close'):
                return self._fresh_input_oracle().click('reward/award-info/close')
            if name == 'EQUIP_CONFIRM':
                oracle = self._fresh_input_oracle()
                self._storage_box_equipment_observation(oracle)
                receipt = oracle._click_retirement_button('storage/box/equipment/confirm-selection',
                    'ResolveEquipmentUI(Clone)/main/ok_btn',
                    identity_text_suffix='ResolveEquipmentUI(Clone)/main/ok_btn/Image',
                    identity_text='确 定')
                self._storage_box_equipment_receipt = receipt
                return receipt
            if name == 'EQUIP_CONFIRM_2':
                selection = getattr(self, '_storage_box_equipment_receipt', None)
                if selection is None:
                    raise SemanticGateClosed('storage equipment confirmation has no owned selection')
                receipt = self._fresh_input_oracle().click_storage_box_equipment_confirmation(
                    selection_generation=selection.generation)
                self._storage_box_destroy_receipt = receipt
                return receipt
        if getattr(self, '_storage_box_candidate', None) is not None and name in (
                'BOX_USE', 'BOX_AMOUNT_CONFIRM', 'AMOUNT_MINUS', 'AMOUNT_PLUS'):
            oracle = self._fresh_input_oracle()
            if name == 'BOX_USE':
                detail = oracle.storage_box_detail()
                self._validate_storage_box_identity(detail)
                return oracle.click_storage_box_detail('use', expected_name=detail.name,
                                                       expected_rarity=detail.rarity)
            amount = oracle.storage_box_amount()
            self._validate_storage_box_identity(amount)
            action = {'BOX_AMOUNT_CONFIRM': 'confirm', 'AMOUNT_MINUS': 'minus', 'AMOUNT_PLUS': 'plus'}[name]
            receipt = oracle.click_storage_box_amount(action, expected_name=amount.name,
                expected_rarity=amount.rarity, expected_quantity=amount.quantity)
            if action == 'confirm':
                self._storage_box_use_receipt = receipt
                self._storage_box_use_quantity = amount.quantity
            return receipt
        if name == 'GOTO_MAIN' and getattr(self._frame_or_live_observation_oracle(), 'storage_page_visible', lambda: False)():
            self._package_gate()
            return self._fresh_input_oracle().click_storage_page_back()
        if name == 'MATERIAL_ENTER' and getattr(self._frame_or_live_observation_oracle(), 'storage_page_visible', lambda: False)():
            self._package_gate()
            return self._fresh_input_oracle().click_storage_material_tab()
        if (name in ('POPUP_CONFIRM_WHITE', 'POPUP_CONFIRM_WHITE_UI_ADDITIONAL')
                and getattr(self.oracle, 'campaign_timeout_prompt_visible', lambda: False)()):
            self._package_gate()
            receipt = self.oracle.click('campaign/map-timeout/confirm')
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                state = self.oracle.read_state()
                if (state.generation > receipt.generation
                        and not any(b.active_in_hierarchy and b.active_and_enabled
                                    and ('/LevelGrid/' in b.path or '/LevelStageView(Clone)/' in b.path)
                                    for b in state.buttons)):
                    try:
                        if self.oracle.campaign_page_is_normal() or self.oracle.campaign_menu_is_entry():
                            self._package_gate()
                            return receipt
                    except SemanticGateClosed:
                        pass
                time.sleep(.1)
            raise SemanticGateClosed('expired campaign acknowledgement did not return to selection')
        if (name == 'GOTO_MAIN' and not self._login_flow.active
                and self._dorm_context is None
                and any(self._frame_or_live_observation_oracle().observation_target_present(target) for target in (
                    'dorm/feed/shop/cancel', 'dorm/feed/close'))):
            oracle = self._fresh_input_oracle()
            target = self._inherited_dorm_overlay_return(oracle)
            # Reacquire the normal final input frame; the existing reviewed
            # close enforces package/PID, freshness, ambiguity and blockers.
            if target is not None:
                return oracle.click(target)
        if name == 'MAP_PREPARATION_CANCEL':
            oracle = self._frame_or_live_observation_oracle()
            if self._inherited_exercise_precombat(oracle):
                self._package_gate()
                receipt = self.oracle.click_daily_precombat_back()
                deadline = time.monotonic() + 12.0
                while True:
                    state = self.oracle.read_state()
                    if (state.generation > receipt.generation
                            and not self.oracle.daily_precombat_visible()
                            and self.oracle.exercise_page_visible()
                            and not self.oracle._blocking_rules(state, 'exercise/page/home')):
                        return receipt
                    if time.monotonic() >= deadline:
                        raise SemanticGateClosed('inherited Exercise preparation cancel postcondition unavailable')
                    time.sleep(.1)
        if (name == 'GET_SHIP' and not self._login_flow.active
                and self._build_context is None and self._mission_context is None):
            # Acknowledging an already displayed ordinary acquisition is not
            # a new claim by the task that inherited it. Owned build/mission
            # flows retain their receipts and mutation accounting.
            self._package_gate()
            if not self.oracle.new_ship_reward_visible():
                raise SemanticGateClosed('reviewed inherited ship reward popup is absent')
            # NewShipLayer can ignore a click until its background is loaded.
            # Return the accepted input to ALAS' GET_SHIP loop, which owns the
            # next screenshot, subsequent acknowledgement and page completion.
            return self.oracle.click('reward/new-ship/continue')
        if name == 'AUTO_SEARCH_REWARD':
            oracle = self._frame_or_live_observation_oracle()
            if oracle.observation_target_present('os/auto-search/reward/close'):
                self._package_gate()
                receipt = self._fresh_input_oracle().click('os/auto-search/reward/close')
                deadline = time.monotonic()+4.0
                while time.monotonic() < deadline:
                    state = self.oracle.read_state()
                    if (state.generation > receipt.generation and not any(
                            button.active_in_hierarchy and '/WorldAutoFightRewardUI(Clone)/' in '/'+button.path
                            for button in state.buttons)):
                        self._package_gate()
                        return receipt
                    time.sleep(.1)
                raise SemanticGateClosed('auto-search reward close postcondition was not observed; do not retry')
        if name in ('POPUP_CONFIRM', 'POPUP_CANCEL') and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'operation_siren_energy_submission_prompt_visible', lambda: False)():
                self._package_gate()
                # The live oracle re-proves input and observes the newer
                # postcondition after the submitted frame is invalidated.
                return self.oracle.click_operation_siren_energy_submission(
                    confirm=name == 'POPUP_CONFIRM')
        if name == 'COIN' and self._minigame_context is not None:
            self._package_gate()
            oracle = self._fresh_input_oracle()
            before = oracle.minigame_coin_amount()
            receipt = oracle.click('game-room/free-coins')
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                state = self.oracle.read_state()
                if (state.generation > receipt.generation
                        and self.oracle.game_room_page_visible()
                        and not any(rule.blocker_id != 'award-info' for rule in
                                    self.oracle._blocking_rules(state, 'ui/absence-probe'))
                        and not self.oracle.observation_target_present('game-room/free-coins')
                        and self.oracle.minigame_coin_amount() > before):
                    self._package_gate()
                    return receipt
                time.sleep(.1)
            raise SemanticGateClosed('free minigame coin claim was not proven; do not retry')
        if name == 'GOTO_MAIN':
            oracle = self._frame_or_live_observation_oracle()
            if (oracle.observation_target_present('minigame/new-year/back')
                    and oracle.new_year_challenge_result() is not None):
                self._package_gate()
                receipt = self._fresh_input_oracle().click_new_year_challenge_result_close()
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    if (self.oracle.read_state().generation > receipt.generation
                            and self.oracle.new_year_challenge_result() is None
                            and (self.oracle.new_year_challenge_home_visible()
                                 or self.oracle.game_room_page_visible())):
                        return receipt
                    time.sleep(.1)
                raise SemanticGateClosed('retained Fushun result did not close; inspect before retry')
        inherited_tactical_award = (
            self._commission_context is not None
            and self._commission_context.flow_kind == 'tactical'
            and self._commission_context.tactical_reward_receipt is None
        )
        if (name == 'GET_ITEMS_1' and self._mission_context is None
                and self._build_context is None and self._research_context is None
                and (self._commission_context is None or inherited_tactical_award)
                and not self.daily_execution_active()
                and not self._meta_beacon_active and not self._meta_assist_active):
            oracle = self._frame_or_live_observation_oracle()
            if (oracle.award_info_page_visible()
                    and oracle.enabled('reward/award-info/close')):
                self._package_gate()
                receipt = self._fresh_input_oracle().click('reward/award-info/close')
                if inherited_tactical_award:
                    # Closing an already-open ordinary award does not claim a
                    # Tactical reward. Keep that claim's ledger and receipt
                    # untouched; original ALAS owns the subsequent page scan.
                    deadline = time.monotonic() + 12.0
                    while time.monotonic() < deadline:
                        state = self.oracle.read_state()
                        if (state.generation > receipt.generation
                                and not self.oracle.observation_target_present('reward/award-info/close')):
                            return receipt
                        time.sleep(.1)
                    raise SemanticGateClosed('inherited tactical award close postcondition not observed; do not retry')
                return receipt
        if self._campaign_context is None and name == 'AUTO_SEARCH_MENU_EXIT':
            self._package_gate()
            if self.oracle.observation_target_present('reward/campaign-total/exit'):
                receipt = self._fresh_input_oracle().click('reward/campaign-total/exit')
                deadline = time.monotonic() + 20.0
                while time.monotonic() < deadline:
                    if (self.oracle.read_state().generation > receipt.generation
                            and not self.oracle.observation_target_present('reward/campaign-total/exit')
                            and (self.oracle.event_campaign_page_visible()
                                 or self.oracle.campaign_page_is_normal())):
                        return receipt
                    time.sleep(.1)
                raise SemanticGateClosed('inherited total reward did not return to stage; do not retry')
        if self._campaign_context is None and name in ('WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM'):
            self._package_gate()
            oracle = self._fresh_input_oracle()
            confirm = name == 'CAMPAIGN_WITHDRAW_CONFIRM'
            receipt_field = '_inherited_withdraw_' + ('confirm' if confirm else 'open') + '_receipt'
            if getattr(self, receipt_field, None) is not None:
                raise SemanticGateClosed('inherited withdrawal input already submitted')
            if oracle.inherited_campaign_withdraw_control(confirm=confirm) is None:
                raise SemanticGateClosed('inherited withdrawal target is not actionable')
            receipt = oracle.click_campaign_withdraw(confirm=confirm)
            setattr(self, receipt_field, receipt)
            # Input invalidates its leased frame. Observe the postcondition
            # from fresh live state, never borrow the submitted input frame.
            oracle = self.oracle
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline:
                post = oracle.read_state()
                if post.generation > receipt.generation:
                    if confirm:
                        map_mounted = any(b.active_in_hierarchy and b.active_and_enabled
                                          and b.path.startswith('LevelCamera/Canvas/UIMain/LevelGrid/')
                                          for b in post.buttons)
                        if not map_mounted and oracle.campaign_withdraw_control(confirm=True) is None:
                            return receipt
                    elif oracle.campaign_withdraw_control(confirm=True) is not None:
                        return receipt
                time.sleep(.1)
            raise SemanticGateClosed('inherited withdrawal postcondition not observed; do not retry')
        if name == 'MAP_PREPARATION_CANCEL' and self._campaign_context is None:
            self._package_gate()
            oracle = self._fresh_input_oracle()
            detail = getattr(oracle, 'inherited_event_map_preparation_state', lambda: None)()
            if detail is not None:
                return oracle.cancel_campaign_map_preparation(detail.stage_code)
        if name in ('POPUP_CONFIRM', 'POPUP_CANCEL'):
            if getattr(self.oracle, 'meta_skill_full_prompt_visible', lambda: False)():
                self._package_gate()
                return self.oracle.click_meta_skill_full_prompt(name == 'POPUP_CONFIRM')
        if (name in ('GOTO_MAIN', 'GAME_ROOM_GOTO_MAIN')
                and self.oracle.observation_target_present('game-room/back')
                and getattr(self.oracle, 'game_room_page_visible', lambda: False)()
                and self.oracle.observation_target_present('game-room/home')):
            self._package_gate()
            receipt = self._fresh_input_oracle().click('game-room/home')
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline:
                state = self.oracle.read_state()
                if (state.generation > receipt.generation
                        and self.oracle.main_page_visible()
                        and not self.oracle._blocking_rules(state, 'ui/absence-probe')):
                    self._package_gate()
                    return receipt
                time.sleep(.1)
            raise SemanticGateClosed('game-room home return was not proven; inspect before retry')
        if name == 'DOSSIER_REWARD_RECEIVE':
            self._package_gate()
            return self.oracle.click_meta_dossier_sync_rewards()
        if (name in ('CLICK_SAFE_AREA', 'GET_ITEMS_1', 'GET_ITEMS_2')
                and (self._meta_beacon_active or self._meta_assist_active)
                and self._meta_reward_close_receipt is not None
                and not self.oracle.observation_target_present('reward/award-info/close')
                and not self.oracle.observation_target_present('reward/award-info1/close')
                and (self.oracle.meta_page_visible()
                     or getattr(self.oracle, 'meta_character_sync_page_visible', lambda: False)())
                and self.oracle.read_state().generation > self._meta_reward_close_receipt.generation):
            self._package_gate()
            if getattr(self.oracle, 'meta_character_sync_page_visible', lambda: False)():
                self.oracle.meta_character_sync_rewards()
            receipt = self._meta_reward_close_receipt
            self._meta_reward_close_receipt = None
            return receipt
        if self._meta_beacon_active and name == 'DOSSIER_REWARD_ENTER':
            self._package_gate()
            prior = getattr(self, '_meta_dossier_sync_open_receipt', None)
            if (prior is not None
                    and self.oracle.observation_target_present('meta/dossier/sync/back')):
                # The native loop can still hold its pre-click dossier frame.
                # A complete fresh arrival acknowledges that accepted entry;
                # it never dispatches the now-absent old control again.
                self.oracle.meta_dossier_sync_points()
                if self.oracle.read_state().generation <= prior.generation:
                    raise SemanticGateClosed('META dossier sync arrival is not fresh')
                self._meta_dossier_sync_open_receipt = None
                return prior
            receipt = self.oracle.click_meta_dossier_sync_open()
            self._meta_dossier_sync_open_receipt = receipt
            return receipt
        if (self._meta_beacon_active or self._meta_assist_active) and name == 'META_AUTO_CONFIRM':
            self._package_gate()
            return self.oracle.click_meta_dossier_auto_result_confirm()
        if self._meta_beacon_active and name == 'META_AUTO_ATTACK_CONFIRM':
            self._package_gate()
            return self.oracle.click_meta_dossier_auto_confirm()
        if self._meta_beacon_active and name == 'META_AUTO_ATTACK_START':
            self._package_gate()
            return self.oracle.click_meta_dossier_auto_start()
        if (name in ('SYNC_ENTER', 'SYNC_ENTER2', 'SYNC_TAP')
                and getattr(self.oracle, 'meta_character_sync_page_visible', lambda: False)()):
            self._package_gate()
            return self.oracle.click_meta_character_sync_rewards()
        if (name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'CLICK_SAFE_AREA')
                and (getattr(self.oracle, 'meta_character_sync_page_visible', lambda: False)()
                     or ((self._meta_assist_active or self._meta_beacon_active)
                         and self.oracle.award_info_page_visible()))):
            self._package_gate()
            target = self._award_close_target()
            if target is None:
                if (not self.oracle.exists('reward/award-info/close')
                        and not self.oracle.exists('reward/award-info1/close')):
                    if getattr(self.oracle, 'meta_character_sync_page_visible', lambda: False)():
                        self.oracle.meta_character_sync_rewards()
                    raise SemanticTargetMissing('META reward popup has disappeared')
                raise SemanticGateClosed('META synchronization reward close is not actionable')
            receipt = self.oracle.click(target)
            if self._meta_assist_active or self._meta_beacon_active:
                self._meta_reward_close_receipt = receipt
            return receipt
        if (self._build_context is not None
                and name in ('GET_ITEMS_1', 'GET_ITEMS_2')):
            self._package_gate()
            target = self._award_close_target()
            if target is None:
                if (not self.oracle.exists('reward/award-info/close')
                        and not self.oracle.exists('reward/award-info1/close')):
                    # ui_page_main_popups probes both aliases in one ALAS
                    # frame. The first may already have closed the reward;
                    # the second must re-enter the original loop without a
                    # duplicate tap, once the exact queue is proven again.
                    self.oracle.build_queue_timers()
                    raise SemanticTargetMissing('construction reward popup has disappeared')
                raise SemanticGateClosed('construction reward close is not actionable')
            return self._close_build_award(target)
        if (name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3')
                and self.oracle.award_info_page_visible()
                and self.oracle.exists('guild/report/close')):
            self._package_gate()
            target = self._award_close_target()
            if target is None:
                raise SemanticGateClosed('guild report reward close is not actionable')
            return self.oracle.click(target)
        if (not self._login_flow.active
                and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
                and self.oracle.exists("research/progress/confirm")):
            self._package_gate()
            target = "research/progress/confirm" if name == "POPUP_CONFIRM" else "research/progress/cancel"
            receipt = self.oracle.click(target)
            self._research_progress_close_receipt = receipt
            self._research_progress_close_until = time.monotonic() + 5.0
            return receipt
        if (not self._login_flow.active and name in ('POPUP_CONFIRM','POPUP_CANCEL')
                and self._research_progress_close_receipt is not None
                and time.monotonic() <= self._research_progress_close_until):
            prior = self._research_progress_close_receipt
            state = self.oracle.read_state()
            if (state.generation > prior.generation and self.oracle.main_page_visible()
                    and not self.oracle._blocking_rules(state, 'ui/absence-probe')):
                # A native popup handler can repeat its leased observation
                # while this already submitted dismissal reaches Main.
                # Complete the prior receipt; do not route a second input to
                # the unrelated generic network-confirm mapping.
                self._package_gate()
                return prior
        if name == "RESET_FLEET_PREPARATION":
            self._package_gate()
            receipt = self.oracle.click_operation_siren_reset_fleet()
            self.begin_operation_siren_page_remount(20.0)
            return receipt
        if name == "RESET_TICKET_POPUP":
            self._package_gate()
            receipt = self.oracle.click_operation_siren_reset_ticket()
            self.begin_operation_siren_page_remount(20.0)
            return receipt
        if name == "POPUP_CONFIRM" and self.oracle.observation_surface_present(ObservationSurface.RESET_SHOP):
            self._package_gate()
            receipt = self.oracle.click_operation_siren_reset_shop()
            self.begin_operation_siren_page_remount(20.0)
            return receipt
        if (
            not self._login_flow.active
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                # NetworkDown is a global topmost overlay.  Resolve its exact
                # typed target before any task context interprets ALAS'
                # generic POPUP_* name as a task-local confirmation.
                return self.click_network_reconnect(name == 'POPUP_CONFIRM')
        if name in (
            "RETIRE_APPEAR_1",
            "RETIRE_APPEAR_2",
            "RETIRE_APPEAR_3",
        ) and self.dock_full_recovery_owned():
            if name == "RETIRE_APPEAR_2":
                raise SemanticGateClosed(
                    "campaign dock expansion is not authorized"
                )
            return self.click_campaign_dock_full_choice(
                "organize" if name == "RETIRE_APPEAR_1" else "enhance"
            )
        if self._meta_beacon_active and self.oracle.daily_precombat_visible():
            if name == "BATTLE_PREPARATION":
                return self.click_meta_precombat_start()
            if name == "BACK_ARROW":
                return self.click_meta_precombat_back()
        if self._login_flow.active and name == 'GET_SHIP':
            if not self.oracle.new_ship_reward_visible():
                raise SemanticGateClosed('reviewed login new-ship popup is absent')
            receipt = self.oracle.click('reward/new-ship/continue')
            self._login_flow.extend_passive_transition(60.0)
            return receipt
        if (
            self._login_flow.active
            and name in ("GET_ITEMS_1", "GET_ITEMS_2")
        ):
            target = self._award_close_target()
            if target is None or name != "GET_ITEMS_1":
                raise SemanticGateClosed(
                    "reviewed login reward popup is absent"
                )
            receipt = self.oracle.click(target)
            self._login_flow.extend_passive_transition(60.0)
            return receipt
        return UNHANDLED

    def _click_back(self, name):
        if name == 'BACK_ARROW' and getattr(self.oracle, 'storage_page_visible', lambda: False)():
            self._package_gate()
            return self._fresh_input_oracle().click_storage_page_back()
        if name == 'BACK_ARROW':
            # This port reads its final live proof and then waits for a new
            # generation. A screenshot lease is invalidated by the tap and
            # cannot supply the postcondition reader.
            input_oracle = self.oracle
            if input_oracle.observation_target_present('meowfficer/buy/max'):
                try:
                    input_oracle.meowfficer_purchase_state()
                except SemanticGateClosed:
                    pass
                else:
                    self._package_gate()
                    return input_oracle.click('meowfficer/buy/close')
            if input_oracle.enhancement_dock_back_control() is not None:
                self._package_gate()
                receipt = input_oracle.click_enhancement_dock_back()
                if self._campaign_context is not None:
                    self._campaign_context.passive_transition_until = time.monotonic() + 20.0
                return receipt
        if name == 'BACK_ARROW' and self._meta_assist_active:
            if self.oracle.daily_precombat_visible():
                return self.click_meta_precombat_back()
            prior = self._meta_precombat_back_receipt
            if (prior is not None
                    and time.monotonic() <= self._meta_precombat_back_until
                    and self.oracle.read_state().generation > prior.generation):
                self.oracle.meta_assist_state()
                return prior
        if name == 'BACK_ARROW' and (
            self._commission_context is None
            or self._commission_context.flow_kind == 'tactical'
        ):
            input_oracle = self._fresh_input_oracle()
            if (self._commission_context is None
                    and input_oracle.observation_target_present('tactical/page/back')
                    and input_oracle.enabled('tactical/page/back')):
                # The original page graph may leave a classroom retained by
                # the preceding task. This is navigation, not a tactical grant.
                return input_oracle.click('tactical/page/back')
            if (input_oracle.observation_target_present('commission/page/back')
                    and input_oracle.enabled('commission/page/back')):
                # A different ALAS task may inherit this exact page. Its
                # normal page graph uses BACK_ARROW to leave it.
                receipt = input_oracle.click('commission/page/back')
                self._commission_return_transition_until = time.monotonic() + 12.0
                return receipt
        if name == "BACK_ARROW" and all(
            context is None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            if (self.oracle.observation_target_present('research/page/back')
                    and self.oracle.enabled('research/page/back')):
                return self._record_mission_transition(
                    self.oracle.click('research/page/back'))
            if (self.oracle.observation_target_present("exercise/page/back")
                    and self.oracle.exercise_page_visible()):
                receipt = self.oracle.click("exercise/page/back")
                self._exercise_page_back_transition_until = time.monotonic() + 20.0
                return receipt
            if (self.oracle.observation_target_present("exercise/opponent/back")
                    and self.oracle.exercise_opponent_detail_visible()):
                return self.oracle.click_exercise_opponent_back()
            if (self.oracle.observation_target_present("daily/precombat/back")
                    and self.oracle.daily_precombat_visible()):
                return self.oracle.click_daily_precombat_back()
            if (self.oracle.observation_target_present("daily/page/back")
                    and self.oracle.daily_page_visible()):
                return self.oracle.click_daily_control("daily/page/back")
            oracle = self._frame_or_live_observation_oracle()
            current_raid_visible = (
                oracle.observation_surface_present(ObservationSurface.CURRENT_RAID)
                and oracle.raid_page_visible(oracle.current_raid_event())
            )
            if current_raid_visible:
                return self.click_raid_home(oracle.current_raid_event())
            input_oracle = self._fresh_input_oracle()
            if (
                input_oracle.observation_target_present("campaign-menu/page/back")
                and (
                    input_oracle.campaign_menu_is_entry()
                    or input_oracle.campaign_page_is_normal()
                )
                and input_oracle.enabled("campaign-menu/page/back")
            ):
                from_chapter = input_oracle.campaign_page_is_normal()
                receipt = input_oracle.click("campaign-menu/page/back")
                if from_chapter:
                    self._exercise_chapter_back_transition_until = time.monotonic() + 20.0
                return receipt
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: BACK_ARROW"
            )
        return UNHANDLED

    def _click_admission(self, name, semantic_id, campaign_stage_code, navbar_match, commission_row_match, build_side_navbar_match, build_pool_navbar_match):
        if (
            semantic_id is None
            and name not in MISSION_CLICK_RESOURCES
            and name not in MAIL_CLICK_RESOURCES
            and name not in CAMPAIGN_CLICK_RESOURCES
            and not (
                self._research_context is not None
                and name in RESEARCH_CLICK_RESOURCES
            )
            and not (
                self._dorm_context is not None
                and name in DORM_VIRTUAL_RESOURCES
            )
            and not (
                self._build_context is not None
                and name in BUILD_VIRTUAL_RESOURCES
            )
            and not (
                self._commission_context is not None
                and self._commission_context.flow_kind == "tactical"
                and (name in TACTICAL_VIRTUAL_RESOURCES or name == "GET_MISSION")
            )
            and not (
                self._commission_context is not None
                and name in COMMISSION_CLICK_RESOURCES
            )
            and campaign_stage_code is None
            and CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name) is None
            and navbar_match is None
            and commission_row_match is None
            and not (
                self._build_context is not None
                and (
                    build_side_navbar_match is not None
                    or build_pool_navbar_match is not None
                )
            )
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        return UNHANDLED

    def _main_battle_destination_visible(self):
        receipt = self._main_battle_transition_receipt
        if receipt is None or self.oracle.read_state().generation <= receipt.generation:
            return False
        for probe in (self.oracle.campaign_menu_is_entry,
                      self.oracle.campaign_page_is_normal, self.oracle.campaign_is_in_map):
            try:
                if probe():
                    return True
            except (SemanticGateClosed, SemanticTargetMissing):
                continue
        return False

    def _main_shop_destination_visible(self):
        receipt = self._main_shop_transition_receipt
        return bool(
            receipt is not None
            and self.oracle.read_state().generation > receipt.generation
            and self.oracle.observation_target_present("shop/home")
            and self.oracle.recommendation_shop_visible()
        )

    def _research_menu_return_completed(self):
        previous = self._research_back_receipt
        if (previous is None
                or previous.semantic_id != 'research-menu/page/back'
                or self.oracle.observation_target_present('research-menu/page/back')
                or not self.oracle.main_page_visible()):
            return None
        state = self.oracle.read_state()
        if (state.generation <= previous.generation
                or self.oracle._blocking_rules(state, 'ui/absence-probe')):
            return None
        # A retained ALAS screenshot can reissue the edge after its accepted
        # input reached Main. Consume that receipt once without another tap.
        self._package_gate()
        self._research_back_receipt = None
        return previous

    def _click_main(self, name, semantic_id):
        if (name in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME')
                and self.oracle.award_info_page_visible()
                and (self.oracle.meta_page_visible()
                     or self.oracle.exists('guild/report/close'))):
            target = self._award_close_target()
            if target is None:
                raise SemanticGateClosed('reward overlay has no actionable close target')
            return self._record_mission_transition(self.oracle.click(target))
        if (
            semantic_id == "reward/page/back"
            and not self.oracle.observation_target_present("reward/page/back")
            and self.oracle.main_page_visible()
            and self.oracle.enabled("main/battle")
        ):
            # ALAS may repeat the old sidebar edge while its closing frame is
            # fading. A fresh, unobstructed destination needs no second input.
            return self.oracle.main_page_receipt()
        if semantic_id is None and name == "GOTO_MAIN":
            reconnect_target = "overlay/network-reconnect/confirm"
            if self.oracle.enabled(reconnect_target):
                # NetworkDown is a global topmost owner.  It can mount after
                # ui_goto proved the current page but before the linked home
                # action is revalidated.  Consume only that exact reviewed
                # recovery target; ALAS' next ui_goto iteration retries the
                # unchanged page edge after the overlay is gone.
                receipt = self.oracle.click(reconnect_target)
                self._network_reconnect_transition_until = time.monotonic() + 20.0
                return receipt
            if self._mail_context is not None and self.oracle.enabled("mail/manage/back"):
                return self._record_mission_transition(
                    self.oracle.click("mail/manage/back")
                )
            handoff = self._shop_home_handoff
            if (handoff is not None
                    and self.oracle.input_dispatch_count == handoff[1]
                    and time.monotonic() <= handoff[2]):
                observed = self._frame_or_live_observation_oracle()
                state = observed.read_state()
                if not any(rule.blocker_id != 'loading'
                           for rule in observed._blocking_rules(state, 'shop/home')):
                    # Our accepted Home can leave the old shop mounted while
                    # Main loads. Native ui_goto owns the next screenshot and
                    # destination proof; never repeat that accepted input or
                    # manufacture another action receipt during this handoff.
                    return handoff[0]
            target = self._goto_main_target()
            if target in ('archive/activity-list/home', 'settings/back', 'player/profile/back'):
                # This is ALAS' unknown-page Home edge. Its next screenshot
                # discovers Main and handles any newly mounted popup; an
                # unrelated battle button need not be actionable to arrive.
                previous = self._inherited_home_return_receipt
                if previous is not None and previous.semantic_id == target:
                    if time.monotonic() <= self._inherited_home_return_until:
                        # A fading source can remain mounted after its tap.
                        # Acknowledge only that accepted input; ALAS owns the
                        # next screenshot and destination decision.
                        return previous
                    raise SemanticTargetNotActionable(
                        target, self._frame_or_live_observation_oracle().read_state().generation)
                receipt = self._fresh_input_oracle().click(target)
                self._inherited_home_return_receipt = receipt
                self._inherited_home_return_until = time.monotonic() + 12.0
                return receipt
            if target == 'commission/detail/back':
                input_oracle = self._fresh_input_oracle()
                if not self._retained_commission_detail_visible(input_oracle):
                    raise SemanticGateClosed('retained commission detail changed before return')
                receipt = input_oracle.click(target)
                self.oracle.wait_for_any(('commission/page/back', 'reward/page/back'),
                                         timeout_seconds=12.0,
                                         minimum_generation=receipt.generation)
                return receipt
            if target in (None, 'research-menu/page/back'):
                completed = self._research_menu_return_completed()
                if completed is not None:
                    return completed
            if (target is None
                    and self.oracle.observation_target_present('campaign-menu/page/back')):
                # OS exit mounts LevelMainScene before its back button becomes
                # actionable. Await that exact existing edge using live reads.
                for attempt in range(24):
                    if not self.oracle.observation_target_present('campaign-menu/page/back'):
                        break
                    if self.oracle.enabled('campaign-menu/page/back'):
                        target = 'campaign-menu/page/back'
                        break
                    if attempt < 23:
                        time.sleep(0.2)
            if target in (None, 'research/page/back'):
                previous = self._research_back_receipt
                if (previous is not None
                        and getattr(previous, 'semantic_id', 'research/page/back') == 'research/page/back'
                        and not self.oracle.observation_target_present('research/page/back')
                        and (self.oracle.enabled('research-menu/page/back')
                             or self.oracle.main_page_visible())
                        and self.oracle.read_state().generation > previous.generation):
                    # The old ALAS page edge can outlive its actual return.
                    # Consume only our own receipt on a proven destination.
                    self._research_back_receipt = None
                    return previous
            if target in ('minigame/new-year/back', 'minigame/poke/back', 'minigame/shooting/back'):
                input_oracle = self._fresh_input_oracle()
                if target == 'minigame/poke/back':
                    receipt = input_oracle.click_poke_minigame_back()
                elif target == 'minigame/shooting/back':
                    receipt = input_oracle.click_shooting_minigame_back()
                else:
                    receipt = input_oracle.click_new_year_challenge_prepare_control('back')
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    if self.oracle.game_room_page_visible():
                        return receipt
                    time.sleep(0.1)
                raise SemanticGateClosed('minigame prepare back did not restore the game room')
            if target == 'private-quarters/home':
                return self.oracle.click_private_quarters_home()
            if target == 'meta/character/back':
                receipt = self._fresh_input_oracle().click_meta_character_back()
                self._inherited_home_return_receipt = receipt
                self._inherited_home_return_until = time.monotonic() + 12.0
                return receipt
            if target is None:
                previous = self._inherited_home_return_receipt
                if (previous is not None and previous.semantic_id == 'meta/character/back'
                        and time.monotonic() <= self._inherited_home_return_until):
                    # The accepted back can unmount META before ReshMenu is
                    # actionable. Yield once without another input; ALAS' next
                    # screenshot retains page discovery and completion checks.
                    self._inherited_home_return_receipt = None
                    return previous
                context = self._battle_pass_context
                if (
                    context is not None
                    and context.home_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    # ui_goto may reissue GOTO_MAIN after the clicked page has
                    # unmounted but before the main root is fully observable.
                    # Return the proven receipt instead of issuing a second
                    # input into an unidentified transition frame.
                    return context.home_receipt
                if self.oracle.main_page_visible():
                    return self.oracle.main_page_receipt()
                # Valid observation with no mapped exit is a capability gap.
                # ALAS' existing task-local failure interval owns re-entry;
                # identity, freshness and ambiguity errors above keep their
                # original classification, and no input is authorized here.
                raise AlasSemanticUnmapped("GOTO_MAIN has no reviewed page target")
            if target == "os/page/back":
                previous = self._operation_siren_exit_receipt
                handoff = self._operation_siren_exit_handoff
                if (previous is None and handoff is not None
                        and handoff[1] == self.oracle.input_dispatch_count):
                    # The native popup loop can acknowledge the accepted
                    # close before its page graph consumes the old map edge.
                    # Retain that same input result until another real input;
                    # only a fresh, actionable destination can acknowledge it.
                    previous = handoff[0]
                if previous is not None and previous.semantic_id == 'os/exit/confirm':
                    # A retained map observation can clear the passive entry
                    # lease after confirmation. It must not cancel this
                    # bounded, input-free wait for the proven destination.
                    # Dialog acknowledgement can also precede the map fade;
                    # its retained handoff needs the same wait, not a second
                    # map-back attempt after just one still-mounted frame.
                    deadline = time.monotonic() + 5.0
                    while True:
                        input_oracle = self._fresh_input_oracle()
                        state = input_oracle.read_state()
                        if (state.generation > previous.generation
                                and tuple(rule.blocker_id for rule in
                                    input_oracle._blocking_rules(state, 'os/page/back')) == ('loading',)):
                            # An accepted exit can load longer than this
                            # adapter wait. Native navigation owns the next
                            # screenshot and timeout; never repeat map-back.
                            return None
                        if (state.generation > previous.generation
                                and not input_oracle.observation_target_present('os/page/back')
                                and ((input_oracle.main_page_visible()
                                      and input_oracle.enabled('main/battle'))
                                     or (input_oracle.campaign_menu_is_entry()
                                         and input_oracle.enabled('campaign-menu/page/back')))):
                            # The old screenshot can retain the map during
                            # its exit animation. Await fresh frames after the
                            # accepted confirmation, never send another back.
                            self._operation_siren_exit_receipt = None
                            return previous
                        if time.monotonic() >= deadline:
                            raise SemanticGateClosed('operation siren exit destination did not become actionable')
                        time.sleep(0.2)
                return self._record_mission_transition(
                    self._fresh_input_oracle().click_operation_siren_back()
                )
            if target == "os/globe/map":
                # The original unknown-page home recovery returns one level
                # to the local OS page, then its page graph owns the next edge.
                receipt = self.oracle.click_operation_siren_globe_map()
                self.begin_operation_siren_page_remount(20.0)
                return receipt
            if target == 'daily/page/back':
                return self._record_mission_transition(self.oracle.click_daily_control(target))
            if target == "meta/home":
                previous = self._meta_home_receipt
                if (previous is not None
                        and not self.oracle.observation_target_present('meta/home')
                        and self.oracle.main_page_visible()
                        and self.oracle.read_state().generation > previous.generation):
                    # ALAS can select its old home edge from the screenshot
                    # frame after the live page has already reached main.
                    self._meta_home_receipt = None
                    return previous
                receipt = self._fresh_input_oracle().click_meta_home()
                self._meta_home_receipt = receipt
                return self._record_mission_transition(receipt)
            if target == "raid/page/home":
                return self._record_mission_transition(
                    self.click_raid_home(event=self.oracle.current_raid_event())
                )
            if target == "battle-pass/home":
                context = self._battle_pass_context
                if (
                    context is not None
                    and context.home_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.home_receipt
                receipt = self._record_mission_transition(
                    self.oracle.click_battle_pass_home()
                )
                if context is not None:
                    context.home_receipt = receipt
                    context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if target == "shop/home":
                receipt = self._record_mission_transition(
                    self._fresh_input_oracle().click_recommendation_shop_home()
                )
                self._shop_home_handoff = (
                    receipt, self.oracle.input_dispatch_count, time.monotonic() + 12.0)
                context = self._battle_pass_context
                if context is not None:
                    context.home_receipt = receipt
                    context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if (
                self._research_context is not None
                and target in ("research/page/back", "research-menu/page/back")
            ):
                context = self._research_context
                cached = context.navigation_receipts.get(target)
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                receipt = self._record_mission_transition(self.oracle.click(target))
                context.navigation_receipts[target] = receipt
                return receipt
            source_oracle = (self._fresh_input_oracle()
                             if target == 'campaign-menu/page/back' else self.oracle)
            # Keep chapter identity and the admitted Back target in the same
            # prepared input frame. Destination checks below stay live after
            # that input invalidates its source lease.
            if target == 'campaign-menu/page/back':
                handoff = self._operation_siren_exit_handoff
                if (handoff is not None and handoff[0].semantic_id == 'os/exit/confirm'
                        and handoff[1] == self.oracle.input_dispatch_count
                        and time.monotonic() <= self._operation_siren_entry_transition_until
                        and source_oracle.campaign_menu_is_entry()):
                    state = source_oracle.read_state()
                    back = source_oracle._unique(state, target)
                    if (state.generation > handoff[0].generation
                            and not source_oracle.observation_target_present('os/page/back')
                            and back.active_in_hierarchy and back.active_and_enabled
                            and back.interactable and back.raycast_top is not True
                            and back.point is not None and back.bounds is not None
                            and back.bounds.contains(back.point)
                            and not source_oracle._blocking_rules(state, target)):
                        # The accepted OS exit reached its known menu while
                        # Back's raycast is still mounting. No input is allowed;
                        # native ui_goto owns the next screenshot and retry.
                        return None
            from_chapter = (
                target == 'campaign-menu/page/back'
                and source_oracle.campaign_page_is_normal()
            )
            from_event = (
                target == 'campaign-menu/page/back'
                and source_oracle.event_campaign_page_visible()
            )
            receipt = self._record_mission_transition(source_oracle.click(target))
            if target == 'academy/page/back':
                # Return one reviewed page edge; the original ALAS page graph
                # owns any further navigation after the Academy unmounts.
                self.oracle.wait_for_any(('main/battle', 'dorm-menu/academy'),
                                         timeout_seconds=12.0,
                                         minimum_generation=receipt.generation)
            if target == 'research/page/back':
                self._research_back_receipt = receipt
            if target == 'build/page/back':
                self._build_return_transition_until = time.monotonic() + 12.0
            if target == 'commission/page/back':
                self._commission_return_transition_until = time.monotonic() + 12.0
            if target == 'campaign-menu/page/back':
                deadline = time.monotonic() + 12.0
                while time.monotonic() < deadline:
                    if self.oracle.read_state().generation > receipt.generation:
                        if (from_event
                                and not self.oracle.event_campaign_page_visible()
                                and self.oracle.campaign_page_is_normal()):
                            # The event selector can return to its retained
                            # normal chapter before the campaign entrance.
                            # ALAS' page graph owns the next back edge.
                            return receipt
                        if from_chapter:
                            if (self.oracle.campaign_menu_is_entry()
                                    and not self.oracle.campaign_page_is_normal()):
                                return receipt
                        elif (self.oracle.main_page_visible()
                              and not self.oracle.observation_target_present(target)):
                            return receipt
                    time.sleep(0.2)
                raise SemanticGateClosed(
                    'Campaign back did not reach its exact next page')
            context = self._battle_pass_context
            if context is not None:
                context.home_receipt = receipt
                context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        return UNHANDLED

    def _click_confirmation(self, name):
        if name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
            if (name == 'POPUP_CONFIRM' and self._mission_context is not None
                    and self.oracle.mission_overflow_prompt_visible()):
                return self.oracle.click_mission_overflow_confirm()
            if (
                self._commission_context is not None
                and self._commission_context.start_receipt is not None
            ):
                context = self._commission_context
                cost = self.oracle.commission_start_prompt_cost()
                if cost is None or cost != context.selected_oil_cost:
                    raise SemanticGateClosed("commission start prompt changed")
                target = (
                    "commission/start/confirm"
                    if name == "POPUP_CONFIRM"
                    else "commission/start/cancel"
                )
                receipt = self.oracle.click(target)
                if name == "POPUP_CONFIRM":
                    context.start_confirm_receipt = receipt
                return receipt
            prompt_kind = self.oracle.observation_prompt_kind()
            prior_entry = self._operation_siren_abyssal_entry_receipt
            if (name == "POPUP_CONFIRM" and prompt_kind is None
                    and prior_entry is not None
                    and time.monotonic() <= self._operation_siren_entry_transition_until
                    and self._operation_siren_abyssal_entry_input_count is not None
                    and self.oracle.input_dispatch_count
                        == self._operation_siren_abyssal_entry_input_count):
                # globe_enter may still own the screenshot of a confirmation
                # already accepted by Unity. A newer, unobscured local map
                # completes that real input; it does not authorize another tap.
                destination = self._fresh_input_oracle()
                state = destination.read_state()
                if (state.generation > prior_entry.generation
                        and destination.operation_siren_local_map_visible()
                        and not destination.observation_surface_present(ObservationSurface.MESSAGE_BOX)
                        and not destination._blocking_rules(state, 'os/page/back')):
                    back = destination._unique(state, 'os/page/back')
                    if back.active_in_hierarchy and back.active_and_enabled:
                        self._operation_siren_abyssal_entry_receipt = None
                        self._operation_siren_abyssal_entry_input_count = None
                        return prior_entry
            prior_exit = self._operation_siren_exit_receipt
            if (name == "POPUP_CONFIRM" and prompt_kind is None
                    and prior_exit is not None
                    and time.monotonic() <= self._operation_siren_entry_transition_until):
                # Consume an already accepted dialog close from one fresh
                # observation. An abyss can return to its local map, and the
                # next page may still be mounting. Native ALAS owns that page
                # transition; this is no new input or exit-completion claim.
                observed = self._frame_or_live_observation_oracle()
                state = observed.read_state()
                if (state.generation > prior_exit.generation
                        and not observed.observation_surface_present(ObservationSurface.MESSAGE_BOX)):
                    self._operation_siren_exit_receipt = None
                    return prior_exit
            if (prompt_kind == "opsi-exit"
                    and self.oracle.operation_siren_exit_prompt_visible()):
                receipt = self._fresh_input_oracle().click_operation_siren_exit(
                    confirm=name == "POPUP_CONFIRM"
                )
                if name == "POPUP_CONFIRM":
                    self._operation_siren_exit_receipt = receipt
                    self._operation_siren_exit_handoff = (receipt, self.oracle.input_dispatch_count)
                    self._operation_siren_entry_transition_until = (
                        time.monotonic() + 30.0
                    )
                return receipt
            if (prompt_kind == "opsi-abyssal-entry"
                    and self.oracle.operation_siren_abyssal_entry_prompt_visible()):
                receipt = self._fresh_input_oracle().click_operation_siren_abyssal_entry(
                    confirm=name == "POPUP_CONFIRM"
                )
                if name == "POPUP_CONFIRM":
                    self._operation_siren_abyssal_entry_receipt = receipt
                    self._operation_siren_abyssal_entry_input_count = getattr(
                        self.oracle, 'input_dispatch_count', None)
                    self._operation_siren_entry_transition_until = (
                        time.monotonic() + 30.0
                    )
                else:
                    self._operation_siren_abyssal_entry_receipt = None
                    self._operation_siren_abyssal_entry_input_count = None
                return receipt
            if (prompt_kind == "meta-simulation"
                    and self.oracle.meta_simulation_prompt_visible()):
                if name != "POPUP_CANCEL":
                    raise SemanticGateClosed(
                        "META simulation is not an authorized beacon action"
                    )
                return self.oracle.click_meta_simulation_cancel()
            if (prompt_kind == "meta-sortie"
                    and self.oracle.meta_assist_sortie_prompt_visible()):
                if self._meta_beacon_active:
                    receipt = self.oracle.click_meta_assist_sortie(
                        name == "POPUP_CONFIRM"
                    )
                    if name == "POPUP_CONFIRM":
                        self._operation_siren_combat_active = True
                    return receipt
                if name == "POPUP_CONFIRM":
                    if (self._meta_assist_active and self._meta_precombat_start_receipt is not None
                            and time.monotonic() < self._meta_precombat_start_until):
                        receipt = self.oracle.click_meta_assist_sortie(True)
                    else:
                        receipt = self._dispatch_mutation(
                            "meta.assist",
                            lambda: self.oracle.click_meta_assist_sortie(True),
                        )
                    self._operation_siren_combat_active = True
                    return receipt
                return self.oracle.click_meta_assist_sortie(False)
        return UNHANDLED

    def _click_mapped(self, name, semantic_id):
        if semantic_id is not None:
            if semantic_id == 'main/storage':
                completed = self._main_storage_entry_completed()
                if completed is not None:
                    return completed
            if semantic_id == 'research-menu/page/back':
                completed = self._research_menu_return_completed()
                if completed is not None:
                    return completed
            if semantic_id == 'private-quarters/room/new-jersey':
                receipt = self.oracle.click(semantic_id)
                self._private_quarters_transition_until = time.monotonic() + 90.0
                return receipt
            if semantic_id == 'private-quarters/dialogue/continue':
                prior = getattr(self, '_private_quarters_dialogue_receipt', None)
                if (prior is not None
                        and not self.oracle.observation_target_present(semantic_id)
                        and self.oracle.private_quarters_room_visible()
                        and self.oracle.enabled('private-quarters/room/back')
                        and self.oracle.read_state().generation > prior.generation):
                    return prior
                receipt = self.oracle.click(semantic_id)
                self._private_quarters_dialogue_receipt = receipt
                return receipt
            if semantic_id in ('private-quarters/page/left', 'private-quarters/page/right'):
                return self.oracle.click_private_quarters_page(semantic_id.rsplit('/', 1)[1])
            if semantic_id == "research-menu/research":
                completed = self._research_entry_completed()
                if completed is not None:
                    return completed
            if semantic_id == 'private-quarters/room/back':
                return self.oracle.click_private_quarters_room_back()
            if semantic_id == 'private-quarters/home':
                if (not self.oracle.private_quarters_page_visible()
                        and self.oracle.main_page_visible()
                        and self.oracle.enabled('main/battle')):
                    return self.oracle.main_page_receipt()
                receipt = self.oracle.click_private_quarters_home()
                # The old page can unmount before the new main raycast settles.
                # Only ALAS' passive page scan gets this bounded transition.
                self._private_quarters_home_transition_until = time.monotonic() + 30.0
                return receipt
            if (semantic_id == 'dorm-menu/private-quarters' and self._private_quarters_entry_receipt is not None
                    and self.oracle.private_quarters_page_visible()
                    and self.oracle.enabled('private-quarters/home')
                    and self.oracle.read_state().generation > self._private_quarters_entry_receipt.generation):
                return self._private_quarters_entry_receipt
            if (semantic_id == 'main/live' and self._main_live_entry_receipt is not None
                    and self.oracle.observation_target_present('dorm-menu/dorm')
                    and self.oracle.enabled('dorm-menu/dorm')
                    and self.oracle.read_state().generation > self._main_live_entry_receipt.generation):
                return self._main_live_entry_receipt
            if (semantic_id == 'main/live' and self._minigame_context is not None
                    and self._main_live_entry_receipt is not None
                    and time.monotonic() <= self._minigame_context.passive_transition_until):
                # The panel may mount before its entry finishes its raycast
                # animation. Await that existing input's postcondition rather
                # than toggling the covered main-page button again.
                deadline = min(time.monotonic() + 5.0,
                               self._minigame_context.passive_transition_until)
                while time.monotonic() < deadline:
                    if (self.oracle.enabled('dorm-menu/academy')
                            and self.oracle.read_state().generation > self._main_live_entry_receipt.generation):
                        return self._main_live_entry_receipt
                    if self.oracle.observation_surface_present(ObservationSurface.MESSAGE_BOX):
                        break
                    time.sleep(0.1)
                raise SemanticGateClosed('live-menu academy entry did not become actionable')
            if (semantic_id == 'main/live' and self._main_live_entry_receipt is not None
                    and self._private_quarters_entry_receipt is not None
                    and self._private_quarters_entry_receipt.generation >= self._main_live_entry_receipt.generation
                    and self.oracle.private_quarters_page_visible()
                    and self.oracle.enabled('private-quarters/home')
                    and self.oracle.read_state().generation > self._private_quarters_entry_receipt.generation):
                # The same ALAS page scan can advance through the live menu
                # before reaching a fading main-page alias. Both entries have
                # completed; acknowledge arrival without another input.
                return self._private_quarters_entry_receipt
            if (semantic_id == 'research-menu/shipyard' and self._shipyard_entry_receipt is not None
                    and self.oracle.shipyard_page_visible()
                    and self.oracle.read_state().generation > self._shipyard_entry_receipt.generation):
                return self._shipyard_entry_receipt
            if (semantic_id == 'research-menu/meta' and self._meta_character_entry_receipt is not None
                    and (self.oracle.meta_character_page_visible() or self.oracle.meta_character_menu_visible())
                    and self.oracle.read_state().generation > self._meta_character_entry_receipt.generation):
                return self._meta_character_entry_receipt
            if semantic_id == 'meta/character/sync':
                return self.oracle.click_meta_character_sync()
            if semantic_id == 'main/tech':
                completed = self._main_tech_entry_completed()
                if completed is not None:
                    return completed
            if semantic_id == 'meta/current/list' and getattr(self.oracle, 'meta_dossier_assist_visible', lambda: False)():
                return self.oracle.click_meta_dossier_current()
            if semantic_id == 'meta/dossier/list':
                return self.oracle.click_meta_dossier_list()
            if (semantic_id == 'main/more' and self._main_more_entry_receipt is not None
                    and self.oracle.observation_target_present('reward/page/back')
                    and self.oracle.enabled('reward/page/back')
                    and self.oracle.read_state().generation > self._main_more_entry_receipt.generation):
                return self._main_more_entry_receipt
            if (semantic_id == 'main/more' and self._main_more_entry_receipt is not None
                    and time.monotonic() <= self._main_more_entry_until
                    and self.oracle.observation_target_present('reward/page/back')):
                state = self.oracle.read_state()
                blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                if (state.generation > self._main_more_entry_receipt.generation
                        and blockers and all(rule.blocker_id == 'loading' for rule in blockers)):
                    # The sidebar exists beneath Loading after this exact entry.
                    # Preserve ALAS polling without toggling the source twice.
                    return self._main_more_entry_receipt
            if semantic_id == "campaign-menu/exercise":
                receipt = self.oracle.click_campaign_exercise_entrance()
                self._exercise_entry_receipt = receipt
                self._exercise_entry_transition_until = time.monotonic() + 20.0
                return receipt
            if semantic_id == "campaign-menu/normal" and self._campaign_context is None:
                receipt = self.oracle.click(semantic_id)
                self._exercise_chapter_entry_transition_until = time.monotonic() + 20.0
                return receipt
            if semantic_id == "campaign-menu/archive":
                if self._data_key_context is not None:
                    target = self._award_close_target()
                    if target is not None:
                        receipt = self.oracle.click(target)
                        self._data_key_context.passive_transition_until = (
                            time.monotonic() + 60.0
                        )
                        return receipt
                context = self._campaign_context
                previous = self._campaign_archive_entry_receipt
                if (previous is not None
                        and time.monotonic() <= self._campaign_archive_entry_transition_until
                        and self.oracle.war_archives_page_visible()
                        and self.oracle.read_state().generation > previous.generation):
                    return previous
                receipt = self.oracle.click_campaign_archive_entrance()
                self._campaign_archive_entry_receipt = receipt
                self._campaign_archive_entry_transition_until = time.monotonic() + 30.0
                if context is not None:
                    context.archive_menu_entry_receipt = receipt
                return receipt
            if semantic_id == "campaign-menu/os":
                if (
                    self._operation_siren_entry_receipt is not None
                    and time.monotonic()
                    <= self._operation_siren_entry_transition_until
                ):
                    return self._operation_siren_entry_receipt
                receipt = self.oracle.click_campaign_os_entrance()
                self._operation_siren_entry_receipt = receipt
                self._operation_siren_entry_transition_until = (
                    time.monotonic() + 30.0
                )
                return receipt
            if semantic_id == "campaign-menu/event":
                receipt = self.oracle.click_campaign_event_entrance()
                self._campaign_event_entry_transition_until = time.monotonic() + 12.0
                return receipt
            if semantic_id == "event/mode/story":
                return self.oracle.click_event_story_mode()
            if semantic_id == "event/mode/battle":
                return self.oracle.click_event_battle_mode()
            if semantic_id == "os/page/back":
                return self.oracle.click_operation_siren_back()
            if semantic_id == "os/map/globe":
                receipt = self.oracle.click_operation_siren_globe()
                # The local-map hierarchy unmounts before the globe panel is
                # fully observable. Keep optional OS event probes passive only
                # across that bounded, exact navigation transition.
                self._operation_siren_entry_transition_until = (
                    time.monotonic() + 30.0
                )
                return receipt
            if semantic_id == "os/map/exit":
                return self.oracle.click_operation_siren_map_exit()
            if (
                name == "AUTO_SEARCH_REWARD"
                and self.oracle.operation_siren_world_overview_visible()
            ):
                return self.oracle.click_operation_siren_world_overview()
            if semantic_id == "os/globe/map":
                if (
                    self._operation_siren_globe_map_receipt is not None
                    and time.monotonic()
                    <= self._operation_siren_entry_transition_until
                ):
                    return self._operation_siren_globe_map_receipt
                receipt = self.oracle.click_operation_siren_globe_map()
                self._operation_siren_globe_map_receipt = receipt
                self._operation_siren_entry_transition_until = (
                    time.monotonic() + 30.0
                )
                return receipt
            if semantic_id == "os/globe/voucher":
                return self.oracle.click_operation_siren_voucher()
            if semantic_id == "os/globe/zone-enter":
                return self.oracle.click_operation_siren_globe_zone_enter()
            if semantic_id == "os/globe/zone-switch":
                return self.oracle.click_operation_siren_globe_zone_switch()
            if semantic_id.startswith("os/globe/zone-type/"):
                return self.oracle.click_operation_siren_globe_zone_type(
                    semantic_id.rsplit("/", 1)[-1].upper()
                )
            if semantic_id == "os/shop/back":
                return self.oracle.click("os/shop/back")
            if semantic_id == "os/voucher/back":
                return self.oracle.click("os/voucher/back")
            if semantic_id == "reward/meta/enter":
                previous = self._meta_entry_receipt
                if previous is not None and not self.oracle.meta_entrance_available():
                    self.oracle.meta_entrance_state()
                    if self.oracle.read_state().generation > previous.generation:
                        return previous
                receipt = self.oracle.click_meta_entrance()
                self._meta_entry_receipt = receipt
                return receipt
            if name in REWARD_RESOURCE_FIELDS:
                return self.oracle.click_reward_resource(
                    REWARD_RESOURCE_FIELDS[name]
                )
            if semantic_id == 'meta/category/back':
                return self._fresh_input_oracle().click_meta_category_back()
            if semantic_id in ("meta/current/open", "meta/dossier/open"):
                card_oracle = self._fresh_input_oracle()
                dossier_previous = self._meta_dossier_entry_receipt
                if (semantic_id == 'meta/dossier/open' and dossier_previous is not None
                        and not card_oracle.observation_target_present('meta/dossier/open')):
                    card_oracle.meta_dossier_empty_points()
                    if card_oracle.read_state().generation > dossier_previous.generation:
                        return dossier_previous
                previous = self._meta_current_entry_receipt
                if (semantic_id == 'meta/current/open' and previous is not None
                        and not card_oracle.observation_target_present('meta/current/open')):
                    try:
                        card_oracle.meta_current_empty_points()
                    except SemanticGateClosed:
                        card_oracle.meta_current_detail_state()
                    if card_oracle.read_state().generation > previous.generation:
                        return previous
                receipt = card_oracle.click_meta_card(
                    dossier=semantic_id == "meta/dossier/open"
                )
                if semantic_id == 'meta/current/open':
                    self._meta_current_entry_receipt = receipt
                else:
                    self._meta_dossier_entry_receipt = receipt
                return receipt
            if semantic_id == "meta/current/list":
                try:
                    self.oracle.meta_current_detail_state()
                except SemanticGateClosed:
                    pass
                else:
                    return self.oracle.click_meta_current_detail_list()
                return self.oracle.click_meta_current_list()
            if semantic_id == "meta/current/create":
                if self._meta_beacon_active:
                    try:
                        self.oracle.meta_dossier_empty_points(require_create=True)
                    except SemanticGateClosed:
                        pass
                    else:
                        return self.oracle.click_meta_dossier_create()
                return self._click_meta_current_create()
            if semantic_id == "meta/current/reward":
                if self._meta_beacon_active and self.oracle.meta_dossier_detail_visible():
                    return self.oracle.click_meta_dossier_reward()
                return self._fresh_input_oracle().click_meta_current_reward()
            if semantic_id == "meta/current/help":
                return self.oracle.click_meta_current_help()
            if semantic_id is not None and semantic_id.startswith("meta/help/"):
                return self.oracle.click_meta_help_control(
                    semantic_id.rsplit("/", 1)[1]
                )
            if semantic_id == "meta/assist/start":
                if self._meta_beacon_active and self.oracle.meta_dossier_detail_visible():
                    return self.oracle.click_meta_dossier_start()
                try:
                    self.oracle.meta_current_detail_state()
                except SemanticGateClosed:
                    pass
                else:
                    return self.oracle.click_meta_current_start()
                return self.click_meta_assist_entry()
            if semantic_id == "campaign-menu/daily":
                def arrived():
                    return (self._daily_entry_receipt is not None
                            and self.oracle.daily_entry_visible()
                            and self.oracle.read_state().generation > self._daily_entry_receipt.generation)
                if arrived():
                    return self._daily_entry_receipt
                before_input = self.oracle.input_dispatch_count
                try:
                    receipt = self.oracle.click_campaign_daily_entrance()
                except SemanticGateClosed:
                    # A source-frame retry may meet the newly mounted Daily page.
                    # Only acknowledge a real earlier entry and no new input.
                    if self.oracle.input_dispatch_count == before_input and arrived():
                        return self._daily_entry_receipt
                    raise
                self._daily_entry_receipt = receipt
                self._daily_entry_transition_until = time.monotonic() + 12.0
                return receipt
            if semantic_id == "daily/precombat/start" and (
                    self._exercise_pending or self._exercise_execution_active):
                return self.click_exercise_precombat_start()
            if semantic_id == "daily/precombat/start":
                return self.click_daily_precombat_start()
            if semantic_id == "exercise/opponent/start":
                receipt = self.oracle.click(semantic_id)
                self._exercise_pending = True
                return receipt
            if semantic_id == "exercise/opponent/refresh":
                return self._dispatch_mutation(
                    "exercise.refresh", lambda: self.oracle.click(semantic_id)
                )
            if semantic_id in ("daily/next", "daily/prev"):
                return self.oracle.click_daily_control(semantic_id)
            if (
                self._dorm_context is not None
                and semantic_id in ("main/live", "dorm-menu/dorm", "dorm/page/back")
            ):
                cached = self._dorm_context.navigation_receipts.get(semantic_id)
                if (
                    cached is not None
                    and time.monotonic()
                    <= self._dorm_context.passive_transition_until
                ):
                    return cached
            if self._build_context is not None and semantic_id == "main/build":
                entry = self._build_context.entry_receipt
                if (
                    entry is not None
                    and time.monotonic() <= self._build_context.passive_transition_until
                    and self.oracle.exists("build/page/back")
                    and self.oracle.read_state().generation > entry.generation
                ):
                    return entry
                try:
                    self._build_context.coins_owned = self.oracle.main_gold()
                except SemanticGateClosed as exc:
                    entry_unavailable = (
                        str(exc) == "main build entry identity is not proven"
                        or (isinstance(exc, SemanticTargetMissing)
                            and str(exc) == "semantic target is absent: main/build"))
                    if (not entry_unavailable
                            or entry is None
                            or time.monotonic() > self._build_context.passive_transition_until):
                        raise
                    # ALAS can repeat the entry while Build replaces main.
                    # Reuse only its real prior receipt after the typed
                    # destination becomes actionable; never submit another tap.
                    deadline = time.monotonic() + 5.0
                    while True:
                        if (self.oracle.exists("build/page/back")
                                and self.oracle.enabled("build/page/back")
                                and self.oracle.read_state().generation > entry.generation):
                            return entry
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.25)
            if (
                self._research_context is not None
                and semantic_id.startswith("research/project/")
            ):
                slot = int(semantic_id.rsplit("/", 1)[1])
                projects = self.oracle.research_projects()
                matches = tuple(project for project in projects if project.slot == slot)
                if len(matches) != 1:
                    raise SemanticGateClosed("research project slot identity is ambiguous")
                project = matches[0]
                project_identity = {"expected_code": project.code}
                if getattr(project, "series", None) is not None:
                    project_identity["expected_series"] = project.series
                if project.status == ResearchProjectStatus.FINISHED:
                    receipt = self._dispatch_mutation(
                        "research.reward",
                        lambda: self.oracle.click_research_project(
                            slot, **project_identity
                        ),
                    )
                    self._research_context.reward_receipts.append(receipt)
                    self._research_context.selected_slot = None
                    self._research_context.selected_code = None
                    self._research_context.selected_series = None
                    self._research_context.selected_status = None
                    self._research_context.start_receipt = None
                    self._research_context.start_confirm_receipt = None
                    self._research_context.pending_resource_id = None
                    self._research_context.pending_resource_required = None
                    self._research_context.pending_resource_costs = ()
                    self._research_context.last_queue_state = None
                    self._research_context.last_projects = None
                    self._research_context.queue_add_receipt = None
                    self._research_context.queue_confirm_receipt = None
                    self._research_context.queue_add_requires_start_grant = False
                    return receipt
                receipt = self.oracle.click_research_project(
                    slot, **project_identity
                )
                self._research_context.selected_slot = slot
                self._research_context.selected_code = project.code
                self._research_context.selected_series = getattr(project, "series", None)
                self._research_context.selected_status = project.status
                self._research_context.start_receipt = None
                self._research_context.start_confirm_receipt = None
                self._research_context.pending_resource_id = None
                self._research_context.pending_resource_required = None
                self._research_context.pending_resource_costs = ()
                self._research_context.queue_add_receipt = None
                self._research_context.queue_confirm_receipt = None
                self._research_context.queue_add_requires_start_grant = False
                return receipt
            if self._mission_context is not None:
                if (
                    semantic_id == "main/more"
                    and self._mission_context.summary_entry_receipt is not None
                ):
                    previous = self._mission_context.summary_entry_receipt
                    deadline = time.monotonic() + 5.0
                    while time.monotonic() < deadline:
                        state = self._live_oracle.read_state()
                        blockers = self._live_oracle._blocking_rules(state, 'reward/page/back')
                        if any(rule.blocker_id != 'loading' for rule in blockers):
                            raise SemanticGateClosed('reward sidebar entry is obscured')
                        if (state.generation > previous.generation and not blockers
                                and self._live_oracle.reward_sidebar_entry_ready(state)):
                            # The Mellow sidebar root has no generic input
                            # listener; its exact root and actionable child
                            # prove the destination without another toggle.
                            # Reuse this validated sample instead of fetching
                            # separate live states for its root and child.
                            return previous
                        time.sleep(0.2)
                    raise SemanticGateClosed('reward sidebar entry postcondition was not observed')
                if (
                    semantic_id == "main/task"
                    and self._mission_context.entry_receipt is not None
                ):
                    return self._mission_context.entry_receipt
            if self._commission_context is not None and semantic_id in (
                "reward/commission/finish",
                "reward/tactical/finish",
            ):
                context = self._commission_context
                if semantic_id == "reward/commission/finish":
                    if context.flow_kind != "commission":
                        raise SemanticGateClosed(
                            "commission reward input used outside commission flow"
                        )
                    if getattr(self._fresh_input_oracle(), 'commission_reward_oil_maxed', lambda: False)():
                        raise AlasSemanticActionDeferred(
                            'commission.reward: client oil capacity rejects the reward; '
                            'normal oil consumption and native retry are required; no input submitted')
                    previous_cycle = None
                    if context.reward_claim_receipt is not None:
                        if not self._commission_next_reward_cycle_ready():
                            return context.reward_claim_receipt
                        previous_cycle = (context.reward_claim_receipt,
                            tuple(context.reward_close_receipts), context.reward_detected_count)
                    # Refresh the counter so the postcondition covers every
                    # observed row claimed by this single budgeted input.
                    if not self.commission_reward_pending():
                        raise SemanticGateClosed("commission reward requires finished rows")
                    receipt = self._dispatch_mutation(
                        "commission.reward",
                        lambda: self.oracle.click(semantic_id),
                    )
                    if previous_cycle is not None:
                        context.reward_prior_claims.append(previous_cycle)
                        context.reward_close_receipts.clear()
                        context.ship_exp_observation_generation = None
                        context.reward_proof = None
                    context.reward_claim_receipt = receipt
                    return self._record_mission_transition(receipt)
                if context.flow_kind != "tactical":
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                if context.tactical_reward_receipt is not None:
                    return context.tactical_reward_receipt
                context.tactical_reward_receipt = self._record_mission_transition(
                    self._dispatch_mutation(
                        "tactical.reward", lambda: self.oracle.click(semantic_id)
                    )
                )
                return context.tactical_reward_receipt
            if (
                self._research_context is not None
                and semantic_id in (
                    "main/tech",
                    "research-menu/research",
                    "research-menu/page/back",
                    "research/page/back",
                )
            ):
                cached = self._research_context.navigation_receipts.get(semantic_id)
                if (
                    cached is not None
                    and time.monotonic()
                    <= self._research_context.passive_transition_until
                ):
                    return cached
            if (
                semantic_id == "main/battle"
                and self._main_battle_transition_receipt is not None
                and self._main_battle_destination_visible()
            ):
                # ui_goto can still classify the fading main underlay after
                # the first exact battle-menu click has already mounted the
                # CampaignMenu, chapter or retained map. Reuse that receipt so the
                # original ALAS loop can observe its destination; never issue
                # the same underlay click through the new top raycast.
                return self._main_battle_transition_receipt
            if (
                semantic_id == "main/shop"
                and self._main_shop_transition_receipt is not None
                and time.monotonic() <= self._main_shop_transition_until
                and self._main_shop_destination_visible()
            ):
                # ALAS may still classify the departing main alias after the
                # exact Shop shell has mounted. The first click already owns
                # this edge; let ui_goto observe its destination.
                return self._main_shop_transition_receipt
            if (semantic_id == "main/dock"
                    and self._main_dock_transition_receipt is not None
                    and time.monotonic() <= self._main_dock_transition_until):
                state = self.oracle.read_state()
                blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                dock_mounted = any(
                    button.active_in_hierarchy
                    and button.path == 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button'
                    for button in state.buttons)
                if (state.generation > self._main_dock_transition_receipt.generation
                        and (dock_mounted
                             or time.monotonic() <= self._main_dock_transition_until - 10.0
                             or (blockers and all(
                            rule.blocker_id == 'loading' for rule in blockers)))):
                    return self._main_dock_transition_receipt
            if (semantic_id == "main/mail" and self._mail_context is not None
                    and self._mail_context.entry_receipt is not None
                    and time.monotonic() <= self._mail_context.passive_transition_until):
                state = self.oracle.read_state()
                blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                if (state.generation > self._mail_context.entry_receipt.generation
                        and not any(rule.blocker_id not in ('loading', 'mail-page')
                                    for rule in blockers)):
                    return self._mail_context.entry_receipt
            if (semantic_id == "main/guild"
                    and self._main_guild_entry_receipt is not None
                    and time.monotonic() <= self._main_guild_entry_until):
                state = self.oracle.read_state()
                blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                if (state.generation > self._main_guild_entry_receipt.generation
                        and ((blockers and all(rule.blocker_id == 'loading' for rule in blockers))
                             or not self.oracle.enabled("main/guild"))
                        and not any(rule.blocker_id not in ('loading', 'guild-page')
                                    for rule in blockers)):
                    # This accepted entry owns its Loading transition. A
                    # second independent source enabled read can straddle
                    # publication and accidentally retry the covered source.
                    return self._main_guild_entry_receipt
            if semantic_id in ("os/order/scan", "os/order/submarine"):
                order_kind = semantic_id.rsplit("/", 1)[1]
                for attempt in range(12):
                    try:
                        receipt = self.oracle.click_operation_siren_order(
                            order_kind
                        )
                        break
                    except SemanticGateClosed as exc:
                        if (
                            str(exc)
                            != "operation siren order snapshots are not coherent"
                            or attempt == 11
                        ):
                            raise
                        time.sleep(0.25)
                self._operation_siren_pending_order = semantic_id.rsplit("/", 1)[1]
            elif semantic_id == "os/order/back":
                receipt = self.oracle.click_operation_siren_order_back()
                self._operation_siren_order_entry_receipt = None
            else:
                before_input = getattr(self.oracle, 'input_dispatch_count', 0)
                try:
                    if semantic_id in ('main/tech', 'main/more', 'main/live', 'main/mail', 'main/dock', 'main/battle', 'main/storage'):
                        receipt = self._click_main_ready(semantic_id)
                    elif semantic_id in ('research-menu/research', 'academy/munitions'):
                        # Navigation admission can outlive the offered frame.
                        # Reuse the existing fresh immutable input acquisition
                        # instead of splitting this proof across live reads.
                        receipt = self._fresh_input_oracle().click(semantic_id)
                    else:
                        receipt = self.oracle.click(semantic_id)
                except SemanticTargetMissing:
                    if (semantic_id == 'research-menu/page/back'
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        completed = self._research_menu_return_completed()
                        if completed is not None:
                            return completed
                    if (semantic_id == "research-menu/research"
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        completed = self._research_entry_completed()
                        if completed is not None:
                            return completed
                    if (semantic_id == 'main/tech'
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        completed = self._main_tech_entry_completed(wait=True)
                        if completed is not None:
                            return completed
                    if (semantic_id == 'main/battle'
                            and self._main_battle_transition_receipt is not None
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input
                            and self._main_battle_destination_visible()):
                        return self._main_battle_transition_receipt
                    if (semantic_id == 'main/shop'
                            and self._main_shop_transition_receipt is not None
                            and time.monotonic() <= self._main_shop_transition_until
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input
                            and self._main_shop_destination_visible()):
                        return self._main_shop_transition_receipt
                    raise
                except SemanticGateClosed as exc:
                    if semantic_id == 'reward/tactical/go':
                        prior = self._accepted_tactical_entry_loading(exc, before_input)
                        if prior is not None:
                            return prior
                    if (semantic_id == 'main/live'
                            and str(exc) == 'semantic target is not actionable'
                            and self._main_live_entry_receipt is not None
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        # The main theme checks can race the already dispatched
                        # live-area entry. Complete only that exact edge after
                        # the real destination is actionable; do not tap again.
                        deadline = time.monotonic() + 12.0
                        while time.monotonic() < deadline:
                            state = self.oracle.read_state()
                            if (state.generation > self._main_live_entry_receipt.generation
                                    and self.oracle.observation_target_present('dorm-menu/dorm')
                                    and self.oracle.enabled('dorm-menu/dorm')
                                    and not self.oracle.enabled('main/live')):
                                return self._main_live_entry_receipt
                            time.sleep(0.2)
                        raise
                    if (semantic_id == 'main/battle'
                            and str(exc) == 'semantic target is not actionable'
                            and self._main_battle_transition_receipt is not None
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        # The destination can mount between the earlier probe
                        # and the input check. Its fresh proof completes the
                        # already owned edge without a second input.
                        deadline = time.monotonic() + 12.0
                        while time.monotonic() < deadline:
                            if self._main_battle_destination_visible():
                                return self._main_battle_transition_receipt
                            time.sleep(0.2)
                        raise
                    if (semantic_id == 'main/tech'
                            and str(exc) == 'semantic target is not actionable'
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        completed = self._main_tech_entry_completed(wait=True)
                        if completed is not None:
                            return completed
                    if (semantic_id == 'main/shop'
                            and str(exc) == 'semantic target is not actionable'
                            and self._main_shop_transition_receipt is not None
                            and time.monotonic() <= self._main_shop_transition_until
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        state = self.oracle.read_state()
                        blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                        if (state.generation > self._main_shop_transition_receipt.generation
                                and blockers
                                and all(rule.blocker_id == 'loading' for rule in blockers)):
                            return self._main_shop_transition_receipt
                    if (semantic_id == 'main/more'
                            and str(exc) == 'semantic target is not actionable'
                            and self._main_more_entry_receipt is not None
                            and time.monotonic() <= self._main_more_entry_until
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        state = self.oracle.read_state()
                        blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                        if (state.generation > self._main_more_entry_receipt.generation
                                and not any(rule.blocker_id not in ('reward-page', 'loading')
                                            for rule in blockers)):
                            # ALAS can reissue the same main sidebar edge
                            # while CommissionInfoUI mounts. The first input
                            # already owns it; no second input is authorized.
                            return self._main_more_entry_receipt
                    raise
            if semantic_id == 'main/more':
                self._main_more_entry_receipt = receipt
                self._main_more_entry_until = time.monotonic() + 8.0
            if semantic_id == 'research-menu/shipyard':
                self._shipyard_entry_receipt = receipt
            if semantic_id == 'research-menu/meta':
                self._meta_character_entry_receipt = receipt
            if semantic_id == 'main/tech':
                self._main_tech_entry_receipt = receipt
            if semantic_id == 'main/storage':
                self._main_storage_entry_receipt = receipt
            if semantic_id == 'os/map/order':
                self._operation_siren_order_entry_receipt = receipt
            if semantic_id == 'main/live':
                self._main_live_entry_receipt = receipt
                if self._minigame_context is not None:
                    self._minigame_context.passive_transition_until = time.monotonic() + 20.0
            if semantic_id == 'main/build' and self._build_context is not None:
                self._build_context.entry_receipt = receipt
            if semantic_id == 'dorm-menu/private-quarters':
                self._private_quarters_entry_receipt = receipt
                self._private_quarters_entry_transition_until = time.monotonic() + 30.0
            if semantic_id == "main/battle":
                self._main_battle_transition_receipt = receipt
            if semantic_id == "main/shop":
                self._main_shop_transition_receipt = receipt
                self._main_shop_transition_until = time.monotonic() + 20.0
            if semantic_id == "main/dock":
                self._main_dock_transition_receipt = receipt
                self._main_dock_transition_until = time.monotonic() + 12.0
            if semantic_id == "main/guild":
                self._main_guild_entry_receipt = receipt
                self._main_guild_entry_until = time.monotonic() + 12.0
            if semantic_id == "os/map/auto-search/off":
                self._operation_siren_auto_search_transition_until = (
                    time.monotonic() + 30.0
                )
                self._operation_siren_auto_search_active = True
                self._operation_siren_startup_search_provisional = False
                self._operation_siren_auto_search_completed_empty = False
            if semantic_id == "main/task" and self._mission_context is not None:
                self._mission_context.entry_clicked = True
                self._mission_context.entry_receipt = receipt
            if semantic_id == "main/more" and self._mission_context is not None:
                self._mission_context.summary_entry_clicked = True
                self._mission_context.summary_entry_receipt = receipt
            if semantic_id == "main/mail" and self._mail_context is not None:
                self._mail_context.entry_clicked = True
                self._mail_context.entry_receipt = receipt
                self._mail_context.passive_transition_until = time.monotonic() + 12.0
            if (
                self._minigame_context is not None
                and semantic_id
                in (
                    "main/live",
                    "dorm-menu/academy",
                    "academy/game-room",
                    "game-room/back",
                    "game-room/home",
                )
            ):
                self._minigame_context.passive_transition_until = (
                    time.monotonic() + 20.0
                )
            if (semantic_id == 'reward/tactical/go'
                    and self._commission_context is not None
                    and self._commission_context.flow_kind == 'tactical'):
                self._commission_context.tactical_entry_receipt = receipt
                self._commission_context.tactical_entry_input_count = self.oracle.input_dispatch_count
            receipt = self._record_mission_transition(receipt)
            if semantic_id == "dorm/page/back":
                self._dorm_return_transition_until = time.monotonic() + 8.0
            if (
                self._research_context is not None
                and semantic_id in (
                    "main/tech",
                    "research-menu/research",
                    "research-menu/page/back",
                    "research/page/back",
                )
            ):
                self._research_context.navigation_receipts[semantic_id] = receipt
            if (
                self._dorm_context is not None
                and semantic_id in ("main/live", "dorm-menu/dorm", "dorm/page/back")
            ):
                self._dorm_context.navigation_receipts[semantic_id] = receipt
            return receipt
        return UNHANDLED

    def _click_mission(self, name):
        context = self._require_mission_context()
        if name == "MISSION_MULTI":
            state = self._stable_mission_state()
            if (
                state is None
                or state.disposition != MissionDisposition.CLAIMABLE_ALL
                or state.claim_all is None
            ):
                raise SemanticGateClosed("stable mission claim-all is absent")
            receipt = self._dispatch_mutation(
                "mission.claim",
                lambda: self.oracle.click("task/claim/all"),
            )
            context.last_signature = None
            context.last_generation = -1
            context.stable_generations = 0
            context.stable_state = None
            return receipt
        if name == "MISSION_SINGLE":
            state = self._stable_mission_state()
            if (
                state is None
                or state.disposition != MissionDisposition.CLAIMABLE_ROW
                or len(state.claim_rows) != 1
            ):
                raise SemanticGateClosed("stable mission claim row is absent")
            expected_path = state.claim_rows[0].path
            receipt = self._dispatch_mutation(
                "mission.claim",
                lambda: self.oracle.click_mission_claim_row(expected_path),
            )
            context.last_signature = None
            context.last_generation = -1
            context.stable_generations = 0
            context.stable_state = None
            return receipt
        if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
            target = self._award_close_target()
            if target is None:
                if self._mission_award_close_completed():
                    raise SemanticTargetMissing('mission reward popup already closed by this flow')
                if (self.oracle.enabled("task/page/back")
                        and not self.oracle.exists("reward/award-info/close")
                        and not self.oracle.exists("reward/award-info1/close")):
                    raise SemanticTargetMissing("mission reward popup has disappeared")
                raise SemanticGateClosed("reviewed reward popup close is absent")
            receipt = self.oracle.click(target)
            context.award_close_receipt = receipt
            return receipt
        if name == "GET_SHIP":
            if not self.oracle.new_ship_reward_visible():
                if self._mission_award_close_completed(('reward/new-ship/continue',)):
                    raise SemanticTargetMissing('mission ship reward already closed by this flow')
                raise SemanticGateClosed("reviewed ship reward popup is absent")
            receipt = self.oracle.click("reward/new-ship/continue")
            context.award_close_receipt = receipt
            return receipt
        raise AlasSemanticUnmapped(
            "ALAS resource is not semantically mapped for input: {0}".format(name)
        )
        return UNHANDLED
