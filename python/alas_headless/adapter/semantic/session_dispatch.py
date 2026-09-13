"""Session dispatch for the typed ALAS boundary."""

from __future__ import annotations

from typing import Union
from ...oracle.private_quarters import PrivateQuartersPhysicsReceipt

import time
from dataclasses import replace
from typing import Any, Tuple
from ...adapter.flows import LOGIN_ACTION_TARGETS
from ...alas_combat_state_replay import (
    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES,
    ALAS_COMBAT_RESOURCE_ACTION_TARGETS,
)
from ...semantic_oracle import ActionReceipt, SemanticGateClosed, SemanticTargetMissing
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

    def appear(self, button: Any) -> bool:
        name = AlasSemanticAdapter._button_name(button)
        adapter = self.open()
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
        if adapter.oracle.enabled("overlay/network-reconnect/confirm"):
            # NetworkDown is a global exact overlay and may mount over any
            # owned page between ALAS' page probe and its next action.  Expose
            # only the reviewed reconnect pair before asking any covered page
            # reader to classify its underlay; the original ALAS popup handler
            # remains the owner of the retry.
            if name == "POPUP_CONFIRM":
                return True
            if name == "POPUP_CANCEL":
                return adapter.oracle.enabled(
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
            and adapter._campaign_context is not None
            and adapter.campaign_combat_committed()
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
        if getattr(
            adapter, "operation_siren_combat_committed", lambda: False
        )():
            adapter.complete_operation_siren_combat_if_map_restored()
        if (
            getattr(adapter, "operation_siren_combat_committed", lambda: False)()
            and adapter.oracle.operation_siren_battle_result_visible()
        ):
            grade = adapter.oracle.operation_siren_battle_result_grade()
            observed = (
                "BATTLE_STATUS_S" if grade == "VICTORY" else "BATTLE_STATUS_D"
            )
            self._combat_result_observation = (observed, time.monotonic())
            return name == observed
        result_owner_active = bool(
            getattr(adapter, "daily_execution_active", lambda: False)()
            or getattr(adapter, "current_raid_result_active", lambda: False)()
            or adapter.campaign_combat_committed()
            or getattr(
                adapter, "operation_siren_combat_committed", lambda: False
            )()
            or getattr(adapter, "_exercise_execution_active", False)
        )
        if result_owner_active and adapter.oracle.daily_battle_result_visible():
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
        if adapter.oracle.enabled("reward/award-info/close"):
            return name == "GET_ITEMS_1"
        combat_oracle = adapter._frame_or_live_observation_oracle()
        if (
            combat_oracle.observation_surface_present(ObservationSurface.COMBAT)
            and combat_oracle.daily_combat_visible()
        ):
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
                if (adapter._meta_assist_active and str(exc).startswith(
                        'combat action control is not exact top-raycast actionable: '
                        'OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/')):
                    # The statistics Button can outlive its result page during
                    # the return animation. Only the fresh typed assist list
                    # can complete that transition; never click the old Button.
                    self.refresh_frame()
                    adapter = self.open()
                    adapter.oracle.meta_assist_state()
                    adapter._operation_siren_combat_active = False
                    return adapter.appear(button)
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
            oracle = self.open().oracle
            if (name in UI_PAGE_CHECK_RESOURCES
                    and self.open()._frame_or_live_observation_oracle().exists('research-menu/page/back')):
                # The existing refresh may have caught the completed Shipyard
                # return. Reclassify that exact menu in the newly leased frame
                # instead of rethrowing the old transition's unknown-page error.
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
                    and oracle.raid_page_visible(event="raid_20260827")):
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

    def click(self, button: Any) -> Union[ActionReceipt, PrivateQuartersPhysicsReceipt]:
        if AlasSemanticAdapter._campaign_grid_location(button) is not None:
            self.refresh_frame()
            context = self.open()._campaign_context
            if context is not None and context.submarine_move_entry is not None:
                return self.open().click_campaign_submarine_grid(button)
            return self.open().click_campaign_combat_grid(button)
        name = AlasSemanticAdapter._button_name(button)
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
        if name == "CLICK_SAFE_AREA":
            adapter = self.open()
            if adapter.oracle.exercise_reward_item_info_visible():
                receipt = adapter.oracle.click_exercise_reward_item_info_cancel()
                self._combat_result_transition_until = time.monotonic() + 1.5
                return receipt
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and adapter.oracle.award_info_page_visible()
            ):
                receipt = adapter.oracle.click_exercise_award_info_close()
                self._combat_result_transition_until = time.monotonic() + 1.5
                return receipt
            if adapter.oracle.daily_battle_result_visible():
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
            result_oracle = self._combat_result_action_oracle(adapter)
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and result_oracle.award_info_page_visible()
            ):
                return result_oracle.click_exercise_award_info_close()
            if result_oracle.campaign_battle_reward_visible():
                target = (
                    "reward/award-info/close"
                    if result_oracle.enabled("reward/award-info/close")
                    else "reward/award-info1/close"
                )
                receipt = result_oracle.click(target)
                self._combat_last_result_receipt = receipt
                self._arm_combat_result_transition(adapter)
                return receipt
        if (
            name == "GET_SHIP"
            and self.adapter is not None
            and self.adapter.campaign_combat_committed()
        ):
            adapter = self.open()
            result_oracle = self._combat_result_action_oracle(adapter)
            if not result_oracle.new_ship_reward_visible():
                raise SemanticTargetMissing("new-ship reward page is absent")
            receipt = result_oracle.click("reward/new-ship/continue")
            self._combat_last_result_receipt = receipt
            self._arm_combat_result_transition(adapter)
            return receipt
        if (
            name == "CLICK_SAFE_AREA"
            and self.open().oracle.enabled("reward/award-info/close")
        ):
            self.refresh_frame()
            return self.open().oracle.click("reward/award-info/close")
        if name == "GOTO_MAIN" and self.open().oracle.exercise_page_visible():
            self.refresh_frame()
            return self.open().oracle.click("exercise/page/back")
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
            and name not in MISSION_CLICK_RESOURCES
            and name not in MAIL_CLICK_RESOURCES
            and name not in CAMPAIGN_CLICK_RESOURCES
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
                and name in TACTICAL_VIRTUAL_RESOURCES
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
        self.refresh_frame()
        return self.open().click(button)
