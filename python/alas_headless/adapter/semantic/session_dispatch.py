"""Session dispatch for the typed ALAS boundary."""

from __future__ import annotations

from typing import Optional, Union
from ...oracle.private_quarters import PrivateQuartersPhysicsReceipt

import time
import re
from dataclasses import replace
from typing import Any, Tuple
from ...adapter.flows import LOGIN_ACTION_TARGETS
from ...adapter import StaleFrameError
from ...alas_combat_state_replay import (
    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES,
    ALAS_COMBAT_RESOURCE_ACTION_TARGETS,
)
from ...semantic_oracle import ActionReceipt, SemanticGateClosed, SemanticTargetMissing
from ...oracle.errors import SemanticInputTargetMissing
from ...oracle.surfaces import ObservationSurface
from .adapter import AlasSemanticAdapter
from .contracts import AlasSemanticUnmapped
from .resources import (
    BATTLE_PASS_VIRTUAL_RESOURCES,
    BUILD_POOL_NAVBAR_PATTERN,
    BUILD_SIDE_NAVBAR_PATTERN,
    BUILD_VIRTUAL_RESOURCES,
    CAMPAIGN_CLICK_RESOURCES,
    CAMPAIGN_FLEET_BAR_PATTERN,
    COMMISSION_CLICK_RESOURCES,
    COMMISSION_ROW_PATTERN,
    DATA_KEY_VIRTUAL_RESOURCES,
    DEFAULT_ALAS_BUTTON_TARGETS,
    DORM_VIRTUAL_RESOURCES,
    MAIL_CLICK_RESOURCES,
    MINIGAME_VIRTUAL_RESOURCES,
    MISSION_CLICK_RESOURCES,
    MISSION_NAVBAR_PATTERN,
    RESEARCH_CLICK_RESOURCES,
    SUPPLY_PACK_VIRTUAL_RESOURCES,
    TACTICAL_VIRTUAL_RESOURCES,
    UI_PAGE_CHECK_RESOURCES,
)


class SessionDispatchPorts:
    """Session dispatch on the shared immutable frame."""

    def _meta_assist_result_return_observation(self, button: Any) -> bool:
        self.refresh_frame()
        adapter = self.open()
        oracle = adapter._frame_or_live_observation_oracle()
        state = oracle.read_state()
        if any(b.active_in_hierarchy and b.path ==
               'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
               for b in state.buttons):
            # No action or completion while the result page unloads. ALAS'
            # existing combat loop owns the next screenshot and timeout.
            return False
        if adapter.meta_beacon_active():
            if not oracle.meta_page_visible():
                raise SemanticGateClosed('META result return page is not reviewed')
        else:
            oracle.meta_assist_state()
        adapter._operation_siren_combat_active = False
        return adapter.appear(button)

    def appear(self, button: Any) -> bool:
        name = AlasSemanticAdapter._button_name(button)
        adapter = self.open()
        clock = getattr(self, '_frame_clock', None)
        if clock is not None:
            try:
                clock.borrow()
            except StaleFrameError:
                # ALAS may skip its first screenshot after a navigation tap.
                # That input invalidated our frame; establish one new semantic
                # boundary before the page sweep instead of polling live state
                # separately for every candidate. Valid frames remain frozen.
                self.refresh_frame()
        if name in ('GUILD_POPUP_CONFIRM', 'GUILD_POPUP_CANCEL'):
            oracle = adapter._frame_or_live_observation_oracle()
            if oracle.observation_target_present('overlay/guild-message/close'):
                # The reviewed global notice can mount after combat returns
                # to its map. Its existing owner precedes optional combat
                # selectors so original InfoHandler can dismiss it.
                return adapter.appear(button)
        if name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'):
            oracle = adapter._frame_or_live_observation_oracle()
            pending = getattr(self, '_combat_reward_close_pending', None)
            if pending is not None:
                targets = ('reward/award-info/close', 'reward/award-info1/close')
                state = oracle.read_state()
                source_present = any(
                    b.path == pending.path and b.active_in_hierarchy
                    for b in state.buttons)
                if (source_present
                        and time.monotonic() <= self._combat_result_transition_until
                        and any(oracle.enabled(target) for target in targets)):
                    # A committed close can leave AwardInfo mounted in the
                    # next screenshot. Let the original result loop observe
                    # its disappearance before offering that same close again.
                    # Direct input still needs the full fresh action proof.
                    return False
                self._combat_reward_close_pending = None
            if (oracle.award_info_page_visible()
                    and getattr(oracle, 'reward_item_info_visible', lambda: False)()):
                # The exact item description may remain over a reward across
                # task changes. ALAS' existing reward handler owns dismissal.
                return name == 'GET_ITEMS_1'
        if name in ('RETIRE_APPEAR_1', 'RETIRE_APPEAR_2', 'RETIRE_APPEAR_3'):
            # The shared dock modal must precede combat defensive probes in
            # both campaign and OS. Its dedicated parser proves all choices.
            if adapter.dock_full_recovery_owned():
                return adapter.appear(button)
        if name.startswith('PRIVATE_QUARTERS_') or (
                name == 'POPUP_CANCEL_WHITE'
                and time.monotonic() <= getattr(adapter, '_private_quarters_transition_until', 0.0)):
            # Room observations belong to ALAS' screenshot frame. An unrelated
            # live network probe must not split it while Unity loads the room.
            return adapter.appear(button)
        if name == 'GET_MISSION' and adapter._campaign_context is not None:
            oracle = adapter._frame_or_live_observation_oracle()
            if oracle._campaign_urgent_notice_matches(oracle.read_state()):
                return True
        if (name in ('POPUP_CONFIRM', 'POPUP_CANCEL') and getattr(adapter, '_campaign_context', None) is not None
                and adapter._campaign_context.submarine_move_confirm is not None):
            return adapter.campaign_submarine_move_popup_appear(name)
        if name in (
            'SUBMARINE_READY', 'SUBMARINE_CALLED',
            'SUBMARINE_AVAILABLE_CHECK_1', 'SUBMARINE_AVAILABLE_CHECK_2') and adapter._campaign_context is not None:
            return adapter.campaign_submarine_call_appear(name)
        retirement_return = getattr(self, '_retirement_return_receipt', None)
        if retirement_return is not None and name in ('IN_RETIREMENT_CHECK', 'DOCK_CHECK'):
            state = adapter._frame_or_live_observation_oracle().read_state()
            still_dock = state.generation <= retirement_return.generation or any(
                b.active_in_hierarchy and ('/DockyardUI(Clone)/' in b.path
                    or b.path.endswith('/blur_panel/select_panel/quick_select')) for b in state.buttons)
            if not still_dock and name == 'DOCK_CHECK':
                self._retirement_return_receipt = None
            return still_dock
        if name == "IN_RETIREMENT_CHECK":
            return adapter._frame_or_live_observation_oracle().retirement_selection_visible()
        if name == "DOCK_CHECK" and adapter._frame_or_live_observation_oracle().retirement_selection_visible():
            return True
        if name == 'BACK_ARROW' and adapter._frame_or_live_observation_oracle().retirement_selection_visible():
            return adapter._frame_or_live_observation_oracle().retirement_page_back_available()
        if name in ('GAME_TIPS', 'GAME_TIPS3', 'GAME_TIPS4'):
            oracle = adapter._frame_or_live_observation_oracle()
            if oracle.retirement_selection_visible() and oracle.retirement_page_back_available():
                # Original Retirement probes game tips before recognizing its
                # selection. An unobscured, idle typed selection proves these
                # absent without consulting unrelated Exercise/daily pages.
                return False
        sample_use = getattr(self, '_opsi_sample_use', None)
        if sample_use is not None:
            adapter._package_gate()
            result = sample_use.appear(adapter._frame_or_live_observation_oracle(), name)
            if result is not None:
                return result
        if adapter._login_flow.active:
            # Startup/login owns its own bounded stale-frame handling and
            # exact popup inventory. Do not run unrelated daily-combat probes
            # first while Unity is still mounting the main scene.
            return adapter.appear(button)
        loading_oracle = adapter._frame_or_live_observation_oracle()
        if getattr(loading_oracle, 'daily_battle_loading_visible', lambda: False)():
            # CombatLoadUI has no actionable controls. As for the exact
            # CombatUI below, native popup/page probes are absent here; the
            # separate combat_is_loading observation owns the positive state.
            return False
        if adapter._mail_context is not None:
            # MailMgrMsgboxUI is a legitimate overlay above MailUI.  Let the
            # mail flow's own virtual-resource handlers classify it before
            # generic reward/result probes apply unrelated blocker rules.
            return adapter.appear(button)
        if adapter._minigame_context is not None:
            # GameHallUI legitimately sits under its ticket-limit Msgbox and
            # list overlay. Let the minigame context classify those before
            # generic reward/combat probes apply unrelated blocker rules.
            return adapter.appear(button)
        if getattr(adapter, "_build_context", None) is not None:
            # Construction results reuse generic reward controls, but
            # GET_ITEMS_SHIP_1 is a build-owned acknowledgement.  Delegate it
            # before the generic AwardInfo fallback aliases only GET_ITEMS_1.
            return adapter.appear(button)
        observation_oracle = adapter._frame_or_live_observation_oracle()
        if name in ('AUTOMATION_CONFIRM_CHECK', 'AUTOMATION_CONFIRM') and (
                adapter._meta_assist_active or adapter.meta_beacon_active()
                or adapter.daily_execution_active()
                or adapter.operation_siren_combat_committed()
                or getattr(adapter, 'campaign_auto_search_owned', lambda: False)()):
            return observation_oracle.combat_automation_info_visible()
        if observation_oracle.enabled("overlay/network-reconnect/confirm"):
            # NetworkDown is a global exact overlay and may mount over any
            # owned page. Observe it in ALAS' current screenshot frame; input
            # revalidates the current target independently. Expose
            # only the reviewed reconnect pair before asking any covered page
            # reader to classify its underlay; the original ALAS popup handler
            # remains the owner of the retry.
            if name == "POPUP_CONFIRM":
                return True
            if name == "POPUP_CANCEL":
                return observation_oracle.enabled(
                    "overlay/network-reconnect/cancel"
                )
            return False
        if adapter._campaign_context is not None and name in ("MAP_AMBUSH_EVADE", "MAP_AMBUSH_ATTACK"):
            return adapter.appear(button)
        if adapter._campaign_context is not None and name in (
            "EMERGENCY_REPAIR_AVAILABLE", "EMERGENCY_REPAIR_CONFIRM"
        ):
            # After one battle the broad combat observer still owns defensive
            # queries. The repair panel is a Campaign preparation surface;
            # its exact typed port must own these two probes instead.
            return adapter.appear(button)
        if (
            name == "GET_SHIP"
            and (adapter._meta_assist_active or adapter.meta_beacon_active()
                 or (adapter._campaign_context is not None and adapter.campaign_combat_committed()))
        ):
            # NewShipUI is a generic acquisition page; its identity and input
            # do not depend on which event stage produced the drop.  Keep the
            # original ALAS handler in charge and expose only its GET_SHIP
            # observation when the typed full-screen continue layer is the
            # exact top raycast above coherent ship-name/type/dialogue text.
            return adapter.oracle.new_ship_reward_visible()
        if (
            name in ("CAMPAIGN_CHECK", "AUTO_SEARCH_MENU_EXIT")
            and adapter._campaign_context is not None
            and adapter.campaign_combat_committed()
        ):
            if name == 'AUTO_SEARCH_MENU_EXIT' and adapter._campaign_context.manual_result_exit_receipt is not None:
                # The preceding exit may still be visible in the closing
                # animation frame. Wait for the chapter, never submit it twice.
                return False
            # Both markers are part of the broad defensive combat query set,
            # but after the boss result it must be decided by the strict
            # chapter-page identity in the campaign adapter.  Otherwise the
            # combat observer's empty visible-resource set masks the restored
            # stage page forever.
            return adapter.appear(button)
        result_receipt = getattr(self, '_combat_last_result_receipt', None)
        if (result_receipt is not None
                and (getattr(adapter, '_meta_beacon_active', False)
                     or getattr(adapter, '_meta_assist_active', False))
                and adapter.operation_siren_combat_committed()
                and observation_oracle.read_state().generation > result_receipt.generation
                and not observation_oracle.daily_battle_result_visible()
                and not observation_oracle.daily_combat_visible()
                and observation_oracle.meta_page_visible()):
            # The accepted result has returned to a reviewed META page.
            # Release the old combat observation owner before probing optional
            # combat controls; ALAS still decides its expected_end and next step.
            adapter._operation_siren_combat_active = False
            self._combat_last_result_receipt = None
            self._combat_result_transition_until = 0.0
        if getattr(
            adapter, "operation_siren_combat_committed", lambda: False
        )() and getattr(self, '_combat_last_result_receipt', None) is not None:
            adapter.complete_operation_siren_combat_if_map_restored()
        opsi_result_owner = bool(
            not (getattr(adapter, '_meta_beacon_active', False)
                 or getattr(adapter, '_meta_assist_active', False))
            and (getattr(adapter, "operation_siren_combat_committed", lambda: False)()
                 or (getattr(adapter, '_operation_siren_auto_search_active', False)
                     and not getattr(adapter, '_operation_siren_startup_search_provisional', False)))
        )
        if (
            opsi_result_owner
            and observation_oracle.operation_siren_battle_result_visible()
        ):
            # Native auto-search fights have no manually committed boss cell.
            # Their accepted search still owns the exact VICTORY/DEFEAT page;
            # expose its grade to ALAS' existing failure/result handlers.
            grade = observation_oracle.operation_siren_battle_result_grade()
            observed = (
                "BATTLE_STATUS_S" if grade == "VICTORY" else "BATTLE_STATUS_D"
            )
            self._combat_result_observation = (observed, time.monotonic())
            return name == observed
        if (opsi_result_owner and getattr(observation_oracle,
                'operation_siren_battle_statistics_visible', lambda: False)()):
            if name not in ('EXP_INFO_S', 'EXP_INFO_A', 'EXP_INFO_B', 'EXP_INFO_C', 'EXP_INFO_D'):
                # The exact result layer hides unrelated map/combat probes.
                # Its grade is consumed only by the native EXP_INFO handler;
                # an icon mounting between frames must not gate a reward probe.
                return False
            grade = getattr(observation_oracle,
                            'operation_siren_battle_statistics_grade', lambda: None)()
            if grade is not None:
                # OS auto-search explicitly handles EXP_INFO_C/D after a
                # failed fight. The retained CombatUI and the campaign's old
                # EXP_INFO_B selector must not mask the native statistics grade.
                return name == 'EXP_INFO_' + grade
            return False
        result_owner_active = bool(
            getattr(adapter, "daily_execution_active", lambda: False)()
            or getattr(adapter, "current_raid_result_active", lambda: False)()
            or adapter.campaign_combat_committed()
            or getattr(
                adapter, "operation_siren_combat_committed", lambda: False
            )()
            or getattr(adapter, "_exercise_execution_active", False)
        )
        if result_owner_active and observation_oracle.daily_battle_result_visible():
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and time.monotonic() <= self._combat_result_transition_until
            ):
                return False
            if name == "BATTLE_STATUS_S":
                self._combat_result_observation = (name, time.monotonic())
                return True
            return False
        if (
            getattr(adapter, "_exercise_execution_active", False)
            and adapter.oracle.award_info_page_visible()
        ):
            return name == "GET_ITEMS_1"
        if observation_oracle.enabled("reward/award-info/close"):
            return name == "GET_ITEMS_1"
        combat_oracle = adapter._frame_or_live_observation_oracle()
        if (
            combat_oracle.observation_surface_present(ObservationSurface.COMBAT)
            and combat_oracle.daily_combat_visible()
        ):
            if getattr(adapter, "campaign_auto_search_owned", lambda: False)():
                if self._official_auto_search_combat_state(adapter) != (True, True):
                    return False
                if name in ("AUTOMATION_ON", "AUTOMATION_OFF", "COMBAT_AUTO",
                            "COMBAT_AUTO_133", "COMBAT_AUTO_150"):
                    state = combat_oracle.campaign_official_combat_auto_state()
                    if state is None:
                        return False
                    enabled = state[1]
                    if name in ("AUTOMATION_ON", "AUTOMATION_OFF"):
                        return enabled == (name == "AUTOMATION_ON")
                    # Native CombatAuto probes its joystick aliases, then
                    # owns COMBAT_AUTO_SWITCH. Observe the actual toggle;
                    # a CombatUI root alone does not prove auto is enabled.
                    return not enabled
            self._daily_combat_seen_at = time.monotonic()
            if name == "AUTOMATION_ON":
                return True
            # Combat preparation/status loops probe many optional pixel-only
            # popups. The exact live CombatUI root proves those are absent.
            return False
        if (
            name in ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            try:
                visible = name in self._live_combat_visible()
                if visible and name in ("AUTOMATION_OFF", "AUTOMATION_ON"):
                    self._combat_automation_source = name
                if visible and name == "BATTLE_STATUS_S":
                    self._combat_result_observation = (name, time.monotonic())
                return visible
            except SemanticGateClosed as exc:
                if ((adapter._meta_assist_active or (
                        adapter.meta_beacon_active()
                        and self._combat_last_result_receipt is not None
                        and time.monotonic() <= self._combat_result_transition_until))
                        and str(exc).startswith(
                        'combat action control is not exact top-raycast actionable: '
                        'OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/')):
                    # The statistics Button can outlive its result page during
                    # the return animation. Only the fresh typed assist list
                    # can complete that transition; never click the old Button.
                    return self._meta_assist_result_return_observation(button)
                if (str(exc) == 'combat Unity selector path is ambiguous'
                        and adapter._campaign_context is not None):
                    # The live combat reader may observe a newly mounted dock
                    # modal after the current screenshot. Refresh that boundary
                    # before asking its dedicated parser to own the popup.
                    self.refresh_frame()
                    if adapter._frame_or_live_observation_oracle().campaign_dock_full_visible(
                            adapter._campaign_context.resolved_stage_code or adapter._campaign_context.stage_code):
                        return name in ('RETIRE_APPEAR_1', 'RETIRE_APPEAR_3')
                if (
                    str(exc)
                    == "combat observer blocker is active: network_down"
                    and adapter.oracle.enabled(
                        "overlay/network-reconnect/confirm"
                    )
                ):
                    # NetworkDown can mount after the first prompt probe but
                    # before the combat observer read.  Reclassify only the
                    # independently proven exact reconnect prompt; every other
                    # blocker remains fail-closed.
                    if name == "POPUP_CONFIRM":
                        return True
                    if name == "POPUP_CANCEL":
                        return adapter.oracle.enabled(
                            "overlay/network-reconnect/cancel"
                        )
                    return False
                if self._campaign_combat_transition_error(exc):
                    # ChapterPreCombatUI mounts its Button before the same
                    # control becomes the exact top raycast.  This is a
                    # bounded post-grid transition only; outside it the same
                    # mismatch remains fail-closed.
                    return False
                if self._operation_siren_combat_observer_gap(exc):
                    # Keep optional combat probes absent across an OS observer
                    # gap.  combat_is_executing() remains the owner of whether
                    # the committed battle is still running.
                    return False
                raise
        try:
            return self.open().appear(button)
        except AlasSemanticUnmapped:
            # The battle can switch to its result hierarchy between the
            # session-level surface check above and Adapter.appear()'s fresh
            # observer read.  Re-read once: on a proven Daily combat/result
            # surface every optional pixel popup is absent, while the result
            # sentinel remains the only positive probe.
            self.refresh_frame()
            oracle = self.open()._frame_or_live_observation_oracle()
            if self.open()._reward_sidebar_ready(
                    self.open()._frame_or_live_observation_oracle()):
                # Commission can finish returning to the Reward sidebar on
                # this existing refresh. Its normal classifier owns the new
                # frame; do not rethrow the preceding transition's error.
                return self.open().appear(button)
            if self.open()._inherited_dorm_overlay_return() is not None:
                # The existing refresh may finish shop cancellation and expose
                # its Feed owner. Reclassify on that immutable screenshot.
                return self.open().appear(button)
            if (name == 'CAMPAIGN_WITHDRAW_CONFIRM'
                    and self.open()._frame_or_live_observation_oracle().observation_target_present('dorm/page/manage')
                    and self.open()._frame_or_live_observation_oracle().enabled('dorm/page/back')):
                # The same existing refresh can finish Feed panel unmount.
                # The normal CourtYard classifier already proves this unrelated
                # campaign confirmation absent; do not rethrow its old frame.
                return self.open().appear(button)
            if self.open()._frame_or_live_observation_oracle().operation_siren_local_map_visible():
                # The existing single refresh can finish a combat-to-map
                # return. Reclassify optional probes on that proven frame;
                # the adapter still rejects unknown input and malformed owners.
                return self.open().appear(button)
            if self.open()._frame_or_live_observation_oracle().main_page_visible():
                # The existing single refresh can finish a native page return.
                # Let the normal classifier inspect that new screenshot rather
                # than rethrowing an unmapped probe from the preceding frame.
                # Unknown resources and covered owners retain their errors.
                return self.open().appear(button)
            if (name == 'GOTO_MAIN_WHITE'
                    and self.open()._frame_or_live_observation_oracle().exercise_page_visible()):
                # The existing refresh can complete Exercise entry after the
                # first screenshot contained no mounted page controls. Let
                # the normal classifier inspect that new immutable frame;
                # its blocker and target checks still own the decision.
                return self.open().appear(button)
            if ((name in UI_PAGE_CHECK_RESOURCES
                    or (name == 'CAMPAIGN_WITHDRAW_CONFIRM'
                        and self.open()._campaign_context is None
                        and self.open()._frame_or_live_observation_oracle().enabled('research-menu/page/back')))
                    and self.open()._frame_or_live_observation_oracle().exists('research-menu/page/back')):
                # The existing refresh may have caught the completed Shipyard
                # or Research return. Its existing classifier also owns the
                # unowned withdrawal probe from ui_additional; foreign modals
                # still fail there. Reuse this one refreshed screenshot instead
                # of rethrowing the preceding transition's unknown-page error.
                return self.open().appear(button)
            if (oracle.observation_surface_present(ObservationSurface.BATTLE_RESULT)
                    and oracle.daily_battle_result_visible()):
                if name == "BATTLE_STATUS_S":
                    self._combat_result_observation = (name, time.monotonic())
                    return True
                return False
            if (oracle.observation_surface_present(ObservationSurface.COMBAT)
                    and oracle.daily_combat_visible()):
                self._daily_combat_seen_at = time.monotonic()
                return name == "AUTOMATION_ON"
            if (name == "RAID_REWARDS"
                    and oracle.observation_surface_present(ObservationSurface.CURRENT_RAID)
                    and oracle.raid_page_visible(event=oracle.current_raid_event())):
                # The exact current Raid page has no legacy rewards overlay.
                # A malformed present owner still raises its classified error.
                return False
            if time.monotonic() - getattr(
                self, "_daily_combat_seen_at", float("-inf")
            ) <= 20.0:
                # Unity briefly removes CombatUI before mounting the grade
                # result page.  Keep ALAS polling without inventing a target;
                # the next exact combat/result hierarchy decides the probe.
                return False
            raise

    def match_template_color(self, button: Any) -> bool:
        return self.open().match_template_color(button)

    def image_color_count(
        self,
        button: Any,
        color: Tuple[int, int, int],
        threshold: int,
        count: int,
    ) -> bool:
        return self.open().image_color_count(button, color, threshold, count)

    def click(self, button: Any, *, require_present: bool = False) -> Optional[Union[ActionReceipt, PrivateQuartersPhysicsReceipt]]:
        from .contracts import StorageBoxCandidate
        if isinstance(button, StorageBoxCandidate):
            receipt = self.inspect_storage_material_item(button.slot,
                expected_label=button.display_label, expected_icon=button.icon_sprite)
            self.open()._storage_box_candidate = button
            self.open()._storage_box_use_receipt = None
            self.open()._storage_box_use_quantity = None
            self.open()._storage_box_equipment_receipt = None
            self.open()._storage_box_destroy_receipt = None
            return receipt
        if AlasSemanticAdapter._operation_siren_camera_grid(button):
            self.refresh_frame()
            return self.open().click_operation_siren_camera_grid(button)
        if AlasSemanticAdapter._campaign_grid_location(button) is not None:
            self.refresh_frame()
            context = self.open()._campaign_context
            if context is not None and context.submarine_move_entry is not None:
                return self.open().click_campaign_submarine_grid(button)
            return self.open().click_campaign_combat_grid(button)
        name = AlasSemanticAdapter._button_name(button)
        if (name in ('POPUP_CONFIRM', 'POPUP_CANCEL')
                and not self.open()._login_flow.active):
            target = ('overlay/network-reconnect/confirm' if name == 'POPUP_CONFIRM'
                      else 'overlay/network-reconnect/cancel')
            if self.open()._frame_or_live_observation_oracle().enabled(target):
                self.refresh_frame()
                # This global owner was already proved by ALAS' screenshot.
                # Bind its exact input before the unrelated combat table;
                # Oracle.click rechecks the prompt after refresh and cannot
                # fall through to another task's colliding Msgbox control.
                return self.open().click_network_reconnect(name == 'POPUP_CONFIRM')
        if name == 'AUTOMATION_CONFIRM' and (
                self.open()._meta_assist_active or self.open().meta_beacon_active()
                or self.open().daily_execution_active()
                or self.open().operation_siren_combat_committed()
                or getattr(self.open(), 'campaign_auto_search_owned', lambda: False)()):
            self.refresh_frame()
            return self.open().oracle.click_combat_automation_info()
        if (name == 'GUILD_POPUP_CANCEL'
                and self.open()._frame_or_live_observation_oracle().observation_target_present(
                    'overlay/guild-message/close')):
            self.refresh_frame()
            adapter = self.open()
            current = adapter._require_frame_observation_oracle()
            if not current.observation_target_present('overlay/guild-message/close'):
                # A global notice may expire after the original positive
                # screenshot. A new complete frame proves disappearance;
                # return to ALAS without input or an invented close receipt.
                return None
            with adapter.prepared_input_frame(lambda: current):
                return adapter.click(button)
        if name in ('SYNC_ENTER', 'SYNC_ENTER2', 'SYNC_TAP'):
            self.refresh_frame()
            return self.open().click(button)
        if name == 'SUBMARINE_READY' and self.open()._campaign_context is not None:
            self.refresh_frame()
            return self.open().click_campaign_submarine_call()
        if name == "BACK_ARROW" and self.open().oracle.retirement_selection_visible():
            self.refresh_frame()
            receipt = self.open().oracle.click_retirement_page_back()
            self._retirement_return_receipt = receipt
            return receipt
        if name in ("MAP_AMBUSH_EVADE", "MAP_AMBUSH_ATTACK"):
            self.refresh_frame()
            return self.open().click(button)
        sample_use = getattr(self, '_opsi_sample_use', None)
        if sample_use is not None and name in (sample_use.selected.name, 'STORAGE_USE', 'BOX_USE', 'CLICK_SAFE_AREA'):
            self.refresh_frame()
            adapter = self.open()
            adapter._package_gate()
            receipt = sample_use.click(adapter.oracle, name)
            adapter.begin_operation_siren_page_remount(20.0)
            return receipt
        if name in ("RESET_FLEET_PREPARATION", "RESET_TICKET_POPUP"):
            self.refresh_frame()
            return self.open().click(button)
        if name == "ACTION_POINT_REMAIN_OS":
            return self.click_operation_siren_action_point_open()
        if name in ("ACTION_POINT_USE", "ACTION_POINT_CANCEL"):
            self.refresh_frame()
            return self.open().click_operation_siren_action_point_control(
                name == "ACTION_POINT_USE"
            )
        if (
            name == "PAUSE"
            and self.open()._exercise_execution_active
        ):
            return self.open().oracle.click_exercise_combat_pause()
        navigation_frame = None
        if name == "CLICK_SAFE_AREA":
            navigation_frame = self.refresh_frame()
            adapter = self.open()
            navigation_oracle = adapter._require_frame_observation_oracle()
            if navigation_oracle.exercise_reward_item_info_visible():
                receipt = adapter.oracle.click_exercise_reward_item_info_cancel()
                self._combat_result_transition_until = time.monotonic() + 1.5
                return receipt
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and navigation_oracle.award_info_page_visible()
            ):
                receipt = adapter.oracle.click_exercise_award_info_close()
                self._combat_result_transition_until = time.monotonic() + 1.5
                return receipt
            if navigation_oracle.daily_battle_result_visible():
                receipt = adapter.oracle.click_daily_battle_result()
                # ChapterMap can take well over the generic overlay-close
                # interval to remount after the typed result action.  Keep
                # only the exact committed campaign owner tolerant during
                # that bounded Unity transition.
                self._arm_combat_result_transition(
                    adapter,
                    transition_seconds=20.0,
                )
                return receipt
        shop_item_index = getattr(button, "semantic_shop_index", None)
        if shop_item_index is not None:
            self.refresh_frame()
            return self.open().oracle.click_shop_item(shop_item_index)
        shop_nav_labels = {
            "NAV_GENERAL": "补给商店",
            "NAV_MONTHLY": "月度商店",
        }
        if name in shop_nav_labels:
            self.refresh_frame()
            return self.open().oracle.click_shop_nav(shop_nav_labels[name])
        shop_tab_labels = {
            "TAB_MERIT": "军需",
            "TAB_GUILD": "舰队",
            "TAB_META": "META",
            "TAB_PRIZE": "奖券",
            "TAB_CORE_LIMITED": "核心限定",
            "TAB_CORE_MONTHLY": "核心月度",
            "TAB_MEDAL": "勋章",
            "TAB_PROTOTYPE": "原型",
        }
        if name in shop_tab_labels:
            self.refresh_frame()
            return self.open().oracle.click_shop_tab(shop_tab_labels[name])
        if name in ('EXP_INFO_S', 'EXP_INFO_A', 'EXP_INFO_B', 'EXP_INFO_C', 'EXP_INFO_D'):
            adapter = self.open()
            if (not (getattr(adapter, '_meta_beacon_active', False)
                     or getattr(adapter, '_meta_assist_active', False))
                    and (adapter.operation_siren_combat_committed()
                         or (getattr(adapter, '_operation_siren_auto_search_active', False)
                             and not getattr(adapter, '_operation_siren_startup_search_provisional', False)))):
                result_oracle = self._combat_result_action_oracle(adapter)
                grade = result_oracle.operation_siren_battle_statistics_grade()
                if grade is None or name != 'EXP_INFO_' + grade:
                    raise SemanticGateClosed('operation siren statistics grade changed before input')
                receipt = result_oracle.click_daily_battle_result()
                self._combat_last_result_receipt = receipt
                self._arm_combat_result_transition(adapter)
                return receipt
        if name in ("BATTLE_STATUS_S", "BATTLE_STATUS_D", "CLICK_SAFE_AREA"):
            adapter = self.open()
            # Reuse the immutable ALAS frame that authorized this click.  A
            # second live observer read can take longer than the input lease
            # on a busy result transition, producing a TOCTOU stale-frame
            # failure even though the exact result target was already proven.
            # The frame-bound oracle performs the same semantic checks without
            # hidden refreshes, and the final tap still invalidates that lease.
            result_oracle = self._combat_result_action_oracle(adapter)
            if (
                result_oracle.daily_battle_result_visible()
                or getattr(
                    result_oracle,
                    "operation_siren_battle_result_visible",
                    lambda: False,
                )()
            ):
                receipt = result_oracle.click_daily_battle_result()
                self._combat_result_observation = None
                self._combat_last_result_receipt = receipt
                if adapter.campaign_combat_committed():
                    self._arm_combat_result_transition(adapter)
                if getattr(
                    adapter, "operation_siren_combat_committed", lambda: False
                )():
                    self._arm_combat_result_transition(adapter)
                return receipt
            observation = self._combat_result_observation
            if (name == 'BATTLE_STATUS_S'
                    and getattr(adapter, '_meta_assist_active', False)
                    and observation is not None and observation[0] == name):
                # META's award/grade page can become the statistics page
                # during ALAS' deliberate sleep before clicking. Re-prove
                # the current exact result target instead of committing the
                # no-longer-visible resource from the preceding screenshot.
                self.refresh_frame()
                adapter = self.open()
                current_result = adapter._frame_or_live_observation_oracle()
                if current_result.daily_battle_result_visible():
                    receipt = current_result.click_daily_battle_result()
                    self._combat_result_observation = None
                    self._combat_last_result_receipt = receipt
                    self._arm_combat_result_transition(adapter)
                    return receipt
            if (
                name == "BATTLE_STATUS_S"
                and adapter.campaign_combat_committed()
                and observation is not None
                and observation[0] == name
                # A3's large typed result hierarchy can take several seconds
                # between ALAS's positive probe and its subsequent click.
                # This remains a passive, no-input acknowledgement; the exact
                # positive observation and six-second lease are sufficient
                # even when refreshing that frame correctly closed the prior
                # post-action transition window.
                and time.monotonic() <= observation[1] + 6.0
            ):
                # The grade-page root can temporarily leave the Button slice
                # while its victory animation keeps the exact typed result
                # hierarchy mounted.  Refresh once after the positive ALAS
                # probe and require the complete result target again; this
                # does not authorize a different or merely image-like page.
                if self._combat_last_result_receipt is None:
                    self.refresh_frame()
                    adapter = self.open()
                # The immutable ALAS frame may still describe the award popup
                # while Unity has already mounted the statistics confirm page.
                # Re-prove that exact live result target before treating the
                # delayed ALAS click as a no-input acknowledgement.
                if adapter.oracle.daily_battle_result_visible():
                    receipt = adapter.oracle.click_daily_battle_result()
                    self._combat_result_observation = None
                    self._combat_last_result_receipt = receipt
                    self._arm_combat_result_transition(adapter)
                    return receipt
                # ALAS deliberately sleeps between appear() and click().  The
                # exact result page can finish its own transition during that
                # delay.  Consume the one-use positive observation without
                # injecting another input; every ordinary combat action still
                # revalidates and fails closed below.
                if self._combat_last_result_receipt is not None:
                    self._combat_result_observation = None
                    return replace(
                        self._combat_last_result_receipt,
                        semantic_id="combat/result-transition/passive",
                    )
        if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
            adapter = self.open()
            if (adapter.oracle.award_info_page_visible()
                    and adapter.oracle.observation_target_present('reward/item-info/close')):
                self.refresh_frame()
                adapter = self.open()
                adapter._package_gate()
                if (adapter.oracle.award_info_page_visible()
                        and adapter.oracle.reward_item_info_visible()):
                    # Close this exact foreground description; ALAS' reward
                    # loop observes and closes the still-pending award next.
                    return adapter.oracle.click('reward/item-info/close')
            result_oracle = self._combat_result_action_oracle(adapter)
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and result_oracle.award_info_page_visible()
            ):
                return result_oracle.click_exercise_award_info_close()
            pending_daily = getattr(adapter, "_daily_pending_receipt", None)
            daily_quick_reward = (
                adapter.daily_execution_active()
                and pending_daily is not None
                and pending_daily.semantic_id.endswith("/quick/all")
            )
            # Let Daily correlate its quick receipt with the reward close via
            # the ordinary refreshed adapter input path below.
            if not daily_quick_reward and result_oracle.campaign_battle_reward_visible():
                target = (
                    "reward/award-info/close"
                    if result_oracle.enabled("reward/award-info/close")
                    else "reward/award-info1/close"
                )
                receipt = result_oracle.click(target)
                self._combat_last_result_receipt = receipt
                self._combat_reward_close_pending = receipt
                if adapter._meta_assist_active or adapter.meta_beacon_active():
                    # Shared AwardInfo dispatch can close a synchronization
                    # reward too. Hand the accepted receipt to the META port
                    # so a delayed native probe cannot submit another input.
                    adapter._meta_reward_close_receipt = receipt
                self._arm_combat_result_transition(adapter)
                return receipt
        if (
            name == "GET_SHIP"
            and self.adapter is not None
            and (self.adapter._meta_assist_active or self.adapter.meta_beacon_active()
                 or self.adapter.campaign_combat_committed())
        ):
            adapter = self.open()
            result_oracle = self._combat_result_action_oracle(adapter)
            if not result_oracle.new_ship_reward_visible():
                raise SemanticTargetMissing("new-ship reward page is absent")
            receipt = result_oracle.click("reward/new-ship/continue")
            self._combat_last_result_receipt = receipt
            self._arm_combat_result_transition(adapter)
            return receipt
        if name in ("CLICK_SAFE_AREA", "GOTO_MAIN"):
            navigation_frame = navigation_frame or self.refresh_frame()
            navigation_oracle = self.open()._require_frame_observation_oracle()
            if name == 'CLICK_SAFE_AREA':
                completed = self.open()._operation_siren_reward_return_completed(navigation_oracle)
                if completed is not None:
                    return completed
            if name == "CLICK_SAFE_AREA" and navigation_oracle.enabled("reward/award-info/close"):
                return navigation_oracle.click("reward/award-info/close")
            tactical_context = self.open()._commission_context
            if (name == 'GOTO_MAIN'
                    and tactical_context is not None
                    and tactical_context.flow_kind == 'tactical'
                    and navigation_oracle.enabled('tactical/dock/cancel')
                    and navigation_oracle.tactical_candidate_ships()):
                # The ordinary Dock exit rejects selection dialogs. This
                # task owns the reviewed student selection return instead.
                return navigation_oracle.click('tactical/dock/back')
            if (name == "GOTO_MAIN"
                    and not (getattr(navigation_oracle, 'meta_character_page_visible', lambda: False)()
                             or navigation_oracle.meta_character_menu_visible())
                    and any(
                    button.active_in_hierarchy
                    and button.path == "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back"
                    for button in navigation_oracle.read_state().buttons)
                    and any(button.active_in_hierarchy and button.path ==
                            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button"
                            for button in navigation_oracle.read_state().buttons)):
                # The shared back path also belongs to Guild. Dock needs its
                # distinct filter anchor before entering the capacity proof.
                oracle = self.open().oracle
                receipt = oracle.click_dock_page_back()
                deadline = time.monotonic() + 12.0
                while time.monotonic() < deadline:
                    state = oracle.read_state()
                    if (state.generation > receipt.generation
                            and oracle.main_page_visible()
                            and not any(
                                button.active_in_hierarchy
                                and button.path == "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back"
                                for button in state.buttons)):
                        return receipt
                    time.sleep(0.2)
                raise SemanticGateClosed("Dock return did not reach the exact main page")
            if name == "GOTO_MAIN" and navigation_oracle.exercise_page_visible():
                # Original ui_goto owns screenshots, retries and destination
                # proof. The optional Home control did not advance in live
                # recovery; leave one level through the existing reviewed Back
                # port and let the native page graph rediscover its destination.
                receipt = self.open()._fresh_input_oracle().click('exercise/page/back')
                self.open()._exercise_page_back_transition_until = time.monotonic() + 20.0
                return receipt
        if (name == 'AUTO_SEARCH_MENU_EXIT' and self.adapter is not None
                and self.adapter._campaign_context is not None):
            self.refresh_frame()
            return self.open().click(button)
        if (name in ('EMERGENCY_REPAIR_AVAILABLE', 'EMERGENCY_REPAIR_CONFIRM',
                     'RETIRE_APPEAR_1', 'RETIRE_APPEAR_2', 'RETIRE_APPEAR_3')
                and self.adapter is not None and self.adapter._campaign_context is not None):
            self.refresh_frame()
            return self.open().click(button)
        if (
            name in ALAS_COMBAT_RESOURCE_ACTION_TARGETS
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            return self._live_combat_click(name)
        if (
            name == "AUTOMATION_SWITCH"
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            return self._click_live_combat_automation_switch()
        if (
            name == "COMBAT_AUTO_SWITCH"
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            # Original CombatAuto probes COMBAT_AUTO first and reaches this
            # action only when that exact manual-mode resource was visible.
            return self._live_combat_click("COMBAT_AUTO")
        if name == "SWITCH_OVER" and self.adapter is not None:
            self.refresh_frame()
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        if (
            name not in DEFAULT_ALAS_BUTTON_TARGETS
            and name not in LOGIN_ACTION_TARGETS
            and name != "DAILY_ENTER"
            and not name.startswith("DAILY_MISSION_")
            and name not in ("DAILY_NORMAL_RUN", "DAILY_SKIP")
            and name not in ("MISSION_FINISH", "MISSION_CHECKOUT")
            and not (name == 'CLICK_SAFE_AREA' and self.adapter is not None
                     and (self.adapter._meta_beacon_active or self.adapter._meta_assist_active)
                     and (self.adapter.oracle.award_info_page_visible()
                          or self.adapter._meta_reward_close_receipt is not None))
            and name not in MISSION_CLICK_RESOURCES
            and name not in MAIL_CLICK_RESOURCES
            and name not in CAMPAIGN_CLICK_RESOURCES
            and not (name == 'POPUP_CONFIRM_WHITE_UI_ADDITIONAL' and self.adapter is not None
                     and (self.adapter._operation_siren_adaptability_info_receipt is not None
                          or getattr(self.adapter._frame_or_live_observation_oracle(),
                                     'operation_siren_adaptability_info_visible', lambda: False)()))
            and not (self.adapter is not None
                     and getattr(self.adapter, '_storage_box_candidate', None) is not None
                     and name in ('BOX_USE', 'BOX_AMOUNT_CONFIRM', 'AMOUNT_MINUS', 'AMOUNT_PLUS',
                                  'MATERIAL_ENTER', 'EQUIP_CONFIRM', 'EQUIP_CONFIRM_2'))
            and not (self.adapter is not None and name == 'GUILD_DISPATCH_CLOSE')
            and not (self.adapter is not None
                     and re.fullmatch(r'GUILD_FORMATION_FLEET_([1-9][0-9]*|add)', name))
            and not (
                self.adapter is not None
                and name in RESEARCH_CLICK_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in DORM_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in MINIGAME_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in BUILD_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and (name in TACTICAL_VIRTUAL_RESOURCES
                     or (name == "GET_MISSION"
                         and self.adapter._commission_context is not None
                         and self.adapter._commission_context.flow_kind == "tactical"))
            )
            and not (
                self.adapter is not None
                and name in BATTLE_PASS_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in SUPPLY_PACK_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in DATA_KEY_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in COMMISSION_CLICK_RESOURCES
            )
            and MISSION_NAVBAR_PATTERN.fullmatch(name) is None
            and COMMISSION_ROW_PATTERN.fullmatch(name) is None
            and BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name) is None
            and BUILD_POOL_NAVBAR_PATTERN.fullmatch(name) is None
            and CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name) is None
            and campaign_stage_code is None
            and not name.startswith(
                ("POPUP_CONFIRM_ORDER_", "POPUP_CANCEL_ORDER_")
            )
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        # A page scan can legitimately take longer than one frame lease.  The
        # semantic target is re-read by Adapter.click(); refresh the frozen
        # screenshot-equivalent immediately before that read/input boundary.
        prepared_frame = navigation_frame or self.refresh_frame()
        adapter = self.open()
        if name in ('META_MAIN_DOSSIER_ENTRANCE', 'META_MAIN_BEACON_ENTRANCE'):
            reader = adapter._require_frame_observation_oracle()
            blockers = reader._blocking_rules(reader.read_state(), 'meta/home')
            if blockers and all(rule.blocker_id == 'loading' for rule in blockers):
                # The native category loop may still hold its positive scan
                # after the card opens. Only its next screenshot can identify
                # the destination; neither resubmit nor manufacture success.
                return None
        if (adapter._exercise_pending
                and DEFAULT_ALAS_BUTTON_TARGETS.get(name) in (
                    'exercise/opponent/1', 'exercise/opponent/2',
                    'exercise/opponent/3', 'exercise/opponent/4')):
            reader = adapter._require_frame_observation_oracle()
            if reader.daily_precombat_visible():
                blockers = reader._blocking_rules(reader.read_state(), 'exercise/opponent/1')
                if all(rule.blocker_id in ('daily-precombat', 'loading') for rule in blockers):
                    # A positive overview scan can precede its accepted detail
                    # start mounting preparation. Native selection re-observes;
                    # no second rival input or synthetic receipt is needed.
                    return None
        if (name in ('BATTLE_PREPARATION', 'BATTLE_PREPARATION_WITH_OVERLAY')
                and (adapter._exercise_pending or adapter._exercise_execution_active)):
            reader = adapter._require_frame_observation_oracle()
            blockers = reader._blocking_rules(reader.read_state(), 'daily/precombat/start')
            if blockers and all(rule.blocker_id == 'loading' for rule in blockers):
                # The earlier positive scan can precede the loading curtain.
                # No start was sent: native preparation takes its next screenshot.
                return None
        if (name == 'DORM_FEED_ENTER' and adapter._dorm_context is not None
                and time.monotonic() <= adapter._dorm_context.passive_transition_until):
            reader = adapter._require_frame_observation_oracle()
            if reader.enabled('dorm/statistics/confirm'):
                return None
            state = reader.read_state()
            targets = reader._matches(state, 'dorm/feed')
            blockers = reader._blocking_rules(state, 'dorm/feed')
            if (len(targets) == 1 and targets[0].active_in_hierarchy
                    and targets[0].active_and_enabled and targets[0].interactable
                    and targets[0].raycast_top is False
                    and targets[0].point is not None and targets[0].bounds is not None
                    and targets[0].bounds.contains(targets[0].point)
                    and not any(rule.blocker_id != 'loading' for rule in blockers)):
                # During the existing Dorm entry window a mounting summary or
                # statistics layer can briefly own this raycast. Leave input
                # closed and let the original feed/info handlers re-observe.
                return None
        frame_oracle = (
            adapter._require_frame_observation_oracle()
            if name == "LOGIN_GAME_UPDATE" else None
        )
        def prepared_oracle():
            self._frame_clock.borrow(prepared_frame.frame_id, require_fresh=True)
            return adapter._require_frame_observation_oracle()

        with adapter.prepared_input_frame(prepared_oracle):
            if require_present and not adapter.appear(button):
                # ALAS' earlier positive screenshot can outlive an overlay.
                # Recheck the same fresh frame used for generic dispatch; an
                # absent target returns to its existing loop with no input.
                raise SemanticTargetMissing("ALAS target disappeared before input")
            try:
                receipt = adapter.click(button)
            except SemanticTargetMissing as exc:
                if (require_present or name != 'POPUP_CONFIRM'
                        or (adapter._mail_context is None
                            and not isinstance(exc, SemanticInputTargetMissing))):
                    raise
                # InfoHandler's original popup path calls Device.click
                # directly after a positive screenshot. The prompt may have
                # disappeared meanwhile; let its next screenshot handle the
                # reward without sending input or fabricating a receipt.
                return None
        if frame_oracle is not None and frame_oracle._login_update_retry_attempted:
            adapter.oracle._login_update_retry_attempted = True
        return receipt
