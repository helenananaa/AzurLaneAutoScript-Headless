"""Combat for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    OracleState,
    Point,
    TextState,
    UiState,
)
from .errors import SemanticGateClosed


class CombatOracle:
    """Combat operations sharing the oracle frame and input boundary."""

    def daily_page_visible(self) -> bool:
        state = self.read_state()
        return bool(
            self._matches(state, "daily/page/back")
            and not self._daily_precombat_visible(state)
        )

    def daily_detail_visible(self) -> bool:
        state = self.read_state()
        return self._daily_detail_visible(state)

    @staticmethod
    def _daily_detail_visible(state: OracleState) -> bool:
        if CombatOracle._daily_precombat_visible(state):
            return False
        prefix = (
            "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/desc_panel/main_mask/"
            "main/scrollview/content/stagetpl(Clone)/info"
        )
        return any(
            button.path == prefix
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            for button in state.buttons
        )

    @staticmethod
    def _daily_battle_result_buttons(state: OracleState) -> Tuple[ButtonState, ...]:
        return tuple(
            button
            for button in state.buttons
            if button.path.endswith(
                "/NewBattleResultEmptyUI(Clone)/NewBattleResultGradePage(Clone)"
            )
            or button.path.endswith(
                "/NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn"
            )
        )

    def daily_precombat_visible(self) -> bool:
        state = self.read_state()
        return self._daily_precombat_visible(state)

    @staticmethod
    def _daily_precombat_visible(state: OracleState) -> bool:
        if CombatOracle._daily_combat_visible(state):
            return False
        return any(
            button.path.endswith(
                "/PreCombatUI(Clone)/adapt/right/start"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            for button in state.buttons
        )

    @staticmethod
    def _daily_combat_visible(state: OracleState) -> bool:
        return any(
            button.path == "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            for button in state.buttons
        )

    def daily_combat_visible(self) -> bool:
        return self._daily_combat_visible(self.read_state())

    @staticmethod
    def _operation_siren_battle_result_grade(ui_state: UiState) -> Optional[str]:
        """Return VICTORY or DEFEAT from the Operation Siren grade title."""

        titles = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and "/NewBattleResultEmptyUI(Clone)/" in item.path
            and item.text.strip() in {"VICTORY", "DEFEAT"}
        )
        if not titles:
            return None
        preferred = tuple(
            item
            for item in titles
            if item.path.endswith("/NewBattleResultEmptyUI(Clone)/Effect/bg03/Text")
        )
        candidates = preferred or titles
        grades = {item.text.strip() for item in candidates}
        if len(grades) != 1:
            on_screen = tuple(
                item
                for item in candidates
                if item.bounds.right > 0
                and item.bounds.bottom > 0
                and item.bounds.left < 1280
                and item.bounds.top < 720
            )
            grades = {item.text.strip() for item in on_screen}
            if len(grades) != 1:
                raise SemanticGateClosed(
                    "operation siren battle result grade is ambiguous"
                )
        return next(iter(grades))

    @staticmethod
    def _operation_siren_battle_result_continue(ui_state: UiState) -> Optional[TextState]:
        """Return the exact EventTrigger continue text for an OS grade page."""

        active_texts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        continue_text = tuple(
            item
            for item in active_texts
            if item.path.endswith(
                "/NewBattleResultGradePage(Clone)/bg/ResultEffect/Tips/"
                "dianjijixu/bg20"
            )
            and item.text.strip() == "点击继续"
        )
        if len(continue_text) != 1:
            return None
        if CombatOracle._operation_siren_battle_result_grade(ui_state) is None:
            return None
        return continue_text[0]

    def daily_battle_result_visible(self) -> bool:
        state = self.read_state()
        targets = self._daily_battle_result_buttons(state)
        if len(targets) > 1:
            raise SemanticGateClosed("daily battle result target is ambiguous")
        if len(targets) == 1:
            return bool(
                targets[0].actionable
                and not self._blocking_rules(state, "daily/battle/result")
            )

        # Operation Siren's result grade page is an EventTrigger surface, not
        # a Unity Button.  Prove that exact typed stack instead of allowing the
        # still-mounted CombatUI underneath to win the surface classification.
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("battle result snapshots are not coherent")
        return bool(
            self._operation_siren_battle_result_continue(ui_state) is not None
            and not self._blocking_rules(
                state, "operation-siren/battle/result"
            )
        )

    def operation_siren_battle_result_visible(self) -> bool:
        """True when the shared grade page belongs to an Operation Siren fight."""

        return (
            self._operation_siren_battle_result_continue(self.read_ui_state())
            is not None
        )

    def operation_siren_battle_result_grade(self) -> str:
        """Return VICTORY or DEFEAT for the exact Operation Siren grade page."""

        ui_state = self.read_ui_state()
        if self._operation_siren_battle_result_continue(ui_state) is None:
            raise SemanticGateClosed("operation siren battle result is absent")
        grade = self._operation_siren_battle_result_grade(ui_state)
        if grade is None:
            raise SemanticGateClosed("operation siren battle result grade is absent")
        return grade

    def combat_pause_visible(self) -> bool:
        """Recognize the shared actionable combat pause control."""

        state = self.read_state()
        targets = self._matches(state, "exercise/combat/pause")
        return bool(
            len(targets) == 1
            and targets[0].active_in_hierarchy
            and targets[0].active_and_enabled
            and targets[0].interactable
            and targets[0].raycast_top is None
            and targets[0].point is not None
            and targets[0].bounds is not None
            and targets[0].bounds.contains(targets[0].point)
        )

    def click_combat_pause(self) -> ActionReceipt:
        """Click the shared pause control after its exact typed proof."""

        if not self.combat_pause_visible():
            raise SemanticGateClosed("combat pause target is absent")
        state = self.read_state()
        target = self._unique(state, "exercise/combat/pause")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="combat/pause", generation=state.generation,
            point=target.point, bounds=target.bounds, path=target.path,
        )

    def click_daily_battle_result(self) -> ActionReceipt:
        state = self.read_state()
        targets = self._daily_battle_result_buttons(state)
        if len(targets) > 1:
            raise SemanticGateClosed("daily battle result target is ambiguous")
        if not targets:
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("battle result snapshots are not coherent")
            continue_text = self._operation_siren_battle_result_continue(
                ui_state
            )
            if continue_text is None or continue_text.bounds is None:
                raise SemanticGateClosed("daily battle result is absent")
            if self._blocking_rules(state, "operation-siren/battle/result"):
                raise SemanticGateClosed("battle result input is blocked")
            point = Point(
                (continue_text.bounds.left + continue_text.bounds.right) / 2.0,
                (continue_text.bounds.top + continue_text.bounds.bottom) / 2.0,
            )
            if not (
                0 <= point.x < self.fingerprint.width
                and 0 <= point.y < self.fingerprint.height
                and continue_text.bounds.contains(point)
            ):
                raise SemanticGateClosed("battle result target is off screen")
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed("foreground changed immediately before input")
            self._tap(int(round(point.x)), int(round(point.y)))
            return ActionReceipt(
                semantic_id="operation-siren/battle/result",
                generation=ui_state.generation,
                point=point,
                bounds=continue_text.bounds,
                path=continue_text.path,
            )
        target = targets[0]
        if not target.actionable:
            raise SemanticGateClosed("daily battle result is not actionable")
        if self._blocking_rules(state, "daily/battle/result"):
            raise SemanticGateClosed("daily battle result input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="daily/battle/result",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_daily_precombat_back(self) -> ActionReceipt:
        state = self.read_state()
        if not self._daily_precombat_visible(state):
            raise SemanticGateClosed("daily precombat page is absent")
        target = self._unique(state, "daily/precombat/back")
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not None
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("daily precombat back is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="daily/precombat/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_daily_precombat_start(self) -> ActionReceipt:
        state = self.read_state()
        if not self._daily_precombat_visible(state):
            raise SemanticGateClosed("daily precombat page is absent")
        target = self._unique(state, "daily/precombat/start")
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not None
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("daily precombat start is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="daily/precombat/start",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def daily_current_active(self) -> bool:
        """Read the centered daily card and reject its exact lock subtree."""

        if self.daily_detail_visible():
            return False
        state = self.read_state()
        if not self.daily_page_visible():
            raise SemanticGateClosed("daily page is absent")
        prefix = "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/list_panel/list/"
        cards = tuple(
            button
            for button in state.buttons
            if button.path.startswith(prefix)
            and button.path.count("/") == prefix.count("/")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and 500.0 <= button.point.x <= 780.0
        )
        if len(cards) != 1:
            raise SemanticGateClosed("centered daily card is absent or ambiguous")
        root = cards[0].path + "/lock"
        ui = self.read_ui_state()
        locked = any(
            image.path == root
            and image.active_in_hierarchy
            and image.active_and_enabled
            for image in ui.images
        )
        return not locked

    def daily_current_kind(self) -> str:
        """Return the centered challenge identity from its exact card sprite."""

        if not self.daily_page_visible():
            raise SemanticGateClosed("daily page is absent")
        prefix = "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/list_panel/list/"
        buttons = self.read_state()
        cards = tuple(
            button
            for button in buttons.buttons
            if button.path.startswith(prefix)
            and button.path.count("/") == prefix.count("/")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.point is not None
            and 500.0 <= button.point.x <= 780.0
        )
        if len(cards) != 1:
            raise SemanticGateClosed("centered daily card is absent or ambiguous")
        title_path = cards[0].path + "/icon/card/title"
        titles = tuple(
            image
            for image in self.read_ui_state().images
            if image.path == title_path
            and image.active_in_hierarchy
            and image.active_and_enabled
        )
        if len(titles) != 1:
            raise SemanticGateClosed("centered daily identity is absent or ambiguous")
        kinds = {
            "shangchuanhuwei_zi": "escort_mission",
            "haiyutujin_zi": "advance_mission",
            "zhanshouxingdong_zi": "fierce_assault",
            "zhanshuzuanyan_zi": "tactical_training",
            "pojiaozuozhan_zi": "supply_line_disruption",
            "bingzhuangDesc": "module_development",
        }
        try:
            return kinds[titles[0].sprite]
        except KeyError as exc:
            raise SemanticGateClosed("centered daily identity is not reviewed") from exc

    def daily_current_remain(self) -> int:
        """Return the remaining count from the centered card's exact text."""

        prefix = "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/list_panel/list/"
        button_state = self.read_state()
        cards = tuple(
            button
            for button in button_state.buttons
            if button.path.startswith(prefix)
            and button.path.count("/") == prefix.count("/")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and 500.0 <= button.point.x <= 780.0
        )
        if len(cards) != 1:
            raise SemanticGateClosed("centered daily card is absent or ambiguous")
        count_path = cards[0].path + "/count"
        state = self.read_ui_state()
        candidates = tuple(
            text
            for text in state.texts
            if text.path == count_path
            and text.active_in_hierarchy
            and text.active_and_enabled
            and text.bounds is not None
        )
        if len(candidates) != 1:
            raise SemanticGateClosed("centered daily remaining count is ambiguous")
        match = re.fullmatch(r"([0-4])/([0-4])", candidates[0].text.strip())
        if match is None:
            raise SemanticGateClosed("daily remaining count is malformed")
        remain, total = (int(value) for value in match.groups())
        if remain > total:
            raise SemanticGateClosed("daily remaining count exceeds total")
        return remain

    def click_daily_current_card(self) -> ActionReceipt:
        if not self.daily_current_active():
            raise SemanticGateClosed("centered daily card is locked")
        state = self.read_state()
        prefix = "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/list_panel/list/"
        cards = tuple(
            button
            for button in state.buttons
            if button.path.startswith(prefix)
            and button.path.count("/") == prefix.count("/")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
            and 500.0 <= button.point.x <= 780.0
        )
        if len(cards) != 1:
            raise SemanticGateClosed("centered daily card is absent or ambiguous")
        target = cards[0]
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="daily/current",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _daily_visible_stages(
        self, state: Optional[OracleState] = None
    ) -> Tuple[ButtonState, ...]:
        if state is None:
            state = self.read_state()
        prefix = (
            "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/desc_panel/main_mask/"
            "main/scrollview/content/stagetpl(Clone)/info"
        )
        return tuple(
            sorted(
                (
                    button
                    for button in state.buttons
                    if button.path == prefix
                    and button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.interactable
                    and button.raycast_top is True
                    and button.point is not None
                    and button.bounds is not None
                    and button.bounds.contains(button.point)
                    and 110.0 <= button.point.y <= 650.0
                ),
                key=lambda button: button.point.y,
            )
        )

    def daily_stage_available(self, index: int) -> bool:
        if index not in (1, 2, 3) or not self.daily_detail_visible():
            return False
        return len(self._daily_visible_stages()) >= index

    def daily_selected_stage_visible(self, index: int) -> bool:
        """Prove that the requested row is mounted in the exact selected layer."""

        if index not in (1, 2, 3):
            return False
        state = self.read_state()
        if not self._daily_detail_visible(state):
            return False
        return self._daily_selected_stage_target(state, index) is not None

    @staticmethod
    def _daily_selected_stage_target(
        state: OracleState, index: int
    ) -> Optional[ButtonState]:
        rows = tuple(
            sorted(
                (
                    button
                    for button in state.buttons
                    if button.path.endswith(
                        "/DailyLevelUI(Clone)/desc_panel/main_mask/main/"
                        "scrollview/content/stagetpl(Clone)/info"
                    )
                    and button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.bounds is not None
                    and 110.0 <= button.bounds.top <= 650.0
                ),
                key=lambda button: button.bounds.top,
            )
        )
        selected = tuple(
            button
            for button in state.buttons
            if button.path == "OverlayCamera/Overlay/UIMain/selected/stagetpl/info"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if (
            len(rows) >= index
            and len(selected) == 1
            and abs(selected[0].bounds.top - rows[index - 1].bounds.top) <= 2.0
            and abs(selected[0].bounds.bottom - rows[index - 1].bounds.bottom) <= 2.0
        ):
            return selected[0]
        return None

    def daily_run_choice_visible(self, choice: str) -> bool:
        """Return whether an exact action is present on the expanded stage."""

        names = {"normal": "challenge", "skip": "mult"}
        try:
            name = names[choice]
        except KeyError as exc:
            raise ValueError("unknown daily run choice") from exc
        path = "OverlayCamera/Overlay/UIMain/selected/stagetpl/quickly/bg/" + name
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.path == path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        return len(matches) == 1

    def click_daily_run_choice(self, choice: str) -> ActionReceipt:
        names = {"normal": "challenge", "skip": "mult"}
        try:
            name = names[choice]
        except KeyError as exc:
            raise ValueError("unknown daily run choice") from exc
        path = "OverlayCamera/Overlay/UIMain/selected/stagetpl/quickly/bg/" + name
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.path == path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("daily run choice is absent or ambiguous")
        target = matches[0]
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="daily/run/{0}".format(choice),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_daily_selected_stage(self, index: int) -> ActionReceipt:
        if index not in (1, 2, 3):
            raise SemanticGateClosed("selected daily stage is absent")
        state = self.read_state()
        if not self._daily_detail_visible(state):
            raise SemanticGateClosed("selected daily stage is absent")
        target = self._daily_selected_stage_target(state, index)
        if target is None:
            raise SemanticGateClosed("selected daily stage is absent")
        assert target.point is not None and target.bounds is not None
        point = target.point
        if not target.bounds.contains(point):
            raise SemanticGateClosed("selected daily stage point is outside its bounds")
        if self._blocking_rules(state, "daily/stage/{0}/selected".format(index)):
            raise SemanticGateClosed("selected daily stage input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="daily/stage/{0}/selected".format(index),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_daily_stage(self, index: int) -> ActionReceipt:
        state = self.read_state()
        stages = self._daily_visible_stages(state)
        if index not in (1, 2, 3) or len(stages) < index:
            raise SemanticGateClosed("daily stage is absent")
        target = stages[index - 1]
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed("daily stage action point is absent")
        point = target.point
        if not target.bounds.contains(point):
            raise SemanticGateClosed("daily stage point is outside its bounds")
        if self._blocking_rules(state, "daily/stage/{0}".format(index)):
            raise SemanticGateClosed("daily stage input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="daily/stage/{0}".format(index),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def daily_fleet_index(self) -> int:
        """Read the selected 1-6 fleet from the exact pre-combat label."""

        if not self.daily_precombat_visible():
            raise SemanticGateClosed("daily precombat page is absent")
        suffix = "/PreCombatUI(Clone)/adapt/middle/fleet_info/fleet_number"
        matches = tuple(
            text
            for text in self.read_ui_state().texts
            if text.path.endswith(suffix)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if len(matches) != 1 or re.fullmatch(r"[1-6]", matches[0].text.strip()) is None:
            raise SemanticGateClosed("daily fleet index is absent or ambiguous")
        return int(matches[0].text.strip())

    def click_daily_fleet(self, direction: str) -> ActionReceipt:
        """Move one fleet in the requested direction on Daily pre-combat."""

        if direction not in ("next", "prev") or not self.daily_precombat_visible():
            raise SemanticGateClosed("daily fleet direction is not actionable")
        suffix = "/PreCombatUI(Clone)/adapt/middle/{0}Page".format(direction)
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("daily fleet control is absent or ambiguous")
        target = matches[0]
        assert target.point is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="daily/fleet/" + direction,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_daily_control(self, semantic_id: str) -> ActionReceipt:
        if semantic_id not in ("daily/page/back", "daily/next", "daily/prev"):
            raise SemanticGateClosed("daily control is not reviewed")
        state = self.read_state()
        if not self.daily_page_visible():
            raise SemanticGateClosed("daily page is absent")
        target = self._unique(state, semantic_id)
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not None
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
            or self._blocking_rules(state, semantic_id)
        ):
            raise SemanticGateClosed("daily control is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
