"""Guild for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    GuildExchangeItemState,
    GuildFormationState,
    GuildLogisticsState,
    GuildOperationsState,
    OracleState,
    Point,
    ToggleState,
    UiState,
)
from .errors import SemanticGateClosed


class GuildOracle:
    """Guild operations sharing the oracle frame and input boundary."""

    @staticmethod
    def _guild_page_visible_from_states(
        button_state: OracleState,
        ui_state: UiState,
    ) -> bool:
        back = tuple(
            button
            for button in button_state.buttons
            if button.name == "back"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.bounds is not None
            and button.point is not None
            and button.bounds.contains(button.point)
        )
        nav_root = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/frame/"
            "scroll_rect/tagRoot/"
        )
        nav = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.path.startswith(nav_root)
            and toggle.path.count("/") == nav_root.count("/")
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.interactable
            and toggle.bounds is not None
            and toggle.point is not None
            and toggle.bounds.contains(toggle.point)
        )
        names = {toggle.name for toggle in nav}
        member_names = {"main", "member", "office", "technology", "battle"}
        leader_names = member_names | {"apply"}
        return bool(
            len(back) == 1
            and len(nav) in (5, 6)
            and names in (member_names, leader_names)
            and sum(toggle.checked for toggle in nav) == 1
        )

    def guild_page_visible(self) -> bool:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild page snapshots are not coherent")
        return self._guild_page_visible_from_states(button_state, ui_state)

    def guild_report_count(self) -> int:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild report snapshots are not coherent")
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildEventReportUI(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildEventReportUI(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        counts = tuple(
            text.text
            for text in ui_state.texts
            if text.path.endswith("GuildEventReportUI(Clone)/frame/cnt")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if len(roots) != 1 or len(counts) != 1:
            raise SemanticGateClosed("guild report identity is absent or ambiguous")
        match = re.fullmatch(r"([0-9]+)/20", counts[0])
        if match is None:
            raise SemanticGateClosed("guild report count is malformed")
        return int(match.group(1))

    def _guild_nav_delegated_raycast_proven(
        self,
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        matches: Tuple[ToggleState, ...],
    ) -> bool:
        if not semantic_id.startswith("guild/nav/") or len(matches) != 1:
            return False
        if not self._guild_page_visible_from_states(button_state, ui_state):
            return False
        toggle = matches[0]
        if not (
            toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.interactable
            and toggle.raycast_top is None
            and toggle.point is not None
            and toggle.bounds is not None
            and toggle.bounds.contains(toggle.point)
        ):
            return False
        sprites = {
            "guild/nav/lobby": ("toggle_souye_sel", "toggle_souye_unsel"),
            "guild/nav/member": (
                "toggle_chengyuan_sel",
                "toggle_chengyuan_unsel",
            ),
            "guild/nav/logistics": ("toggle_office_sel", "toggle_office_unsel"),
            "guild/nav/technology": ("toggle_tech_sel", "toggle_tech_unsel"),
            "guild/nav/operations": ("toggle_battle_sel", "toggle_battle_unsel"),
        }
        expected = sprites[semantic_id][0 if toggle.checked else 1]
        images = tuple(
            image
            for image in ui_state.images
            if image.name == "Image"
            and image.path.startswith(toggle.path + "/")
            and image.sprite == expected
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
            and toggle.bounds.contains(
                Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                )
            )
        )
        return len(images) == 1

    @staticmethod
    def _guild_selected_toggle(
        ui_state: UiState,
        name: str,
    ) -> bool:
        matches = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.name == name
            and toggle.path.endswith(
                "blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/" + name
            )
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.checked
        )
        return len(matches) == 1

    def _guild_delegated_button_proven(
        self,
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        contracts = {
            "guild/lobby/report": ("main", "text_report2"),
            "guild/logistics/supply": ("office", "get_btn"),
            "guild/logistics/mission": ("office", "accept_btn"),
            "guild/operations/formation": ("battle", "BUTTEN_2"),
            "guild/operations/report": ("battle", "BUTTEN_"),
            "guild/operations/dispatch/open": ("battle", "4_1"),
        }
        contract = contracts.get(semantic_id)
        if contract is None:
            return False
        selected_name, sprite = contract
        if not (
            self._guild_page_visible_from_states(button_state, ui_state)
            and self._guild_selected_toggle(ui_state, selected_name)
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        return len(images) == 1

    @staticmethod
    def _guild_dispatch_detail_control_proven(
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        sprites = {
            "guild/dispatch-detail/close": "close",
            "guild/dispatch-detail/formation": "BUTTEN",
        }
        sprite = sprites.get(semantic_id)
        if sprite is None:
            return False
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildMissionInfoPage(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildMissionInfoPage(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if not (
            len(roots) == 1
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        return len(images) == 1

    @staticmethod
    def _guild_report_control_proven(
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        sprites = {
            "guild/report/close": "close",
            "guild/report/claim-all": "btn_di",
        }
        sprite = sprites.get(semantic_id)
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildEventReportUI(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildEventReportUI(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if sprite is None or not (
            len(roots) == 1
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        return len(images) == 1

    @staticmethod
    def _guild_formation_control_proven(
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        sprites = {
            "guild/formation/close": "close",
            "guild/formation/recommend": "btn_rec",
            "guild/formation/go": "btn",
        }
        sprite = sprites.get(semantic_id)
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildMissionFormationPage(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if sprite is None or not (
            len(roots) == 1
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        return len(images) == 1

    def guild_formation_state(self) -> GuildFormationState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild formation snapshots are not coherent")
        root = "GuildMissionFormationPage(Clone)/frame/"
        page_roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildMissionFormationPage(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)"
            )
        )
        if len(page_roots) != 1:
            raise SemanticGateClosed("guild formation page identity is absent")

        def numeric(suffix: str) -> int:
            values = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith(root + suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(values) != 1:
                raise SemanticGateClosed("guild formation value is ambiguous")
            numbers = re.findall(r"-?[0-9]+", values[0])
            if len(numbers) != 1:
                raise SemanticGateClosed("guild formation value is malformed")
            return int(numbers[0])

        empty = tuple(
            image
            for image in ui_state.images
            if re.search(r"/frame/single/[1-4]/Image$", image.path)
            and re.fullmatch(r"[1-4]_2", image.sprite)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        if len(empty) > 4:
            raise SemanticGateClosed("guild formation empty-slot count is invalid")
        return GuildFormationState(
            generation=max(button_state.generation, ui_state.generation),
            effect=numeric("bottom/effect/Text"),
            score_addition=numeric("bottom/score_addition/Text"),
            effect_addition=numeric("bottom/effect_addition/Text"),
            empty_slots=len(empty),
        )

    @staticmethod
    def _guild_parse_amount(value: str) -> int:
        normalized = re.sub(r"<[^>]+>", "", value).strip().upper()
        match = re.fullmatch(r"([0-9]+)(K)?", normalized)
        if match is None:
            raise SemanticGateClosed("guild amount is malformed")
        amount = int(match.group(1))
        return amount * 1000 if match.group(2) else amount

    def guild_logistics_state(self) -> GuildLogisticsState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild logistics snapshots are not coherent")
        if not (
            self._guild_page_visible_from_states(button_state, ui_state)
            and self._guild_selected_toggle(ui_state, "office")
        ):
            raise SemanticGateClosed("guild logistics page identity is absent")

        def one_text(suffix: str) -> str:
            matches = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("guild logistics text is absent or ambiguous")
            return matches[0]

        supply_match = re.fullmatch(
            r"([0-9]+)/([0-9]+)",
            one_text("TaskPanel/SupplyPanel/frame/open/Text"),
        )
        mission_value = re.sub(
            r"<[^>]+>",
            "",
            one_text("TaskPanel/open/top/progress"),
        )
        mission_match = re.fullmatch(r"([0-9]+)/([0-9]+)", mission_value)
        if supply_match is None or mission_match is None:
            raise SemanticGateClosed("guild logistics progress is malformed")
        remaining_text = one_text("TaskPanel/SubmitPanel/cnt/Text")
        remaining_numbers = re.findall(r"[0-9]+", remaining_text)
        if len(remaining_numbers) != 1:
            raise SemanticGateClosed("guild exchange remaining count is malformed")

        submits = sorted(
            (
                button
                for button in button_state.buttons
                if button.name == "submit"
                and "/TaskPanel/SubmitPanel/list/" in button.path
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.raycast_top is None
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            ),
            key=lambda button: button.bounds.left if button.bounds else -1,
        )
        if len(submits) != 3:
            raise SemanticGateClosed("guild exchange buttons are absent or ambiguous")
        items = []
        for index, submit in enumerate(submits):
            assert submit.bounds is not None
            center_x = (submit.bounds.left + submit.bounds.right) / 2.0
            icon_matches = tuple(
                image
                for image in ui_state.images
                if image.name == "icon"
                and image.path.endswith("/item/icon_bg/icon")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and abs(
                    (image.bounds.left + image.bounds.right) / 2.0 - center_x
                ) < 15.0
            )
            count_matches = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith("/item/Text")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and abs((text.bounds.left + text.bounds.right) / 2.0 - center_x) < 25.0
            )
            reward_matches = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith("/award/Text")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and abs((text.bounds.left + text.bounds.right) / 2.0 - center_x) < 45.0
            )
            if len(icon_matches) != 1 or len(count_matches) != 1 or len(reward_matches) != 1:
                raise SemanticGateClosed("guild exchange row identity is ambiguous")
            count = re.fullmatch(r"([^/]+)/([^/]+)", count_matches[0])
            if count is None or not reward_matches[0].isdigit():
                raise SemanticGateClosed("guild exchange row values are malformed")
            items.append(
                GuildExchangeItemState(
                    index=index,
                    icon_sprite=icon_matches[0].sprite,
                    owned=self._guild_parse_amount(count.group(1)),
                    required=self._guild_parse_amount(count.group(2)),
                    contribution=int(reward_matches[0]),
                    button=submit,
                )
            )
        supply_current, supply_total = map(int, supply_match.groups())
        mission_current, mission_total = map(int, mission_match.groups())
        supply = self._matches(button_state, "guild/logistics/supply")
        mission = self._matches(button_state, "guild/logistics/mission")
        finish_masks = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("TaskPanel/open/mask_all")
            and image.sprite == "finish_mask1"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        mission_finished = len(finish_masks) == 1
        return GuildLogisticsState(
            generation=max(button_state.generation, ui_state.generation),
            supply_remaining=supply_current,
            supply_total=supply_total,
            supply_claimable=bool(
                len(supply) == 1
                and self._guild_delegated_button_proven(
                    button_state, ui_state, "guild/logistics/supply", supply[0]
                )
            ),
            mission_current=mission_current,
            mission_total=mission_total,
            mission_claimable=bool(
                mission_current >= mission_total
                and not mission_finished
                and len(mission) == 1
                and self._guild_delegated_button_proven(
                    button_state, ui_state, "guild/logistics/mission", mission[0]
                )
            ),
            mission_finished=mission_finished,
            exchange_remaining=int(remaining_numbers[0]),
            exchange_items=tuple(items),
        )

    def guild_operations_state(self) -> GuildOperationsState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild operations snapshots are not coherent")
        if not (
            self._guild_page_visible_from_states(button_state, ui_state)
            and self._guild_selected_toggle(ui_state, "battle")
        ):
            raise SemanticGateClosed("guild operations page identity is absent")
        root = "GuildEventPage(Clone)/missionlist/path/"
        candidates = []
        for button in button_state.buttons:
            if root not in button.path or button.bounds is None:
                continue
            tips = tuple(
                image
                for image in ui_state.images
                if image.path == button.path + "/tip"
                and image.sprite == "exclamation_mark"
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
            )
            if len(tips) == 1:
                candidates.append(button)
            elif len(tips) > 1:
                raise SemanticGateClosed("guild active operation marker is ambiguous")
        if len(candidates) > 1:
            raise SemanticGateClosed("guild active operation node is ambiguous")
        boss = tuple(
            button
            for button in button_state.buttons
            if button.name in ("enter", "start")
            and "Guild" in button.path
            and button.bounds is not None
        )
        mode = "boss" if boss else ("active" if candidates else "inactive")
        reports = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("GuildEventPage(Clone)/report_btn/tip")
            and image.sprite in ("tip_1920", "tip")
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        active = candidates[0] if candidates else None
        return GuildOperationsState(
            generation=max(button_state.generation, ui_state.generation),
            mode=mode,
            active_node=active.name if active else None,
            active_node_path=active.path if active else None,
            report_available=len(reports) == 1,
        )

    def click_guild_exchange_item(
        self,
        index: int,
        expected_icon_sprite: str,
        expected_owned: int,
        expected_required: int,
    ) -> ActionReceipt:
        state = self.guild_logistics_state()
        if index not in range(len(state.exchange_items)):
            raise SemanticGateClosed("guild exchange index is invalid")
        item = state.exchange_items[index]
        if (
            state.exchange_remaining <= 0
            or item.icon_sprite != expected_icon_sprite
            or item.owned != expected_owned
            or item.required != expected_required
            or not item.enough
            or not item.button.interactable
        ):
            raise SemanticGateClosed("guild exchange item changed before input")
        target = item.button
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point) or not (
            0 <= point.x < self.fingerprint.width
            and 0 <= point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("guild exchange point is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before guild exchange input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="guild/logistics/exchange/{0}".format(index),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_guild_active_operation(self, expected_path: str) -> ActionReceipt:
        state = self.guild_operations_state()
        if state.mode != "active" or state.active_node_path != expected_path:
            raise SemanticGateClosed("guild active operation node changed")
        button_state = self.read_state()
        matches = tuple(
            button
            for button in button_state.buttons
            if button.path == expected_path
            and button.name == state.active_node
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("guild active operation node is not actionable")
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before guild operation input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="guild/operations/node/" + str(state.active_node),
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _guild_dispatch_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None or parts[1:] not in (("取消", "确定"), ("ȡ��", "ȷ��")):
            return False
        ui_state = self._stable_msgbox_ui_state(state)
        formation_roots = tuple(
            button
            for button in state.buttons
            if button.name == "GuildMissionFormationPage(Clone)"
            and button.path.endswith(
                "UICamera/Canvas/UIOrigin/GuildMissionFormationPage(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        button_sprites = {
            image.sprite
            for image in ui_state.images
            if image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_1(Clone)"
            )
            or image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_2(Clone)"
            )
        }
        content = parts[0]
        text_shape = bool(
            content
            and (
                ("派遣" in content and "无法" in content and "确定" in content)
                or ("��ǲ" in content and "�޷�" in content and "ȷ��" in content)
            )
        )
        return bool(
            len(formation_roots) == 1
            and text_shape
            and button_sprites == {"btn_big_blue", "btn_big_grey"}
        )

    def _guild_exchange_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None or parts[1:] != ("取消", "确定"):
            return False
        ui_state = self._stable_msgbox_ui_state(state)
        logistics_roots = tuple(
            button
            for button in state.buttons
            if "/TaskPanel(Adapt)/TaskPanel/SubmitPanel/" in button.path
            and button.name == "submit"
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        button_sprites = {
            image.sprite
            for image in ui_state.images
            if image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_1(Clone)"
            )
            or image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_2(Clone)"
            )
        }
        prompt = re.fullmatch(
            r"即将提交(.+?)([1-9][0-9]*)个\(目前拥有([1-9][0-9]*)个\)，"
            r"为大舰队提供后勤补给，是否确定？",
            parts[0],
        )
        return bool(
            len(logistics_roots) == 3
            and prompt is not None
            and int(prompt.group(3)) >= int(prompt.group(2))
            and button_sprites == {"btn_big_blue", "btn_big_grey"}
        )
