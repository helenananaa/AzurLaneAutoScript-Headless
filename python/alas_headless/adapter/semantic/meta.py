"""Meta for the typed ALAS boundary."""

from __future__ import annotations

from typing import Tuple
import time
from ...semantic_oracle import (
    ActionReceipt,
    MetaAssistState,
    MetaCurrentDetailState,
    MetaEntranceState,
    SemanticGateClosed,
)
from .dispatch_result import UNHANDLED
from .contracts import AlasSemanticUnmapped
from .resources import REWARD_RESOURCE_FIELDS


class MetaAdapterPorts:
    """Meta ports on the shared adapter context."""

    def begin_meta_assist(self) -> None:
        self._package_gate()
        self._meta_assist_active = True

    def end_meta_assist(self) -> None:
        self._meta_assist_active = False
        self._meta_reward_close_receipt = None
        self._operation_siren_combat_active = False
        self._meta_precombat_start_receipt = None
        self._meta_precombat_start_until = 0.0
        self._meta_precombat_back_receipt = None
        self._meta_precombat_back_until = 0.0
        self._meta_assist_entry_receipt = None
        self._meta_assist_entry_until = 0.0

    def click_meta_assist_entry(self) -> ActionReceipt:
        self._package_gate()
        prior = self._meta_assist_entry_receipt
        if (self._meta_assist_active and prior is not None
                and time.monotonic() <= self._meta_assist_entry_until
                and self.oracle.daily_precombat_visible()
                and self.oracle.read_state().generation > prior.generation):
            return prior
        receipt = self.oracle.click_meta_assist_start()
        if self._meta_assist_active:
            self._meta_assist_entry_receipt = receipt
            self._meta_assist_entry_until = time.monotonic() + 20.0
        return receipt

    def begin_meta_beacon(self) -> None:
        """Own one complete META beacon task until its explicit finally block."""

        self._package_gate()
        self._meta_beacon_active = True

    def end_meta_beacon(self) -> None:
        self._meta_beacon_active = False
        self._meta_reward_close_receipt = None
        self._meta_precombat_start_receipt = None
        self._meta_precombat_start_until = 0.0

    def meta_beacon_active(self) -> bool:
        return self._meta_beacon_active

    def click_meta_beacon_sortie_confirm(self) -> ActionReceipt:
        self._package_gate()
        if not self._meta_beacon_active:
            raise SemanticGateClosed("META beacon task owner is absent")
        receipt = self.oracle.click_meta_assist_sortie(True)
        self._operation_siren_combat_active = True
        return receipt

    def meta_entrance_state(self) -> MetaEntranceState:
        self._package_gate()
        return self.oracle.meta_entrance_state()

    def meta_page_visible(self) -> bool:
        self._package_gate()
        return self.oracle.meta_page_visible()

    def meta_assist_state(self) -> MetaAssistState:
        self._package_gate()
        for attempt in range(5):
            try:
                return self.oracle.meta_assist_state()
            except SemanticGateClosed as exc:
                if str(exc) != 'META assist snapshots are not coherent' or attempt == 4:
                    raise
                time.sleep(.05)

    def click_meta_assist_next_candidate(
        self, *, expected_index: int, expected_level: int
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_meta_assist_next_candidate(
            expected_index=expected_index,
            expected_level=expected_level,
        )

    def meta_current_empty_points(self) -> Tuple[int, int]:
        self._package_gate()
        return self.oracle.meta_current_empty_points()

    def meta_dossier_empty_points(self) -> Tuple[int, int]:
        self._package_gate()
        return self.oracle.meta_dossier_empty_points()

    def meta_current_detail_state(self) -> MetaCurrentDetailState:
        self._package_gate()
        return self.oracle.meta_current_detail_state()

    def meta_precombat_visible(self) -> bool:
        self._package_gate()
        return self.oracle.daily_precombat_visible()

    def click_meta_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        if (self._meta_assist_active and self._meta_precombat_start_receipt is not None
                and time.monotonic() < self._meta_precombat_start_until):
            return self._meta_precombat_start_receipt
        prior = self._meta_precombat_start_receipt
        if (self._meta_beacon_active and prior is not None
                and time.monotonic() < self._meta_precombat_start_until):
            # The original loop can request start again from its prior frame
            # while the live UI has already accepted this sortie.
            deadline = self._meta_precombat_start_until
            while True:
                state = self.oracle.read_state()
                blockers = self.oracle._blocking_rules(state, 'daily/precombat/start')
                if state.generation > prior.generation and (
                        self.oracle.daily_combat_visible()
                        or getattr(self.oracle, 'daily_battle_loading_visible', lambda: False)()
                        or self.oracle.daily_battle_result_visible()
                        or self.oracle.meta_assist_sortie_prompt_visible()
                        or (blockers and all(b.blocker_id == 'loading' for b in blockers))):
                    return prior
                if time.monotonic() >= deadline:
                    break
                time.sleep(.1)
            raise SemanticGateClosed(
                'META sortie start did not reach a reviewed transition: '
                f'generation={state.generation}, start={prior.generation}, '
                f'blockers={[b.blocker_id for b in blockers]}'
            )
        if self._meta_assist_active and not self._action_ledger.allowed('meta.assist'):
            raise SemanticGateClosed('META assist requires remaining sortie budget')
        if not self.oracle.meta_precombat_fleet_ready():
            raise SemanticGateClosed(
                "META precombat requires non-empty main and vanguard fleets"
            )
        if self._meta_assist_active:
            receipt = self._dispatch_mutation('meta.assist', self.oracle.click_meta_assist_precombat_start)
        else:
            receipt = self.oracle.click_daily_precombat_start()
        if self._meta_assist_active or self._meta_beacon_active:
            self._meta_precombat_start_receipt = receipt
            self._meta_precombat_start_until = time.monotonic() + 20.0
        self._operation_siren_combat_active = True
        return receipt

    def click_meta_precombat_back(self) -> ActionReceipt:
        self._package_gate()
        receipt = self.oracle.click_daily_precombat_back()
        if self._meta_assist_active:
            self._meta_precombat_back_receipt = receipt
            self._meta_precombat_back_until = time.monotonic() + 20.0
        return receipt

    def _appear_meta(self, name, semantic_id):
        if (self._meta_beacon_active
                and name in ('ASH_SHOWDOWN', 'BEACON_LIST', 'DOSSIER_LIST',
                             'HELP_ENTER', 'BEACON_REWARD', 'BATTLE_START',
                             'META_AUTO_CONFIRM', 'META_AUTO_ATTACK_START',
                             'META_AUTO_ATTACKING', 'META_AUTO_ATTACK_CONFIRM')):
            blockers = self.oracle._blocking_rules(
                self.oracle.read_state(), 'ui/absence-probe')
            if blockers and all(rule.blocker_id == 'loading' for rule in blockers):
                # The original META loop must take its next screenshot before
                # classifying a detail page covered by the loading curtain.
                return False
        if (self._meta_beacon_active
                and name in ('ASH_SHOWDOWN', 'BEACON_LIST', 'DOSSIER_LIST',
                             'HELP_ENTER', 'BEACON_REWARD', 'BATTLE_START',
                             'META_AUTO_ATTACK_START', 'META_AUTO_ATTACKING',
                             'META_AUTO_ATTACK_CONFIRM')
                and (self.oracle.observation_target_present('meta/dossier/auto/result/confirm')
                     or any(rule.blocker_id == 'meta-dossier-auto-result'
                            for rule in self.oracle._blocking_rules(
                                self.oracle.read_state(), 'ui/absence-probe')))):
            # The original map-event handler owns this result before the
            # covered detail can classify a new challenge or claim rewards.
            # Its root can mount before the confirm child is published; the
            # full result reader still owns confirmation on a later frame.
            return False
        if self._meta_beacon_active and name == 'META_AUTO_CONFIRM':
            return self.oracle.meta_dossier_auto_result() is not None
        if self._meta_beacon_active and name in ('META_AUTO_ATTACK_START', 'META_AUTO_ATTACKING', 'META_AUTO_ATTACK_CONFIRM'):
            prompt = self.oracle.meta_dossier_auto_prompt() is not None
            summary = self.oracle.meta_dossier_detail_state(allow_auto_prompt=prompt)
            if summary.current_hp == 0 and summary.auto_sprite is None:
                return False
            if summary.auto_sprite == 'auto_01':
                return summary.current_hp > 0 and (name == 'META_AUTO_ATTACK_START'
                    or (name == 'META_AUTO_ATTACK_CONFIRM' and prompt))
            if summary.auto_sprite == 'auto_02':
                return name == 'META_AUTO_ATTACKING' and self.oracle.meta_dossier_auto_remaining_seconds() is not None
            if summary.auto_sprite != 'auto_03':
                raise AlasSemanticUnmapped('META dossier auto phase is unsupported: '+str(summary.auto_sprite))
            # The captured client tooltip proves auto_03 is locked until one
            # ordinary challenge completes. ALAS owns that challenge branch.
            return False
        if name == 'META_MENU_CHECK':
            return self.oracle.meta_character_menu_visible()
        if name == 'META_CHECK':
            return (self.oracle.meta_character_page_visible()
                    or self.oracle.meta_character_menu_visible())
        if name in ('SYNC_ENTER', 'SYNC_ENTER2', 'SYNC_REWARD_NOTICE', 'SYNC_TAP',
                    'META_REWARD_NOTICE', 'REWARD_ENTER'):
            if self.oracle.award_info_page_visible():
                return False
            if self.oracle.meta_character_sync_page_visible():
                _, eligible, claimed = self.oracle.meta_character_sync_rewards()
                if name == 'SYNC_REWARD_NOTICE':
                    return eligible > claimed
                return name == 'REWARD_ENTER' and eligible == claimed
            # These belong to MetaCharacterUI, never WorldBoss's reward preview.
            self.oracle.meta_character_pending_sync()
            return name == 'SYNC_ENTER'
        if name == 'BEACON_MY':
            try:
                self.oracle.meta_assist_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == 'meta/current/list' and getattr(self.oracle, 'meta_dossier_assist_visible', lambda: False)():
            return True
        if semantic_id == 'meta/dossier/list':
            if self.oracle.meta_dossier_detail_visible():
                return True
            try:
                self.oracle.meta_dossier_empty_points()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "reward/meta/enter":
            return self.oracle.meta_entrance_available()
        if name in REWARD_RESOURCE_FIELDS:
            return self.oracle.reward_resource_available(
                REWARD_RESOURCE_FIELDS[name]
            )
        if semantic_id == "meta/page/back":
            try:
                self.oracle.meta_entrance_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id in ("meta/current/open", "meta/dossier/open"):
            try:
                self.oracle.meta_entrance_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/list":
            try:
                self.oracle.meta_current_detail_state()
                return True
            except SemanticGateClosed:
                pass
            try:
                self.oracle.meta_current_empty_points()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/create":
            if self._meta_beacon_active:
                try:
                    self.oracle.meta_dossier_empty_points(require_create=True)
                    return True
                except SemanticGateClosed:
                    pass
            try:
                self.oracle.meta_current_empty_points(require_create=True)
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/help":
            if self._meta_beacon_active and self.oracle.meta_dossier_detail_visible():
                return self.oracle.meta_dossier_detail_state(
                    allow_auto_prompt=self.oracle.meta_dossier_auto_prompt() is not None).current_hp > 0
            try:
                return self.oracle.meta_current_detail_state().current_hp > 0
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/reward":
            if self._meta_beacon_active and self.oracle.meta_dossier_auto_prompt() is not None:
                return False
            if self._meta_beacon_active and self.oracle.meta_dossier_detail_visible():
                return self.oracle.meta_dossier_reward_visible()
            return self.oracle.meta_current_reward_visible()
        if semantic_id is not None and semantic_id.startswith("meta/help/"):
            return self.oracle.meta_help_visible()
        if semantic_id == "meta/assist/start":
            if self._meta_beacon_active and self.oracle.meta_dossier_detail_visible():
                return self.oracle.meta_dossier_detail_state().current_hp > 0
            try:
                self.oracle.meta_current_detail_state()
                return True
            except SemanticGateClosed:
                pass
            try:
                self.oracle.meta_assist_state()
                return True
            except SemanticGateClosed:
                return False
        return UNHANDLED
