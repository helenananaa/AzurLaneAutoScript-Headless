"""Combat for the typed ALAS boundary."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    OracleState,
    Point,
    TextState,
    UiState,
)
from .errors import SemanticGateClosed, SemanticInputBlocked

DAILY_KIND_BY_SPRITE = {
    'shangchuanhuwei_zi': 'escort_mission',
    'haiyutujin_zi': 'advance_mission',
    'zhanshouxingdong_zi': 'fierce_assault',
    'zhanshuzuanyan_zi': 'tactical_training',
    'pojiaozuozhan_zi': 'supply_line_disruption',
    'bingzhuangDesc': 'module_development',
}


@dataclass(frozen=True)
class SubmarineCallState:
    """Observed weapon control, not evidence that a submarine was deployed."""

    generation: int
    battle_instance_id: int
    button: Optional[ButtonState]


class CombatOracle:
    """Combat operations sharing the oracle frame and input boundary."""

    def campaign_submarine_call_state(self) -> Optional[SubmarineCallState]:
        state = self.read_state()
        root = 'UICamera/Canvas/UIMain/CombatUIStandard(Clone)'
        pauses = [b for b in state.buttons if b.path == root + '/PauseBtn'
                  and b.active_in_hierarchy and b.active_and_enabled]
        if not pauses:
            return None
        if self._daily_battle_result_buttons(state) or self._blocking_rules(state, 'campaign/combat/submarine/call'):
            return None
        if len(pauses) != 1:
            raise SemanticGateClosed('submarine combat identity is ambiguous')
        identity = pauses[0].raw.get('instance_id')
        if type(identity) is not int or identity == 0:
            raise SemanticGateClosed('submarine combat identity is unavailable')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2 or ui.image_truncated:
            raise SemanticGateClosed('submarine combat frame is incomplete')
        path = root + '/Weapon_button_container/Weapon_button(Clone)/ActCtl'
        icons = [i for i in ui.images if i.path == path + '/skill_icon/filled'
                 and i.sprite == 'filled_combined_submarine'
                 and i.active_in_hierarchy and i.active_and_enabled]
        if not icons:
            return SubmarineCallState(ui.generation, identity, None)
        if len(icons) != 1 or icons[0].truncated or icons[0].bounds is None:
            raise SemanticGateClosed('submarine weapon icon is ambiguous or incomplete')
        bounds = icons[0].bounds
        centre = Point((bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2)
        buttons = [b for b in state.buttons if b.path == path
                   and b.active_in_hierarchy and b.active_and_enabled
                   and b.bounds is not None and b.bounds.contains(centre)]
        backgrounds = [i for i in ui.images if i.path == path + '/unselect'
                       and i.sprite == 'sub_unselecte' and i.active_in_hierarchy
                       and i.active_and_enabled and not i.truncated
                       and i.bounds is not None and i.bounds.contains(centre)]
        if len(buttons) != 1 or len(backgrounds) != 1:
            raise SemanticGateClosed('submarine weapon binding is ambiguous or incomplete')
        return SubmarineCallState(ui.generation, identity, buttons[0])

    def click_campaign_submarine_call(self, expected_battle_instance_id: int) -> ActionReceipt:
        observed = self.campaign_submarine_call_state()
        if (observed is None or type(expected_battle_instance_id) is not int
                or observed.battle_instance_id != expected_battle_instance_id):
            raise SemanticGateClosed('submarine battle changed before input')
        target = observed.button
        if target is None or not target.actionable:
            raise SemanticGateClosed('submarine call is not actionable')
        state = self.read_state()
        semantic_id = 'campaign/combat/submarine/call'
        pauses = [b for b in state.buttons if b.path == 'UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn'
                  and b.active_in_hierarchy and b.active_and_enabled]
        if len(pauses) != 1 or pauses[0].raw.get('instance_id') != expected_battle_instance_id:
            raise SemanticGateClosed('submarine battle changed before input')
        if state.generation - observed.generation not in (0, 1, 2):
            raise SemanticGateClosed('submarine call frame changed before input')
        if self._blocking_rules(state, semantic_id) or self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('submarine call is blocked')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=observed.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def daily_page_visible(self) -> bool:
        state = self.read_state()
        return bool(
            self._matches(state, "daily/page/back")
            and not self._daily_precombat_visible(state)
        )

    def daily_entry_visible(self) -> bool:
        """Prove arrival without treating a UI observation as new input authority."""
        state = self.read_state()
        targets = self._matches(state, 'daily/page/back')
        return bool(len(targets) == 1 and targets[0].active_in_hierarchy
                    and targets[0].active_and_enabled and targets[0].interactable
                    and targets[0].raycast_top is not False
                    and not self._daily_precombat_visible(state)
                    and not self._blocking_rules(state, 'daily/page/back'))

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

    def daily_battle_loading_visible(self) -> bool:
        """Recognize the typed combat loader without requiring a Loading button."""
        state = self.read_state()
        if any(b.active_in_hierarchy and b.active_and_enabled
               and b.path != 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
               for b in state.buttons):
            return False
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2 or ui.skipped_count:
            raise SemanticGateClosed('combat loading snapshots are not coherent or complete')
        root = 'UICamera/Canvas/UIMain/CombatLoadUI(Clone)/loading/loading_label'
        def texts(path):
            return [t for t in ui.texts if t.path == path and t.active_in_hierarchy
                    and t.active_and_enabled and not t.truncated and t.bounds is not None]
        labels, percents = texts(root), texts(root + '/percent')
        return bool(len(labels) == len(percents) == 1
                    and labels[0].text == 'NOW LOADING...'
                    and re.fullmatch(r'(?:100(?:\.0+)?|\d{1,2}(?:\.\d+)?)%', percents[0].text)
                    and all(r.blocker_id == 'loading' for r in self._blocking_rules(state, 'ui/absence-probe')))

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
        # This fallback consumes only complete grade/continue text. Dock ship
        # toggles may exceed their independent cap while ALAS is entering
        # retirement; retain that flag without rejecting an unrelated probe.
        ui_state = self.read_ui_state(
            check_foreground=False, _preserve_partial_toggles=True
        )
        # This is a passive probe used even on Campaign preparation. A fresh
        # UI without the result identity proves absence by itself; only a
        # positive result needs to combine that UI with state blocker proof.
        result = self._operation_siren_battle_result_continue(ui_state)
        if result is None:
            return False
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("battle result snapshots are not coherent")
        return bool(
            result is not None
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

    @staticmethod
    def _operation_siren_statistics_targets(state):
        root = ("OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
                "NewBattleResultStatisticsPage(Clone)")
        return tuple(b for b in state.buttons
                     if b.path == root + "/bottom/confirmBtn"
                     and b.active_in_hierarchy and b.active_and_enabled)

    def operation_siren_battle_statistics_visible(self) -> bool:
        state = self.read_state()
        targets = self._operation_siren_statistics_targets(state)
        if len(targets) > 1:
            raise SemanticGateClosed("operation siren statistics target is ambiguous")
        return bool(targets and not self._blocking_rules(state, "daily/battle/result"))

    def operation_siren_battle_statistics_grade(self) -> Optional[str]:
        """Read the native statistics grade above any retained CombatUI."""

        root = ("OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
                "NewBattleResultStatisticsPage(Clone)")
        state = self.read_state()
        targets = self._operation_siren_statistics_targets(state)
        if not targets:
            return None
        if len(targets) != 1:
            raise SemanticGateClosed("operation siren statistics target is ambiguous")
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed("operation siren statistics snapshots are not coherent")
        icons = tuple(i for i in ui.images
                      if i.path == root + "/top/grade/icon"
                      and i.active_in_hierarchy and i.active_and_enabled)
        labels = tuple(i for i in ui.images
                       if i.path == root + "/top/grade/Text"
                       and i.active_in_hierarchy and i.active_and_enabled)
        if len(icons) != 1 or len(labels) != 1:
            if (len(icons) <= 1 and len(labels) <= 1
                    and not ui.image_truncated and not ui.skipped_count
                    and (targets[0].raycast_top is False or not targets[0].interactable)):
                # The statistics prefab can mount its disabled/covered
                # confirm before the grade Images. No grade or input is
                # available yet; native ALAS owns the next screenshot.
                return None
            raise SemanticGateClosed("operation siren statistics grade is ambiguous or incomplete")
        grade = icons[0].sprite.removeprefix("letter_")
        if (grade not in ("S", "A", "B", "C", "D")
                or icons[0].sprite != "letter_" + grade
                or labels[0].sprite.casefold() != "label_" + grade.casefold()
                or icons[0].truncated or labels[0].truncated):
            raise SemanticGateClosed("operation siren statistics grade is unsupported or inconsistent")
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
        if (self._blocking_rules(state, 'exercise/combat/pause')
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('combat pause is covered or foreground changed')
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
        return self._click_shared_precombat_back(owned_meta_assist=False)

    def click_meta_assist_precombat_back(self) -> ActionReceipt:
        return self._click_shared_precombat_back(owned_meta_assist=True)

    def _click_shared_precombat_back(self, *, owned_meta_assist: bool) -> ActionReceipt:
        def ready_state():
            state = self.read_state()
            if not self._daily_precombat_visible(state):
                raise SemanticGateClosed("daily precombat page is absent")
            if owned_meta_assist:
                # Returning spends no assist attempt, including after exhaustion.
                # Prove the same typed owner as start before ignoring its underlay.
                self.meta_assist_state()
                state = self.read_state()
                if not self._daily_precombat_visible(state):
                    raise SemanticGateClosed('META assist precombat changed during observation')
            blockers = self._blocking_rules(state, 'daily/precombat/back')
            if owned_meta_assist:
                blockers = tuple(rule for rule in blockers
                    if not (rule.blocker_id == 'meta-assist' and rule.path_fragment ==
                        '/WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/'))
            if blockers:
                raise SemanticGateClosed('daily precombat back is blocked: '+','.join(b.blocker_id for b in blockers))
            return state
        state = self._retry_transition_read(ready_state)
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
        if not (0 <= target.point.x < self.fingerprint.width
                and 0 <= target.point.y < self.fingerprint.height):
            raise SemanticGateClosed('daily precombat back is outside the screen')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before daily precombat back')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed after daily precombat back')
        return ActionReceipt(
            semantic_id="daily/precombat/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_daily_precombat_start(self, *, input_frame=None) -> ActionReceipt:
        return self._click_shared_precombat_start(owned_meta_assist=False, input_frame=input_frame)

    def combat_automation_info_visible(self, *, require_actionable: bool = True) -> bool:
        return self._combat_automation_info_state(require_actionable=require_actionable) is not None

    def _combat_automation_info_state(self, *, require_actionable: bool = True):
        state = self.read_state()
        if not (self._daily_precombat_visible(state) or self._daily_combat_visible(state)
                or self.campaign_precombat_visible(state)):
            return None
        targets = [b for b in self._matches(state, 'os/precombat/info/confirm')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return None
        ui = self._paired_ui_after_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('automation information frames are incoherent')
        def texts(suffix):
            return [re.sub(r'\s+', '', t.text) for t in ui.texts
                    if t.path.endswith('Msgbox(Clone)/window/' + suffix)
                    and t.active_in_hierarchy and t.active_and_enabled
                    and not t.truncated and t.bounds is not None]
        if texts('help_panel/list/help_tpl') != ['注意，自律战斗时可能出现以下情况']:
            return None
        if texts('button_container/custom_button_1(Clone)/pic') != ['知道了']:
            return None
        if any(b.active_in_hierarchy and b.active_and_enabled
               and '/Msgbox(Clone)/window/button_container/' in b.path
               and b.path != targets[0].path for b in state.buttons):
            raise SemanticGateClosed('automation information choices are ambiguous')
        return state if len(targets) == 1 and (not require_actionable or targets[0].actionable) else None

    def click_combat_automation_info(self) -> ActionReceipt:
        # Retry only a complete read before dispatch, never the tap. Use that
        # same Button/UI pair for identity and the actionable target.
        state = self._retry_transition_read(self._combat_automation_info_state)
        if state is None:
            raise SemanticGateClosed('automation information identity is not proven')
        precombat = self._daily_precombat_visible(state)
        campaign_precombat = self.campaign_precombat_visible(state)
        target = self._unique(state, 'os/precombat/info/confirm')
        blockers = [rule for rule in self._blocking_rules(state, 'os/precombat/info/confirm')
                    if (rule.blocker_id, rule.path_fragment) not in (
                        ('daily-precombat', '/PreCombatUI(Clone)/'),
                        ('meta-current-detail', '/WorldBossUI(Clone)/pages/CurrentWorldBossDetailUI(Clone)/'),
                        ('meta-assist', '/WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/'))]
        if (not target.actionable or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point) or blockers
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('automation information target is not actionable')
        self._tap(round(target.point.x), round(target.point.y))
        receipt = ActionReceipt(semantic_id='os/precombat/info/confirm', generation=state.generation,
                                path=target.path, point=target.point, bounds=target.bounds)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            after = self.read_state()
            if after.generation > receipt.generation and not self.combat_automation_info_visible():
                restored = (self.campaign_precombat_visible(after) if campaign_precombat
                            else self._daily_precombat_visible(after) if precombat
                            else self._daily_combat_visible(after))
                if not restored:
                    raise SemanticGateClosed('automation information did not restore its combat page')
                return receipt
            self._sleep(.2)
        raise SemanticGateClosed('automation information did not close after input')

    def click_meta_assist_precombat_start(self, *, input_frame=None) -> ActionReceipt:
        return self._click_shared_precombat_start(owned_meta_assist=True, input_frame=input_frame)

    def _click_shared_precombat_start(self, *, owned_meta_assist: bool, input_frame=None) -> ActionReceipt:
        previous_target = None
        observations = []
        def ready_state(reader=None):
            nonlocal previous_target
            reader = self if reader is None else reader
            state = reader.read_state()
            observation = {'generation': state.generation}
            observations.append(observation)
            if not reader._daily_precombat_visible(state):
                raise SemanticGateClosed("daily precombat page is absent")
            if owned_meta_assist:
                summary = reader.meta_assist_state()
                if summary.remaining_attempts <= 0:
                    raise SemanticGateClosed('META assist has no remaining attempts')
                state = reader.read_state()
                if not reader._daily_precombat_visible(state):
                    raise SemanticGateClosed('META assist precombat changed during observation')
            blockers = reader._blocking_rules(state, 'daily/precombat/start')
            if owned_meta_assist:
                blockers = tuple(rule for rule in blockers
                    if not (rule.blocker_id == 'meta-assist' and rule.path_fragment ==
                        '/WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/'))
            if len(blockers) == 1 and blockers[0].blocker_id == 'loading':
                raise SemanticInputBlocked('daily/precombat/start', state.generation, ('loading',))
            if blockers:
                raise SemanticGateClosed('daily precombat start is blocked: '+','.join(b.blocker_id for b in blockers))
            target = reader._unique(state, "daily/precombat/start")
            observation.update(path=target.path,
                point=(target.point.x, target.point.y) if target.point else None)
            if (
                not target.active_in_hierarchy
                or not target.active_and_enabled
                or not target.interactable
                or target.raycast_top is not None
                or target.point is None
                or target.bounds is None
                or not target.bounds.contains(target.point)
                or not (0 <= target.point.x < self.fingerprint.width
                        and 0 <= target.point.y < self.fingerprint.height)
            ):
                raise SemanticGateClosed("daily precombat start is not actionable")
            prior = previous_target
            previous_target = target
            if (prior is None or prior.path != target.path
                    or abs(prior.point.x - target.point.x) > 1.0
                    or abs(prior.point.y - target.point.y) > 1.0):
                # This delegated control has no raycast proof while its panel
                # slides in. Reuse the short read-only transition wait, then
                # tap the latest native point once. Subpixel motion is harmless
                # at ADB input precision; no absolute position is prescribed.
                raise SemanticGateClosed("daily precombat start geometry is moving")
            return state, target
        try:
            state, target = self._retry_transition_read(ready_state)
        except SemanticGateClosed as exc:
            if str(exc) == 'daily precombat start geometry is moving':
                # Retain every read-only attempt, including attempts that fail
                # before geometry comparison. A first warmup traceback alone
                # cannot establish that the final target was still moving.
                raise SemanticGateClosed(
                    f'{exc}; readiness observations={observations}') from exc
            raise
        input_reader = self
        if input_frame is not None:
            # Live readiness can outlast its entry lease during slow ADB reads.
            # Reacquire once, then prove the same stable target and META fleet
            # from that coherent frame. Never retry a submitted input.
            input_reader = input_frame()
            state, target = ready_state(input_reader)
            if not input_reader.meta_precombat_fleet_ready():
                raise SemanticGateClosed('META precombat requires non-empty main and vanguard fleets')
        if input_reader._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before daily precombat start')
        input_reader._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed after daily precombat start')
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
        try:
            return DAILY_KIND_BY_SPRITE[titles[0].sprite]
        except KeyError as exc:
            raise SemanticGateClosed("centered daily identity is not reviewed") from exc

    def daily_remaining_for_kind(self, kind: str) -> int:
        """Read a challenge after the native carousel reorders on completion."""
        if kind not in DAILY_KIND_BY_SPRITE.values() or not self.daily_page_visible():
            raise SemanticGateClosed('daily challenge page or kind is unavailable')
        ui = self.read_ui_state()
        if ui.image_truncated:
            raise SemanticGateClosed('daily challenge identity snapshot is truncated')
        prefix = 'UICamera/Canvas/UIMain/DailyLevelUI(Clone)/list_panel/list/'
        titles = [i for i in ui.images if i.path.startswith(prefix)
                  and i.path.endswith('/icon/card/title') and i.active_in_hierarchy
                  and i.active_and_enabled and not i.truncated
                  and DAILY_KIND_BY_SPRITE.get(i.sprite) == kind]
        if len(titles) != 1:
            raise SemanticGateClosed('daily challenge identity is absent or ambiguous')
        path = titles[0].path[:-len('/icon/card/title')] + '/count'
        counts = [t for t in ui.texts if t.path == path and t.active_in_hierarchy
                  and t.active_and_enabled and not t.truncated]
        if len(counts) != 1:
            raise SemanticGateClosed('daily challenge remaining count is ambiguous')
        match = re.fullmatch(r'([0-4])/([0-4])', counts[0].text.strip())
        if match is None or int(match[1]) > int(match[2]):
            raise SemanticGateClosed('daily challenge remaining count is malformed')
        return int(match[1])

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
        semantic_id = 'daily/run/' + choice
        if (target.raycast_top is False or (choice == 'skip' and target.raycast_top is not True)
                or self._blocking_rules(state, semantic_id)):
            raise SemanticGateClosed('daily run choice is obscured or not top-raycast actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed immediately before daily input')
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
