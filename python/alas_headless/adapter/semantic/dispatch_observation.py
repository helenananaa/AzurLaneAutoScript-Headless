"""Dispatch observation for the typed ALAS boundary."""

from __future__ import annotations

import time
import re
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

    def _inherited_exercise_precombat(self, oracle):
        return (not self._exercise_pending and not self._exercise_execution_active
                and self._daily_kind is None
                and not self._meta_beacon_active and not self._meta_assist_active
                and oracle.observation_target_present('daily/precombat/back')
                and oracle.daily_precombat_visible() and oracle.exercise_page_visible()
                and not oracle._blocking_rules(oracle.read_state(), 'daily/precombat/back'))

    @staticmethod
    def _reward_sidebar_ready(oracle):
        return (oracle.observation_target_present('reward/page/back')
                and (oracle.enabled('reward/page/back')
                     or any(oracle.enabled(target) for target in (
                         'reward/commission/go', 'reward/commission/finish',
                         'reward/tactical/go', 'reward/tactical/finish',
                         'reward/research/go', 'reward/research/finish'))))

    def _campaign_notice_navigation_surface(self):
        state = self.oracle.read_state()
        blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
        if {rule.blocker_id for rule in blockers} == {'loading', 'campaign-menu'}:
            # Stage entry can retain its chapter while Loading owns the frame.
            # This passive notice probe must let ALAS take its next screenshot;
            # the caller still checks the exact urgent-notice identity.
            return True
        if time.monotonic() <= self._campaign_event_entry_transition_until:
            if not any(rule.blocker_id != 'loading' for rule in blockers):
                # The exact event entrance was submitted; its selector may
                # mount after this screenshot. The notice matcher still runs.
                return True
        if any((b.path == 'LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat'
                or b.path == 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/top_stage/back_button')
               and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons):
            if self.oracle.campaign_is_in_map():
                return True
        if (self.oracle.event_campaign_page_visible()
                or getattr(self.oracle, 'event_campaign_stage_selector_visible', lambda: False)()):
            # The original event page graph already owns this selector.
            # An unrelated urgent-commission probe must not parse it as a
            # normal chapter; its exact notice matcher still runs below.
            return True
        try:
            return self.oracle.campaign_page_is_normal()
        except SemanticGateClosed:
            # Stage details can mount after the first passive owner probe.
            # Re-prove that exact owned layer rather than parsing its underlay.
            if (self._campaign_context is not None
                    and self._campaign_preparation_kind() in ('map', 'fleet')):
                return True
            raise

    def _validate_storage_box_identity(self, detail):
        candidate = getattr(self, '_storage_box_candidate', None)
        if candidate is None:
            raise SemanticGateClosed('storage box selection is not owned by native ALAS')
        prefix = candidate.display_label.rstrip('.…')
        if (detail.rarity != candidate.rarity or detail.icon_sprite != candidate.icon_sprite
                or not prefix or not detail.name.startswith(prefix)):
            raise SemanticGateClosed('storage equipment box detail does not match selected item')

    def _storage_box_resource_present(self, name):
        oracle = self._frame_or_live_observation_oracle()
        state = oracle.read_state()
        blockers = oracle._blocking_rules(state, 'storage/box/passive')
        if (getattr(self, '_storage_box_candidate', None) is not None and blockers
                and all(rule.blocker_id == 'loading' for rule in blockers)):
            # An accepted item/quantity/disassembly entry owns the wait; ALAS owns its
            # next screenshot and timeout. No source control is actionable.
            return False
        root = 'OverlayCamera/Overlay/UIMain/ItemInfoUI(Clone)/'
        detail = any(b.path == root + 'window/actions/use_one_button' for b in state.buttons)
        amount = any(b.path == root + 'operate/actions/confirm_button' for b in state.buttons)
        if detail and amount:
            raise SemanticGateClosed('storage box operation owner is ambiguous')
        if detail:
            observed = oracle.storage_box_detail()
            self._validate_storage_box_identity(observed)
            return name == 'BOX_USE' and observed.use_button.actionable
        if amount:
            observed = oracle.storage_box_amount()
            self._validate_storage_box_identity(observed)
            if name == 'BOX_AMOUNT_CONFIRM':
                return observed.confirm_button.actionable
            if name in ('AMOUNT_MINUS', 'AMOUNT_PLUS'):
                target = observed.minus if name == 'AMOUNT_MINUS' else observed.plus
                return target.raycast_target and target.raycast_top is True and target.bounds is not None
            return False
        receipt = getattr(self, '_storage_box_use_receipt', None)
        if receipt is not None and state.generation > receipt.generation:
            if any(b.path == 'OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/destroy_confirm/actions/destroy_button'
                   for b in state.buttons):
                confirmation = oracle.storage_box_equipment_confirmation()
                selection = getattr(self, '_storage_box_equipment_receipt', None)
                if selection is None or confirmation.generation <= selection.generation:
                    raise SemanticGateClosed('storage equipment confirmation has no owned selection')
                return name == 'EQUIP_CONFIRM_2' and confirmation.confirm_button.actionable
            if any(b.path == 'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close'
                   for b in state.buttons):
                return name == 'GET_ITEMS_1' and oracle.enabled('reward/award-info/close')
            if any(b.path == 'OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/main/ok_btn'
                   for b in state.buttons):
                self._storage_box_equipment_observation(oracle)
                targets = tuple(b for b in state.buttons if b.path ==
                    'OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/main/ok_btn')
                return name == 'EQUIP_CONFIRM' and len(targets) == 1 and targets[0].actionable
        if oracle.storage_material_visible():
            completed = getattr(self, '_storage_box_destroy_receipt', None)
            if completed is not None:
                candidate = self._storage_box_candidate
                item = oracle.storage_material_item(candidate.slot)
                if (item.generation <= completed.generation or item.display_label != candidate.display_label
                        or item.icon_sprite != candidate.icon_sprite
                        or item.quantity != candidate.quantity - self._storage_box_use_quantity):
                    raise SemanticGateClosed('storage box use inventory postcondition did not match')
            return name == 'MATERIAL_CHECK'
        return None

    def _storage_box_equipment_observation(self, oracle):
        equipment = oracle._retirement_equipment_state()
        receipt = getattr(self, '_storage_box_use_receipt', None)
        if (receipt is None or equipment.generation <= receipt.generation
                or sum(count for _, count in equipment.item_quantities) != self._storage_box_use_quantity):
            raise SemanticGateClosed('storage box equipment batch does not match confirmed box use')
        return equipment

    def _appear_priority(self, name):
        if name == 'HOSIPITAL_CHECK':
            from ..task_lifecycle import current_semantic_task
            if current_semantic_task() == 'hospital':
                oracle = self._frame_or_live_observation_oracle()
                if (oracle.event_campaign_page_visible()
                        and not oracle.war_archives_campaign_page_visible()):
                    page = oracle.event_campaign_page_state()
                    raise AlasSemanticUnmapped(
                        'Hospital navigation reached an ordinary event battle selector '
                        f'({page.chapter_name}); the generic event entrance did not '
                        'reach the Hospital activity. Re-entry requires a typed Hospital '
                        'page or a separately identified Hospital entrance')
        if (name in UI_PAGE_CHECK_RESOURCES.union((
                'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'POPUP_CONFIRM', 'POPUP_CANCEL'))
                and (self._commission_context is None
                     or self._commission_context.flow_kind != 'tactical')):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'tactical_continue_prompt_text', lambda: None)() is not None:
                if name in ('POPUP_CONFIRM', 'POPUP_CANCEL'):
                    self._orphan_tactical_prompt_probe = (
                        oracle.read_state().generation, self.oracle.input_dispatch_count)
                # A completed lesson can mount its prompt after Tactical has
                # yielded. Native InfoHandler owns closing this exact inherited
                # modal before its page graph can navigate another task.
                return name in ('POPUP_CONFIRM', 'POPUP_CANCEL')
        if (name == 'EXERCISE_CHECK'
                and (self._exercise_pending or self._exercise_execution_active)
                and self._frame_or_live_observation_oracle().daily_precombat_visible()):
            # The overview remains mounted under preparation. Its accepted
            # entry now belongs to native preparation, not rival selection.
            return False
        if not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if (oracle.observation_target_present('dorm/statistics/confirm')
                    and oracle.enabled('dorm/statistics/confirm')):
                # The native global DORM_INFO handler owns this exact modal,
                # including when a later task inherits it after Dorm defers.
                return name == 'DORM_INFO'
        if not self._login_flow.active and (name in UI_PAGE_CHECK_RESOURCES.union((
                'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'POPUP_CONFIRM', 'POPUP_CONFIRM_WHITE',
                'POPUP_CONFIRM_UI_ADDITIONAL', 'POPUP_CONFIRM_WHITE_UI_ADDITIONAL',
                'RESET_TICKET_POPUP', 'RESET_FLEET_PREPARATION',
                'EXCHANGE_CHECK', 'ORDER_ENTER', 'ORDER_CHECK', 'AUTO_SEARCH_REWARD',
                'WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM'))
                or name.startswith(('POPUP_CONFIRM_', 'POPUP_CANCEL_'))):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'operation_siren_adaptability_info_visible', lambda: False)():
                return (name in ('POPUP_CONFIRM', 'POPUP_CONFIRM_UI_ADDITIONAL',
                                'POPUP_CONFIRM_WHITE', 'POPUP_CONFIRM_WHITE_UI_ADDITIONAL')
                        and oracle.operation_siren_adaptability_info_actionable())
        if not self._login_flow.active and name in UI_PAGE_CHECK_RESOURCES.union((
                'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'GET_SHIP', 'GET_MISSION')):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'operation_siren_order_panel_visible', lambda: False)():
                return name == 'GOTO_MAIN' and oracle.enabled('os/order/back')
        if getattr(self, '_storage_box_candidate', None) is not None and name in (
                'MATERIAL_CHECK', 'BOX_USE', 'BOX_AMOUNT_CONFIRM', 'AMOUNT_MINUS', 'AMOUNT_PLUS',
                'GET_ITEMS_1', 'GET_ITEMS_2', 'EQUIP_CONFIRM', 'EQUIP_CONFIRM_2', 'EQUIPMENT_FULL'):
            observed = self._storage_box_resource_present(name)
            if observed is not None:
                return observed
        if not self._login_flow.active and (name in UI_PAGE_CHECK_RESOURCES or name in ('MATERIAL_CHECK', 'GET_SHIP')):
            storage_oracle = self._frame_or_live_observation_oracle()
            if getattr(storage_oracle, 'storage_page_visible', lambda: False)():
                return (name == 'STORAGE_CHECK' or
                        (name == 'MATERIAL_CHECK' and storage_oracle.storage_material_visible()))
        if (name in ('WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM')
                and self._campaign_context is None
                and not self._login_flow.active):
            oracle = self._frame_or_live_observation_oracle()
            blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
            if (any(rule.blocker_id == 'loading' for rule in blockers)
                    and all(rule.blocker_id in ('loading', 'campaign-menu') for rule in blockers)):
                # The known curtain/menu pair covers these passive probes.
                # A foreign modal must reach the existing owned-surface checks.
                return False
        if not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'campaign_timeout_prompt_visible', lambda: False)():
                # The original generic popup handler owns the expired map.
                # Covered map/page/reward probes must reach that handler.
                return (name in ('POPUP_CONFIRM_WHITE', 'POPUP_CONFIRM_WHITE_UI_ADDITIONAL')
                        and oracle.enabled('campaign/map-timeout/confirm'))
            if (name in ('GOTO_MAIN_WHITE', 'RPG_HOME')
                    and oracle.observation_target_present('campaign-menu/page/back')
                    and oracle.enabled('campaign-menu/page/back')
                    and (oracle.campaign_menu_is_entry() or oracle.campaign_page_is_normal())):
                # Native chapter -> entrance navigation probes these unrelated
                # recovery aliases between screenshots. The proven page uses
                # its own back edge, without acquiring a Mail or RPG owner.
                return False
        if (name in UI_PAGE_CHECK_RESOURCES.union((
                'GET_MISSION', 'WITHDRAW', 'GET_SHIP', 'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3',
                'AUTO_SEARCH_MAP_OPTION_ON', 'AUTO_SEARCH_MAP_OPTION_OFF'))
                and self.campaign_auto_search_owned()):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'campaign_auto_search_map_transition_visible', lambda: False)():
                # Official auto-search animates the HUD before LevelGrid. Its
                # exact shell covers chapter/page and notice probes; native
                # status owns waiting for its next screenshot, without input.
                return False
        if (not self._login_flow.active and self._dorm_context is None
                and name in UI_PAGE_CHECK_RESOURCES.union((
                    'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'))):
            oracle = self._frame_or_live_observation_oracle()
            if self._inherited_dorm_overlay_return(oracle) is not None:
                # A task-local failure may leave its reviewed Feed panel.
                # Native unknown-page recovery owns the same exact close;
                # no underlay page or unrelated Home alias is declared present.
                return name == 'GOTO_MAIN'
        if (name in ('OIL_MAXED', 'REWARD_1', 'REWARD_1_WHITE')
                and self._commission_context is not None
                and self._commission_context.flow_kind == 'commission'):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'commission_reward_oil_maxed', lambda: False)():
                # Let native _commission_receive reach its OilMaxed handler
                # instead of continuing another refused finish click.
                return name == 'OIL_MAXED'
        if (not self._login_flow.active and name in UI_PAGE_CHECK_RESOURCES.union((
                'CAMPAIGN_WITHDRAW_CONFIRM', 'GAME_TIPS'))):
            oracle = self._frame_or_live_observation_oracle()
            if (oracle.observation_target_present('archive/activity-list/home')
                    and getattr(oracle, '_activity_archive_home_proven',
                                lambda state: False)(oracle.read_state())):
                # This full-screen list has an existing reviewed Home port.
                # Native unknown-page recovery owns it; unrelated page and
                # withdrawal probes must not prevent reaching that recovery.
                return False
        if name in UI_PAGE_CHECK_RESOURCES:
            oracle = self._frame_or_live_observation_oracle()
            if any(oracle.observation_target_present(target)
                   for target in ('settings/back', 'player/profile/back')):
                # The inherited page has its own reviewed return.
                # Native unknown-page recovery must precede covered page aliases.
                return False
        if name in UI_PAGE_CHECK_RESOURCES.union((
                'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'BATTLE_PREPARATION',
                'FLEET_PREPARATION', 'MAP_PREPARATION', 'RAID_FLEET_PREPARATION',
                'CAMPAIGN_WITHDRAW_CONFIRM', 'POPUP_SINGLE_WHITE', 'PLAYER_CHECK',
                'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP', 'GET_MISSION',
                'GAME_TIPS', 'DORM_INFO', 'DORM_FEED_CANCEL', 'DORM_TROPHY_CONFIRM',
                'MEOWFFICER_INFO', 'MEOWFFICER_BUY')):
            oracle = self._frame_or_live_observation_oracle()
            if self._inherited_exercise_precombat(oracle):
                # ALAS' existing ui_additional preparation cancellation owns
                # this inherited page; its covered Exercise list is absent.
                return name == 'FLEET_PREPARATION'
        if (not self._login_flow.active and name in UI_PAGE_CHECK_RESOURCES.union((
                'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'GET_SHIP',
                'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_MISSION',
                'CAMPAIGN_WITHDRAW_CONFIRM', 'POPUP_SINGLE_WHITE', 'PLAYER_CHECK',
                'AUTO_SEARCH_REWARD', 'AUTO_SEARCH_MENU_EXIT', 'WITHDRAW',
                'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                'EXERCISE_PREPARATION', 'GAME_TIPS', 'GAME_TIPS3', 'GAME_TIPS4',
                'DORM_INFO', 'DORM_FEED_CANCEL', 'DORM_TROPHY_CONFIRM',
                'MEOWFFICER_INFO', 'MEOWFFICER_BUY', 'LOGIN_RETURN_SIGN',
                'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
                'MAINTENANCE_ANNOUNCE'))):
            oracle = self._frame_or_live_observation_oracle()
            if (oracle.observation_target_present('reward/new-ship/continue')
                    and not oracle._blocking_rules(
                        oracle.read_state(), 'reward/new-ship/continue')
                    and oracle.new_ship_reward_page_visible()):
                # Even a mounting popup hides its navigation underlay. ALAS
                # owns waiting for the next screenshot; only the complete
                # name/type/dialogue proof authorizes its GET_SHIP handler.
                return name == 'GET_SHIP' and oracle.new_ship_reward_visible()
        if name in ('GUILD_POPUP_CONFIRM', 'GUILD_POPUP_CANCEL'):
            oracle = self._frame_or_live_observation_oracle()
            # InfoHandler probes this reviewed global overlay in every task.
            # A complete frame can prove its absence without a Mission owner;
            # its actual close input retains the same independent validation.
            return oracle.enabled('overlay/guild-message/close')
        if (not self._login_flow.active and name in UI_PAGE_CHECK_RESOURCES.union((
                'AUTO_SEARCH_REWARD', 'AUTO_SEARCH_MENU_EXIT', 'WITHDRAW',
                'AUTO_SEARCH_OS_MAP_OPTION_OFF', 'AUTO_SEARCH_OS_MAP_OPTION_OFF_DISABLED',
                'AUTO_SEARCH_OS_MAP_OPTION_ON',
                'CAMPAIGN_WITHDRAW_CONFIRM', 'MAP_PREPARATION', 'FLEET_PREPARATION',
                'RAID_FLEET_PREPARATION', 'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME',
                'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP', 'GET_MISSION',
                'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
                'GAME_TIPS', 'GAME_TIPS3', 'GAME_TIPS4', 'DORM_INFO', 'DORM_FEED_CANCEL',
                'DORM_TROPHY_CONFIRM', 'LOGIN_RETURN_SIGN'))):
            oracle = self._frame_or_live_observation_oracle()
            if oracle.observation_target_present('os/auto-search/reward/close'):
                # A retained foreground reward hides its map underlay. The
                # existing UI.ui_additional AUTO_SEARCH_REWARD handler owns
                # dismissal, including when another task inherits this page.
                return name == 'AUTO_SEARCH_REWARD' and oracle.enabled('os/auto-search/reward/close')
        if (not self._login_flow.active
                and name in UI_PAGE_CHECK_RESOURCES.union((
                    'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP', 'GET_MISSION',
                    'GOTO_MAIN_WHITE', 'RPG_HOME', 'POPUP_SINGLE_WHITE', 'GAME_TIPS',
                    'DORM_TROPHY_CONFIRM', 'PLAYER_CHECK', 'CAMPAIGN_WITHDRAW_CONFIRM',
                    'MEOWFFICER_INFO', 'MEOWFFICER_BUY', 'MONTHLY_PASS_NOTICE',
                    'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON', 'MAINTENANCE_ANNOUNCE',
                    'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION'))
                and (name not in ('CAMPAIGN_WITHDRAW_CONFIRM', 'MAP_PREPARATION',
                                 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION')
                     or self._campaign_context is None)):
            oracle = self._frame_or_live_observation_oracle()
            blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
            if (any(rule.blocker_id == 'loading' for rule in blockers)
                    and all(rule.blocker_id in (
                        'loading', 'commission-page', 'tactical-page', 'dorm-page', 'academy-page',
                        'reward-page', 'research-page', 'research-menu', 'campaign-menu')
                            for rule in blockers)):
                # A known loading layer covers these page, reward and tutorial
                # probes, including ui_additional's unowned withdrawal probe.
                # This includes a departing chapter menu before the event
                # selector mounts. ALAS owns waiting and the next screenshot;
                # active Campaign preparation and foreign modals stay separate.
                return False
        if not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'operation_siren_energy_submission_prompt_visible', lambda: False)():
                # The exact modal owns the foreground; native ui_additional
                # must handle its choices before any covered map back edge.
                return name in ('POPUP_CONFIRM', 'POPUP_CANCEL')
        if (not self._login_flow.active
                and name in UI_PAGE_CHECK_RESOURCES.union(('GAME_TIPS', 'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'))):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'academy_page_visible', lambda: False)():
                blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
                if not any(b.blocker_id != 'academy-page' for b in blockers):
                    # The complete landmark/label proof owns page discovery.
                    # Earlier unrelated page and pixel-tip probes are absent;
                    # the existing ALAS Academy page graph selects its inputs.
                    return name == 'ACADEMY_CHECK'
                if name == 'ACADEMY_CHECK':
                    # Do not fall through to the unoccluded page identity
                    # below when another modal owns the foreground.
                    return False
        if (name in ('MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
                     'POPUP_SINGLE_WHITE', 'PLAYER_CHECK', 'GAME_TIPS', 'DORM_TROPHY_CONFIRM',
                     'MEOWFFICER_INFO', 'MEOWFFICER_BUY', 'MAINTENANCE_ANNOUNCE',
                     'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION', 'WITHDRAW')
                and self._campaign_context is None and not self._login_flow.active):
            oracle = self._frame_or_live_observation_oracle()
            # Native ui_additional scans unrelated popups and preparation
            # pages on META's retained source after Back. Prove that complete
            # uncovered owner; a later live destination is not its evidence.
            # This observation-only branch admits no dismissal or navigation.
            if getattr(oracle, 'meta_character_menu_visible', lambda: False)():
                return False
            if getattr(oracle, 'meta_character_sync_page_visible', lambda: False)():
                oracle.meta_character_sync_rewards()
                return False
        if name in ('POPUP_SINGLE_WHITE', 'PLAYER_CHECK', 'GAME_TIPS', 'DORM_TROPHY_CONFIRM') and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if name != 'GAME_TIPS' and self._reward_sidebar_ready(oracle):
                return False
            if (oracle.observation_target_present('commission/page/back')
                    and oracle.enabled('commission/page/back')):
                # Native ui_additional probes these notices after the Commission
                # back edge. Its unique uncovered page proves only absence;
                # a real modal or ambiguous back target cannot pass enabled().
                return False
        if name in ('MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
                    'MEOWFFICER_INFO', 'MEOWFFICER_BUY', 'MAINTENANCE_ANNOUNCE') and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if time.monotonic() <= self._commission_return_transition_until:
                state = oracle.read_state()
                backs = oracle._matches(state, 'commission/page/back')
                blockers = oracle._blocking_rules(state, 'ui/absence-probe')
                if (len(backs) == 1 and backs[0].active_in_hierarchy
                        and backs[0].active_and_enabled
                        and not any(rule.blocker_id not in ('commission-page', 'loading') for rule in blockers)):
                    # Its back input was accepted. Loading can obscure the
                    # departing source; native ALAS owns the next screenshot.
                    # No repeat source input or notice dismissal is authorized.
                    return False
        if name == 'MAINTENANCE_ANNOUNCE' and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if (self._reward_sidebar_ready(oracle)
                    and not oracle._blocking_rules(oracle.read_state(), 'reward/page/back')):
                # Reward inherits this sidebar after Commission returns. Its
                # uncovered typed owner proves only the unrelated notice absent.
                return False
        if name in ('MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON') and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if oracle.observation_target_present('meta/current/detail/list'):
                # Another task can inherit WorldBossUI after META defers.
                # Its complete unobscured detail proves only notice absence;
                # the original navigation graph still owns leaving this page.
                oracle.meta_current_detail_state()
                return False
            if self._reward_sidebar_ready(oracle):
                return False
            if (oracle.observation_target_present('commission/page/back')
                    and oracle.enabled('commission/page/back')):
                # Original ui_goto probes main popups on the retained list
                # immediately after its reviewed back edge. The exact,
                # unobscured Commission page proves this popup absent.
                return False
            if oracle.observation_target_present('meowfficer/page/back'):
                blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
                if not any(rule.blocker_id not in ('meowfficer-dock', 'loading') for rule in blockers):
                    return False
            if (oracle.observation_target_present('guild/page/back')
                    and getattr(oracle, 'guild_page_mounted', lambda: False)()):
                blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
                if not any(rule.blocker_id not in ('guild-page', 'loading') for rule in blockers):
                    # A complete Guild owner may retain its known loading
                    # curtain while native navigation probes main-page notices.
                    return False
            if (oracle.observation_target_present('dorm/page/manage')
                    and getattr(oracle, '_dorm_back_delegated_raycast_proven',
                                lambda state: False)(oracle.read_state())):
                # A complete uncovered CourtYard may be inherited by the next
                # task. Its return proof excludes these main-page notices.
                self._package_gate()
                return False
        if (self._campaign_context is None and not self._login_flow.active
                and name in ('CAMPAIGN_WITHDRAW_CONFIRM', 'GET_MISSION',
                             'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP',
                             'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
                             'PLAYER_CHECK', 'POPUP_SINGLE_WHITE', 'GAME_TIPS',
                             'DORM_TROPHY_CONFIRM', 'MEOWFFICER_INFO', 'MEOWFFICER_BUY',
                             'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION')):
            oracle = self._frame_or_live_observation_oracle()
            state = oracle.read_state()
            blockers = oracle._blocking_rules(state, 'ui/absence-probe')
            if (not blockers and getattr(oracle, 'inherited_campaign_withdraw_control',
                                        lambda **kw: None)(confirm=False) is not None):
                # Native ui_additional probes these popups before WITHDRAW.
                # The complete uncovered inherited map owns their absence;
                # its original retreat handler still owns the recovery input.
                self._package_gate()
                return False
            if (any(rule.blocker_id == 'campaign-total-reward' for rule in blockers)
                    and all(rule.blocker_id in ('campaign-total-reward', 'campaign-menu')
                            for rule in blockers)
                    and oracle.observation_target_present('reward/campaign-total/exit')
                    and oracle.enabled('reward/campaign-total/exit')):
                # Native UI probes unrelated popups before its retained result
                # exit handler. This exact, uncovered result owns their absence;
                # a foreign overlay or ambiguous exit cannot supply that proof.
                self._package_gate()
                return False
        if name == 'GET_MISSION' and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            state = oracle.read_state()
            if (oracle.observation_target_present('guild/page/back')
                    and getattr(oracle, 'guild_page_mounted', lambda: False)()
                    and not any(rule.blocker_id != 'guild-page' for rule in
                                oracle._blocking_rules(state, 'ui/absence-probe'))):
                # Native ui_ensure probes the urgent-mission notice after
                # entering Guild. Its complete page/nav owner proves absence
                # even after the short entry lease ends. This grants no input.
                self._package_gate()
                if getattr(oracle, '_campaign_urgent_notice_matches',
                           lambda state: False)(state):
                    raise SemanticGateClosed('urgent commission notice has no guild owner')
                return False
            if (oracle.observation_target_present('dorm/page/manage')
                    and not any(rule.blocker_id != 'dorm-page' for rule in
                                oracle._blocking_rules(state, 'ui/absence-probe'))
                    and getattr(oracle, '_dorm_back_delegated_raycast_proven',
                                lambda state: False)(state)):
                self._package_gate()
                notice_matches = getattr(oracle, '_campaign_urgent_notice_matches',
                                         lambda state: False)
                if notice_matches(state):
                    raise SemanticGateClosed('urgent commission notice has no dorm owner')
                # Original navigation can inherit CourtYard after Dorm ends.
                # Its existing back identity proves this passive notice absent.
                return False
        if name == 'COIN' and self._minigame_context is not None:
            oracle = self._frame_or_live_observation_oracle()
            if not oracle.game_room_page_visible() or oracle.game_room_list_visible():
                raise SemanticGateClosed('minigame free coin owner is unavailable')
            if oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe'):
                raise SemanticGateClosed('minigame free coin page is obscured')
            return oracle.observation_target_present('game-room/free-coins')
        if name in UI_PAGE_CHECK_RESOURCES.union(('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME')):
            oracle = self._frame_or_live_observation_oracle()
            if oracle.award_info_page_visible():
                # A reward canvas owns the foreground even before its close
                # button becomes actionable. Native ui_additional owns it.
                return False
            if oracle.observation_target_present('reward/campaign-total/exit'):
                # A prior run can leave its official result after a transport
                # failure. Native AUTO_SEARCH_MENU_EXIT already owns recovery;
                # covered home probes must not enter unrelated Mail dispatch.
                return False
        if name in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'):
            oracle = self._frame_or_live_observation_oracle()
            if self._reward_sidebar_ready(oracle):
                # The sidebar is an owned page even when its generic root
                # cannot be raycast. ALAS uses REWARD_GOTO_MAIN to leave it.
                return False
            if (oracle.observation_prompt_kind() == 'opsi-exit'
                    and oracle.operation_siren_exit_prompt_visible()):
                # Original ui_additional must handle the retained exit popup
                # before ui_get_current_page probes its covered back button.
                return False
        if name in ('WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM', 'MAP_PREPARATION',
                    'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                    'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD') and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'daily_entry_visible', lambda: False)():
                # DailyLevelUI is already a reviewed unobscured destination.
                # Its mounting/return frames must reach native page discovery
                # without acquiring an unrelated campaign preparation owner.
                return False
            if self._meta_dossier_allows_passive_page_probe():
                # ui_additional visits these virtual campaign probes before
                # unknown-page recovery can use the reviewed META home edge.
                return False
            if self._reward_sidebar_ready(oracle):
                # The exact actionable reward hub owns this screenshot even
                # when the previous task left its campaign context attached.
                # Its controls and blocker checks prove these popup probes
                # absent; original ALAS still owns closing the sidebar.
                return False
            if (oracle.observation_target_present('guild/page/back')
                    and (oracle.guild_page_visible() or
                         (callable(getattr(oracle, 'guild_page_mounted', None))
                          and oracle.guild_page_mounted()))):
                blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
                if not any(rule.blocker_id not in ('guild-page', 'loading') for rule in blockers):
                    # The mounted Guild page owns this passive absence even
                    # while a previous task retains its campaign context.
                    return False
            entry = self._main_guild_entry_receipt
            if entry is not None and time.monotonic() <= self._main_guild_entry_until:
                self._package_gate()
                state = oracle.read_state()
                blockers = oracle._blocking_rules(state, 'ui/absence-probe')
                if (state.generation > entry.generation
                        and not any(rule.blocker_id not in ('loading', 'guild-page')
                                    for rule in blockers)):
                    # Native ui_additional runs during the same reviewed
                    # Guild mount as Page checks; this passive popup probe
                    # must also yield to its next screenshot.
                    return False
        if name in ('WITHDRAW','CAMPAIGN_WITHDRAW_CONFIRM','DOCK_CHECK') and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if (self._campaign_context is None
                    and name != 'DOCK_CHECK'
                    and oracle.war_archives_campaign_page_visible()):
                # Other native tasks can inherit an archive chapter with no
                # campaign context. Its strict page proof owns these passive
                # absences; navigation/input still use their reviewed ports.
                return False
            if (oracle.observation_target_present('task/page/back')
                    and not any(rule.blocker_id != 'task-page' for rule in
                                oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe'))):
                # Reward intentionally returns on TaskScene. These passive
                # popup probes are absent there; ALAS owns the page back edge.
                return False
            if (oracle.observation_target_present('dorm/page/manage')
                    and not any(rule.blocker_id != 'dorm-page' for rule in
                                oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe'))):
                return False
            if (oracle.main_page_visible()
                    and not oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')):
                # Main owns these read-only absences even if a task retains
                # its campaign context after returning from another page.
                return False
        if not self._login_flow.active and name in UI_PAGE_CHECK_RESOURCES.union((
                'MEOWFFICER_BUY', 'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME',
                'WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM',
                'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP',
                'GET_MISSION', 'DORM_INFO', 'DORM_FEED_CANCEL', 'DORM_TROPHY_CONFIRM')):
            oracle = self._frame_or_live_observation_oracle()
            if oracle.observation_target_present('meowfficer/buy/max'):
                try:
                    oracle.meowfficer_purchase_state()
                except SemanticGateClosed:
                    pass
                else:
                    # Original ui_additional already owns BUY -> BACK_ARROW.
                    return name == 'MEOWFFICER_BUY'
        if name == 'GET_SHIP' and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
            if (((oracle.main_page_visible() and not blockers)
                    or (oracle.observation_target_present('campaign-menu/page/back')
                        and all(rule.blocker_id == 'campaign-menu' for rule in blockers))
                    or (not blockers and (oracle.meta_character_page_visible()
                        or oracle.meta_character_menu_visible() or oracle.meta_page_visible())))
                    and not oracle.observation_target_present('reward/new-ship/continue')
                    and not oracle.award_info_page_visible()):
                # ui_additional scans this shared ship resource on ordinary
                # navigation too. Its typed owner proves a passive absence;
                # a real reward or foreign overlay keeps its existing handler.
                return False
        if name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3') and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            if (oracle.main_page_visible()
                    and not oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
                    and not any(oracle.enabled(target) for target in (
                        'reward/award-info/close', 'reward/award-info1/close'))):
                # Resolve the proven main-page absence before unrelated task
                # readers. The next native screenshot owns any mounted reward;
                # this grants no input or authority for an unknown layer.
                return False
            if oracle.award_info_page_visible() and self._mission_context is None:
                if self._build_context is not None and name in ('GET_ITEMS_1', 'GET_ITEMS_2'):
                    return self._award_close_target() is not None
                # AwardInfo can be inherited from any original task, including
                # the minigame which bypasses the session's generic fallback.
                return name == 'GET_ITEMS_1' and oracle.enabled('reward/award-info/close')
            if (self._reward_sidebar_ready(oracle)
                    and self._award_close_target() is None):
                # A ready hub owns absence even when a previous task retains
                # its Mission context; no reward or resource input is granted.
                return False
            blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
            if (oracle.observation_target_present('campaign-menu/page/back')
                    and all(rule.blocker_id == 'campaign-menu' for rule in blockers)):
                # Original ui_additional probes rewards during ordinary
                # chapter navigation too. The unobscured typed chapter owner
                # proves absence without a Mission context or stage parsing.
                # Award overlays were handled above; input authority is unchanged.
                return False
            if blockers and all(rule.blocker_id == 'loading' for rule in blockers):
                # A loading curtain proves reward controls unavailable, even
                # when inherited from the preceding scheduler task.
                return False
            if getattr(oracle, 'daily_battle_loading_visible', lambda: False)():
                # The native map-event loop checks rewards before handing a
                # boss encounter to combat. CombatLoadUI also proves their
                # absence when it has no generic Loading button or map shell.
                return False
            if (self._minigame_context is not None and not blockers
                    and self._known_minigame_surface_exists()):
                # A known game page owns absence until its reward canvas
                # mounts. Native screenshot/popup handling observes it next.
                return False
        if name in UI_PAGE_CHECK_RESOURCES and not self._login_flow.active:
            oracle = self._frame_or_live_observation_oracle()
            state = oracle.read_state()
            blockers = oracle._blocking_rules(state, 'ui/absence-probe')
            if (oracle.observation_target_present('minigame/new-year/back')
                    and not blockers
                    and (oracle.new_year_challenge_result() is not None
                         or oracle.new_year_challenge_home_visible())):
                # The generic page graph owns recovery from this exact game;
                # unrelated page markers must reach its GOTO_MAIN edge.
                return False
            if (name not in ('EVENT_CHECK', 'SP_CHECK')
                    and time.monotonic() <= self._campaign_event_entry_transition_until
                    and not any(rule.blocker_id != 'loading' for rule in blockers)):
                # Unrelated pages cannot own this bounded event-entry edge.
                # Both original event page markers retain the full selector
                # contract below; current T stages use SP_CHECK.
                return False
            if (blockers and all(rule.blocker_id == 'campaign-total-reward' for rule in blockers)
                    and oracle.observation_target_present('reward/campaign-total/exit')
                    and oracle.enabled('reward/campaign-total/exit')):
                # ALAS' existing total-reward exit precedes selector discovery.
                return False
            if any(b.path == 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/top_stage/back_button'
                   and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons):
                if oracle.campaign_is_in_map():
                    # A fully identified map covers the still-mounted selector.
                    # The original UI graph owns its withdrawal/recovery edge.
                    return False
        if (self._campaign_context is None and not self._login_flow.active
                and name in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME')):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'inherited_campaign_withdraw_control',
                       lambda **kw: None)(confirm=True) is not None:
                # The original UI confirmation owns this exact modal. A HOME
                # alias cannot navigate through its still-mounted map underlay.
                self._package_gate()
                return False
        if name == 'DOCK_CHECK' and self._campaign_context is not None:
            oracle = self._frame_or_live_observation_oracle()
            state = oracle.read_state()
            if getattr(oracle, 'daily_battle_loading_visible', lambda: False)():
                # Let the original retirement probe yield to the typed loader.
                return False
            if (not any(b.path == 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button'
                        and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons)
                    and any((b.path == 'LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat'
                             or b.path == 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/top_stage/back_button')
                            and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons)
                    and oracle.campaign_is_in_map()):
                return False
        if name in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'):
            oracle = self._frame_or_live_observation_oracle()
            state = oracle.read_state()
            if any((b.path == 'LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat'
                    or b.path == 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/top_stage/back_button')
                   and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons):
                if oracle.campaign_is_in_map():
                    # ALAS' ui_additional withdrawal handler owns leaving a
                    # retained map. No HOME alias may inspect its underlay.
                    return False
        if self._campaign_context is None and name == 'AUTO_SEARCH_MENU_EXIT':
            oracle = self._frame_or_live_observation_oracle()
            if oracle.observation_target_present('reward/campaign-total/exit'):
                return oracle.enabled('reward/campaign-total/exit')
        if (self._campaign_context is None and not self._login_flow.active
                and name in ('WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM')):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'inherited_campaign_withdraw_control', lambda **kw: None)(
                    confirm=name == 'CAMPAIGN_WITHDRAW_CONFIRM') is not None:
                return True
            if (name == 'CAMPAIGN_WITHDRAW_CONFIRM'
                    and getattr(oracle, 'inherited_campaign_withdraw_control',
                                lambda **kw: None)(confirm=False) is not None):
                # Native ui_additional checks the confirmation before the
                # retreat button. A proven inherited map owns that absence;
                # ALAS must reach its existing WITHDRAW branch to open it.
                return False
            # Absence of a withdrawal control does not identify an unknown
            # surface. Continue to the existing owned-surface classifiers.
        if (self._campaign_context is None and not self._login_flow.active
                and name in ('MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                             'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                             'CAMPAIGN_WITHDRAW_CONFIRM', 'GET_MISSION',
                             'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP')):
            oracle = self._frame_or_live_observation_oracle()
            if oracle.observation_target_present('dorm/page/manage'):
                try:
                    # Task-end clears the Dorm flow before goto_main scans
                    # unrelated popups. Prove the retained summary from this
                    # one immutable frame; do not retry that same frame.
                    oracle._dorm_state_once()
                except SemanticGateClosed:
                    pass
                else:
                    return False
        if (self._campaign_context is None and not self._login_flow.active
                and name in ('MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                             'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                             'CAMPAIGN_WITHDRAW_CONFIRM', 'GET_ITEMS_1', 'GET_ITEMS_2',
                             'GET_ITEMS_3', 'GET_SHIP')):
            oracle = self._frame_or_live_observation_oracle()
            if oracle.observation_target_present('meowfficer/page/back'):
                blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
                if not any(rule.blocker_id not in ('meowfficer-dock', 'loading') for rule in blockers):
                    return False
        if (self._campaign_context is None and not self._login_flow.active
                and name in ('MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                             'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                             'CAMPAIGN_WITHDRAW_CONFIRM', 'GET_ITEMS_1', 'GET_ITEMS_2',
                             'GET_ITEMS_3', 'GET_SHIP')
                and time.monotonic() <= self._dorm_return_transition_until):
            oracle = self._frame_or_live_observation_oracle()
            blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
            if not any(rule.blocker_id != 'loading' for rule in blockers):
                # A reviewed CourtYard back edge can precede main's complete
                # hierarchy. Yield unrelated campaign probes to the next frame.
                return False
        if (self._campaign_context is None and not self._login_flow.active
                and name in UI_PAGE_CHECK_RESOURCES.union((
                    'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'MAP_PREPARATION',
                    'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION', 'WITHDRAW',
                    'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD',
                    'CAMPAIGN_WITHDRAW_CONFIRM', 'GET_MISSION',
                    'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP'))):
            oracle = self._frame_or_live_observation_oracle()
            detail = getattr(oracle, 'inherited_event_map_preparation_state', lambda: None)()
            if detail is not None:
                # The original ui_additional handler cancels retained stage
                # details before page discovery; no campaign flow is created.
                return name == 'MAP_PREPARATION'
        if name in ('POPUP_CONFIRM', 'POPUP_CANCEL'):
            oracle = self._frame_or_live_observation_oracle()
            if getattr(oracle, 'meta_skill_full_prompt_visible', lambda: False)():
                return True
        if name in UI_PAGE_CHECK_RESOURCES.union((
                'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD')) and not self._login_flow.active:
            observation_oracle = self._frame_or_live_observation_oracle()
            blockers = observation_oracle._blocking_rules(
                observation_oracle.read_state(), 'ui/absence-probe')
            if (any(rule.blocker_id == 'loading' for rule in blockers)
                    and all(rule.blocker_id in ('loading', 'campaign-menu') for rule in blockers)):
                # Loading owns this screenshot. Let ALAS refresh and time out
                # through its existing unknown-page loop, without reading the
                # transitioning underlay or granting any input.
                # ChapterMenu remains mounted during Daily entry; its own
                # blocker must not make an unrelated page check fatal.
                return False
            if not blockers and observation_oracle.exercise_page_visible():
                # A new task can inherit MilitaryExerciseUI. Its exact page
                # identity must precede task-local unrelated-probe suppression.
                return name == 'EXERCISE_CHECK'
            if (observation_oracle.observation_target_present('tactical/page/back')
                    and not any(rule.blocker_id not in ('tactical-page', 'loading')
                                for rule in blockers)):
                if name != 'TACTICAL_CHECK':
                    # A retained tactical task does not make unrelated page
                    # checks unknown on this same proven classroom surface.
                    return False
                # A following task can inherit the classroom before its back
                # transition publishes Main. Its exact root owns page probes;
                # the native UI graph still owns leaving the classroom.
                if not (self._commission_context is not None
                        and self._commission_context.flow_kind == 'tactical'):
                    return not any(rule.blocker_id == 'loading' for rule in blockers)
            if (getattr(observation_oracle, 'game_room_page_visible', lambda: False)()
                    and observation_oracle.observation_target_present('game-room/home')
                    and not blockers):
                return name == 'GAME_ROOM_CHECK'
        if (name == 'GOTO_MAIN_WHITE' and self._mail_context is None
                and self._frame_or_live_observation_oracle().observation_target_present('task/page/back')):
            # TaskScene uses the original GOTO_MAIN recovery edge. Its exact
            # shell also proves the earlier MailWhite alias absent while a
            # task-list transition temporarily hides MISSION_CHECK.
            return False
        if (name in ('DOSSIER_REWARD_CHECK', 'DOSSIER_REWARD_RECEIVE')
                and self.oracle.observation_target_present('meta/dossier/sync/back')
                and self.oracle.award_info_page_visible()):
            blockers = self.oracle._blocking_rules(self.oracle.read_state(), 'ui/absence-probe')
            if blockers and all(rule.blocker_id in ('award-info', 'loading') for rule in blockers):
                # Original DossierReward probes eligibility before its ordinary
                # reward handler. The result owns this frame, so that covered
                # eligibility control is absent until ALAS closes the result.
                return False
        if name == 'DOSSIER_REWARD_CHECK':
            return self.oracle.meta_dossier_sync_page_visible()
        if name == 'DOSSIER_REWARD_RECEIVE':
            return self.oracle.meta_dossier_sync_reward_available()
        if (name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3')
                and getattr(self.oracle, 'meta_character_menu_visible', lambda: False)()):
            return False
        if (name in ('GET_ITEMS_1', 'GET_ITEMS_2')
                and (getattr(self.oracle, 'meta_character_sync_page_visible', lambda: False)()
                     or ((self._meta_assist_active or self._meta_beacon_active)
                         and self.oracle.award_info_page_visible()))):
            return self._award_close_target() is not None
        if (self._build_context is not None
                and name in ('GET_ITEMS_1', 'GET_ITEMS_2')):
            # A queued construction result may be inherited when ui_ensure
            # starts. Keep ALAS' ordinary reward handler ahead of its page
            # sweep rather than classifying that handler as an absent page.
            return self._award_close_target() is not None
        if (not self._login_flow.active and self._mail_context is None
                and name in UI_PAGE_CHECK_RESOURCES
                and self.oracle.observation_target_present('mail/manage/back')
                and self.oracle.enabled('mail/manage/back')):
            # A retained manager owns the page sweep. ALAS' unknown-page
            # recovery closes this exact layer, then rediscovers MailUI.
            return False
        if (name in ('CAMPAIGN_WITHDRAW_CONFIRM', 'GET_MISSION',
                     'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP',
                     'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
                     'POPUP_SINGLE_WHITE', 'PLAYER_CHECK', 'GAME_TIPS')
                and self._campaign_context is None
                and not self._login_flow.active):
            oracle = self._frame_or_live_observation_oracle()
            if (name == 'CAMPAIGN_WITHDRAW_CONFIRM'
                    and getattr(oracle, 'daily_entry_visible', lambda: False)()):
                return False
            if (name == 'CAMPAIGN_WITHDRAW_CONFIRM'
                    and getattr(oracle, 'meta_character_menu_visible', lambda: False)()):
                return False
            if (name == 'CAMPAIGN_WITHDRAW_CONFIRM'
                    and getattr(oracle, 'meta_character_sync_page_visible', lambda: False)()):
                oracle.meta_character_sync_rewards()
                return False
            state = oracle.read_state()
            if any(b.active_in_hierarchy and b.active_and_enabled and b.path ==
                   'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button'
                   for b in getattr(state, 'buttons', ())):
                self._package_gate()
                if (name == 'GET_MISSION' and getattr(
                        oracle, '_campaign_urgent_notice_matches', lambda state: False)(state)):
                    raise SemanticGateClosed('urgent commission notice has no dock owner')
                context = self._commission_context
                if (context is not None and context.flow_kind == 'tactical'
                        and any(b.active_in_hierarchy and b.active_and_enabled
                                and '/DockyardUI(Clone)/main/ship_container/' in b.path
                                for b in state.buttons)):
                    # Tactical owns a select-mode Dock, including its mounted
                    # classroom underlay. Enhancement capacity/filter artwork
                    # is unrelated to these passive popup probes. Prove the
                    # existing select shell; actual ship/confirm input retains
                    # its own complete identity and actionability checks.
                    back = oracle._unique(state, 'tactical/dock/back')
                    confirm = oracle._unique(state, 'tactical/dock/confirm')
                    if (not all(b.active_in_hierarchy and b.active_and_enabled
                                for b in (back, confirm))
                            or any(rule.blocker_id not in ('tactical-dock', 'tactical-page', 'loading')
                                   for rule in oracle._blocking_rules(state, 'ui/absence-probe'))):
                        raise SemanticGateClosed('Tactical Dock passive surface is incomplete or obscured')
                    return False
                receipt = self._main_dock_transition_receipt
                blockers = oracle._blocking_rules(state, 'ui/absence-probe')
                if (receipt is not None
                        and time.monotonic() <= self._main_dock_transition_until
                        and state.generation > receipt.generation
                        and not any(rule.blocker_id not in ('loading', 'tactical-dock')
                                    for rule in blockers)):
                    # Reuse the accepted entry's existing passive proof before
                    # full Dock parsing retries this same immutable screenshot.
                    # ALAS owns the next screenshot; this authorizes no input.
                    return False
                oracle._enhancement_dock_records()
                if not any(rule.blocker_id not in ('loading', 'tactical-dock')
                           for rule in oracle._blocking_rules(state, 'ui/absence-probe')):
                    # Dockyard is itself labelled tactical-dock by the shared
                    # blocker registry. Its proven page identity still owns
                    # these unrelated passive probes; no input is admitted.
                    return False
        if (name in ('MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                     'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                     'CAMPAIGN_WITHDRAW_CONFIRM') and self._campaign_context is None
                and time.monotonic() <= self._commission_return_transition_until):
            self._package_gate()
            blockers = self.oracle._blocking_rules(self.oracle.read_state(), 'ui/absence-probe')
            if not any(rule.blocker_id not in ('commission-page', 'loading')
                       for rule in blockers):
                return False
        if (name in ('MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                     'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                     'CAMPAIGN_WITHDRAW_CONFIRM') and self._campaign_context is None
                and time.monotonic() <= self._meowfficer_return_transition_until):
            self._package_gate()
            blockers = self.oracle._blocking_rules(self.oracle.read_state(), 'ui/absence-probe')
            if not any(rule.blocker_id not in ('meowfficer-dock', 'loading')
                       for rule in blockers):
                return False
        if (name in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME')
                and self._dorm_context is not None
                and (self.oracle.exists('dorm/statistics/confirm')
                     or self.oracle.exists('dorm/feed/close'))):
            # Unknown-page recovery must reach the native DORM_INFO handler;
            # DORM_FEED_CANCEL owns a retained feed panel. Both surfaces
            # cover the underlying navigation.
            return False
        if (name in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME')
                and self.oracle.award_info_page_visible()
                and (self.oracle.meta_page_visible()
                     or self.oracle.exists('guild/report/close'))):
            # A claimed beacon can switch tasks with its exact reward overlay
            # still mounted. The original unknown-page recovery edge closes
            # this reviewed overlay before re-observing its underlying page.
            return True
        if (name in ('GOTO_MAIN_WHITE', 'RPG_HOME')
                and self.oracle.exists('guild/report/close')):
            return False
        if (name == 'GOTO_MAIN'
                and self.oracle.observation_target_present('minigame/shooting/back')
                and not self.oracle.observation_surface_present(ObservationSurface.MESSAGE_BOX)):
            return self.oracle.shooting_minigame_prepare_visible()
        if (name == 'GOTO_MAIN'
                and self.oracle.observation_target_present('minigame/poke/back')
                and not self.oracle.observation_surface_present(ObservationSurface.MESSAGE_BOX)):
            return self.oracle.poke_minigame_prepare_visible()
        if (name == 'GOTO_MAIN'
                and self.oracle.observation_target_present('minigame/new-year/back')
                and not self.oracle.observation_surface_present(ObservationSurface.MESSAGE_BOX)):
            # Unknown-page recovery must reach the exact Fushun back edge
            # before the task's unrelated passive-probe suppression.
            if self.oracle._blocking_rules(self.oracle.read_state(), 'minigame/new-year/back'):
                return False
            return (self.oracle.new_year_challenge_result() is not None
                    or self.oracle.new_year_challenge_home_visible())
        if name == 'BACK_ARROW' and self.oracle.enhancement_dock_back_control() is not None:
            return True
        if (name in UI_PAGE_CHECK_RESOURCES
                and (self._commission_context is None
                     or self._commission_context.flow_kind == 'commission')):
            # ALAS' page graph owns navigation into Dock. The exact Dock
            # capacity/filter subtree distinguishes it from mounted underlays.
            # Commission can inherit this ordinary page from Awaken too;
            # its active task context does not change the page's identity.
            state = self.oracle.read_state()
            dock_candidate = any(
                    button.active_in_hierarchy
                    and button.path == 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button'
                    for button in getattr(state, 'buttons', ()))
            if dock_candidate:
                try:
                    self.oracle._enhancement_dock_records()
                except SemanticGateClosed:
                    pass
                else:
                    if not any(rule.blocker_id not in ('tactical-dock', 'loading')
                               for rule in self.oracle._blocking_rules(state, 'ui/absence-probe')):
                        return name == 'DOCK_CHECK'
            receipt = self._main_dock_transition_receipt
            if (receipt is not None
                    and time.monotonic() <= self._main_dock_transition_until
                    and state.generation > receipt.generation):
                blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                still_loading = bool(blockers) and all(
                    rule.blocker_id == 'loading' for rule in blockers)
                if still_loading or not self.oracle.main_page_visible():
                    # The Dock is replacing Main after an exact entry receipt.
                    # Page enumeration waits for coherent Dock identity.
                    return False
            if name == 'DOCK_CHECK':
                daily_receipt = self._daily_entry_receipt
                if (daily_receipt is not None
                        and time.monotonic() <= self._daily_entry_transition_until
                        and state.generation > daily_receipt.generation):
                    return False
                exercise_receipt = self._exercise_entry_receipt
                if (exercise_receipt is not None
                        and time.monotonic() <= self._exercise_entry_transition_until
                        and state.generation > exercise_receipt.generation):
                    return False
                blockers = self.oracle._blocking_rules(state, 'ui/absence-probe')
                if not any(rule.blocker_id != 'loading' for rule in blockers):
                    if blockers:
                        return False
                    if time.monotonic() <= max(
                            self._mission_page_return_transition_until,
                            self._exercise_page_back_transition_until,
                            self._exercise_chapter_back_transition_until):
                        return False
                # A known non-Dock owner must reach the remaining page
                # classification below. Unidentified pages still fail in the
                # ordinary fallback; no input is admitted by this probe.
        if (name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP')
                and time.monotonic() <= max(
                    self._meowfficer_return_transition_until,
                    self._guild_return_transition_until,
                    self._main_guild_entry_until,
                )
                and self._award_close_target() is None):
            self._package_gate()
            blockers = self.oracle._blocking_rules(
                self.oracle.read_state(), 'ui/absence-probe')
            if not any(rule.blocker_id not in ('meowfficer-dock', 'guild-page', 'loading')
                       for rule in blockers):
                return False
        if (name in UI_PAGE_CHECK_RESOURCES
                and self.oracle.observation_target_present('meowfficer/page/back')):
            return name == 'MEOWFFICER_CHECK' and self.oracle.enabled('meowfficer/page/back')
        if (name in UI_PAGE_CHECK_RESOURCES
                and self.oracle.observation_target_present('guild/page/back')
                and self.oracle.guild_page_visible()):
            return name == 'GUILD_CHECK'
        if (name in UI_PAGE_CHECK_RESOURCES
                and self.oracle.observation_target_present('mail/page/back')
                and self.oracle.enabled('mail/page/back')):
            return name == 'MAIL_CHECK'
        if (name in UI_PAGE_CHECK_RESOURCES
                and time.monotonic() <= self._main_guild_entry_until
                and not self.oracle.main_page_visible()
                and not self.oracle.guild_page_visible()):
            self._package_gate()
            blockers = self.oracle._blocking_rules(
                self.oracle.read_state(), 'ui/absence-probe')
            if not any(rule.blocker_id != 'loading' for rule in blockers):
                return False
        if (name in UI_PAGE_CHECK_RESOURCES
                and time.monotonic() <= self._mission_page_return_transition_until):
            self._package_gate()
            oracle = self._frame_or_live_observation_oracle()
            blockers = oracle._blocking_rules(
                oracle.read_state(), 'ui/absence-probe')
            if not any(rule.blocker_id != 'task-page' for rule in blockers):
                # TaskScene may unmount before the main page becomes the
                # current frame. An exact task back receipt permits only
                # passive page checks through this bounded transition.
                if (not oracle.exists('task/page/back')
                        and not oracle.main_page_visible()):
                    return False
        if (name in UI_PAGE_CHECK_RESOURCES.union(('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'POPUP_SINGLE_WHITE', 'PLAYER_CHECK'))
                and time.monotonic() <= self._commission_return_transition_until):
            oracle = self._frame_or_live_observation_oracle()
            blockers = oracle._blocking_rules(oracle.read_state(), 'ui/absence-probe')
            if (not any(rule.blocker_id not in ('commission-page', 'loading')
                        for rule in blockers)
                    and not oracle.main_page_visible()
                    and (not oracle.enabled('commission/page/back')
                         or name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'POPUP_SINGLE_WHITE', 'PLAYER_CHECK'))
                    and self._award_close_target() is None):
                # The original back edge has dispatched. Rewards are absent
                # on both the retained Commission page and its unmount; page
                # enumeration still keeps the mounted Commission identity.
                return False
        if name in UI_PAGE_CHECK_RESOURCES.union(('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME')):
            oracle = self._frame_or_live_observation_oracle()
            if self._retained_commission_detail_visible(oracle):
                # The detail is deliberately not reported as the list page.
                # Preserve the native unknown-page loop's one reviewed exit.
                return name == 'GOTO_MAIN'
        if (name in UI_PAGE_CHECK_RESOURCES
                and self.oracle.observation_target_present('commission/page/back')
                and self.oracle.enabled('commission/page/back')):
            # Original Page.iter_pages() scans unrelated page identities
            # before COMMISSION_CHECK even when a previous task left the
            # exact, unobscured commission page mounted.
            return name == 'COMMISSION_CHECK'
        if (name == 'GET_ITEMS_1' and self._commission_context is not None
                and self._commission_context.reward_claim_receipt is None
                and self.oracle.enabled('reward/ship-exp/close')):
            # ui_additional() uses this generic reward-close probe when an
            # interrupted commission left ShipExpUI over the main hierarchy.
            return True
        if (name in ('GOTO_MAIN_WHITE', 'RPG_HOME')
                and not self._login_flow.active and self.oracle.main_page_visible()):
            return False
        if (name in ('GOTO_MAIN_WHITE', 'RPG_HOME')
                and not self._login_flow.active):
            oracle = self._frame_or_live_observation_oracle()
            if (oracle.exercise_page_visible()
                    and not oracle._blocking_rules(
                        oracle.read_state(), 'exercise/page/home')):
                # Complete Exercise identity proves these unrelated aliases
                # absent even while its optional Home control is unmounted.
                # Native recovery still owns the reviewed Back/Home inputs.
                return False
        if (name in ('GOTO_MAIN_WHITE', 'RPG_HOME')
                and not self._login_flow.active
                and self.oracle.observation_target_present('dorm/page/manage')
                and self.oracle.enabled('dorm/page/back')):
            # The retained CourtYard can still be mounting its food counters.
            # Its exact actionable return belongs to the ordinary GOTO_MAIN
            # edge; MailWhite and RPG aliases describe neither this page nor
            # its return control.
            return False
        if (name in ('GOTO_MAIN_WHITE', 'RPG_HOME')
                and not self._login_flow.active
                and self._frame_or_live_observation_oracle().observation_target_present('research/page/back')):
            # Unknown-page recovery probes legacy home aliases while its
            # ordinary GOTO_MAIN interval is still counting down.
            return False
        if (name in ('GOTO_MAIN_WHITE', 'RPG_HOME')
                and not self._login_flow.active
                and self._meta_dossier_allows_passive_page_probe()):
            # The native unknown-page loop owns recovery through GOTO_MAIN.
            # Its other home aliases do not identify controls on this page.
            return False
        if (name in UI_PAGE_CHECK_RESOURCES.union(('GOTO_MAIN_WHITE', 'RPG_HOME'))
                and self.oracle.observation_target_present('meta/home')
                and self.oracle.meta_page_visible()
                and not self.oracle._blocking_rules(self.oracle.read_state(), 'meta/home')):
            # A reviewed WorldBoss page is not the MetaCharacter sync page. Let the
            # native unknown-page recovery reach its reviewed GOTO_MAIN edge.
            return False
        if (name in ('MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                     'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                     'CAMPAIGN_WITHDRAW_CONFIRM')
                and self._campaign_context is None
                and not self.oracle.observation_target_present('campaign/map-preparation/proceed')
                and (self.oracle.main_page_visible()
                     or time.monotonic() <= self._guild_return_transition_until
                     or time.monotonic() <= max(self._private_quarters_home_transition_until,
                                               self._private_quarters_entry_transition_until))):
            # ui_additional also probes this virtual campaign resource
            # on the proven main page and reviewed PQ entry/home transitions.
            self._package_gate()
            if time.monotonic() <= self._guild_return_transition_until:
                blockers = self.oracle._blocking_rules(
                    self.oracle.read_state(), 'ui/absence-probe')
                if any(rule.blocker_id != 'guild-page' for rule in blockers):
                    return UNHANDLED
            return False
        if (
            self._minigame_context is not None
            and name in ("GET_MISSION", "GET_SHIP")
            and self._known_minigame_surface_exists()
            and not self.oracle.new_ship_reward_visible()
            and self._award_close_target() is None
        ):
            self._package_gate()
            return False
        if (name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP')
                and self.oracle.exercise_page_visible()
                and not self.oracle._blocking_rules(self.oracle.read_state(), 'exercise/page/back')):
            # Native navigation can poll popups on the intact inherited page
            # after Back. Its complete identity proves only their absence.
            return False
        if (
            name == "GET_MISSION"
            and self._campaign_context is not None
            and self.oracle.observation_target_present("campaign/map-preparation/cancel")
            and (
                self.oracle.observation_target_present("campaign/map-preparation/proceed")
                or self.oracle.observation_target_present("campaign/map-preparation/proceed-clear")
                or self.oracle.campaign_map_preparation_state(
                    self._campaign_context.stage_code
                ).kind == "map"
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
            name == "GET_MISSION"
            and (
                time.monotonic() <= self._exercise_chapter_entry_transition_until
                or self._campaign_notice_navigation_surface()
                or self.oracle.main_page_visible()
                or self.oracle.observation_target_present('dorm-menu/page/root')
                or getattr(self.oracle, 'private_quarters_page_visible', lambda: False)()
                or self.oracle.observation_target_present('research-menu/page/back')
                or self.oracle.observation_target_present('meowfficer/page/back')
                or time.monotonic() <= self._research_menu_return_transition_until
                or time.monotonic() <= self._commission_return_transition_until
                or time.monotonic() <= self._guild_return_transition_until
                or time.monotonic() <= self._main_guild_entry_until
                or getattr(self.oracle, 'meta_character_menu_visible', lambda: False)()
                or getattr(self.oracle, 'meta_character_page_visible', lambda: False)()
                or time.monotonic() <= self._private_quarters_home_transition_until
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
            name in UI_PAGE_CHECK_RESOURCES.union(('GOTO_MAIN_WHITE', 'RPG_HOME'))
            and time.monotonic() <= self._exercise_entry_transition_until
            and not self.oracle.exercise_page_visible()
        ):
            self._package_gate()
            return False
        if (
            name in (
                "MAP_PREPARATION", "FLEET_PREPARATION", "RAID_FLEET_PREPARATION",
                "AUTO_SEARCH_MENU_EXIT", "AUTO_SEARCH_REWARD", "WITHDRAW", "CAMPAIGN_WITHDRAW_CONFIRM",
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
        if (name in ('BATTLE_PREPARATION', 'BATTLE_PREPARATION_WITH_OVERLAY')
                and (self._exercise_pending or self._exercise_execution_active)):
            # ALAS owns preparation timing and retries. A retained source under
            # Loading is absent; a fresh source may be retried by its original
            # loop. This delegated control uses raycast=None; the generic
            # enabled() predicate requires a direct raycast and cannot describe
            # its readiness. The reviewed input port still checks it fully.
            return (self.oracle.daily_precombat_visible()
                    and not self.oracle._blocking_rules(
                        self.oracle.read_state(), 'daily/precombat/start'))
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
            observation_oracle = self._frame_or_live_observation_oracle()
            if not observation_oracle.shipyard_page_visible():
                return False
            phase = observation_oracle.shipyard_active_phase()
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
        if (not self._login_flow.active and self._campaign_context is None
                and name in ('MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                             'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                             'CAMPAIGN_WITHDRAW_CONFIRM')
                and observation_oracle.observation_target_present('research/page/back')
                and not observation_oracle.observation_target_present('campaign/map-preparation/proceed')):
            blockers = observation_oracle._blocking_rules(observation_oracle.read_state(), 'ui/absence-probe')
            if {rule.blocker_id for rule in blockers} == {'loading', 'research-page'}:
                # Research can hand off while its reviewed Loading still covers
                # Back. This passive probe yields to ALAS' next screenshot.
                return False
        if (not self._login_flow.active and self._campaign_context is None and name in (
                'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
                'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
                'CAMPAIGN_WITHDRAW_CONFIRM')
                and not observation_oracle.observation_target_present('campaign/map-preparation/proceed')
                and (observation_oracle.main_page_visible()
                     or observation_oracle.observation_target_present('dorm-menu/page/root')
                     or getattr(observation_oracle, 'private_quarters_page_visible', lambda: False)()
                     or observation_oracle.campaign_menu_is_entry()
                     or observation_oracle.campaign_page_is_normal()
                     or (observation_oracle.observation_target_present('research/page/back')
                         and observation_oracle.enabled('research/page/back'))
                     or (observation_oracle.observation_target_present('research-menu/page/back')
                         and observation_oracle.enabled('research-menu/page/back')))):
            state = observation_oracle.read_state()
            blockers = observation_oracle._blocking_rules(state, 'ui/absence-probe')
            if not any(rule.blocker_id not in ('campaign-menu', 'research-menu', 'research-page') for rule in blockers):
                # UI.ui_additional scans these Campaign resources without a
                # Campaign task. An unobscured navigation page proves their
                # absence; ignore only that navigation page's own blocker,
                # while actual overlays keep their owned handling below.
                return False
        if (not self._login_flow.active and name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP')
                and self._mission_context is None
                and ((observation_oracle.main_page_visible()
                      and not observation_oracle._blocking_rules(
                          observation_oracle.read_state(), 'ui/absence-probe'))
                     or observation_oracle.campaign_menu_is_entry()
                     or observation_oracle.enabled('reward/page/back')
                     or (observation_oracle.observation_target_present('commission/page/back')
                         and observation_oracle.enabled('commission/page/back'))
                     or time.monotonic() <= self._build_return_transition_until
                     or observation_oracle.observation_target_present('dorm-menu/page/root')
                     or observation_oracle.observation_target_present('research-menu/page/back')
                     or time.monotonic() <= self._research_menu_return_transition_until
                     or getattr(observation_oracle, 'private_quarters_page_visible', lambda: False)())
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
            if (self._campaign_context is None
                    and observation_oracle.war_archives_campaign_page_visible()):
                # This chapter has no native Page entry. Unrelated tasks must
                # finish page enumeration, then let ALAS use its existing
                # unknown-page Back recovery, rather than require a Campaign
                # flow merely to observe that other pages are absent.
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
            if getattr(observation_oracle, 'meta_character_menu_visible', lambda: False)():
                return name in ('META_CHECK', 'META_MENU_CHECK')
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
        if name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
            reset_oracle = self._frame_or_live_observation_oracle()
            if reset_oracle.observation_surface_present(ObservationSurface.RESET_SHOP):
                if name == "POPUP_CANCEL":
                    from ...opsi_monthstart import reset_shop
                    return reset_shop(reset_oracle, cancel=True) is not None
                return reset_oracle.operation_siren_reset_shop_visible()
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.observation_target_present("reward/page/back")
        ):
            # The reward sidebar retains the main hierarchy underneath. Its
            # own page must win or ALAS repeatedly toggles the expand button.
            return name == "REWARD_CHECK" and self._reward_sidebar_ready(observation_oracle)
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.exists("research-menu/page/back")
        ):
            # This exact full-screen owner is enough to classify ALAS' page
            # sweep before any unrelated task-specific reader runs.  Inputs
            # still go through their individual typed mappings and raycasts.
            return name == "RESHMENU_CHECK"
        if (not self._login_flow.active and name in UI_PAGE_CHECK_RESOURCES
                and self._dorm_context is None
                and observation_oracle.exists("dorm/page/manage")):
            # Later tasks can inherit CourtYard after Dorm has returned.
            # Classify its proven summary before unrelated page readers run.
            if (name != "DORM_CHECK"
                    or observation_oracle.exists("dorm/statistics/confirm")
                    or observation_oracle.enabled("dorm/feed/close")):
                return False
            try:
                observation_oracle.dorm_state()
                return True
            except SemanticGateClosed:
                return False
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
            return observation_oracle.research_page_visible()
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.observation_target_present("shop/home")
            and observation_oracle.recommendation_shop_visible()
        ):
            if getattr(observation_oracle, 'munitions_page_visible', lambda: False)():
                return name == "MUNITIONS_CHECK"
            if (self._supply_pack_context is not None
                    and observation_oracle.gift_pack_page_visible()):
                return name == "SUPPLY_PACK_CHECK"
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
            and (observation_oracle.observation_target_present('reward/award-info/close')
                 or observation_oracle.observation_target_present('reward/award-info1/close')
                 or observation_oracle.observation_target_present('reward/ship-exp/close'))
            and any(rule.blocker_id in ('ship-exp', 'award-info', 'award-info1')
                    for rule in observation_oracle._blocking_rules(
                        observation_oracle.read_state(), 'ui/absence-probe'))
        ):
            # ALAS must reach ui_additional() to close the exact reward
            # overlay before its page graph can classify the underlying page.
            # A mounted overlay still covers that page while its close is not
            # yet actionable; input continues to require the full close proof.
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
        mission_probe = name in UI_PAGE_CHECK_RESOURCES.union((
            'GET_MISSION', 'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP',
            'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
            'LOGIN_RETURN_SIGN', 'PLAYER_CHECK', 'POPUP_SINGLE_WHITE',
            'GAME_TIPS', 'GAME_TIPS3', 'GAME_TIPS4', 'DORM_INFO', 'DORM_FEED_CANCEL',
            'DORM_TROPHY_CONFIRM', 'MEOWFFICER_INFO', 'MEOWFFICER_BUY',
            'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
            'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'WITHDRAW',
            'CAMPAIGN_WITHDRAW_CONFIRM', 'EXERCISE_PREPARATION', 'MAINTENANCE_ANNOUNCE'))
        mission_oracle = self._frame_or_live_observation_oracle() if mission_probe else observation_oracle
        mission_page_state = getattr(mission_oracle, "mission_page_state", None)
        if (
            not self._login_flow.active
            and mission_probe
            and callable(mission_page_state)
            and mission_oracle.exists("task/page/back")
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
                notice_matches = getattr(mission_oracle, '_campaign_urgent_notice_matches', lambda state: False)
                if name != 'GET_MISSION' or not notice_matches(mission_oracle.read_state()):
                    # Generic reward handlers also enumerate on a complete
                    # TaskScene after another task inherits it. A real reward
                    # or foreign overlay prevents this page proof above.
                    return name == "MISSION_CHECK"
        if (
            not self._login_flow.active
            and name in CURRENT_RAID_EARLIER_PAGE_CHECKS.union(('DOCK_CHECK',))
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
                and observation_oracle.raid_page_visible(event=observation_oracle.current_raid_event())
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
        if name in (
            "RETIRE_APPEAR_1",
            "RETIRE_APPEAR_2",
            "RETIRE_APPEAR_3",
        ) and self.dock_full_recovery_owned():
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
        if (semantic_id is None and name in UI_PAGE_CHECK_RESOURCES
                and self._meta_dossier_allows_passive_page_probe()):
            return False
        if (
            semantic_id is None
            and (self._campaign_context is None
                 or self._campaign_context.sortie_receipt is None)
            and (name != "IN_MAP" or self._campaign_context is None)
            and self._operation_siren_allows_passive_probe()
        ):
            if name == "IN_MAP":
                # IN_MAP is shared with campaign code, but on an exact OpSi
                # local-map shell it is a positive typed identity.  Returning
                # the generic passive miss here strands AP-popup and other
                # OpSi close loops after their overlay has already unmounted.
                return (self._campaign_context is None
                        and self.oracle.operation_siren_local_map_visible())
            if name == "CAMPAIGN_MENU_CHECK":
                # Operation Siren startup legitimately begins on the campaign
                # menu after a reconnect or a previous task returned there.
                # This virtual ALAS resource has an exact semantic identity;
                # do not hide it behind the transition-wide passive-miss rule.
                return self.oracle.campaign_menu_is_entry()
            if name == "GOTO_MAIN":
                # META uses the original unknown-page recovery during its
                # task scope. Its reviewed home edge is not an absent asset.
                return self._goto_main_target() is not None
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
            and name not in (
                "NAV_GENERAL", "NAV_MONTHLY", "TAB_GENERAL", "TAB_MERIT",
                "TAB_GUILD", "TAB_META", "TAB_PRIZE", "TAB_CORE_LIMITED",
                "TAB_CORE_MONTHLY", "TAB_MEDAL", "TAB_PROTOTYPE",
            )
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
            and name not in ('BUILD_CHECK', 'GOTO_MAIN')
            and time.monotonic() <= self._minigame_context.passive_transition_until
        ):
            # The game-room transition mounts several optional pixel-only
            # surfaces. Keep those passive, but let ALAS recognize an inherited
            # build queue and use its reviewed shared return before this grace
            # expires. A new Minigame flow does not own the inherited page.
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
            if (self._inherited_dorm_overlay_return() == 'dorm/feed/shop/cancel'
                    or self._inherited_dorm_page_visible()):
                return False
            if (getattr(self.oracle, 'private_quarters_page_visible', lambda: False)()
                    and self.oracle.enabled('private-quarters/home')
                    and not self.oracle._blocking_rules(self.oracle.read_state(), 'ui/absence-probe')):
                # An unobscured SelectDorm3DUI owns these legacy page/popup
                # probes. Its mapped controls still use their normal ports.
                return False
            if self._meta_dossier_allows_passive_page_probe():
                # A different task can inherit a running dossier page. Its
                # coherent list/HP identity owns unrelated presence probes;
                # optional auto phases and task input remain independently gated.
                return False
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
            if (self.oracle.observation_target_present("meowfficer/page/back")
                    and not any(rule.blocker_id not in ('meowfficer-dock', 'loading')
                                for rule in self.oracle._blocking_rules(
                                    self.oracle.read_state(), 'ui/absence-probe'))):
                # A previous task can leave the exact Commander Cat page
                # mounted under its loading layer. Unrelated popup/page
                # absence needs no actionable Back button; native discovery
                # waits for Loading and input keeps its own complete proof.
                return False
            if self.oracle.observation_target_present('meowfficer/buy/max'):
                try:
                    self.oracle.meowfficer_purchase_state()
                except SemanticGateClosed:
                    pass
                else:
                    return False
            if getattr(self.oracle, 'guild_page_visible', lambda: False)():
                # GuildUI also owns the unrelated popup/page absence probes
                # after another task navigates here through the native graph.
                return False
            if time.monotonic() <= self._main_guild_entry_until:
                self._package_gate()
                blockers = self.oracle._blocking_rules(self.oracle.read_state(), 'ui/absence-probe')
                if not any(rule.blocker_id != 'loading' for rule in blockers):
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
            if time.monotonic() <= self._research_menu_return_transition_until:
                # The reviewed Research back input briefly leaves neither
                # TechnologyUI nor SelectTechnologyUI mounted.  ALAS scans
                # unrelated presence-only assets during that gap.  A new
                # overlay still fails closed, and click() gains no authority.
                self._package_gate()
                blockers = self.oracle._blocking_rules(
                    self.oracle.read_state(), 'ui/absence-probe'
                )
                if not any(rule.blocker_id not in ('research-page', 'research-menu')
                           for rule in blockers):
                    return False
            if time.monotonic() <= self._guild_return_transition_until:
                self._package_gate()
                blockers = self.oracle._blocking_rules(
                    self.oracle.read_state(), 'ui/absence-probe')
                if not any(rule.blocker_id != 'guild-page' for rule in blockers):
                    # The reviewed Guild back edge can briefly leave neither
                    # GuildUI nor the main root current. Unknown passive
                    # ui_additional probes are absent during that gap.
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
            if (self._mission_context is not None
                    and self._frame_or_live_observation_oracle().mission_overflow_prompt_visible()):
                return True
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
        if name == 'PRIVATE_QUARTERS_CHECK':
            # This is an existing typed page identity. During a page handoff,
            # its missing exact root is a passive miss rather than an
            # unavailable resource; ALAS owns the next screenshot/navigation.
            return self._frame_or_live_observation_oracle().private_quarters_page_visible()
        if name == "EVENT_LIST_CHECK":
            # Page enumeration also probes this while returning through the
            # campaign menu. Absence of the exact ActivityMainUI back control
            # is a negative observation, not a missing task-flow capability.
            return self.oracle.enabled("event-list/page/back")
        if name in PAGE_VIRTUAL_RESOURCES:
            if name == "GUILD_CHECK":
                return self.oracle.guild_page_visible()
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
            if name == "DORM_CHECK" and self._dorm_context is not None:
                if (self.oracle.enabled("dorm/feed/close")
                        or self.oracle.exists("dorm/statistics/confirm")):
                    return False
                # Native dorm_feed_enter uses this marker to click feed.
                # CourtYard's manage button can appear before its feed entry
                # becomes actionable or while a statistics overlay mounts.
                return self.oracle.enabled("dorm/feed")
            if name == "RESEARCH_CHECK" and self._research_context is not None:
                # Page discovery has its own reviewed actionable anchor. A
                # card's optional status cannot make the whole page disappear.
                # The decision/input ports still require complete card data.
                return self.oracle.research_page_visible()
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
            if self.oracle.war_archives_campaign_page_visible():
                # Archives share the chapter shell, but native page_campaign
                # denotes the main campaign. Treating archives as that page
                # incorrectly invokes the main hard-mode daily quota reader.
                return False
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
                    if self._commission_selected_row_still_on_list():
                        # ALAS' existing comm_timer owns re-entry after a row
                        # click that left the exact pending list visible.
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
                    visible = self.oracle.enabled("reward/ship-exp/close")
                    self._commission_context.ship_exp_observation_generation = (
                        self.oracle.read_state().generation if visible else None
                    )
                    return visible
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
            # a decorative raycast layer on current clients. A real reward
            # overlay still owns input and must be handled by ALAS first.
            oracle = self._frame_or_live_observation_oracle()
            return (oracle.exists("event-list/page/back")
                    and not oracle._blocking_rules(
                        oracle.read_state(), "event-list/page/back"))
        # enabled() includes active/interactable/bounds and blocker checks.  A
        # Unity object hidden behind an overlay must not count as visible to ALAS.
        return self.oracle.enabled(semantic_id)
        return UNHANDLED
