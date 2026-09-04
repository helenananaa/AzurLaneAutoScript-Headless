"""Minigame for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from .contracts import ActionReceipt, Bounds, ImageState, OracleState, Point
from .errors import SemanticGateClosed, SemanticOracleError, SemanticTargetMissing


class MinigameOracle:
    """Minigame operations sharing the oracle frame and input boundary."""

    def game_room_page_visible(self) -> bool:
        """Identify the game room without treating its list overlay as a new page."""

        state = self.read_state()
        for semantic_id in ("game-room/play", "game-room/back"):
            matches = self._matches(state, semantic_id)
            if not (
                len(matches) == 1
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].bounds is not None
            ):
                return False
        return True

    def shooting_minigame_prepare_visible(self) -> bool:
        """Identify the current shooting-minigame pre-start panel exactly."""

        state = self.read_state()
        required = {
            "back": "GameRoomShootingUI(Clone)/noAdaptPanel/blur_panel/top/back",
            "ruleGame": (
                "GameRoomShootingUI(Clone)/noAdaptPanel/blur_panel/"
                "start_mask/ruleGame"
            ),
            "startGame": (
                "GameRoomShootingUI(Clone)/noAdaptPanel/blur_panel/"
                "start_mask/startGame"
            ),
        }
        for name, suffix in required.items():
            matches = tuple(
                button
                for button in state.buttons
                if button.name == name
                and button.path.endswith(suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.bounds is not None
            )
            if len(matches) != 1:
                return False
        counters = tuple(
            text
            for text in self.read_ui_state().texts
            if text.path.endswith("GameRoomCoinUI(Clone)/ad/window/text")
            and text.name == "text"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[0-9]+/[0-9]+", text.text.strip())
        )
        return len(counters) == 1

    def click_shooting_minigame_back(self) -> ActionReceipt:
        """Leave the proven current shooting-minigame pre-start panel."""

        if not self.shooting_minigame_prepare_visible():
            raise SemanticTargetMissing("shooting minigame pre-start panel is absent")
        state = self.read_state()
        target = self._unique(state, "minigame/shooting/back")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before shooting minigame back")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="minigame/shooting/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def game_room_list_visible(self) -> bool:
        if not self.game_room_page_visible():
            return False
        ui_state = self.read_ui_state()
        icons = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.bounds is not None
            and image.path.endswith(
                "GameHallUI(Clone)/ad/listPanel/ad/viewport/content/"
                "listTpl(Clone)/mask/gameIcon"
            )
        )
        scrollbar = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.bounds is not None
            and image.sprite == "scrollbar"
            and image.path.endswith(
                "GameHallUI(Clone)/ad/listPanel/ad/viewport/Scrollbar/"
                "Sliding Area/Handle"
            )
        )
        return len(icons) >= 1 and len(scrollbar) == 1

    def minigame_coin_amount(self) -> int:
        if not self.game_room_page_visible():
            raise SemanticGateClosed("game-room identity is absent")
        ui_state = self.read_ui_state()
        matches = tuple(
            text
            for text in ui_state.texts
            if text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.path.endswith("GameHallUI(Clone)/ad/topPanel/coin/text")
            and re.fullmatch(r"[0-9]{1,2}", text.text.strip())
        )
        if len(matches) != 1:
            raise SemanticGateClosed("game-room coin amount is absent or ambiguous")
        amount = int(matches[0].text.strip())
        if not 0 <= amount <= 40:
            raise SemanticGateClosed(
                "game-room coin amount is outside the reviewed range"
            )
        return amount

    def minigame_scroll_position(self) -> float:
        if not self.game_room_list_visible():
            raise SemanticGateClosed("game-room list identity is absent")
        ui_state = self.read_ui_state()
        tracks = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.bounds is not None
            and image.sprite == "scrollbarBottom"
            and image.path.endswith(
                "GameHallUI(Clone)/ad/listPanel/ad/viewport/Scrollbar"
            )
        )
        handles = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.bounds is not None
            and image.sprite == "scrollbar"
            and image.path.endswith(
                "GameHallUI(Clone)/ad/listPanel/ad/viewport/Scrollbar/"
                "Sliding Area/Handle"
            )
        )
        if len(tracks) != 1 or len(handles) != 1:
            raise SemanticGateClosed("game-room scrollbar is absent or ambiguous")
        track = tracks[0].bounds
        handle = handles[0].bounds
        assert track is not None and handle is not None
        travel = (track.bottom - track.top) - (handle.bottom - handle.top)
        if travel <= 0:
            raise SemanticGateClosed("game-room scrollbar geometry is invalid")
        position = (handle.top - track.top) / travel
        if not -0.03 <= position <= 1.03:
            raise SemanticGateClosed("game-room scrollbar position is invalid")
        return min(1.0, max(0.0, position))

    def minigame_scroll_to(self, position: float) -> bool:
        if isinstance(position, bool) or not isinstance(position, (int, float)):
            raise TypeError("minigame scroll target must be numeric")
        position = float(position)
        if not 0.0 <= position <= 1.0:
            raise ValueError("minigame scroll target must be within [0, 1]")
        if self._swipe is None:
            raise SemanticGateClosed("semantic minigame swipe backend is unavailable")
        before = self.minigame_scroll_position()
        if abs(position - before) < 0.05:
            return False
        ui_state = self.read_ui_state()
        tracks = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.bounds is not None
            and image.sprite == "scrollbarBottom"
            and image.path.endswith(
                "GameHallUI(Clone)/ad/listPanel/ad/viewport/Scrollbar"
            )
        )
        handles = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.bounds is not None
            and image.sprite == "scrollbar"
            and image.path.endswith(
                "GameHallUI(Clone)/ad/listPanel/ad/viewport/Scrollbar/"
                "Sliding Area/Handle"
            )
        )
        if len(tracks) != 1 or len(handles) != 1:
            raise SemanticGateClosed("game-room scrollbar changed before input")
        track = tracks[0].bounds
        handle = handles[0].bounds
        assert track is not None and handle is not None
        height = handle.bottom - handle.top
        travel = (track.bottom - track.top) - height
        x = int(round((handle.left + handle.right) / 2.0))
        start_y = int(round((handle.top + handle.bottom) / 2.0))
        end_y = int(round(track.top + position * travel + height / 2.0))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before minigame scroll")
        self._swipe(x, start_y, x, end_y, 350)
        deadline = self._monotonic() + 5.0
        while self._monotonic() < deadline:
            try:
                after = self.minigame_scroll_position()
                if abs(after - position) < 0.08:
                    return True
            except SemanticOracleError:
                pass
            self._sleep(0.2)
        raise SemanticGateClosed("game-room scrollbar transition was not proven")

    def click_new_year_challenge_entry(self) -> ActionReceipt:
        if not self.game_room_list_visible():
            raise SemanticGateClosed("game-room list identity is absent")
        state = self.read_state()
        ui_state = self.read_ui_state()
        icons = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.bounds is not None
            and image.sprite == "fushun2"
            and image.path.endswith(
                "GameHallUI(Clone)/ad/listPanel/ad/viewport/content/"
                "listTpl(Clone)/mask/gameIcon"
            )
        )
        if len(icons) != 1:
            raise SemanticTargetMissing("new-year challenge entry is absent")
        icon = icons[0]
        root_path = icon.path.rsplit("/mask/gameIcon", 1)[0]
        assert icon.bounds is not None
        icon_center = Point(
            (icon.bounds.left + icon.bounds.right) / 2.0,
            (icon.bounds.top + icon.bounds.bottom) / 2.0,
        )
        buttons = tuple(
            button
            for button in state.buttons
            if button.path == root_path
            and button.name == "listTpl(Clone)"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
            and button.bounds.contains(icon_center)
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("new-year challenge list item is ambiguous")
        target = buttons[0]
        assert target.bounds is not None
        left = max(0.0, target.bounds.left)
        top = max(0.0, target.bounds.top)
        right = min(float(self.fingerprint.width), target.bounds.right)
        bottom = min(float(self.fingerprint.height), target.bounds.bottom)
        if right - left < 100 or bottom - top < 100:
            raise SemanticTargetMissing(
                "new-year challenge entry is outside the viewport"
            )
        point = Point((left + right) / 2.0, (top + bottom) / 2.0)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before minigame entry")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="minigame/new-year/entry",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _minigame_ticket_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        prompts = {
            "本月可获取游戏奖券数量即将达到上限，继续游玩可能会有部分奖券无法获得，是否继续游玩？",
            "本月可获取游戏奖券数量已达到上限，继续游玩将无法获得游戏奖券，是否继续游玩？",
        }
        return plain in prompts and cancel == "取消" and confirm == "确定"

    def minigame_ticket_prompt_visible(self) -> bool:
        return self._minigame_ticket_prompt_matches(self.read_state())

    def new_year_challenge_ticket_count(self) -> Tuple[int, int]:
        """Read the exact ``selected/owned`` counter on Fushun's prepare page."""

        state = self.read_state()
        required = {
            "sub": "GameRoomCoinUI(Clone)/ad/window/sub",
            "add": "GameRoomCoinUI(Clone)/ad/window/add",
            "btn_start": "GameRoomFushun2UI(Clone)/btn_start",
            "btn_help": "GameRoomFushun2UI(Clone)/btn_help",
        }
        for name, suffix in required.items():
            matches = tuple(
                button
                for button in state.buttons
                if button.name == name
                and button.path.endswith(suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.bounds is not None
                and button.point is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "new-year challenge prepare controls are incomplete"
                )
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed(
                "new-year challenge prepare snapshots are not coherent"
            )
        counters = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("GameRoomCoinUI(Clone)/ad/window/text")
            and text.name == "text"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(counters) != 1:
            raise SemanticGateClosed(
                "new-year challenge ticket counter is absent or ambiguous"
            )
        match = re.fullmatch(r"(\d{1,2})/(\d{1,3})", counters[0].text.strip())
        if match is None:
            raise SemanticGateClosed("new-year challenge ticket counter is malformed")
        selected, owned = (int(match.group(1)), int(match.group(2)))
        if owned <= 0 or selected > owned:
            raise SemanticGateClosed(
                "new-year challenge ticket counter is inconsistent"
            )
        return selected, owned

    def click_new_year_challenge_prepare_control(self, control: str) -> ActionReceipt:
        """Click one exact Fushun prepare control in the current Unity layout."""

        controls = {
            "add": ("add", "GameRoomCoinUI(Clone)/ad/window/add"),
            "sub": ("sub", "GameRoomCoinUI(Clone)/ad/window/sub"),
            "start": ("btn_start", "GameRoomFushun2UI(Clone)/btn_start"),
            "back": ("back", "GameRoomFushun2UI(Clone)/back"),
        }
        try:
            name, suffix = controls[control]
        except KeyError as exc:
            raise SemanticGateClosed(
                "unsupported new-year challenge prepare control"
            ) from exc
        progress, monthly_limit = self.new_year_challenge_ticket_count()
        if control == "add" and progress >= monthly_limit:
            raise SemanticGateClosed(
                "new-year challenge monthly progress is already complete"
            )
        if control == "start" and not 0 <= progress <= monthly_limit:
            raise SemanticGateClosed(
                "new-year challenge monthly progress is inconsistent"
            )
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.name == name
            and button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            # These exact current Fushun controls are observed without a
            # GraphicRaycaster result in the headless bridge.  Their unique
            # hierarchy, enabled Button and in-bounds point form the reviewed
            # delegated input contract.
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "new-year challenge prepare control is absent or ambiguous"
            )
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "foreground changed before new-year challenge input"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="minigame/new-year/{0}".format(control),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def new_year_challenge_result(self) -> Optional[Tuple[int, int]]:
        """Return ``score, highest`` for the exact Fushun result panel."""

        state = self.read_state()
        close_path = (
            "GameRoomFushun2UI(Clone)/FushunAdventureGame(Clone)/UI/"
            "result_panel/frame/close"
        )
        closes = tuple(
            button
            for button in state.buttons
            if button.name == "close"
            and button.path.endswith(close_path)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if not closes:
            return None
        if len(closes) != 1:
            raise SemanticGateClosed("new-year challenge result close is ambiguous")
        ui_state = self.read_ui_state()
        values = {}
        for label, suffix in (
            (
                "score",
                "FushunAdventureGame(Clone)/UI/result_panel/frame/score/Text",
            ),
            (
                "highest",
                "FushunAdventureGame(Clone)/UI/result_panel/frame/highest/Text",
            ),
        ):
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and re.fullmatch(r"\d{1,7}", text.text.strip())
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "new-year challenge result {0} is incomplete".format(label)
                )
            values[label] = int(matches[0].text.strip())
        return values["score"], values["highest"]

    def click_new_year_challenge_result_close(self) -> ActionReceipt:
        result = self.new_year_challenge_result()
        if result is None:
            raise SemanticTargetMissing("new-year challenge result is absent")
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "close"
            and button.path.endswith(
                "FushunAdventureGame(Clone)/UI/result_panel/frame/close"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("new-year challenge result close changed")
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before result close")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="minigame/new-year/result-close",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def new_year_challenge_help_visible(self) -> bool:
        state = self.read_state()
        helps = tuple(
            button
            for button in state.buttons
            if button.name == "help"
            and button.path.endswith("FushunAdventureGame(Clone)/UI/help")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds == Bounds(0.0, 0.0, 1280.0, 720.0)
        )
        if not helps:
            return False
        if len(helps) != 1:
            raise SemanticGateClosed("new-year challenge help is ambiguous")
        ui_state = self.read_ui_state()
        art = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("FushunAdventureGame(Clone)/UI/help/Image")
            and image.sprite == "fushungame"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
        )
        return len(art) == 1

    def click_new_year_challenge_help(self) -> ActionReceipt:
        if not self.new_year_challenge_help_visible():
            raise SemanticTargetMissing("new-year challenge help is absent")
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "help"
            and button.path.endswith("FushunAdventureGame(Clone)/UI/help")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds == Bounds(0.0, 0.0, 1280.0, 720.0)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("new-year challenge help changed")
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before help close")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="minigame/new-year/help-close",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def new_year_challenge_key_sprites(self) -> Tuple[str, str, str]:
        """Read the exact current three-slot A/B command queue."""

        ui_state = self.read_ui_state()
        values: Dict[int, str] = {}
        pattern = re.compile(r"FushunAdventureGame\(Clone\)/UI/keys/([123])$")
        for image in ui_state.images:
            match = pattern.search(image.path)
            if (
                match is None
                or not image.active_in_hierarchy
                or not image.active_and_enabled
                or image.bounds is None
            ):
                continue
            index = int(match.group(1))
            if index in values:
                raise SemanticGateClosed("new-year challenge key slot is ambiguous")
            values[index] = image.sprite
        if tuple(sorted(values)) != (1, 2, 3):
            raise SemanticGateClosed("new-year challenge key queue is incomplete")
        return values[1], values[2], values[3]

    def new_year_challenge_attack_state(self) -> Tuple[int, int, bool]:
        """Return ``score, enemy_hp, attackable`` for the current Fushun frame."""

        if self.new_year_challenge_result() is not None:
            raise SemanticGateClosed("new-year challenge is already settled")
        ui_state = self.read_ui_state()
        scores = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(
                "FushunAdventureGame(Clone)/UI/heart_score/score/Text"
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"\d{1,7}", text.text.strip())
        )
        if len(scores) != 1:
            raise SemanticGateClosed("new-year challenge score is incomplete")
        hp_marks = tuple(
            image
            for image in ui_state.images
            if (
                "/FushunAdventureGame(Clone)/game/fa_beast" in image.path
                and re.search(r"/hp/tpl(?:\(Clone\))?/mark$", image.path) is not None
            )
            if image.sprite == "hp"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
        )
        ranges = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("FushunAdventureGame(Clone)/game/range/Image")
            and image.sprite == "range_sel"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
        )
        if len(ranges) > 1:
            raise SemanticGateClosed("new-year challenge attack state is ambiguous")
        if not ranges:
            return int(scores[0].text.strip()), 0, False
        range_bounds = ranges[0].bounds
        assert range_bounds is not None
        marks_by_root: Dict[str, List[ImageState]] = {}
        for mark in hp_marks:
            root = mark.path.split("/hp/", 1)[0]
            marks_by_root.setdefault(root, []).append(mark)
        candidates = []
        for root, marks in marks_by_root.items():
            if len(marks) > 3:
                raise SemanticGateClosed(
                    "new-year challenge enemy HP is outside the reviewed range"
                )
            enemies = tuple(
                image
                for image in ui_state.images
                if image.path == root
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
            )
            # Spawn/despawn animation can briefly expose HP before the main
            # sprite. Treat that frame as non-actionable and wait for coherence.
            if len(enemies) != 1:
                continue
            enemy_bounds = enemies[0].bounds
            assert enemy_bounds is not None
            enemy_center = (enemy_bounds.left + enemy_bounds.right) / 2.0
            if range_bounds.left <= enemy_center <= range_bounds.right:
                candidates.append((root, len(marks)))
        if len(candidates) > 1:
            raise SemanticGateClosed(
                "multiple new-year challenge enemies overlap the attack area"
            )
        if not candidates:
            return int(scores[0].text.strip()), 0, False
        return int(scores[0].text.strip()), candidates[0][1], True

    def click_new_year_challenge_attack_key(self, key: str) -> Optional[ActionReceipt]:
        if key not in ("A", "B"):
            raise SemanticGateClosed("new-year challenge key is unsupported")
        _, hp, attackable = self.new_year_challenge_attack_state()
        if not attackable or hp <= 0:
            return None
        state = self.read_state()
        ui_state = self.read_ui_state()
        matches = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("FushunAdventureGame(Clone)/UI/{0}".format(key))
            and image.sprite == key
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
            and image.bounds.left >= 0
            and image.bounds.top >= 0
            and image.bounds.right <= self.fingerprint.width
            and image.bounds.bottom <= self.fingerprint.height
        )
        if len(matches) != 1:
            raise SemanticGateClosed("new-year challenge attack key is ambiguous")
        target = matches[0]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before minigame attack")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="minigame/new-year/key-{0}".format(key.lower()),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_new_year_challenge_attack_combo(
        self, first_key: str = "A"
    ) -> Tuple[ActionReceipt, ...]:
        """Atomically prove an in-range enemy and press exactly its HP count."""

        if first_key not in ("A", "B"):
            raise SemanticGateClosed("new-year challenge combo key is unsupported")
        score, hp, attackable = self.new_year_challenge_attack_state()
        del score
        if not attackable or hp <= 0:
            return ()
        state = self.read_state()
        ui_state = self.read_ui_state()
        targets: Dict[str, ImageState] = {}
        for key in ("A", "B"):
            matches = tuple(
                image
                for image in ui_state.images
                if image.path.endswith("FushunAdventureGame(Clone)/UI/{0}".format(key))
                and image.sprite == key
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed("new-year challenge combo key is ambiguous")
            targets[key] = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before minigame combo")
        receipts = []
        for index in range(hp):
            key = first_key if index % 2 == 0 else ("B" if first_key == "A" else "A")
            target = targets[key]
            assert target.bounds is not None
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
            self._tap(int(round(point.x)), int(round(point.y)))
            receipts.append(
                ActionReceipt(
                    semantic_id="minigame/new-year/key-{0}".format(key.lower()),
                    generation=state.generation,
                    point=point,
                    bounds=target.bounds,
                    path=target.path,
                )
            )
            if index + 1 < hp:
                self._sleep(0.08)
        return tuple(receipts)

    def new_year_challenge_tick(
        self, first_key: str = "A"
    ) -> Tuple[Optional[Tuple[int, int]], int, Tuple[ActionReceipt, ...]]:
        """Observe and act on one Fushun frame without cross-frame drift."""

        if first_key not in ("A", "B"):
            raise SemanticGateClosed("new-year challenge tick key is unsupported")
        state = self.read_state()
        ui_state = self.read_ui_state()
        result_close = tuple(
            button
            for button in state.buttons
            if button.name == "close"
            and button.path.endswith(
                "FushunAdventureGame(Clone)/UI/result_panel/frame/close"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
        )
        if result_close:
            if len(result_close) != 1:
                raise SemanticGateClosed("new-year challenge tick result is ambiguous")
            values = {}
            for label, suffix in (
                ("score", "result_panel/frame/score/Text"),
                ("highest", "result_panel/frame/highest/Text"),
            ):
                matches = tuple(
                    text
                    for text in ui_state.texts
                    if text.path.endswith("FushunAdventureGame(Clone)/UI/" + suffix)
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    and text.bounds is not None
                    and re.fullmatch(r"\d{1,7}", text.text.strip())
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "new-year challenge tick result is incomplete"
                    )
                values[label] = int(matches[0].text.strip())
            return (values["score"], values["highest"]), values["score"], ()

        scores = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(
                "FushunAdventureGame(Clone)/UI/heart_score/score/Text"
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"\d{1,7}", text.text.strip())
        )
        if len(scores) != 1:
            return None, 0, ()
        score = int(scores[0].text.strip())
        ranges = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("FushunAdventureGame(Clone)/game/range/Image")
            and image.sprite == "range_sel"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
        )
        if not ranges:
            return None, score, ()
        if len(ranges) != 1:
            raise SemanticGateClosed("new-year challenge tick range is ambiguous")
        range_bounds = ranges[0].bounds
        assert range_bounds is not None
        marks_by_root: Dict[str, List[ImageState]] = {}
        for image in ui_state.images:
            if (
                "/FushunAdventureGame(Clone)/game/fa_beast" in image.path
                and re.search(r"/hp/tpl(?:\(Clone\))?/mark$", image.path) is not None
                and image.sprite == "hp"
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
            ):
                marks_by_root.setdefault(image.path.split("/hp/", 1)[0], []).append(
                    image
                )
        candidates = []
        for root, marks in marks_by_root.items():
            if not 1 <= len(marks) <= 3:
                continue
            enemies = tuple(
                image
                for image in ui_state.images
                if image.path == root
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
            )
            if len(enemies) != 1:
                continue
            bounds = enemies[0].bounds
            assert bounds is not None
            center = (bounds.left + bounds.right) / 2.0
            if range_bounds.left <= center <= range_bounds.right:
                candidates.append((root, len(marks)))
        if len(candidates) != 1:
            return None, score, ()
        hp = candidates[0][1]
        key_images: Dict[str, ImageState] = {}
        for key in ("A", "B"):
            matches = tuple(
                image
                for image in ui_state.images
                if image.path.endswith("FushunAdventureGame(Clone)/UI/{0}".format(key))
                and image.sprite == key
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed("new-year challenge tick key is ambiguous")
            key_images[key] = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before minigame tick")
        receipts = []
        for index in range(hp):
            key = first_key if index % 2 == 0 else ("B" if first_key == "A" else "A")
            target = key_images[key]
            assert target.bounds is not None
            point = Point(
                (target.bounds.left + target.bounds.right) / 2.0,
                (target.bounds.top + target.bounds.bottom) / 2.0,
            )
            self._tap(int(round(point.x)), int(round(point.y)))
            receipts.append(
                ActionReceipt(
                    semantic_id="minigame/new-year/key-{0}".format(key.lower()),
                    generation=state.generation,
                    point=point,
                    bounds=target.bounds,
                    path=target.path,
                )
            )
            if index + 1 < hp:
                self._sleep(0.08)
        return None, score, tuple(receipts)
