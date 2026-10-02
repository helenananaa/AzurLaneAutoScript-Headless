"""Exercise for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import List, Tuple
from .contracts import ActionReceipt, Point
from .errors import SemanticGateClosed


class ExerciseOracle:
    """Exercise operations sharing the oracle frame and input boundary."""

    def click_exercise_home(self) -> ActionReceipt:
        """Use the reviewed home option, independently of the stack back."""
        if not self.exercise_page_visible():
            raise SemanticGateClosed('Exercise page identity is absent')
        state = self.read_state()
        target = self._unique(state, 'exercise/page/home')
        if not (target.active_in_hierarchy and target.active_and_enabled
                and target.interactable and target.raycast_top in (None, True)
                and target.point is not None and target.bounds is not None
                and target.bounds.contains(target.point)
                and not self._blocking_rules(state, 'exercise/page/home')):
            raise SemanticGateClosed('Exercise home option is not actionable')
        ui = self.read_ui_state()
        images = tuple(image for image in ui.images
                       if image.path == target.path and image.active_in_hierarchy
                       and image.active_and_enabled)
        if not (state.generation <= ui.generation <= state.generation + 2
                and len(images) == 1 and not images[0].truncated
                and images[0].sprite == 'viewall_1920'
                and images[0].raycast_target is True):
            raise SemanticGateClosed('Exercise home option identity is not proven')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Exercise home input')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(semantic_id='exercise/page/home', generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def exercise_page_visible(self) -> bool:
        state = self.read_state()
        back = self._matches(state, "exercise/page/back")
        rivals = tuple(
            button
            for button in state.buttons
            if re.fullmatch(r"rivaltpl_[1-4]", button.name)
            and re.search(
                r"MilitaryExerciseUI\(Clone\)/center/rival_list/"
                r"rivaltpl_[1-4]$",
                button.path,
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        ui_state = self.read_ui_state()
        counts = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("MilitaryExerciseUI(Clone)/center/season_info/count")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]+/[0-9]+", text.text.strip())
        )
        return bool(len(back) == 1 and len(rivals) == 4 and len(counts) == 1)

    def exercise_remaining(self) -> int:
        state = self.read_ui_state()
        counts = tuple(
            text.text.strip()
            for text in state.texts
            if text.path.endswith("MilitaryExerciseUI(Clone)/center/season_info/count")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(counts) != 1:
            raise SemanticGateClosed("exercise remaining count is ambiguous")
        match = re.fullmatch(r"([0-9]+)/([0-9]+)", counts[0])
        if match is None:
            raise SemanticGateClosed("exercise remaining count is malformed")
        remain, maximum = (int(value) for value in match.groups())
        if maximum != 10 or not 0 <= remain <= maximum:
            raise SemanticGateClosed("exercise remaining count is outside bounds")
        return remain

    def exercise_period_remaining_text(self) -> str:
        """Return ALAS-compatible season time from exact typed components."""

        if not self.exercise_page_visible():
            raise SemanticGateClosed("exercise page identity is not proven")
        state = self.read_ui_state()
        root = "MilitaryExerciseUI(Clone)/center/season_info/left_time_container/"
        days = tuple(
            text.text.strip() for text in state.texts
            if text.path.endswith(root + "day")
            and text.active_in_hierarchy and text.active_and_enabled
            and not text.truncated and text.bounds is not None
        )
        times = tuple(
            text.text.strip() for text in state.texts
            if text.path.endswith(root + "time")
            and text.active_in_hierarchy and text.active_and_enabled
            and not text.truncated and text.bounds is not None
        )
        if len(days) != 1 or len(times) != 1:
            raise SemanticGateClosed("exercise season time is ambiguous")
        if re.fullmatch(r"[0-9]+", days[0]) is None:
            raise SemanticGateClosed("exercise season day is malformed")
        match = re.fullmatch(r"([0-9]{1,2}):([0-9]{2}):([0-9]{2})", times[0])
        if match is None or int(match.group(1)) > 23 or int(match.group(2)) > 59 or int(match.group(3)) > 59:
            raise SemanticGateClosed("exercise season clock is malformed")
        return "{0}d{1}".format(days[0], times[0])

    def exercise_opponent_power(self, index: int) -> Tuple[int, int]:
        """Return exact main/vanguard power for one proven opponent card."""

        if isinstance(index, bool) or not isinstance(index, int) or index not in range(1, 5):
            raise ValueError("exercise opponent index must be in [1, 4]")
        if not self.exercise_page_visible():
            raise SemanticGateClosed("exercise page identity is not proven")
        state = self.read_ui_state()
        prefix = (
            "MilitaryExerciseUI(Clone)/center/rival_list/rivaltpl_{0}/"
            "comprehensive_panel/comprehensive/"
        ).format(index)
        result = []
        for fleet in ("main_fleet", "vanguard_fleet"):
            matches = tuple(
                text.text.strip() for text in state.texts
                if text.path.endswith(prefix + fleet + "/value")
                and text.active_in_hierarchy and text.active_and_enabled
                and not text.truncated and text.bounds is not None
            )
            if len(matches) != 1 or re.fullmatch(r"[0-9]+", matches[0]) is None:
                raise SemanticGateClosed("exercise opponent power is ambiguous")
            value = int(matches[0])
            if value <= 0:
                raise SemanticGateClosed("exercise opponent power is outside bounds")
            result.append(value)
        return (result[0], result[1])

    def exercise_opponent_detail_visible(self) -> bool:
        state = self.read_state()
        start = self._matches(state, "exercise/opponent/start")
        ui_state = self.read_ui_state()
        titles = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("RivalInfoUI(Clone)/info/title_miex")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        levels = tuple(
            text
            for text in ui_state.texts
            if re.search(
                r"RivalInfoUI\(Clone\)/ships_container/ships/"
                r"(?:main|vanguard)/ShipCardTpl\(Clone\)/content/"
                r"dockyard/lv/Text$",
                text.path,
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]{1,3}", text.text.strip())
        )
        return bool(len(start) == 1 and len(titles) == 1 and 1 <= len(levels) <= 6)

    def exercise_opponent_levels(self) -> Tuple[int, int, int, int, int, int]:
        """Return packed main/vanguard levels, padding empty slots with zero."""

        if not self.exercise_opponent_detail_visible():
            raise SemanticGateClosed("exercise opponent detail identity is not proven")
        state = self.read_ui_state()
        result: List[int] = []
        for fleet in ("main", "vanguard"):
            suffix = (
                "RivalInfoUI(Clone)/ships_container/ships/{0}/"
                "ShipCardTpl(Clone)/content/dockyard/lv/Text"
            ).format(fleet)
            matches = sorted(
                (
                    text for text in state.texts
                    if text.path.endswith(suffix)
                    and text.active_in_hierarchy and text.active_and_enabled
                    and not text.truncated and text.bounds is not None
                    and re.fullmatch(r"[0-9]{1,3}", text.text.strip())
                ),
                key=lambda text: text.bounds.left if text.bounds is not None else -1,
            )
            if not 1 <= len(matches) <= 3:
                raise SemanticGateClosed("exercise opponent fleet levels are ambiguous")
            values = [int(text.text.strip()) for text in matches]
            if any(not 1 <= value <= 150 for value in values):
                raise SemanticGateClosed("exercise opponent level is outside bounds")
            result.extend(values + [0] * (3 - len(values)))
        return tuple(result)  # type: ignore[return-value]

    def click_exercise_opponent_back(self) -> ActionReceipt:
        """Dismiss the full-screen rival overlay through a reviewed blank edge."""

        if not self.exercise_opponent_detail_visible():
            raise SemanticGateClosed("exercise opponent detail identity is not proven")
        state = self.read_state()
        target = self._unique(state, "exercise/opponent/back")
        # This is the center of pinned ALAS BACK_ARROW.button (33,31,81,78).
        # RivalInfoUI exposes the full-screen bg as the actual raycast target.
        point = Point(57.0, 54.0)
        if target.bounds is None or not target.bounds.contains(point):
            raise SemanticGateClosed("exercise opponent back edge is outside its root")
        self._tap(57, 54)
        return ActionReceipt(
            semantic_id="exercise/opponent/back",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_exercise_award_info_close(self) -> ActionReceipt:
        """Close the exact standalone Exercise AwardInfo result popup."""

        if not self.award_info_page_visible():
            raise SemanticGateClosed("exercise award-info page is absent")
        state = self.read_state()
        matches = self._matches(state, "reward/award-info/close")
        if len(matches) != 1:
            raise SemanticGateClosed("exercise award-info close target is ambiguous")
        target = matches[0]
        if (
            not target.active_in_hierarchy or not target.active_and_enabled
            or not target.interactable or target.raycast_top is not True
            or target.point is None or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("exercise award-info close target is invalid")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="exercise/reward/close", generation=state.generation,
            point=target.point, bounds=target.bounds, path=target.path,
        )

    def exercise_reward_item_info_visible(self) -> bool:
        state = self.read_state()
        cancel = self._matches(state, "reward/item-info/cancel")
        ui_state = self.read_ui_state()
        item_texts = tuple(
            text for text in ui_state.texts
            if "/Msgbox(Clone)/window/single_item_panel/" in text.path
            and text.active_in_hierarchy and text.active_and_enabled
            and not text.truncated and text.bounds is not None
        )
        return bool(len(cancel) == 1 and cancel[0].actionable and item_texts)

    def click_exercise_reward_item_info_cancel(self) -> ActionReceipt:
        if not self.exercise_reward_item_info_visible():
            raise SemanticGateClosed("exercise reward item-info prompt is absent")
        state = self.read_state()
        target = self._unique(state, "reward/item-info/cancel")
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed("exercise reward item-info cancel is invalid")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="exercise/reward/item-info/cancel",
            generation=state.generation, point=target.point,
            bounds=target.bounds, path=target.path,
        )

    def exercise_merit_shop_visible(self) -> bool:
        state = self.read_state()
        cards = tuple(
            button for button in state.buttons
            if re.fullmatch(r"[0-9]", button.name)
            and "/ShopSupplyShopUI(Clone)/scroll/content/" in button.path
            and button.active_in_hierarchy and button.active_and_enabled
        )
        return bool(
            len(cards) == 10
            and len(self._matches(state, "exercise/merit-shop/close")) == 1
        )

    def click_exercise_merit_shop_close(self) -> ActionReceipt:
        if not self.exercise_merit_shop_visible():
            raise SemanticGateClosed("exercise merit shop is absent")
        state = self.read_state()
        target = self._unique(state, "exercise/merit-shop/close")
        if (
            not target.active_in_hierarchy or not target.active_and_enabled
            or not target.interactable or target.raycast_top is not None
            or target.point is None or target.bounds is None
        ):
            raise SemanticGateClosed("exercise merit shop close is invalid")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="exercise/merit-shop/close", generation=state.generation,
            point=target.point, bounds=target.bounds, path=target.path,
        )

    def exercise_duel_hp(self) -> Tuple[float, float]:
        """Read the exact attacker/defender duel bars used by upstream Exercise."""

        state = self.read_state()
        pauses = self._matches(state, "exercise/combat/pause")
        ui_state = self.read_ui_state()
        values = []
        for side in ("leftDamageBar", "rightDamageBar"):
            suffix = (
                "CombatUIStandard(Clone)/DuelDamageRate/{0}/bar/progress"
            ).format(side)
            matches = tuple(
                image for image in ui_state.images
                if image.path.endswith(suffix)
                and image.active_in_hierarchy and image.active_and_enabled
                and image.bounds is not None
            )
            if len(matches) != 1 or not 0.0 <= matches[0].fill_amount <= 1.0:
                raise SemanticGateClosed("exercise duel HP bar is ambiguous")
            values.append(float(matches[0].fill_amount))
        if len(pauses) != 1:
            raise SemanticGateClosed("exercise combat identity is not proven")
        return (values[0], values[1])

    def click_exercise_combat_pause(self) -> ActionReceipt:
        self.exercise_duel_hp()
        state = self.read_state()
        target = self._unique(state, "exercise/combat/pause")
        if (
            not target.active_in_hierarchy or not target.active_and_enabled
            or not target.interactable or target.raycast_top is not None
            or target.point is None or target.bounds is None
        ):
            raise SemanticGateClosed("exercise pause target is invalid")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="exercise/combat/pause", generation=state.generation,
            point=target.point, bounds=target.bounds, path=target.path,
        )

    def exercise_combat_pause_menu_visible(self) -> bool:
        state = self.read_state()
        target = self._matches(state, "exercise/combat/leave")
        pause = self._matches(state, "exercise/combat/pause")
        return bool(
            len(target) == 1 and len(pause) == 1
            and target[0].active_in_hierarchy
            and target[0].active_and_enabled
            and target[0].interactable
            and target[0].raycast_top is None
            and target[0].point is not None
            and target[0].bounds is not None
            and target[0].bounds.contains(target[0].point)
        )

    def click_exercise_combat_leave(self) -> ActionReceipt:
        if not self.exercise_combat_pause_menu_visible():
            raise SemanticGateClosed("exercise pause menu is absent")
        state = self.read_state()
        target = self._unique(state, "exercise/combat/leave")
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed("exercise leave target is invalid")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="exercise/combat/leave", generation=state.generation,
            point=target.point, bounds=target.bounds, path=target.path,
        )

    def exercise_combat_quit_confirm_visible(self) -> bool:
        state = self.read_state()
        confirm = self._matches(state, "exercise/combat/quit-confirm")
        cancel = tuple(
            button for button in state.buttons
            if button.path.endswith(
                "Overlay/UIMain/Msgbox(Clone)/window/button_container/"
                "custom_button_1(Clone)"
            )
            and button.active_in_hierarchy and button.active_and_enabled
            and button.interactable
        )
        pause = self._matches(state, "exercise/combat/pause")
        ui_state = self.read_ui_state()
        message = tuple(
            text for text in ui_state.texts
            if text.path.endswith("Overlay/UIMain/Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy and text.active_and_enabled
            and not text.truncated and bool(text.text.strip())
        )
        return bool(
            len(confirm) == 1 and len(cancel) == 1
            and len(pause) == 1 and len(message) == 1
            and confirm[0].active_in_hierarchy
            and confirm[0].active_and_enabled
            and confirm[0].interactable
            and confirm[0].raycast_top is None
            and confirm[0].point is not None
            and confirm[0].bounds is not None
            and confirm[0].bounds.contains(confirm[0].point)
        )

    def click_exercise_combat_quit_confirm(self) -> ActionReceipt:
        if not self.exercise_combat_quit_confirm_visible():
            raise SemanticGateClosed("exercise quit confirmation is absent")
        state = self.read_state()
        target = self._unique(state, "exercise/combat/quit-confirm")
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed("exercise quit confirmation is invalid")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="exercise/combat/quit-confirm",
            generation=state.generation, point=target.point,
            bounds=target.bounds, path=target.path,
        )
