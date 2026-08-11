"""Typed, read-only observations for the frozen G36 normal combat path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ...alas_combat_state_replay import AlasCombatReplayFrame, AlasCombatReplayPhase
from ...semantic_oracle import SemanticGateClosed
from ..errors import UnknownObservationError


# Exact ``appear`` calls recorded from pinned ALAS for H02.  Inclusion here
# means the normal discriminated union can answer the query; it does not
# qualify a defensive action or make that branch production-ready.
G36_NORMAL_APPEAR_RESOURCES = frozenset(
    {
        "AUTOMATION_CONFIRM_CHECK",
        "AUTOMATION_OFF",
        "AUTOMATION_ON",
        "AUTO_SEARCH_MENU_EXIT",
        "BATTLE_PREPARATION",
        "BATTLE_STATUS_A",
        "BATTLE_STATUS_B",
        "BATTLE_STATUS_C",
        "BATTLE_STATUS_D",
        "BATTLE_STATUS_S",
        "CAMPAIGN_CHECK",
        "EVENT_CHECK",
        "EXP_INFO_A",
        "EXP_INFO_B",
        "EXP_INFO_S",
        "FLEET_PREPARATION",
        "GAME_TIPS",
        "GAME_TIPS3",
        "GAME_TIPS4",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "GET_MISSION",
        "GET_SHIP",
        "GUILD_POPUP_CONFIRM",
        "IN_RETIREMENT_CHECK",
        "MAP_AMBUSH_EVADE",
        "MAP_PREPARATION",
        "MISSION_POPUP_GO",
        "PAUSE",
        "POPUP_CANCEL",
        "POPUP_CONFIRM_WHITE",
        "RETIRE_APPEAR_1",
        "SP_CHECK",
        "STORY_CLOSE",
        "STORY_SKIP_3",
    }
)

G36_NORMAL_COMBAT_PHASES = frozenset(
    {
        AlasCombatReplayPhase.BATTLE_PREPARATION,
        AlasCombatReplayPhase.COMBAT_EXECUTING,
        AlasCombatReplayPhase.BATTLE_STATUS,
        AlasCombatReplayPhase.GET_ITEMS,
        AlasCombatReplayPhase.EXP_INFO,
        AlasCombatReplayPhase.GET_MISSION,
        AlasCombatReplayPhase.MAP_SEARCHING,
        AlasCombatReplayPhase.MAP_STABLE,
    }
)
G36_NORMAL_COLOR_COUNT_RESOURCES = frozenset(
    {"MAP_CAT_ATTACK", "MAP_CAT_ATTACK_MIRROR"}
)


@dataclass(frozen=True)
class CombatFlowState:
    """One admitted member of the mutually exclusive normal-screen union."""

    frame: AlasCombatReplayFrame

    def __post_init__(self) -> None:
        if not isinstance(self.frame, AlasCombatReplayFrame):
            raise SemanticGateClosed("combat flow frame is not typed")
        if self.frame.phase not in G36_NORMAL_COMBAT_PHASES:
            raise SemanticGateClosed("combat flow phase is outside G36 normal path")
        expected = {
            AlasCombatReplayPhase.BATTLE_PREPARATION: {
                "AUTOMATION_ON",
                "BATTLE_PREPARATION",
            },
            AlasCombatReplayPhase.COMBAT_EXECUTING: {"PAUSE"},
            AlasCombatReplayPhase.BATTLE_STATUS: {"BATTLE_STATUS_S"},
            AlasCombatReplayPhase.GET_ITEMS: {"GET_ITEMS_1"},
            AlasCombatReplayPhase.EXP_INFO: {"EXP_INFO_S"},
            AlasCombatReplayPhase.GET_MISSION: {"GET_MISSION"},
            AlasCombatReplayPhase.MAP_SEARCHING: {
                "IN_MAP",
                "MAP_ENEMY_SEARCHING",
            },
            AlasCombatReplayPhase.MAP_STABLE: {"IN_MAP"},
        }[self.frame.phase]
        if set(self.frame.visible_resources) != expected:
            raise SemanticGateClosed(
                "combat flow resources do not match the discriminated phase"
            )


class CombatFlow:
    """Resolve original ALAS reads without framebuffer or input authority."""

    def __init__(self, state: CombatFlowState) -> None:
        if not isinstance(state, CombatFlowState):
            raise SemanticGateClosed("combat flow state is not typed")
        self._state = state

    @property
    def phase(self) -> AlasCombatReplayPhase:
        return self._state.frame.phase

    @property
    def generation(self) -> int:
        return self._state.frame.generation

    def appear(self, resource: str) -> bool:
        if resource not in G36_NORMAL_APPEAR_RESOURCES:
            raise UnknownObservationError()
        return resource in self._state.frame.visible_resources

    def image_color_count(self, resource: str) -> int:
        """Resolve reviewed-absent cat-attack probes without reading pixels."""

        if resource not in G36_NORMAL_COLOR_COUNT_RESOURCES:
            raise UnknownObservationError()
        return 0

    def is_in_map(self) -> bool:
        return self._state.frame.in_map

    def is_combat_loading(self) -> bool:
        return self._state.frame.combat_loading

    def is_combat_executing(self) -> bool:
        return self._state.frame.combat_executing

    def enemy_searching_appear(self) -> bool:
        return self._state.frame.enemy_searching

    def hp_get(self) -> Tuple[float, ...]:
        if self.phase is not AlasCombatReplayPhase.MAP_STABLE:
            raise UnknownObservationError()
        if len(self._state.frame.hp) != 6:
            raise SemanticGateClosed("combat flow HP vector is incomplete")
        return self._state.frame.hp

    def lv_get(self) -> Tuple[int, ...]:
        if self.phase is not AlasCombatReplayPhase.MAP_STABLE:
            raise UnknownObservationError()
        if len(self._state.frame.levels) != 6:
            raise SemanticGateClosed("combat flow level vector is incomplete")
        return self._state.frame.levels


__all__ = (
    "CombatFlow",
    "CombatFlowState",
    "G36_NORMAL_APPEAR_RESOURCES",
    "G36_NORMAL_COLOR_COUNT_RESOURCES",
    "G36_NORMAL_COMBAT_PHASES",
)
