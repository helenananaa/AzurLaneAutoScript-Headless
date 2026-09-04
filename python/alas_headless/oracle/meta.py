"""Meta for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, Mapping, Optional, Tuple
from .contracts import (
    ActionReceipt,
    MetaAssistState,
    MetaCurrentDetailState,
    MetaEntranceState,
    Point,
    TextState,
)
from .errors import SemanticGateClosed


class MetaOracle:
    """Meta operations sharing the oracle frame and input boundary."""

    def meta_entrance_available(self) -> bool:
        """Admit the exact META link card on the reward summary page."""

        state = self.read_state()
        page = self._matches(state, "reward/page/back")
        entrance = self._matches(state, "reward/meta/enter")
        if len(page) != 1 or len(entrance) != 1:
            return False
        target = entrance[0]
        # This Selectable delegates the final raycast to its child Image.  The
        # observer therefore reports no top Button while still proving the
        # unique enabled/interactable card and its exact geometry.
        return bool(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "reward/meta/enter")
        )

    def click_meta_entrance(self) -> ActionReceipt:
        """Open META through the proven delegated reward-summary card."""

        if not self.meta_entrance_available():
            raise SemanticGateClosed("META entrance is not actionable")
        state = self.read_state()
        target = self._unique(state, "reward/meta/enter")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="reward/meta/enter",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_entrance_state(self) -> MetaEntranceState:
        """Read current and dossier META resources from the landing page."""

        button_state = self.read_state()
        back = self._unique(button_state, "meta/page/back")
        current = self._unique(button_state, "meta/current/open")
        dossier = self._unique(button_state, "meta/dossier/open")
        if not all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            for target in (back, current, dossier)
        ):
            raise SemanticGateClosed("META landing page identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META landing snapshots are not coherent")
        root = "WorldBossUI(Clone)/pages/WorldBossEntranceUI(Clone)/"

        def exact(path: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(root + path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "META landing text is absent or ambiguous: " + path
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        def fraction(value: str, field: str) -> Tuple[int, int]:
            match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", value)
            if match is None:
                raise SemanticGateClosed("META " + field + " is malformed")
            actual, capacity = map(int, match.groups())
            if actual > capacity:
                raise SemanticGateClosed("META " + field + " is inconsistent")
            return actual, capacity

        current_points, current_capacity = fraction(
            exact("current_progress/value"), "current progress"
        )
        dossier_points, dossier_capacity = fraction(
            exact("past_progress/value"), "dossier progress"
        )
        daily_points, daily_capacity = fraction(exact("current/acc"), "daily progress")
        consume_text = exact("current/consume")
        remaining_text = exact("current/time")
        if (
            re.fullmatch(r"[1-9][0-9]*", consume_text) is None
            or re.fullmatch(r"[0-9]+天", remaining_text) is None
        ):
            raise SemanticGateClosed("META schedule summary is malformed")
        return MetaEntranceState(
            current_points=current_points,
            current_capacity=current_capacity,
            dossier_points=dossier_points,
            dossier_capacity=dossier_capacity,
            daily_points=daily_points,
            daily_capacity=daily_capacity,
            consume_points=int(consume_text),
            remaining_days=int(remaining_text[:-1]),
        )

    def meta_page_visible(self) -> bool:
        """Return whether a reviewed META landing or current-beacon page owns UI."""

        for probe in (
            self.meta_entrance_state,
            self.meta_current_empty_points,
            self.meta_current_detail_state,
            self.meta_assist_state,
        ):
            try:
                probe()
                return True
            except SemanticGateClosed:
                pass
        return False

    def click_meta_home(self) -> ActionReceipt:
        """Return from any reviewed META page through its exact home control."""

        if not self.meta_page_visible():
            raise SemanticGateClosed("META page identity is absent")
        state = self.read_state()
        target = self._unique(state, "meta/home")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "meta/home")
        ):
            raise SemanticGateClosed("META home control is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/home",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_card(self, dossier: bool) -> ActionReceipt:
        """Open one exact META category card from a proven landing state."""

        self.meta_entrance_state()
        state = self.read_state()
        semantic_id = "meta/dossier/open" if dossier else "meta/current/open"
        target = self._unique(state, semantic_id)
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, semantic_id)
        ):
            raise SemanticGateClosed("META category card is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_current_detail_state(self) -> MetaCurrentDetailState:
        """Read the exact self-beacon detail page before assist or combat."""

        button_state = self.read_state()
        controls = tuple(
            self._unique(button_state, semantic_id)
            for semantic_id in (
                "meta/current/detail/list",
                "meta/current/help",
                "meta/current/start",
            )
        )
        if not all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            for target in controls
        ):
            raise SemanticGateClosed("META current detail identity is absent")
        if any(
            self._blocking_rules(button_state, semantic_id)
            for semantic_id in (
                "meta/current/detail/list",
                "meta/current/help",
                "meta/current/start",
            )
        ):
            raise SemanticGateClosed("META current detail is obstructed")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META current detail snapshots are not coherent")
        root = "WorldBossUI(Clone)/pages/CurrentWorldBossDetailUI(Clone)/"

        def exact(path: str) -> str:
            matches = tuple(
                text.text.strip()
                for text in ui_state.texts
                if text.path.endswith(root + path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("META current detail text is ambiguous")
            return matches[0]

        progress = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", exact("progress/value"))
        attempts = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", exact("point/Text"))
        hp = re.fullmatch(
            r"([0-9]+)/<color=#[0-9A-Fa-f]{6}>([1-9][0-9]*)</color>",
            exact("hp/Text"),
        )
        level = exact("hp/level/Text")
        if progress is None or attempts is None or hp is None or not level.isdigit():
            raise SemanticGateClosed("META current detail summary is malformed")
        current_points, point_capacity = map(int, progress.groups())
        remaining_attempts, attempt_capacity = map(int, attempts.groups())
        current_hp, max_hp = map(int, hp.groups())
        if (
            current_points > point_capacity
            or remaining_attempts > attempt_capacity
            or current_hp > max_hp
        ):
            raise SemanticGateClosed("META current detail summary is inconsistent")
        return MetaCurrentDetailState(
            current_points=current_points,
            point_capacity=point_capacity,
            remaining_attempts=remaining_attempts,
            attempt_capacity=attempt_capacity,
            level=int(level),
            current_hp=current_hp,
            max_hp=max_hp,
        )

    def _click_meta_current_detail_control(self, semantic_id: str) -> ActionReceipt:
        self.meta_current_detail_state()
        state = self.read_state()
        target = self._unique(state, semantic_id)
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, semantic_id)
        ):
            raise SemanticGateClosed("META current detail control is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_current_help(self) -> ActionReceipt:
        return self._click_meta_current_detail_control("meta/current/help")

    def click_meta_current_start(self) -> ActionReceipt:
        return self._click_meta_current_detail_control("meta/current/start")

    def click_meta_current_detail_list(self) -> ActionReceipt:
        return self._click_meta_current_detail_control("meta/current/detail/list")

    def meta_current_empty_points(self) -> Tuple[int, int]:
        """Read current-beacon points from the exact empty-beacon page."""

        button_state = self.read_state()
        controls = tuple(
            self._unique(button_state, semantic_id)
            for semantic_id in ("meta/current/list", "meta/current/create")
        )
        if not all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            for target in controls
        ):
            raise SemanticGateClosed("META empty-beacon page identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META empty-beacon snapshots are not coherent")
        suffix = (
            "WorldBossUI(Clone)/pages/CurrentWorldBossEmptyUI(Clone)/progress/value"
        )
        values = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith(suffix)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if len(values) != 1:
            raise SemanticGateClosed("META empty-beacon point counter is ambiguous")
        match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", values[0])
        if match is None:
            raise SemanticGateClosed("META empty-beacon point counter is malformed")
        current, capacity = map(int, match.groups())
        if current > capacity:
            raise SemanticGateClosed("META empty-beacon points are inconsistent")
        return current, capacity

    def click_meta_current_create(self) -> ActionReceipt:
        """Create a current beacon from the exact empty-beacon control."""

        self.meta_current_empty_points()
        state = self.read_state()
        target = self._unique(state, "meta/current/create")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "meta/current/create")
        ):
            raise SemanticGateClosed("META beacon create control is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/current/create",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_current_list(self) -> ActionReceipt:
        """Open the exact current-beacon assist list without selecting combat."""

        state = self.read_state()
        target = self._unique(state, "meta/current/list")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "meta/current/list")
        ):
            raise SemanticGateClosed("META assist list is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/current/list",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_assist_state(self) -> MetaAssistState:
        """Read the selected assist beacon and remaining daily attempts."""

        button_state = self.read_state()
        start = self._unique(button_state, "meta/assist/start")
        root = "WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/"
        candidate_pattern = re.compile(
            r".*/" + re.escape(root) + r"list_panel/mask/bg/container/[1-9][0-9]*$"
        )
        candidates = tuple(
            button
            for button in button_state.buttons
            if candidate_pattern.fullmatch(button.path) is not None
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
        )
        if not (
            start.active_in_hierarchy
            and start.active_and_enabled
            and start.interactable
            and start.point is not None
            and start.bounds is not None
            and candidates
        ):
            raise SemanticGateClosed("META assist page identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META assist snapshots are not coherent")
        selected_pattern = re.compile(
            r".*/"
            + re.escape(root)
            + r"list_panel/mask/bg/container/([1-9][0-9]*)/selected(?:/.*)?$"
        )
        selected_indices = {
            int(match.group(1))
            for text in ui_state.texts
            if text.active_in_hierarchy
            and text.active_and_enabled
            and (match := selected_pattern.fullmatch(text.path)) is not None
        }
        if len(selected_indices) != 1:
            raise SemanticGateClosed("META selected assist candidate is ambiguous")

        def exact(path: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(root + path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "META assist text is absent or ambiguous: " + path
                )
            return text_value(matches[0])

        def text_value(text: TextState) -> str:
            return re.sub(r"<[^>]*>", "", text.text).strip()

        attempts_match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", exact("point/Text"))
        hp_match = re.fullmatch(r"HP:([1-9][0-9]*)", exact("main/hp/Text"))
        level = exact("main/hp/level/Text")
        if (
            attempts_match is None
            or hp_match is None
            or re.fullmatch(r"[1-9][0-9]*", level) is None
        ):
            raise SemanticGateClosed("META assist summary is malformed")
        attempts, capacity = map(int, attempts_match.groups())
        selected_candidate_index = next(iter(selected_indices))
        candidate_indices = {int(candidate.name) for candidate in candidates}
        if attempts > capacity:
            raise SemanticGateClosed("META assist attempts are inconsistent")
        if selected_candidate_index not in candidate_indices:
            raise SemanticGateClosed("META selected assist candidate is inconsistent")
        return MetaAssistState(
            remaining_attempts=attempts,
            attempt_capacity=capacity,
            selected_level=int(level),
            selected_hp=int(hp_match.group(1)),
            candidate_count=len(candidates),
            selected_candidate_index=selected_candidate_index,
        )

    def click_meta_assist_next_candidate(
        self,
        *,
        expected_index: int,
        expected_level: int,
    ) -> ActionReceipt:
        """Select the next mounted assist candidate with exact stale-state guards."""

        if (
            isinstance(expected_index, bool)
            or not isinstance(expected_index, int)
            or expected_index < 1
            or isinstance(expected_level, bool)
            or not isinstance(expected_level, int)
            or expected_level < 1
        ):
            raise SemanticGateClosed("META assist candidate expectation is invalid")
        summary = self.meta_assist_state()
        if (
            summary.selected_candidate_index != expected_index
            or summary.selected_level != expected_level
        ):
            raise SemanticGateClosed("META assist candidate changed before selection")

        state = self.read_state()
        root = "WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/"
        candidate_pattern = re.compile(
            r".*/" + re.escape(root) + r"list_panel/mask/bg/container/([1-9][0-9]*)$"
        )
        candidates = []
        for button in state.buttons:
            match = candidate_pattern.fullmatch(button.path)
            if match is None or button.name != match.group(1):
                continue
            candidates.append((int(match.group(1)), button))
        candidates.sort(key=lambda item: item[0])
        indices = tuple(index for index, _button in candidates)
        if len(candidates) < 2 or expected_index not in indices:
            raise SemanticGateClosed("META next assist candidate is absent")
        selected_position = indices.index(expected_index)
        next_index, target = candidates[(selected_position + 1) % len(candidates)]
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and 0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
            and not self._blocking_rules(state, "meta/assist/start")
        ):
            raise SemanticGateClosed("META next assist candidate is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before META candidate input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/assist/candidate/{0}".format(next_index),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_assist_start(self) -> ActionReceipt:
        """Start the currently proven META assist target."""

        summary = self.meta_assist_state()
        if summary.remaining_attempts < 1:
            raise SemanticGateClosed("META assist attempts are exhausted")
        state = self.read_state()
        target = self._unique(state, "meta/assist/start")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "meta/assist/start")
        ):
            raise SemanticGateClosed("META assist start is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/assist/start",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_assist_sortie_prompt_visible(self) -> bool:
        state = self.read_state()
        ui_state = self.read_ui_state()
        prompt = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip() == "保存当前编队并出击？"
        )
        return bool(
            len(prompt) == 1
            and len(self._matches(state, "os/exit/confirm")) == 1
            and len(self._matches(state, "os/exit/cancel")) == 1
        )

    def meta_precombat_fleet_ready(self) -> bool:
        """Require non-zero main and vanguard power on the shared META formation."""

        if not self.daily_precombat_visible():
            return False
        ui_state = self.read_ui_state()

        def exact_power(side: str) -> Optional[int]:
            suffix = f"PreCombatUI(Clone)/adapt/middle/gear_score/{side}/Text"
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
            )
            return int(matches[0].text.strip()) if len(matches) == 1 else None

        main = exact_power("main")
        vanguard = exact_power("vanguard")
        return bool(main is not None and main > 0 and vanguard is not None and vanguard > 0)

    def meta_simulation_prompt_visible(self) -> bool:
        """Recognize the optional Lv15 simulation prompt without accepting it."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        prompts = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        return bool(
            len(prompts) == 1
            and re.fullmatch(
                r"是否进入当前信标META的模拟战斗？\n战斗强度：Lv15\n"
                r"\*该战斗不消耗石油，不会获得任何奖励",
                prompts[0],
            )
            is not None
            and len(self._matches(state, "os/exit/confirm")) == 1
            and len(self._matches(state, "os/exit/cancel")) == 1
        )

    def _meta_help_texts(self) -> Tuple[int, Mapping[str, TextState]]:
        ui_state = self.read_ui_state()
        expected = {
            "confirm": (
                "WorldBossHelpUI(Clone)/confirm_btn/Text",
                "确定",
            ),
            "cancel": (
                "WorldBossHelpUI(Clone)/cancel_btn/Text",
                "取消",
            ),
            "world": (
                "WorldBossHelpUI(Clone)/window/sliders/content/world/Text",
                "世界",
            ),
            "guild": (
                "WorldBossHelpUI(Clone)/window/sliders/content/guild/Text",
                "大舰队",
            ),
            "friend": (
                "WorldBossHelpUI(Clone)/window/sliders/content/friend/Text",
                "好友",
            ),
        }
        result: Dict[str, TextState] = {}
        for key, (suffix, value) in expected.items():
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and text.text.strip() == value
            )
            if len(matches) != 1:
                raise SemanticGateClosed("META help popup identity is absent")
            result[key] = matches[0]
        return ui_state.generation, result

    def meta_help_visible(self) -> bool:
        try:
            self._meta_help_texts()
            return True
        except SemanticGateClosed:
            return False

    def click_meta_help_control(self, control: str) -> ActionReceipt:
        generation, controls = self._meta_help_texts()
        if control not in ("confirm", "cancel", "world", "guild", "friend"):
            raise ValueError("unknown META help control")
        target = controls[control]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="meta/help/{0}".format(control),
            generation=generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_simulation_cancel(self) -> ActionReceipt:
        if not self.meta_simulation_prompt_visible():
            raise SemanticGateClosed("META simulation prompt is absent")
        state = self.read_state()
        target = self._unique(state, "os/exit/cancel")
        if not (
            target.actionable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("META simulation cancel is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/simulation/cancel",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_assist_sortie(self, confirm: bool) -> ActionReceipt:
        if not self.meta_assist_sortie_prompt_visible():
            raise SemanticGateClosed("META assist sortie prompt is absent")
        state = self.read_state()
        semantic_id = "os/exit/confirm" if confirm else "os/exit/cancel"
        target = self._unique(state, semantic_id)
        # This overlay's label Graphic is the top raycast target, so Unity
        # reports the owning Button itself as raycast_top=False.  The exact,
        # unique prompt and both exact choices above prove the modal identity;
        # retain every other Button actionability invariant here.
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top in (True, False)
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("META assist sortie choice is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=(
                "meta/assist/sortie/confirm" if confirm else "meta/assist/sortie/cancel"
            ),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
