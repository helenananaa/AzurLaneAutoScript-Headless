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
from .resources import REWARD_RESOURCE_FIELDS


class MetaAdapterPorts:
    """Meta ports on the shared adapter context."""

    def begin_meta_assist(self) -> None:
        self._package_gate()
        self._meta_assist_active = True

    def end_meta_assist(self) -> None:
        self._meta_assist_active = False
        self._operation_siren_combat_active = False
        self._meta_precombat_start_receipt = None
        self._meta_precombat_start_until = 0.0

    def begin_meta_beacon(self) -> None:
        """Own one complete META beacon task until its explicit finally block."""

        self._package_gate()
        self._meta_beacon_active = True

    def end_meta_beacon(self) -> None:
        self._meta_beacon_active = False

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
        if self._meta_assist_active and not self._action_ledger.allowed('meta.assist'):
            raise SemanticGateClosed('META assist requires remaining sortie budget')
        if not self.oracle.meta_precombat_fleet_ready():
            raise SemanticGateClosed(
                "META precombat requires non-empty main and vanguard fleets"
            )
        if self._meta_assist_active:
            receipt = self._dispatch_mutation('meta.assist', self.oracle.click_daily_precombat_start)
        else:
            receipt = self.oracle.click_daily_precombat_start()
        if self._meta_assist_active:
            self._meta_precombat_start_receipt = receipt
            self._meta_precombat_start_until = time.monotonic() + 20.0
        self._operation_siren_combat_active = True
        return receipt

    def click_meta_precombat_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_precombat_back()

    def _appear_meta(self, name, semantic_id):
        if name == 'META_CHECK':
            return self.oracle.meta_character_page_visible()
        if name in ('SYNC_ENTER', 'SYNC_ENTER2', 'SYNC_REWARD_NOTICE', 'SYNC_TAP',
                    'META_REWARD_NOTICE', 'REWARD_ENTER'):
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
            return self.oracle.meta_dossier_detail_visible()
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
            try:
                self.oracle.meta_current_empty_points()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/help":
            try:
                self.oracle.meta_current_detail_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id is not None and semantic_id.startswith("meta/help/"):
            return self.oracle.meta_help_visible()
        if semantic_id == "meta/assist/start":
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
