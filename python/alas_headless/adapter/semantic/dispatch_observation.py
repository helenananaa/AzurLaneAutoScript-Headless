"""Dispatch observation for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import SemanticGateClosed
from ...oracle.surfaces import ObservationSurface
from .contracts import AlasSemanticUnmapped
from .dispatch_result import UNHANDLED
from .resources import (
    BATTLE_PASS_VIRTUAL_RESOURCES,
    BUILD_VIRTUAL_RESOURCES,
    CAMPAIGN_VIRTUAL_RESOURCES,
    COMMISSION_TAB_TARGETS,
    COMMISSION_VIRTUAL_RESOURCES,
    CURRENT_RAID_EARLIER_PAGE_CHECKS,
    DATA_KEY_VIRTUAL_RESOURCES,
    DORM_VIRTUAL_RESOURCES,
    MAIL_VIRTUAL_RESOURCES,
    MINIGAME_VIRTUAL_RESOURCES,
    MISSION_VIRTUAL_RESOURCES,
    PAGE_VIRTUAL_RESOURCES,
    RESEARCH_VIRTUAL_RESOURCES,
    SUPPLY_PACK_VIRTUAL_RESOURCES,
    TACTICAL_VIRTUAL_RESOURCES,
    UI_PAGE_CHECK_RESOURCES,
)


class DispatchObservationPorts:
    """Dispatch observation ports on the shared adapter context."""

    def _appear_priority(self, name):
        if (
            name == "GET_MISSION"
            and (
                time.monotonic() <= self._exercise_chapter_entry_transition_until
                or self.oracle.campaign_page_is_normal()
            )
        ):
            self._package_gate()
            notice_matches = getattr(
                self.oracle, "_campaign_urgent_notice_matches", lambda state: False
            )
            if notice_matches(self.oracle.read_state()):
                raise SemanticGateClosed("urgent commission notice has no campaign owner")
            return False
        if (
            name in UI_PAGE_CHECK_RESOURCES
            and time.monotonic() <= self._exercise_page_back_transition_until
            and not self.oracle.campaign_menu_is_entry()
        ):
            self._package_gate()
            return False
        if (
            name in UI_PAGE_CHECK_RESOURCES
            and time.monotonic() <= self._exercise_chapter_back_transition_until
            and not self.oracle.campaign_menu_is_entry()
        ):
            self._package_gate()
            return False
        if (
            name in UI_PAGE_CHECK_RESOURCES
            and time.monotonic() <= self._exercise_entry_transition_until
            and not self.oracle.exercise_page_visible()
        ):
            self._package_gate()
            return False
        if (
            name in (
                "MAP_PREPARATION", "FLEET_PREPARATION", "RAID_FLEET_PREPARATION",
                "AUTO_SEARCH_MENU_EXIT", "AUTO_SEARCH_REWARD", "WITHDRAW",
            )
            and (
                time.monotonic() <= self._exercise_entry_transition_until
                or self.oracle.exercise_page_visible()
            )
            and self._campaign_context is None
        ):
            self._package_gate()
            return False
        if (
            name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3", "GET_SHIP")
            and (
                time.monotonic() <= self._exercise_entry_transition_until
                or time.monotonic() <= self._exercise_chapter_entry_transition_until
            )
            and self._award_close_target() is None
            and (
                name != "GET_SHIP"
                or not self.oracle.observation_target_present("reward/new-ship/continue")
            )
        ):
            self._package_gate()
            return False
        if (
            name in ("BATTLE_PREPARATION", "BATTLE_PREPARATION_WITH_OVERLAY")
            and self._exercise_execution_active
            and not self._exercise_pending
            and self.oracle.daily_precombat_visible()
        ):
            if time.monotonic() <= self._exercise_start_transition_until:
                return False
            raise SemanticGateClosed("Exercise start did not leave preparation")
        if name == "IN_MAP" and self._campaign_context is not None:
            # ALAS reuses IN_MAP for OpSi and campaigns. An exact OpSi map
            # cannot be resumed as a campaign sortie. Failure to parse an
            # optional OpSi surface must not suppress a valid campaign map.
            try:
                if self.oracle.operation_siren_local_map_visible():
                    return False
            except SemanticGateClosed:
                pass
        if name == 'POPUP_CANCEL_WHITE' and self.oracle.private_quarters_download_prompt_absent():
            return False
        if name == 'PRIVATE_QUARTERS_LOADING_CHECK':
            return self.oracle.private_quarters_loading_visible()
        if name == 'PRIVATE_QUARTERS_ROOM_TARGET_INTIMACY_MAX':
            return self.oracle.private_quarters_intimacy_max()
        if name in ('PRIVATE_QUARTERS_ROOM_TARGET_CHECK_1', 'PRIVATE_QUARTERS_ROOM_TARGET_CHECK_2',
                    'PRIVATE_QUARTERS_ROOM_TARGET_CHECK_3'):
            return self.oracle.private_quarters_new_jersey_visible()
        if name == 'PRIVATE_QUARTERS_PAGE_LOCALE_LOFT':
            return self.oracle.private_quarters_loft_visible()
        if name in ("SHIPYARD_IN_DEV", "SHIPYARD_IN_FATE"):
            if not self.oracle.shipyard_page_visible():
                return False
            phase = self.oracle.shipyard_selected_state().phase
            return phase == ("dev" if name == "SHIPYARD_IN_DEV" else "fate")
        if (not self._login_flow.active
                and name in ("GOTO_MAIN", "GOTO_MAIN_WHITE", "RPG_HOME")
                and self.oracle.exists("research/progress/confirm")):
            # The original unknown-page recovery probes home before its
            # popup handler. This notice obscures those navigation controls.
            return False
        if name == 'PRIVATE_QUARTERS_INTERACT_CHECK':
            return self.oracle.private_quarters_interact_check_visible()
        if name == 'PRIVATE_QUARTERS_INTERACT':
            return self.oracle.private_quarters_interact_visible()
        if name == "RESET_FLEET_PREPARATION":
            return self._frame_or_live_observation_oracle().operation_siren_reset_fleet_ready()
        if name == "RESET_TICKET_POPUP":
            return self._frame_or_live_observation_oracle().operation_siren_reset_ticket_visible()
        observation_oracle = (
            (
                self._require_frame_observation_oracle()
                if self._login_flow.active
                else self._frame_or_live_observation_oracle()
            )
            if self._login_flow.active
            or name in UI_PAGE_CHECK_RESOURCES
            else self.oracle
        )
        if (not self._login_flow.active and self._campaign_context is None and name in (
                'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW')
                and (observation_oracle.main_page_visible()
                     or observation_oracle.campaign_menu_is_entry()
                     or observation_oracle.campaign_page_is_normal())):
            state = observation_oracle.read_state()
            blockers = observation_oracle._blocking_rules(state, 'ui/absence-probe')
            if not any(rule.blocker_id != 'campaign-menu' for rule in blockers):
                # UI.ui_additional scans these Campaign resources without a
                # Campaign task. An unobscured navigation page proves their
                # absence; ignore only that navigation page's own blocker,
                # while actual overlays keep their owned handling below.
                return False
        if (not self._login_flow.active and name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP')
                and self._mission_context is None
                and (observation_oracle.main_page_visible() or observation_oracle.campaign_menu_is_entry())
                and (name != 'GET_SHIP' or not observation_oracle.observation_target_present('reward/new-ship/continue'))
                and self._award_close_target() is None):
            # ui_goto probes generic rewards on main and the campaign menu.
            # Their absence is not a missing Mission capability. This does
            # not authorize claiming an unowned popup.
            return False
        if not self._login_flow.active and name in UI_PAGE_CHECK_RESOURCES:
            buttons = getattr(observation_oracle.read_state(), 'buttons', ())
            if any(b.active_in_hierarchy and b.active_and_enabled and b.path.endswith(
                    '/LevelGrid/DragLayer/op1/retreat') for b in buttons):
                if observation_oracle.campaign_is_in_map():
                    return name == 'IN_MAP'
            if observation_oracle.observation_target_present('reward/campaign-total/exit'):
                # The retained result owns the screen. Optional chapter/page
                # checks (e.g. commission notice) are absent, not malformed.
                return False
            # A visible overlay is enough to hide its underlay. Parsing reset
            # conditions, shop labels or story choices belongs to their ports,
            # not to every task's Page.iter_pages() sweep.
            if any(
                observation_oracle.observation_surface_present(surface)
                for surface in (
                    ObservationSurface.MESSAGE_BOX,
                    ObservationSurface.GUILD_MESSAGE,
                    ObservationSurface.RESET_FLEET,
                    ObservationSurface.STORY,
                )
            ):
                return False
            if getattr(observation_oracle, 'shipyard_page_visible', lambda: False)():
                return name == 'SHIPYARD_CHECK'
            if getattr(observation_oracle, 'daily_entry_visible', lambda: False)():
                return name == 'DAILY_CHECK'
            if observation_oracle.observation_target_present('dorm-menu/page/root'):
                return name == 'DORMMENU_CHECK'
            if getattr(observation_oracle, 'private_quarters_page_visible', lambda: False)():
                return name == 'PRIVATE_QUARTERS_CHECK'
            if getattr(observation_oracle, 'private_quarters_room_visible', lambda: False)():
                return False
            if getattr(observation_oracle, 'meta_character_page_visible', lambda: False)():
                return name == 'META_CHECK'
            if (observation_oracle.observation_target_present('archive/page/back')
                    and observation_oracle.war_archives_page_visible()):
                return name == 'WAR_ARCHIVES_CHECK'
            if (observation_oracle.campaign_menu_is_entry()
                    and not any(rule.blocker_id != 'campaign-menu' for rule in
                        observation_oracle._blocking_rules(observation_oracle.read_state(), 'ui/absence-probe'))
                    and not observation_oracle.enabled('overlay/bulletin/close')):
                # The entrance owns page enumeration even when its chapter
                # back button has unmounted after returning from a stage.
                return name == 'CAMPAIGN_MENU_CHECK'
        if name == "POPUP_CONFIRM":
            reset_oracle = self._frame_or_live_observation_oracle()
            if reset_oracle.observation_surface_present(ObservationSurface.RESET_SHOP):
                return reset_oracle.operation_siren_reset_shop_visible()
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.observation_target_present("reward/page/back")
        ):
            # The reward sidebar retains the main hierarchy underneath. Its
            # own page must win or ALAS repeatedly toggles the expand button.
            return name == "REWARD_CHECK" and observation_oracle.enabled("reward/page/back")
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.exists("research-menu/page/back")
        ):
            # This exact full-screen owner is enough to classify ALAS' page
            # sweep before any unrelated task-specific reader runs.  Inputs
            # still go through their individual typed mappings and raycasts.
            return name == "RESHMENU_CHECK"
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.exists("research/page/back")
        ):
            # A retained research page owns page enumeration even after the
            # Research task has ended. Observation needs no resource grant;
            # every project/claim input retains its own task boundary.
            if name != "RESEARCH_CHECK":
                return False
            try:
                return len(observation_oracle.research_projects()) == 5
            except SemanticGateClosed:
                return False
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.observation_target_present("shop/home")
            and observation_oracle.recommendation_shop_visible()
        ):
            # The exact Shop shell owns the passive Page.iter_pages() sweep.
            # Supply Pack and other legacy page checks may precede SHOP_CHECK
            # while the Shop home transition is still settling.
            return name == "SHOP_CHECK"
        if (
            not self._login_flow.active
            and name in ('MAIN_GOTO_FLEET', 'MAIN_GOTO_CAMPAIGN_WHITE')
            and observation_oracle.exists('campaign-menu/page/back')
        ):
            # LevelMainScene can coexist with the departing main hierarchy.
            # Hide only the departing main aliases; original Main/Event/Archive
            # page readers retain ownership of the destination classification.
            return False
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and not observation_oracle.exists('campaign-menu/page/back')
            and not observation_oracle.enabled("overlay/network-reconnect/confirm")
            and not observation_oracle.enabled("overlay/bulletin/close")
            and observation_oracle.main_page_visible()
        ):
            # The exact unobstructed main hierarchy owns the first page in
            # ALAS' registry.  Classify it before unrelated task readers so a
            # page sweep cannot outlive the next server reconnect interval.
            return name in ("MAIN_GOTO_FLEET", "MAIN_GOTO_CAMPAIGN_WHITE")
        mission_page_state = getattr(observation_oracle, "mission_page_state", None)
        if (
            not self._login_flow.active
            and name in CURRENT_RAID_EARLIER_PAGE_CHECKS
            and callable(mission_page_state)
            and observation_oracle.exists("task/page/back")
        ):
            try:
                mission_page_state()
            except SemanticGateClosed:
                # A retained TaskScene back control below an award or another
                # blocker is not enough to expose the underlay as the current
                # page.  The owning overlay keeps its separate typed action.
                pass
            else:
                # Reward.reward_mission() intentionally returns on TaskScene.
                # Page.iter_pages() probes several unrelated legacy pages
                # before MISSION_CHECK, so classify only the fully reviewed
                # TaskScene identity and let ALAS use its normal page graph.
                return name == "MISSION_CHECK"
        if (
            not self._login_flow.active
            and name in CURRENT_RAID_EARLIER_PAGE_CHECKS
            and observation_oracle.exists("event-list/page/back")
            and not any(
                observation_oracle.exists(target)
                for target in (
                    "reward/award-info/close",
                    "reward/award-info1/close",
                )
            )
        ):
            # ActivityMainUI is the exact full-screen event/month-sign page.
            # Generic Page enumeration probes unrelated legacy identities such
            # as FLEET_CHECK before it reaches EVENT_LIST_CHECK.  Classify only
            # that owning page as present so ALAS follows its normal page graph
            # and GOTO_MAIN uses the reviewed event-list/page/back target.
            # A mounted award overlay is deliberately excluded and remains
            # owned by its separate exact close action.
            return name == "EVENT_LIST_CHECK"
        if name == "RAID_CHECK":
            return (
                observation_oracle.observation_surface_present(ObservationSurface.CURRENT_RAID)
                and observation_oracle.raid_page_visible(event="raid_20260827")
            )
        if (
            name in CURRENT_RAID_EARLIER_PAGE_CHECKS
            and observation_oracle.observation_surface_present(ObservationSurface.CURRENT_RAID)
        ):
            # Page.iter_pages() checks these exact page identities before it
            # reaches RAID_CHECK. The full-screen owner proves them absent
            # without parsing Raid cards. RAID_CHECK and inputs still require
            # their complete contracts, including a valid sprite layout.
            return False
        if observation_oracle.observation_surface_present(ObservationSurface.STORY):
            # Page enumeration must not expose any underlay while the exact
            # modern story overlay is mounted. The original ALAS
            # ui_additional()->handle_story_skip() path reads and acts on the
            # typed story surface directly, without an appear() probe.
            return False
        if time.monotonic() <= self._event_story_transition_until:
            # The exact story input above owns one short Unity remount window.
            # Presence-only page enumeration may wait through it, while click()
            # remains mapped and fail-closed independently.
            return False
        if self._campaign_context is not None and name in (
            "RETIRE_APPEAR_1",
            "RETIRE_APPEAR_2",
            "RETIRE_APPEAR_3",
        ):
            if not self.campaign_dock_full_visible():
                return False
            # The middle choice is dock expansion and may consume premium
            # currency. It is intentionally never exposed to ALAS.
            return name != "RETIRE_APPEAR_2"
        if name in ("ACTION_POINT_USE", "ACTION_POINT_CANCEL"):
            self._package_gate()
            try:
                self.oracle.operation_siren_action_point_state()
            except SemanticGateClosed:
                return False
            return True
        if name == "BATTLE_PREPARATION" and self._meta_beacon_active:
            try:
                self.oracle.meta_current_detail_state()
                # AshCombat probes the generic fleet-preparation button before
                # its own ASH_START control.  On the META detail page the
                # similarly placed start button is not DailyLevelUI.
                return False
            except SemanticGateClosed:
                pass
        if (
            not self._login_flow.active
            and name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3")
            and self._operation_siren_allows_passive_probe()
        ):
            self._package_gate()
            return self._award_close_target() is not None
        return UNHANDLED

    def _appear_confirmation(self, name):
        if (not self._login_flow.active
                and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
                and self.oracle.exists("research/progress/confirm")):
            target = "research/progress/confirm" if name == "POPUP_CONFIRM" else "research/progress/cancel"
            return self.oracle.enabled(target)
        if (
            self._campaign_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                return True
        if (
            self._commission_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
            and self._commission_context.start_receipt is not None
        ):
            cost = self.oracle.commission_start_prompt_cost()
            if cost is None:
                return False
            expected_cost = self._commission_context.selected_oil_cost
            if expected_cost is None or cost != expected_cost:
                raise SemanticGateClosed("commission start oil cost changed")
            return self._commission_context.start_confirm_receipt is None
        return UNHANDLED

    def _appear_blocking_overlay(self, name):
        if (
            name not in ("LOGIN_ANNOUNCE", "LOGIN_ANNOUNCE_2")
            and self.oracle.enabled("overlay/bulletin/close")
        ):
            # A bulletin may be mounted after a task has already established
            # its flow context (for example immediately after a cold login).
            # Page enumeration must see every underlying page probe as false
            # until ui_additional() reaches the exact close target.
            return False
        if (
            name not in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL")
            and self.oracle.enabled("overlay/guild-message/close")
        ):
            # GuildMsgBoxUI is a global overlay that may appear while a task
            # is navigating between unrelated pages.  Hide every underlying
            # page identity until ui_additional() reaches the reviewed close
            # target; do not infer or click through the overlay.
            return False
        if (
            not self._login_flow.active
            and self._mission_context is None
            and self._mail_context is None
            and self._commission_context is None
            and self._research_context is None
            and self._dorm_context is None
            and self._build_context is None
            and self._campaign_context is None
            and name not in ("LOGIN_ANNOUNCE", "LOGIN_ANNOUNCE_2")
            and (
                self.oracle.enabled("login/enter")
                or self.oracle.enabled("overlay/bulletin/close")
            )
        ):
            # Page enumeration precedes ui_additional(); every page identity,
            # including virtual identities, is false on the exact login or
            # bulletin overlay so ALAS reaches its own additional handlers.
            return False
        return UNHANDLED

    def _appear_passive_surface(self, name, semantic_id):
        if (
            semantic_id is None
            and self._campaign_context is None
            and self._operation_siren_allows_passive_probe()
        ):
            if name == "IN_MAP":
                # IN_MAP is shared with campaign code, but on an exact OpSi
                # local-map shell it is a positive typed identity.  Returning
                # the generic passive miss here strands AP-popup and other
                # OpSi close loops after their overlay has already unmounted.
                return self.oracle.operation_siren_local_map_visible()
            if name == "CAMPAIGN_MENU_CHECK":
                # Operation Siren startup legitimately begins on the campaign
                # menu after a reconnect or a previous task returned there.
                # This virtual ALAS resource has an exact semantic identity;
                # do not hide it behind the transition-wide passive-miss rule.
                return self.oracle.campaign_menu_is_entry()
            if name in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"):
                # GuildMsgBoxUI is a reviewed global overlay and can be the
                # first post-login surface seen by an Operation Siren task.
                return self.oracle.enabled("overlay/guild-message/close")
            # Generic Page/ui_additional enumeration probes pixel-only assets
            # such as FLEET_CHECK and WITHDRAW before it reaches OS_CHECK.
            # A proven OS surface or an active semantic OS transition makes
            # those passive probes known absences.  Auto-search remains active
            # beyond its initial 30-second loading lease during long battles,
            # so retirement/page checks must not become unmapped mid-combat.
            return False
        if (
            not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and self.oracle.exists("dorm-menu/page/root")
        ):
            # MainLiveAreaUI is an overlay above the still-mounted main page.
            # The underlying main/build button is not evidence of BuildShipUI;
            # during live-area routes the exact overlay owns page discovery.
            # This also applies to callers such as RewardShop which use the
            # shared ALAS page graph without first opening a dorm/minigame
            # flow context.
            return name == "DORMMENU_CHECK"
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and self._commission_context is None
            and name not in ("BUILD_CHECK", "GOTO_MAIN")
            and name not in BUILD_VIRTUAL_RESOURCES
            and (
                (
                    self._build_context is not None
                    and self._known_build_surface_exists()
                )
                or self._current_build_surface_exists()
            )
        ):
            # Page.check resources include both ordinary assets and virtual
            # identifiers such as EVENT_LIST_CHECK.  A typed construction
            # pool/queue proves all of those unrelated probes absent until
            # enumeration reaches BUILD_CHECK.
            return False
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and name not in DATA_KEY_VIRTUAL_RESOURCES
            and self.oracle.observation_target_present("archive/page/back")
            and self.oracle.war_archives_page_visible()
        ):
            # The exact archive root proves unrelated generic page probes
            # absent until Page enumeration reaches WAR_ARCHIVES_CHECK.
            return False
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and name not in ("BATTLE_PASS_CHECK", "GOTO_MAIN")
            and name not in BATTLE_PASS_VIRTUAL_RESOURCES
            and self.oracle.observation_target_present("battle-pass/home")
            and self.oracle.battle_pass_page_visible()
        ):
            # WorldCruiseUI is an exact full-screen page.  Keep unrelated
            # pixel-only page probes absent until ALAS reaches its own page
            # check; navigation still uses the reviewed top-right home.
            return False
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and name != "SHOP_CHECK"
            and name not in SUPPLY_PACK_VIRTUAL_RESOURCES
            and not self.oracle.exists("research-menu/page/back")
            and (
                (self.oracle.observation_target_present("shop/home")
                 and self.oracle.recommendation_shop_visible())
                or (self.oracle.observation_surface_present(ObservationSurface.GIFT_PACK)
                    and self.oracle.gift_pack_page_visible())
            )
        ):
            # The exact shop/gift-pack surface proves unrelated Page.iter_pages
            # probes absent even when another task inherited this page.  This
            # is presence-only classification: supply-pack input remains
            # limited to the reviewed zero-price card and its own context.
            return False
        if (
            self._mail_context is not None
            and self._mail_context.recovered_existing_page
            and name
            not in (
                "MAIL_CHECK",
                "MAIL_MANAGE",
                "MAIN_GOTO_CAMPAIGN",
                "MAIN_GOTO_CAMPAIGN_WHITE",
                "POPUP_CONFIRM",
                "POPUP_CANCEL",
                "POPUP_CONFIRM_UI_ADDITIONAL",
                "POPUP_CONFIRM_MAIL_CLAIM",
                "POPUP_CONFIRM_MAIL_QUIT",
                *MAIL_VIRTUAL_RESOURCES,
            )
        ):
            # Once an exact MailUI/manager/confirmation surface has been
            # proven, generic Page.iter_pages() checks are known absences.
            # Avoid issuing one observer round trip for every unrelated mapped
            # page before ALAS reaches MAIL_CHECK or the main-page identity.
            return False
        if (
            self._mail_context is not None
            and semantic_id is None
            and name not in MAIL_VIRTUAL_RESOURCES
            and self._known_mail_surface_exists()
        ):
            # Mail page/manager identity makes unrelated generic page and
            # popup probes safely absent during ALAS' enumeration pass.
            return False
        if (
            self._mail_context is not None
            and semantic_id is None
            and name not in MAIL_VIRTUAL_RESOURCES
            and time.monotonic() <= self._mail_context.passive_transition_until
        ):
            # During initial page discovery, unknown pixel-only page checks are
            # passive absences. Mapped exact pages (for example task/page/back)
            # continue below and may be used by ALAS' normal page graph.
            return False
        if (
            self._minigame_context is not None
            and semantic_id is None
            and name not in MINIGAME_VIRTUAL_RESOURCES
            and time.monotonic() <= self._minigame_context.passive_transition_until
        ):
            # The game-room transition mounts several optional pixel-only
            # surfaces. They are passive absences until an exact typed surface
            # below proves the next ALAS state.
            return False
        if name == "BACK_ARROW":
            if self.oracle.exercise_opponent_detail_visible():
                return True
            if self.oracle.daily_precombat_visible():
                return True
            if self.oracle.daily_page_visible():
                return True
        return UNHANDLED

    def _appear_unmapped(self, name, semantic_id):
        if (
            semantic_id is None
            and name not in MISSION_VIRTUAL_RESOURCES
            and name not in MAIL_VIRTUAL_RESOURCES
            and name not in COMMISSION_VIRTUAL_RESOURCES
            and name not in CAMPAIGN_VIRTUAL_RESOURCES
            and name not in PAGE_VIRTUAL_RESOURCES
            and name not in RESEARCH_VIRTUAL_RESOURCES
            and name not in DORM_VIRTUAL_RESOURCES
            and name not in MINIGAME_VIRTUAL_RESOURCES
            and name not in BUILD_VIRTUAL_RESOURCES
            and name not in TACTICAL_VIRTUAL_RESOURCES
        ):
            if (
                self.oracle.main_page_visible()
                or self.oracle.campaign_menu_is_entry()
                or self.oracle.campaign_page_is_normal()
            ):
                # Page.iter_pages() probes legacy pixel-only identities such
                # as FLEET_CHECK before it reaches the exact main/campaign
                # menu check.  Either typed root proves those unrelated page
                # identities absent; inputs remain fail closed.
                return False
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
            ):
                # Generic Page enumeration probes every other page identity
                # before reaching DAILY_CHECK. The exact DailyLevelUI root is
                # sufficient to make those presence-only probes false.
                return False
            if self.oracle.exercise_page_visible():
                # Generic page enumeration reaches EXERCISE_CHECK only after
                # probing unrelated page identities.
                return False
            if self._shipyard_page_visible() or self.oracle.exists(
                "research-menu/page/back"
            ):
                # Generic page enumeration reaches SHIPYARD_CHECK only after
                # probing unrelated page identities. The exact blueprint UI
                # root plus actionable top back control prove those absent.
                return False
            if self.oracle.exists("os/voucher/back"):
                # WorldShopUI can be the retained surface when a voucher task
                # is restarted. Generic Page enumeration reaches no legacy
                # pixel identity for it; the exact typed back control proves
                # all unrelated page probes absent until EXCHANGE_CHECK is
                # queried by the Operation Siren handler.
                return False
            opsi_known = getattr(
                self.oracle, "operation_siren_local_map_visible", lambda: False
            )()
            for opsi_reader in (
                self.oracle.operation_siren_state,
                self.oracle.operation_siren_globe_state,
            ):
                try:
                    opsi_reader()
                except SemanticGateClosed:
                    continue
                opsi_known = True
                break
            if opsi_known:
                # Operation Siren handlers probe many optional tips, rewards,
                # missions and event overlays on every stable map iteration.
                # A proven local/globe identity makes those presence-only
                # probes absent; unknown clicks remain fail-closed.
                return False
            if time.monotonic() <= max(
                self._operation_siren_entry_transition_until,
                self._operation_siren_auto_search_transition_until,
            ):
                # Campaign-menu entry briefly removes both the menu and the
                # Operation Siren roots. Page enumeration is presence-only
                # during this bounded transition; clicks remain fail-closed.
                return False
            if (
                name in UI_PAGE_CHECK_RESOURCES
                and time.monotonic() <= self._private_quarters_home_transition_until
            ):
                # A reviewed PQ home input can leave a brief gap between the
                # private page and actionable main. ALAS may keep enumerating
                # pixel-only pages then; no unknown input is admitted.
                self._package_gate()
                return False
            if (
                self._mission_context is None
                and not self._login_flow.active
                and self._mail_context is None
                and self._commission_context is None
                and self._research_context is None
                and self._dorm_context is None
                and self._minigame_context is None
                and self._build_context is None
                and self._campaign_context is None
                and self._data_key_context is None
            ):
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                )
            self._package_gate()
            if (
                self._login_flow.active
                and time.monotonic()
                <= self._login_flow.snapshot().passive_transition_until
            ):
                return False
            if (
                self._mission_context is not None
                and time.monotonic()
                <= self._mission_context.passive_transition_until
            ):
                return False
            if (
                self._commission_context is not None
                and time.monotonic()
                <= self._commission_context.passive_transition_until
            ):
                return False
            if (
                self._research_context is not None
                and time.monotonic()
                <= self._research_context.passive_transition_until
            ):
                return False
            if (
                self._dorm_context is not None
                and time.monotonic()
                <= self._dorm_context.passive_transition_until
            ):
                return False
            if (
                self._minigame_context is not None
                and time.monotonic()
                <= self._minigame_context.passive_transition_until
            ):
                return False
            if (
                self._build_context is not None
                and time.monotonic()
                <= self._build_context.passive_transition_until
            ):
                return False
            if (
                self._data_key_context is not None
            ):
                # DataKey owns one ALAS page-enumeration/navigation run.  Its
                # lifetime, rather than a machine-speed timeout, scopes passive
                # unknown probes; unmapped input is still rejected by click().
                return False
            if self._battle_pass_context is not None:
                # The BattlePass task lifetime scopes only presence probes;
                # no unknown resource becomes eligible for click().
                return False
            if (
                self._campaign_context is not None
                and time.monotonic()
                <= self._campaign_context.passive_transition_until
            ):
                return False
            if (
                self._login_flow.active
                and self._login_flow.known_surface_exists()
            ) or (
                self._mission_context is not None
                and self._known_mission_surface_exists()
            ) or (
                self._mail_context is not None
                and self._known_mail_surface_exists()
            ) or (
                self._commission_context is not None
                and self._known_commission_surface_exists()
            ) or (
                self._research_context is not None
                and self._known_research_surface_exists()
            ) or (
                self._dorm_context is not None
                and self._known_dorm_surface_exists()
            ) or (
                self._minigame_context is not None
                and self._known_minigame_surface_exists()
            ) or (
                self._build_context is not None
                and self._known_build_surface_exists()
            ) or (
                self._campaign_context is not None
                and self._known_campaign_surface_exists()
            ):
                # ALAS scans many page/popup assets.  An independently proven
                # mission surface lets unknown presence checks be safely false;
                # unknown clicks remain forbidden.
                return False
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(name)
            )
        return UNHANDLED

    def _appear_context(self, name, semantic_id):
        if name == "NEW_OPPONENT":
            return self.oracle.exercise_page_visible()
        if name == "EXERCISE_PREPARATION":
            return self.oracle.exercise_opponent_detail_visible()
        if semantic_id is not None and semantic_id.startswith("exercise/opponent/"):
            return self.oracle.exercise_page_visible()
        if (
            self._campaign_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                return True
        if self._mission_context is not None:
            if (
                semantic_id == "main/more"
                and self._mission_context.summary_entry_clicked
            ):
                return False
            if semantic_id == "main/task" and self._mission_context.entry_clicked:
                return False
        if name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
            prompt_kind = self.oracle.observation_prompt_kind()
            if (prompt_kind == "opsi-exit"
                    and self.oracle.operation_siren_exit_prompt_visible()):
                return True
            if (prompt_kind == "opsi-abyssal-entry"
                    and self.oracle.operation_siren_abyssal_entry_prompt_visible()):
                return True
            if (prompt_kind == "meta-simulation"
                    and self.oracle.meta_simulation_prompt_visible()):
                return True
            if (prompt_kind == "meta-sortie"
                    and self.oracle.meta_assist_sortie_prompt_visible()):
                return True
        return UNHANDLED

    def _appear_pages(self, name):
        if name == "EVENT_LIST_CHECK":
            # Page enumeration also probes this while returning through the
            # campaign menu. Absence of the exact ActivityMainUI back control
            # is a negative observation, not a missing task-flow capability.
            return self.oracle.enabled("event-list/page/back")
        if name in PAGE_VIRTUAL_RESOURCES:
            if name == "BATTLE_PASS_CHECK":
                return (self.oracle.observation_target_present("battle-pass/home")
                        and self.oracle.battle_pass_page_visible())
            if name == "SHOP_CHECK":
                return (self.oracle.observation_target_present("shop/home")
                        and self.oracle.recommendation_shop_visible())
            if name == "WAR_ARCHIVES_CHECK":
                return (self.oracle.observation_target_present("archive/page/back")
                        and self.oracle.war_archives_page_visible())
            if name == "DATA_KEY_COLLECTED":
                if (
                    self._data_key_context is not None
                    and self._data_key_context.collect_receipt is not None
                    and time.monotonic()
                    <= self._data_key_context.passive_transition_until
                    and not self.oracle.war_archives_page_visible()
                ):
                    return False
                return self.oracle.war_archives_data_key_collected()
            if name == "DATA_KEY_COLLECT":
                if (
                    self._data_key_context is not None
                    and self._data_key_context.collect_receipt is not None
                    and time.monotonic()
                    <= self._data_key_context.passive_transition_until
                    and not self.oracle.war_archives_page_visible()
                ):
                    return False
                return not self.oracle.war_archives_data_key_collected()
            if name == "EXERCISE_CHECK":
                if self.oracle.exercise_page_visible():
                    return True
                if (
                    self.oracle.main_page_visible()
                    or self.oracle.enabled("reward/page/back")
                    or self.oracle.enabled("reward/meta/enter")
                    or
                    self.oracle.daily_page_visible()
                    or self.oracle.daily_precombat_visible()
                ):
                    # Page.iter_pages() checks Exercise before the exact main
                    # and reward-page identities.  Those typed roots remain
                    # mounted while Main's More panel opens, so they prove the
                    # unrelated Exercise page absent without pixel inference.
                    return False
                if self.oracle.campaign_menu_is_entry():
                    # ui_goto(page_campaign_menu) probes Exercise first.
                    # The exact campaign-menu root makes this a passive miss.
                    return False
                if self.oracle.campaign_page_is_normal():
                    # Hard and normal chapter pages are also unrelated to
                    # Exercise.  ALAS enumerates pages before navigating back
                    # through the campaign menu.
                    return False
                if self._active_flow_allows_passive_probe():
                    return False
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: EXERCISE_CHECK"
                )
        if name in PAGE_VIRTUAL_RESOURCES:
            if name == "ACADEMY_CHECK":
                return self.oracle.academy_page_visible()
            if name == "MUNITIONS_CHECK":
                try:
                    return self.oracle.munitions_page_visible()
                except SemanticGateClosed:
                    return False
            if name == "NAV_GENERAL":
                try:
                    return self.oracle.shop_general_nav_selected()
                except SemanticGateClosed:
                    return False
            if name == "NAV_MONTHLY":
                try:
                    return self.oracle.shop_selected_nav_label() == "月度商店"
                except SemanticGateClosed:
                    return False
            if name == "TAB_GENERAL":
                try:
                    return self.oracle.shop_general_tab_selected()
                except SemanticGateClosed:
                    return False
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
                try:
                    return self.oracle.shop_selected_tab_label() == shop_tab_labels[name]
                except SemanticGateClosed:
                    return False
            if name == "DAILY_CHECK":
                return bool(
                    self.oracle.daily_page_visible()
                    and not self.oracle.daily_detail_visible()
                )
            if name in ("BATTLE_PREPARATION", "BATTLE_PREPARATION_WITH_OVERLAY"):
                return self.oracle.daily_precombat_visible()
            if name == "DAILY_ENTER":
                return self.oracle.daily_current_active()
            if name == "DAILY_ENTER_CHECK":
                if self.daily_quick_consumed():
                    # The spent card can remain expanded until its reward
                    # arrives. Do not reselect the stage while ALAS waits for
                    # the exact reward close and its completion postcondition.
                    return False
                return bool(
                    self.oracle.daily_detail_visible()
                    and self._award_close_target() is None
                    and not (
                        self._daily_stage in (1, 2, 3)
                        and self.oracle.daily_selected_stage_visible(self._daily_stage)
                    )
                )
            if name.startswith("DAILY_MISSION_"):
                return self.oracle.daily_stage_available(int(name.rsplit("_", 1)[1]))
            if name == "DAILY_LOCKED" and self.oracle.daily_detail_visible():
                return False
            if name == "DAILY_SKIP":
                return self.oracle.daily_run_choice_visible("skip")
            if name == "DAILY_NORMAL_RUN":
                return self.oracle.daily_run_choice_visible("normal")
            if (
                name == "DORM_CHECK"
                and self._dorm_context is not None
                and self.oracle.enabled("dorm/feed/close")
            ):
                # The feed panel is a real nested page, unlike the empty-food
                # modal.  Let ALAS' existing close branch resolve it before
                # declaring the underlying CourtYard page visible.
                return False
            if name == "RESEARCH_CHECK" and self._research_context is not None:
                try:
                    return len(self.oracle.research_projects()) == 5
                except SemanticGateClosed:
                    return False
            if name == "SHIPYARD_CHECK":
                return self._shipyard_page_visible()
            if name == "BUILD_CHECK":
                if self.oracle.exists("build/page/start"):
                    return True
                try:
                    self.oracle.build_queue_timers()
                except SemanticGateClosed:
                    return False
                return True
            target = {
                "DORMMENU_CHECK": "dorm-menu/page/root",
                "DORM_CHECK": "dorm/page/manage",
                "RESHMENU_CHECK": "research-menu/page/back",
                "RESEARCH_CHECK": "research/page/back",
                "SHIPYARD_CHECK": "shipyard/page/root",
                "TACTICAL_CHECK": "tactical/page/back",
            }[name]
            return self.oracle.exists(target)
        return UNHANDLED

    def _appear_navigation(self, name, semantic_id):
        if semantic_id is None and name == "CAMPAIGN_MENU_CHECK":
            return self.oracle.campaign_menu_is_entry()
        if semantic_id is None and name == "ACADEMY_CHECK":
            return self.oracle.academy_page_visible()
        if semantic_id is None and name == "MUNITIONS_CHECK":
            return self.oracle.munitions_page_visible()
        if semantic_id is None and name == "GUILD_CHECK":
            return self.oracle.guild_page_visible()
        if semantic_id is None and name == "NAV_GENERAL":
            return self.oracle.shop_general_nav_selected()
        if semantic_id is None and name == "TAB_GENERAL":
            return self.oracle.shop_general_tab_selected()
        if semantic_id is None and name == "CAMPAIGN_MENU_NO_EVENT":
            return not self.oracle.campaign_event_entrance_available()
        if semantic_id is None and name == "CAMPAIGN_CHECK":
            if self._campaign_context is not None:
                # A completed combat returns directly to the normal chapter
                # page.  Prove that strict identity first: probing a stale
                # preparation layer before this check can keep ALAS waiting
                # after the boss result even though the chapter page is
                # already fully restored.
                try:
                    if self.oracle.campaign_page_is_normal():
                        return True
                except SemanticGateClosed:
                    # The hard fleet overlay deliberately remains mounted
                    # when GemsFarming stops because no replacement ship was
                    # admitted. Its chapter underlay is exact but blocked, so
                    # page identity correctly fails. Report only this passive
                    # CAMPAIGN_CHECK as absent when the covering preparation
                    # layer itself is strictly proven; ALAS then reaches its
                    # existing FLEET_PREPARATION cancel branch.
                    if self._campaign_preparation_kind() is not None:
                        return False
                    if (
                        time.monotonic()
                        <= self._campaign_context.passive_transition_until
                    ):
                        return False
                    raise
                if self._campaign_preparation_kind() is not None:
                    return False
                if (
                    self._campaign_context.map_preparation_receipt is not None
                    and self._campaign_context.cancel_receipt is None
                    and time.monotonic()
                    <= self._campaign_context.passive_transition_until
                ):
                    return False
                return False
            return self.oracle.campaign_page_is_normal()
        if semantic_id is None and name in (
            "BATTLE_PREPARATION",
            "BATTLE_PREPARATION_WITH_OVERLAY",
        ):
            return self.oracle.daily_precombat_visible()
        if semantic_id is None and name == "IN_MAP":
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
                or self.oracle.daily_combat_visible()
                or self.oracle.daily_battle_result_visible()
            ):
                return False
            if (
                self._campaign_context is None
                and self.oracle.operation_siren_local_map_visible()
            ):
                return True
            if self._campaign_context is not None:
                if self._campaign_context.sortie_receipt is not None:
                    try:
                        return self.oracle.campaign_is_in_map()
                    except SemanticGateClosed:
                        if (
                            time.monotonic()
                            <= self._campaign_context.passive_transition_until
                        ):
                            return False
                        raise
                if self._campaign_preparation_kind() is not None:
                    return False
                if (
                    self._campaign_context.map_preparation_receipt is not None
                    and time.monotonic()
                    <= self._campaign_context.passive_transition_until
                ):
                    return False
            return self.oracle.campaign_is_in_map()
        if semantic_id is None and name == "GOTO_MAIN":
            if self._mail_context is not None and self.oracle.enabled("mail/manage/back"):
                return True
            return self._goto_main_target() is not None
        return UNHANDLED

    def _appear_fallback(self, name, semantic_id):
        if semantic_id is None:
            if name in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"):
                # The guild-message popup is a global overlay.  Operation
                # Siren's map-event loop probes it while reading any map, so
                # its exact close target remains observable outside the
                # main-page mission reward flow as well.
                if self.oracle.enabled("overlay/guild-message/close"):
                    return True
                if not any(
                    context is not None
                    for context in (
                        self._mission_context,
                        self._mail_context,
                        self._commission_context,
                        self._research_context,
                        self._dorm_context,
                        self._minigame_context,
                        self._build_context,
                        self._campaign_context,
                    )
                ):
                    return False
            if (
                name in UI_PAGE_CHECK_RESOURCES
                and time.monotonic() <= self._network_reconnect_transition_until
            ):
                # Dismissing the exact NetworkDown overlay can leave every
                # page root non-actionable for a few Unity frames.  Page owners
                # proven above still win immediately; unrelated top-level
                # probes are passive misses until one owner remounts.  This
                # never authorizes input and expires back to fail-closed.
                return False
            if (
                self._minigame_context is not None
                and self._known_minigame_surface_exists()
                and name not in MINIGAME_VIRTUAL_RESOURCES
            ):
                # Generic popup/page handlers probe mission rewards and many
                # unrelated assets while the exact game-room/Fushun surface is
                # already known. Presence is safely false; click() remains
                # fail-closed for all unowned resources.
                return False
            if self._shipyard_page_visible() or self.oracle.exists(
                "research-menu/page/back"
            ):
                # The exact shipyard page owns this enumeration pass. All
                # unrelated virtual page/popup probes are absent until ALAS
                # reaches SHIPYARD_CHECK above.
                return False
            opsi_known = False
            for opsi_reader in (
                self.oracle.operation_siren_state,
                self.oracle.operation_siren_globe_state,
            ):
                try:
                    opsi_reader()
                except SemanticGateClosed:
                    continue
                opsi_known = True
                break
            if opsi_known:
                if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                    return self._award_close_target() is not None
                return False
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
                or self.oracle.daily_combat_visible()
                or self.oracle.daily_battle_result_visible()
            ):
                if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                    return self._award_close_target() is not None
                # Daily's transition loop probes reward, skip, popup and combat
                # resources before accepting BATTLE_PREPARATION.  On the exact
                # DailyLevelUI/PreCombatUI surfaces, unrelated probes are absent.
                return False
            if (
                self._commission_context is not None
                and name in COMMISSION_VIRTUAL_RESOURCES
            ):
                tab_target = COMMISSION_TAB_TARGETS.get(name)
                if tab_target is not None:
                    return self.oracle.image_selected(tab_target)
                if name in ("COMMISSION_ADVICE", "COMMISSION_START"):
                    context = self._commission_context
                    if context.selected_signature is None:
                        return False
                    try:
                        detail = self.oracle.commission_detail_state()
                    except SemanticGateClosed:
                        if time.monotonic() - context.selected_at <= 12.0:
                            return False
                        raise
                    expected = context.selected_signature
                    if detail.signature != (expected[1], expected[2], expected[3]):
                        raise SemanticGateClosed(
                            "selected commission detail identity changed"
                        )
                    if name == "COMMISSION_ADVICE":
                        return detail.selected_ship_count < 3
                    return (
                        context.flow_kind == "commission"
                        and detail.selected_ship_count >= 3
                        and self._action_ledger.allowed("commission.start")
                        and context.start_receipt is None
                    )
                if name == "EXP_INFO_S_REWARD":
                    return self.oracle.enabled("reward/ship-exp/close")
                if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                    return self._award_close_target() is not None
                if name == "GET_SHIP":
                    return False
            if (
                self._mission_context is not None
                and name in MISSION_VIRTUAL_RESOURCES
            ):
                return self._mission_resource_appears(name)
            if self._active_flow_allows_passive_probe():
                # ALAS' generic page and popup loops probe resources owned by
                # unrelated modules.  On an independently proven active-flow
                # surface, those presence-only probes are safely absent; the
                # same resources remain forbidden to click().
                return False
            if name in MAIL_VIRTUAL_RESOURCES and name not in MISSION_VIRTUAL_RESOURCES:
                raise AlasSemanticUnmapped(
                    "ALAS mail resource used outside mail flow: {0}".format(name)
                )
            if name in MISSION_VIRTUAL_RESOURCES:
                raise AlasSemanticUnmapped(
                    "ALAS mission resource used outside mission flow: {0}".format(name)
                )
            raise AlasSemanticUnmapped(
                "ALAS virtual resource has no active semantic flow: {0}".format(name)
            )
        if name == "LOGIN_RETURN_SIGN":
            # ActivityMainUI's rollover/sign-in back button is observed below
            # a decorative raycast layer on current clients.  Its exact path,
            # uniqueness and absence of an award overlay are enforced by
            # SemanticOracle.click().
            return self.oracle.exists("event-list/page/back")
        # enabled() includes active/interactable/bounds and blocker checks.  A
        # Unity object hidden behind an overlay must not count as visible to ALAS.
        return self.oracle.enabled(semantic_id)
        return UNHANDLED
