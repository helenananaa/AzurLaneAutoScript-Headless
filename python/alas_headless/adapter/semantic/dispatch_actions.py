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
from .contracts import AlasSemanticUnmapped
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

    def _click_priority(self, name):
        if (not self._login_flow.active
                and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
                and self.oracle.exists("research/progress/confirm")):
            self._package_gate()
            target = "research/progress/confirm" if name == "POPUP_CONFIRM" else "research/progress/cancel"
            return self.oracle.click(target)
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
                receipt = self.oracle.click(reconnect_target)
                self._network_reconnect_transition_until = time.monotonic() + 20.0
                if self._campaign_context is not None:
                    self._campaign_context.passive_transition_until = (
                        time.monotonic() + 20.0
                    )
                return receipt
        if self._campaign_context is not None and name in (
            "RETIRE_APPEAR_1",
            "RETIRE_APPEAR_2",
            "RETIRE_APPEAR_3",
        ):
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
            if (self.oracle.observation_target_present("exercise/page/back")
                    and self.oracle.exercise_page_visible()):
                return self.oracle.click("exercise/page/back")
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
                and oracle.raid_page_visible("raid_20260827")
            )
            if current_raid_visible:
                return self.click_raid_home("raid_20260827")
            input_oracle = self._fresh_input_oracle()
            if (
                input_oracle.observation_target_present("campaign-menu/page/back")
                and (
                    input_oracle.campaign_menu_is_entry()
                    or input_oracle.campaign_page_is_normal()
                )
                and input_oracle.enabled("campaign-menu/page/back")
            ):
                return input_oracle.click("campaign-menu/page/back")
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
                and name in TACTICAL_VIRTUAL_RESOURCES
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

    def _click_main(self, name, semantic_id):
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
            target = self._goto_main_target()
            if target == 'private-quarters/home':
                return self.oracle.click_private_quarters_home()
            if target == 'meta/character/back':
                return self.oracle.click_meta_character_back()
            if target is None:
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
                raise SemanticGateClosed("GOTO_MAIN has no reviewed page target")
            if target == "os/page/back":
                return self._record_mission_transition(
                    self.oracle.click_operation_siren_back()
                )
            if target == 'daily/page/back':
                return self._record_mission_transition(self.oracle.click_daily_control(target))
            if target == "meta/home":
                return self._record_mission_transition(self.oracle.click_meta_home())
            if target == "raid/page/home":
                return self._record_mission_transition(
                    self.click_raid_home(event="raid_20260827")
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
                    self.oracle.click_recommendation_shop_home()
                )
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
            receipt = self._record_mission_transition(self.oracle.click(target))
            context = self._battle_pass_context
            if context is not None:
                context.home_receipt = receipt
                context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        return UNHANDLED

    def _click_confirmation(self, name):
        if name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
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
            if (prompt_kind == "opsi-exit"
                    and self.oracle.operation_siren_exit_prompt_visible()):
                receipt = self.oracle.click_operation_siren_exit(
                    confirm=name == "POPUP_CONFIRM"
                )
                if name == "POPUP_CONFIRM":
                    self._operation_siren_entry_transition_until = (
                        time.monotonic() + 30.0
                    )
                return receipt
            if (prompt_kind == "opsi-abyssal-entry"
                    and self.oracle.operation_siren_abyssal_entry_prompt_visible()):
                receipt = self.oracle.click_operation_siren_abyssal_entry(
                    confirm=name == "POPUP_CONFIRM"
                )
                if name == "POPUP_CONFIRM":
                    self._operation_siren_entry_transition_until = (
                        time.monotonic() + 30.0
                    )
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
            if (semantic_id == 'research-menu/shipyard' and self._shipyard_entry_receipt is not None
                    and self.oracle.shipyard_page_visible()
                    and self.oracle.read_state().generation > self._shipyard_entry_receipt.generation):
                return self._shipyard_entry_receipt
            if (semantic_id == 'main/tech' and self._main_tech_entry_receipt is not None
                    and self.oracle.observation_target_present('research-menu/page/back')
                    and self.oracle.enabled('research-menu/page/back')
                    and self.oracle.read_state().generation > self._main_tech_entry_receipt.generation):
                # The destination mounted after ALAS observed the fading main
                # frame. Acknowledge the actual entry; do not click its underlay.
                return self._main_tech_entry_receipt
            if semantic_id == 'meta/current/list' and getattr(self.oracle, 'meta_dossier_assist_visible', lambda: False)():
                return self.oracle.click_meta_dossier_current()
            if semantic_id == 'meta/dossier/list':
                return self.oracle.click_meta_dossier_list()
            if (semantic_id == 'main/more' and self._main_more_entry_receipt is not None
                    and self.oracle.observation_target_present('reward/page/back')
                    and self.oracle.enabled('reward/page/back')
                    and self.oracle.read_state().generation > self._main_more_entry_receipt.generation):
                return self._main_more_entry_receipt
            if semantic_id == "campaign-menu/exercise":
                return self.oracle.click_campaign_exercise_entrance()
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
                return self.oracle.click_campaign_event_entrance()
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
                return self.oracle.click_meta_entrance()
            if name in REWARD_RESOURCE_FIELDS:
                return self.oracle.click_reward_resource(
                    REWARD_RESOURCE_FIELDS[name]
                )
            if semantic_id in ("meta/current/open", "meta/dossier/open"):
                return self.oracle.click_meta_card(
                    dossier=semantic_id == "meta/dossier/open"
                )
            if semantic_id == "meta/current/list":
                try:
                    self.oracle.meta_current_detail_state()
                except SemanticGateClosed:
                    pass
                else:
                    return self.oracle.click_meta_current_detail_list()
                return self.oracle.click_meta_current_list()
            if semantic_id == "meta/current/create":
                return self.oracle.click_meta_current_create()
            if semantic_id == "meta/current/help":
                return self.oracle.click_meta_current_help()
            if semantic_id is not None and semantic_id.startswith("meta/help/"):
                return self.oracle.click_meta_help_control(
                    semantic_id.rsplit("/", 1)[1]
                )
            if semantic_id == "meta/assist/start":
                try:
                    self.oracle.meta_current_detail_state()
                except SemanticGateClosed:
                    pass
                else:
                    return self.oracle.click_meta_current_start()
                return self.oracle.click_meta_assist_start()
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
                return receipt
            if semantic_id == "daily/precombat/start" and self._exercise_pending:
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
                self._build_context.coins_owned = self.oracle.main_gold()
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
                if project.status == ResearchProjectStatus.FINISHED:
                    if not self._action_ledger.allowed("research.reward"):
                        raise SemanticGateClosed(
                            "finished research claim requires a positive budget"
                        )
                    receipt = self._dispatch_mutation(
                        "research.reward",
                        lambda: self.oracle.click_research_project(
                            slot, expected_code=project.code
                        ),
                    )
                    self._research_context.reward_receipts.append(receipt)
                    self._research_context.selected_slot = None
                    self._research_context.selected_code = None
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
                    slot, expected_code=project.code
                )
                self._research_context.selected_slot = slot
                self._research_context.selected_code = project.code
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
                    return self._mission_context.summary_entry_receipt
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
                    if context.reward_claim_receipt is not None:
                        return context.reward_claim_receipt
                    # Re-read the finished counter immediately before input so
                    # a second commission completing after the preflight cannot
                    # turn a one-item budget into a multi-claim action.
                    self.commission_reward_pending()
                    if not self.commission_reward_allowed():
                        raise SemanticGateClosed(
                            "commission reward requires finished rows and a positive budget"
                        )
                    receipt = self._dispatch_mutation(
                        "commission.reward",
                        lambda: self.oracle.click(semantic_id),
                    )
                    context.reward_claim_receipt = receipt
                    return self._record_mission_transition(receipt)
                if context.flow_kind != "tactical":
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                if context.tactical_reward_receipt is not None:
                    return context.tactical_reward_receipt
                if not self._action_ledger.allowed("tactical.reward"):
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
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
                and time.monotonic() <= self._main_battle_transition_until
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
            else:
                before_input = getattr(self.oracle, 'input_dispatch_count', 0)
                try:
                    receipt = self.oracle.click(semantic_id)
                except SemanticTargetMissing:
                    if (semantic_id == "research-menu/research"
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input):
                        completed = self._research_entry_completed()
                        if completed is not None:
                            return completed
                    if (semantic_id == 'main/tech' and self._main_tech_entry_receipt is not None
                            and getattr(self.oracle, 'input_dispatch_count', 0) == before_input
                            and self.oracle.observation_target_present('research-menu/page/back')
                            and self.oracle.enabled('research-menu/page/back')
                            and self.oracle.read_state().generation > self._main_tech_entry_receipt.generation):
                        return self._main_tech_entry_receipt
                    if (semantic_id == 'main/battle'
                            and self._main_battle_transition_receipt is not None
                            and time.monotonic() <= self._main_battle_transition_until
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
            if semantic_id == 'main/more':
                self._main_more_entry_receipt = receipt
            if semantic_id == 'research-menu/shipyard':
                self._shipyard_entry_receipt = receipt
            if semantic_id == 'main/tech':
                self._main_tech_entry_receipt = receipt
            if semantic_id == 'main/live':
                self._main_live_entry_receipt = receipt
            if semantic_id == 'dorm-menu/private-quarters':
                self._private_quarters_entry_receipt = receipt
            if semantic_id == "main/battle":
                self._main_battle_transition_receipt = receipt
                self._main_battle_transition_until = time.monotonic() + 20.0
            if semantic_id == "main/shop":
                self._main_shop_transition_receipt = receipt
                self._main_shop_transition_until = time.monotonic() + 20.0
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
            receipt = self._record_mission_transition(receipt)
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
            if not self._action_ledger.allowed("mission.claim"):
                raise SemanticGateClosed(
                    "mission claim input requires the separate one-claim opt-in"
                )
            receipt = self._dispatch_mutation(
                "mission.claim",
                lambda: self.oracle.click("task/claim/all"),
            )
            return receipt
        if name == "MISSION_SINGLE":
            state = self._stable_mission_state()
            if (
                state is None
                or state.disposition != MissionDisposition.CLAIMABLE_ROW
                or len(state.claim_rows) != 1
            ):
                raise SemanticGateClosed("stable mission claim row is absent")
            if not self._action_ledger.allowed("mission.claim"):
                raise SemanticGateClosed(
                    "mission claim input requires the separate one-claim opt-in"
                )
            expected_path = state.claim_rows[0].path
            return self._dispatch_mutation(
                "mission.claim",
                lambda: self.oracle.click_mission_claim_row(expected_path),
            )
        if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
            target = self._award_close_target()
            if target is None:
                raise SemanticGateClosed("reviewed reward popup close is absent")
            return self.oracle.click(target)
        if name == "GET_SHIP":
            if not self.oracle.new_ship_reward_visible():
                raise SemanticGateClosed("reviewed ship reward popup is absent")
            return self.oracle.click("reward/new-ship/continue")
        raise AlasSemanticUnmapped(
            "ALAS resource is not semantically mapped for input: {0}".format(name)
        )
        return UNHANDLED
