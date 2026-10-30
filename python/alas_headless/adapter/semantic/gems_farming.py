"""Gems farming for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Tuple
from ...ship_selector_identities import COMMON_CV_NAMES_CN
from ...semantic_oracle import (
    ActionReceipt,
    GemsFarmingDockCandidate,
    GemsFarmingEquipmentLoadout,
    SemanticGateClosed,
    SemanticOracleError,
    SemanticTargetMissing,
)


class GemsFarmingAdapterPorts:
    """Gems farming ports on the shared adapter context."""

    def gems_farming_admit_live_mode(
        self,
        stage_code: str,
        campaign_mode: str,
        change_flagship: str,
        change_vanguard: str,
        attacking_fleet: int,
    ) -> None:
        """Admit only GemsFarming paths whose observation and input are typed."""

        if change_flagship not in ("ship", "ship_equip"):
            raise SemanticGateClosed(
                "GemsFarming flagship change mode is not typed"
            )
        if change_vanguard not in ("disabled", "ship", "ship_equip"):
            raise SemanticGateClosed(
                "GemsFarming vanguard change mode is not typed"
            )
        if campaign_mode == "normal":
            self._gems_farming_hard_profile = None
            return
        if campaign_mode != "hard":
            raise SemanticGateClosed("GemsFarming campaign mode is not reviewed")
        if stage_code.upper() not in ("11-4", "12-1"):
            raise SemanticGateClosed(
                "GemsFarming hard mode is qualified only for reviewed hard stages"
            )
        if change_flagship != "ship" or change_vanguard not in (
            "disabled",
            "ship",
        ):
            raise SemanticGateClosed(
                "GemsFarming hard ship_equip replacement is not typed"
            )
        if attacking_fleet not in (1, 2):
            raise SemanticGateClosed(
                "GemsFarming hard attacking fleet must be 1 or 2"
            )
        self._gems_farming_hard_profile = (
            stage_code.upper(),
            attacking_fleet,
            change_flagship,
            change_vanguard,
        )

    def gems_farming_select_fleet_index(self, fleet_index: int) -> int:
        self._package_gate()
        return self.oracle.gems_farming_select_fleet_index(fleet_index)

    def gems_farming_open_slot(self, role: str) -> ActionReceipt:
        self._package_gate()
        return self.oracle.gems_farming_open_slot(role)

    def gems_farming_hard_slot_occupied(
        self, stage_code: str, fleet_index: int, role: str
    ) -> bool:
        self._package_gate()
        return self.oracle.gems_farming_hard_slot_occupied(
            stage_code, fleet_index, role
        )

    def gems_farming_hard_fleet_preparation_visible(self, stage_code: str) -> bool:
        """Wait briefly for the exact hard fleet overlay during ALAS re-entry."""

        self._package_gate()
        for attempt in range(30):
            try:
                state = self.oracle.campaign_fleet_selection_state(stage_code)
            except (SemanticGateClosed, SemanticTargetMissing):
                if attempt < 29:
                    time.sleep(0.1)
                continue
            return bool(state.hard_mode)
        return False

    def gems_farming_hard_unmount(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        self._package_gate()
        return self._dispatch_mutation(
            "campaign.fleet_mutation",
            lambda: self.oracle.gems_farming_hard_unmount(
                stage_code, fleet_index, role
            ),
        )

    def gems_farming_hard_open_slot(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.gems_farming_hard_open_slot(
            stage_code, fleet_index, role
        )

    def gems_farming_equipment_take_off(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        self._require_action_grant("campaign.fleet_mutation")
        self._package_gate()
        return self.oracle.gems_farming_equipment_take_off(role)

    def gems_farming_equipment_take_on(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        self._package_gate()
        return self.oracle.gems_farming_equipment_take_on(role)

    @staticmethod
    def _gems_candidate_name_allowed(
        role: str, selector: str, ship_name: str
    ) -> bool:
        names = {
            "flagship": COMMON_CV_NAMES_CN,
            "vanguard": {
                "aulick_or_foote": ("奥利克", "富特"),
                "cassin_or_downes": ("卡辛", "卡辛.改", "唐斯", "唐斯.改"),
                "z20_or_z21": ("Z20", "Z21"),
            },
        }
        if selector in ("any", "favourite"):
            return True
        return ship_name in names.get(role, {}).get(selector, ())

    def gems_farming_candidates(
        self,
        *,
        role: str,
        selector: str,
        max_level: int,
        min_emotion: int,
        fleet_index: int,
    ) -> Tuple[GemsFarmingDockCandidate, ...]:
        """Replace ALAS's OCR/template scanner with exact typed Dock cards."""

        if role not in ("flagship", "vanguard"):
            raise ValueError("GemsFarming role must be flagship or vanguard")
        if (
            isinstance(max_level, bool)
            or not isinstance(max_level, int)
            or not 1 <= max_level <= 125
            or isinstance(min_emotion, bool)
            or not isinstance(min_emotion, int)
            or not 0 <= min_emotion <= 150
            or isinstance(fleet_index, bool)
            or not isinstance(fleet_index, int)
            or not 1 <= fleet_index <= 6
        ):
            raise SemanticGateClosed("GemsFarming candidate bounds are invalid")
        allowed_selectors = {
            "flagship": {"any", "bogue", "hermes", "langley", "ranger"},
            "vanguard": {
                "any",
                "favourite",
                "aulick_or_foote",
                "cassin_or_downes",
                "z20_or_z21",
            },
        }
        if selector not in allowed_selectors[role]:
            raise SemanticGateClosed("GemsFarming candidate selector is invalid")
        self._package_gate()
        try:
            favourite = role == "vanguard" and selector == "favourite"
            self.oracle.set_enhancement_dock_favourite(favourite)
            self.oracle.set_gems_farming_dock_sort(role == "vanguard")
            if role == "flagship" or selector == "favourite":
                factions = ("all",)
            elif selector == "z20_or_z21":
                factions = ("iron",)
            elif selector in ("aulick_or_foote", "cassin_or_downes"):
                factions = ("eagle",)
            else:
                factions = ("eagle", "iron")
            self.oracle.set_gems_farming_dock_filter(role, factions)
            observed = self.oracle.gems_farming_dock_candidates()
        except SemanticOracleError as original_error:
            try:
                self.oracle.cancel_gems_farming_dock_filter_if_visible()
                self.oracle.cancel_gems_farming_candidate_selection()
            except SemanticOracleError as recovery_error:
                raise SemanticGateClosed(
                    "GemsFarming candidate observation recovery failed"
                ) from recovery_error
            raise original_error
        expected_type = "cv" if role == "flagship" else "dd"
        candidates = tuple(
            item
            for item in observed
            if item.ship_type == expected_type
            and item.rarity == "common"
            and (
                1 <= item.level <= max_level
                if role == "flagship"
                else item.level == max_level
            )
            and min_emotion <= item.emotion <= 150
            and item.status == "free"
            and self._gems_candidate_name_allowed(role, selector, item.ship_name)
        )
        if role == "flagship":
            same_fleet = tuple(
                item for item in candidates if item.fleet_index == fleet_index
            )
            if same_fleet:
                return same_fleet
            return tuple(item for item in candidates if item.fleet_index == 0)
        return tuple(
            item for item in candidates if item.fleet_index in (0, fleet_index)
        )

    def gems_farming_select_candidate(
        self, candidate: GemsFarmingDockCandidate
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_gems_farming_candidate(candidate)

    def gems_farming_cancel_candidate_selection(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.cancel_gems_farming_candidate_selection()

    def gems_farming_confirm_candidate_selection(
        self, candidate: GemsFarmingDockCandidate, role: str
    ) -> ActionReceipt:
        self._package_gate()
        return self._dispatch_mutation(
            "campaign.fleet_mutation",
            lambda: self.oracle.confirm_gems_farming_candidate_selection(candidate, role),
        )
