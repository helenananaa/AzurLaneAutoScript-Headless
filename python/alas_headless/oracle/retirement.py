"""Retirement for the typed ALAS boundary."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Dict, List, Optional, Tuple, Union
from .contracts import (
    ActionReceipt,
    ButtonState,
    OracleState,
    Point,
    RetirementEquipmentState,
    RetirementExecutionReceipt,
    RetirementNoCandidateReceipt,
    RetirementRewardState,
    RetirementSelectionState,
    RetirementSettingsState,
    TextState,
    UI_SCHEMA,
    UiState,
)
from .errors import ObserverTransportError, SemanticGateClosed, SemanticOracleError


def _selection_path(path: str) -> str:
    """Compare the same selection panel through its additive layout wrapper.

    Typed records and action receipts keep their actual, unmodified paths.
    """
    return path.replace('/blur_panel/select_panel_adapt/select_panel/',
                        '/blur_panel/select_panel/')


class RetirementOracle:
    """Retirement operations sharing the oracle frame and input boundary."""

    def _retirement_records(self) -> Tuple[OracleState, UiState]:
        """Read a coherent retirement slice while tolerating unrelated caps.

        The dock cards can exhaust the global Toggle/Image observer caps.  The
        retirement parsers therefore require every exact dialog record they use
        instead of pretending the unrelated dock-card tail is complete.
        """

        last_error: Optional[SemanticOracleError] = None
        for attempt in range(8):
            try:
                button_state = self.read_state()
                raw = self._request("GET /v1/ui\n")
                if self._foreground_component() != self.fingerprint.component:
                    raise SemanticGateClosed("game activity is not top-resumed")
                if not isinstance(raw, Mapping):
                    raise ObserverTransportError(
                        "UI observer response is not a mapping"
                    )
                self._validate_identity(raw, UI_SCHEMA)
                if raw.get("schema") != 1:
                    raise SemanticGateClosed("UI snapshot schema mismatch")
                if raw.get("text_truncated") is not False:
                    raise SemanticGateClosed("retirement text snapshot is truncated")
                if self._integer(raw.get("error_count"), "UI error_count") != 0:
                    raise SemanticGateClosed("UI snapshot contains extraction errors")
                raw_toggles = raw.get("toggles")
                raw_texts = raw.get("texts")
                raw_images = raw.get("images")
                if not all(
                    isinstance(value, (list, tuple))
                    for value in (raw_toggles, raw_texts, raw_images)
                ):
                    raise SemanticGateClosed("UI record lists are malformed")
                assert isinstance(raw_toggles, (list, tuple))
                assert isinstance(raw_texts, (list, tuple))
                assert isinstance(raw_images, (list, tuple))
                for field, records in (
                    ("toggle_count", raw_toggles),
                    ("text_count", raw_texts),
                    ("image_count", raw_images),
                ):
                    if self._integer(raw.get(field), field) != len(records):
                        raise SemanticGateClosed("UI record count is inconsistent")
                method_mask = self._integer(raw.get("method_mask"), "UI method_mask")
                if method_mask & 0x6 == 0:
                    raise SemanticGateClosed(
                        "typed Unity text accessors are unavailable"
                    )
                generation = self._integer(raw.get("generation"), "UI generation")
                if not (
                    button_state.generation <= generation <= button_state.generation + 2
                ):
                    raise SemanticGateClosed(
                        "retirement button and UI snapshots are not coherent"
                    )
                if (
                    self._last_generation is not None
                    and generation < self._last_generation
                ):
                    raise SemanticGateClosed("observer generation moved backwards")
                self._last_generation = generation
                skipped_count = self._integer(
                    raw.get("skipped_count"), "UI skipped_count"
                )
                if skipped_count < 0:
                    raise SemanticGateClosed("UI skipped_count is negative")
                return button_state, UiState(
                    generation=generation,
                    method_mask=method_mask,
                    skipped_count=skipped_count,
                    image_truncated=bool(raw.get("image_truncated")),
                    snapshot=raw,
                    toggles=tuple(self._parse_toggle(item) for item in raw_toggles),
                    texts=tuple(self._parse_text(item) for item in raw_texts),
                    images=tuple(self._parse_image(item) for item in raw_images),
                )
            except SemanticOracleError as exc:
                last_error = exc
                if attempt < 7:
                    self._sleep(0.05)
        raise SemanticGateClosed(
            "retirement snapshots did not stabilize"
        ) from last_error

    @staticmethod
    def _active_retirement_texts(
        ui_state: UiState,
        path_suffix: str,
        expected: Optional[str] = None,
    ) -> Tuple[TextState, ...]:
        return tuple(
            item
            for item in ui_state.texts
            if _selection_path(item.path).endswith(path_suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and (expected is None or item.text == expected)
        )

    @staticmethod
    def _active_retirement_buttons(
        state: OracleState,
        path_suffix: str,
    ) -> Tuple[ButtonState, ...]:
        return tuple(
            item
            for item in state.buttons
            if _selection_path(item.path).endswith(path_suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
        )

    def _click_retirement_button(
        self,
        semantic_id: str,
        path_suffix: str,
        *,
        identity_text_suffix: str,
        identity_text: str,
        validate_records=None,
    ) -> ActionReceipt:
        state, ui_state = self._retirement_records()
        if validate_records is not None:
            validate_records(state, ui_state)
        buttons = self._active_retirement_buttons(state, path_suffix)
        identity = self._active_retirement_texts(
            ui_state, identity_text_suffix, identity_text
        )
        if len(buttons) != 1 or len(identity) != 1:
            raise SemanticGateClosed("retirement control identity is ambiguous")
        button = buttons[0]
        if (
            button.raycast_top is not True
            or button.point is None
            or button.bounds is None
            or not button.bounds.contains(button.point)
            or not (
                0 <= button.point.x < self.fingerprint.width
                and 0 <= button.point.y < self.fingerprint.height
            )
        ):
            raise SemanticGateClosed("retirement control is not actionable")
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("retirement control is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately after input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=ui_state.generation,
            point=button.point,
            bounds=button.bounds,
            path=button.path,
        )

    def retirement_selection_state(self) -> RetirementSelectionState:
        state, ui_state = self._retirement_records()
        tip_suffix = "/blur_panel/select_panel/tip"
        tip = self._active_retirement_texts(
            ui_state,
            tip_suffix,
            "请选择用于<color=#92fc63>退役</color>的角色：",
        )
        capacity = self._active_retirement_texts(
            ui_state, "/blur_panel/adapt/top/capacity/Text"
        )
        count = self._active_retirement_texts(
            ui_state, "/blur_panel/select_panel/bottom_info/bg_input/count"
        )
        controls = (
            "/blur_panel/adapt/left_length/frame/setting",
            "/blur_panel/select_panel/quick_select",
            "/blur_panel/select_panel/confirm_button",
            "/blur_panel/select_panel/cancel_button",
        )
        if (
            len(tip) != 1
            or len(capacity) != 1
            or len(count) != 1
            or any(
                len(self._active_retirement_buttons(state, path)) != 1
                for path in controls
            )
        ):
            raise SemanticGateClosed("retirement selection page is incomplete")
        capacity_match = re.fullmatch(
            r"([0-9]+)/([1-9][0-9]*)", capacity[0].text.strip()
        )
        count_match = re.fullmatch(r"[0-9]+", count[0].text.strip())
        if capacity_match is None or count_match is None:
            raise SemanticGateClosed("retirement counters are malformed")
        used, total = (int(value) for value in capacity_match.groups())
        selected = int(count_match.group(0))
        # A reward can overflow the dock before the game raises its full
        # dialog (observed 931/930). That is precisely a recovery entry, not
        # malformed data. Selection and the eventual count delta stay exact.
        if selected > used:
            raise SemanticGateClosed("retirement counters are inconsistent")
        return RetirementSelectionState(
            generation=ui_state.generation,
            capacity_used=used,
            capacity_total=total,
            selected_count=selected,
        )

    def click_dock_page_back(self) -> ActionReceipt:
        """Leave the ordinary dock, never an active selection dialog."""
        state, ui = self._retirement_records()
        if any("/blur_panel/select_panel/" in _selection_path(item.path)
               and item.active_in_hierarchy and item.active_and_enabled
               for item in state.buttons):
            raise SemanticGateClosed("dock has an active selection page")
        return self._click_retirement_button(
            "dock/page/back", "/Overlay/UIMain/blur_panel/adapt/top/back",
            identity_text_suffix="/blur_panel/adapt/top/capacity/label",
            identity_text="船坞容量:",
        )

    def retirement_selection_visible(self) -> bool:
        state = self.read_state()
        if not any(_selection_path(b.path).endswith('/blur_panel/select_panel/quick_select')
                   and b.active_in_hierarchy for b in state.buttons):
            return False
        _, ui = self._retirement_records()
        if not self._active_retirement_texts(ui, '/blur_panel/select_panel/tip',
                '请选择用于<color=#92fc63>退役</color>的角色：'):
            return False
        # Presence must survive controls mounting/unmounting. Input and the
        # retirement transaction independently require the complete selection.
        return True

    def _retirement_page_back_target(self):
        selection = self.retirement_selection_state()
        if selection.selected_count != 0:
            raise SemanticGateClosed("retirement page has a live selection")
        state, _ui_state = self._retirement_records()
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "back"
            and button.path
            in ("OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back",
                "UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back")
            and button.actionable
        )
        if len(matches) != 1:
            raise SemanticGateClosed("retirement page back control is ambiguous")
        target = matches[0]
        if self._blocking_rules(state, "retirement/page/back"):
            raise SemanticGateClosed("retirement page back is blocked")
        return selection, target

    def retirement_page_back_available(self) -> bool:
        self._retirement_page_back_target()
        return True

    def click_retirement_page_back(self) -> ActionReceipt:
        """Exit only an idle, unselected retirement page."""
        selection, target = self._retirement_page_back_target()
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately after input")
        return ActionReceipt(
            semantic_id="retirement/page/back",
            generation=selection.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def open_retirement_settings(self) -> ActionReceipt:
        page = self.retirement_selection_state()
        if page.selected_count:
            raise SemanticGateClosed("retirement settings require an empty selection")
        return self._click_retirement_button(
            "retirement/settings/open",
            "/blur_panel/adapt/left_length/frame/setting",
            identity_text_suffix="/blur_panel/select_panel/tip",
            identity_text="请选择用于<color=#92fc63>退役</color>的角色：",
        )

    def retirement_settings_state(self) -> RetirementSettingsState:
        _, ui_state = self._retirement_records()
        if ui_state.method_mask & 0x1 == 0:
            raise SemanticGateClosed("typed retirement Toggle access is unavailable")
        root = "DockyardQuickSelectSettingUI(Clone)/window/notifications/options/"
        expected_options = {
            0: ("on", "off"),
            1: ("sr", "r", "n", "empty"),
            2: ("sr", "r", "n", "empty"),
            3: ("sr", "r", "n", "empty"),
            4: ("keep_all", "keep_one", "keep_none"),
            5: ("keep_all", "keep_needed", "keep_none"),
        }
        selected: Dict[int, str] = {}
        for group, options in expected_options.items():
            records = {}
            for option in options:
                suffix = root + "notify_tpl_{0}/{1}".format(group, option)
                matches = tuple(
                    item
                    for item in ui_state.toggles
                    if item.path.endswith(suffix)
                    and item.name == option
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and item.interactable
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "retirement setting option is absent or ambiguous"
                    )
                records[option] = matches[0]
            checked = tuple(option for option, item in records.items() if item.checked)
            if len(checked) != 1:
                raise SemanticGateClosed("retirement setting group is not exclusive")
            selected[group] = checked[0]

        expected_labels = {
            0: "唯一舰船退役保护",
            1: "选择优先级1",
            2: "选择优先级2",
            3: "选择优先级3",
            4: (
                "<color=#92fc63>「拥有」</color>满星的同名舰船时，"
                "保留几艘<color=#92fc63>符合退役条件</color>的同名舰船"
            ),
            5: (
                "<color=#ff5c5c>「没有」</color>满星的同名舰船时，"
                "保留几艘<color=#92fc63>符合退役条件</color>的同名舰船"
            ),
        }
        for group, text in expected_labels.items():
            if (
                len(
                    self._active_retirement_texts(
                        ui_state,
                        root + "notify_tpl_{0}/Text".format(group),
                        text,
                    )
                )
                != 1
            ):
                raise SemanticGateClosed("retirement setting label changed")
        title = self._active_retirement_texts(
            ui_state,
            "DockyardQuickSelectSettingUI(Clone)/window/top/bg/obtain/title",
            "退役设置",
        )
        if len(title) != 1:
            raise SemanticGateClosed("retirement setting page title changed")
        return RetirementSettingsState(
            generation=ui_state.generation,
            unique_ship_protection=selected[0] == "on",
            priority=tuple(selected[index].upper() for index in (1, 2, 3)),
            full_star_policy=selected[4],
            no_full_star_policy=selected[5],
        )

    def _click_retirement_setting_option(
        self, group: int, option: str
    ) -> ActionReceipt:
        state, ui_state = self._retirement_records()
        root = (
            "DockyardQuickSelectSettingUI(Clone)/window/notifications/options/"
            "notify_tpl_{0}/{1}".format(group, option)
        )
        toggles = tuple(
            item
            for item in ui_state.toggles
            if item.path.endswith(root)
            and item.name == option
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
        )
        if len(toggles) != 1 or toggles[0].checked:
            raise SemanticGateClosed("retirement setting target is not selectable")
        toggle = toggles[0]
        point = toggle.point
        bounds = toggle.bounds
        if group == 0:
            image_suffix = root + "/Image2"
            images = tuple(
                item
                for item in ui_state.images
                if item.path.endswith(image_suffix)
                and item.sprite == "toggle_on"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.raycast_target
                and item.raycast_top is True
                and item.bounds is not None
            )
            if len(images) != 1:
                raise SemanticGateClosed("unique-protection input surface changed")
            bounds = images[0].bounds
            assert bounds is not None
            point = Point(
                (bounds.left + bounds.right) / 2.0,
                (bounds.top + bounds.bottom) / 2.0,
            )
        if (
            point is None
            or bounds is None
            or not bounds.contains(point)
            or not (
                0 <= point.x < self.fingerprint.width
                and 0 <= point.y < self.fingerprint.height
            )
        ):
            raise SemanticGateClosed("retirement setting input point is invalid")
        if group != 0 and toggle.raycast_top is not True:
            raise SemanticGateClosed("retirement setting has no positive hit proof")
        if self._blocking_rules(state, "retirement/settings/{0}/{1}".format(group, option)):
            raise SemanticGateClosed("retirement setting is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="retirement/settings/{0}/{1}".format(group, option),
            generation=ui_state.generation,
            point=point,
            bounds=bounds,
            path=toggle.path,
        )

    def configure_retirement_settings(
        self, keep_limit_break: bool
    ) -> Tuple[RetirementSettingsState, Tuple[ActionReceipt, ...]]:
        if not isinstance(keep_limit_break, bool):
            raise TypeError("retirement limit-break policy must be boolean")
        desired = {
            0: "on",
            1: "r",
            2: "sr",
            3: "n",
            4: "keep_none",
            5: "keep_needed" if keep_limit_break else "keep_none",
        }
        receipts: List[ActionReceipt] = []
        for group, option in desired.items():
            current = self.retirement_settings_state()
            actual = {
                0: "on" if current.unique_ship_protection else "off",
                1: current.priority[0].lower(),
                2: current.priority[1].lower(),
                3: current.priority[2].lower(),
                4: current.full_star_policy,
                5: current.no_full_star_policy,
            }[group]
            if actual == option:
                continue
            receipts.append(self._click_retirement_setting_option(group, option))
            self._sleep(0.2)
            updated = self.retirement_settings_state()
            updated_actual = {
                0: "on" if updated.unique_ship_protection else "off",
                1: updated.priority[0].lower(),
                2: updated.priority[1].lower(),
                3: updated.priority[2].lower(),
                4: updated.full_star_policy,
                5: updated.no_full_star_policy,
            }[group]
            if updated_actual != option:
                raise SemanticGateClosed("retirement setting did not settle")
        final = self.retirement_settings_state()
        expected_state = RetirementSettingsState(
            generation=final.generation,
            unique_ship_protection=True,
            priority=("R", "SR", "N"),
            full_star_policy="keep_none",
            no_full_star_policy=("keep_needed" if keep_limit_break else "keep_none"),
        )
        if final != expected_state:
            raise SemanticGateClosed("official retirement settings are not exact")
        return final, tuple(receipts)

    def close_retirement_settings(self) -> ActionReceipt:
        self.retirement_settings_state()
        return self._click_retirement_button(
            "retirement/settings/close",
            "DockyardQuickSelectSettingUI(Clone)/window/top/btnBack",
            identity_text_suffix=(
                "DockyardQuickSelectSettingUI(Clone)/window/top/bg/obtain/title"
            ),
            identity_text="退役设置",
        )

    def _retirement_preconfirm(self) -> Optional[Tuple[int, int]]:
        state, ui_state = self._retirement_records()
        confirm = self._active_retirement_buttons(
            state, "DestoryInfoUI(Clone)/frame/confirm_button"
        )
        if not confirm:
            return None
        count = self._active_retirement_texts(
            ui_state, "/blur_panel/select_panel/bottom_info/bg_input/count"
        )
        title = self._active_retirement_texts(
            ui_state,
            "DestoryInfoUI(Clone)/frame/top/title_list/infomation/title",
            "信息",
        )
        if len(confirm) != 1 or len(count) != 1 or len(title) != 1:
            raise SemanticGateClosed("retirement confirmation is incomplete")
        if re.fullmatch(r"[1-9][0-9]*", count[0].text.strip()) is None:
            raise SemanticGateClosed("retirement selected count is malformed")
        return int(count[0].text.strip()), ui_state.generation

    def _retirement_screen_kind(self) -> str:
        state, ui_state = self._retirement_records()
        paths = tuple(
            item.path
            for item in state.buttons
            if item.active_in_hierarchy and item.active_and_enabled
        )
        if any(
            path.endswith("DestoryConfirmWindow(Clone)/window/confirm_btn")
            for path in paths
        ):
            return "rarity-warning"
        if any(path.endswith("AwardInfoUI(Clone)/items/close") for path in paths):
            return "award"
        preserve_message = self._active_retirement_texts(
            ui_state,
            "Msgbox(Clone)/window/msg_panel/content",
            "不进行任何操作，所有装备会放入<color=#5f984d>仓库</color>\n是否退出？",
        )
        if preserve_message:
            return "equipment-preserve-confirm"
        if any(
            path.endswith("ResolveEquipmentUI(Clone)/main/cancel_btn") for path in paths
        ):
            return "equipment"
        if any(
            path.endswith("DestoryInfoUI(Clone)/frame/confirm_button") for path in paths
        ):
            return "preconfirm"
        if self._active_retirement_texts(
            ui_state,
            "/blur_panel/select_panel/tip",
            "请选择用于<color=#92fc63>退役</color>的角色：",
        ):
            return "selection"
        return "transition"

    def _retirement_no_candidate_message(self) -> Optional[str]:
        _, ui_state = self._retirement_records()
        messages = self._active_retirement_texts(
            ui_state,
            "TipPanel(Clone)/Grid/toolTip(Clone)/Text",
        )
        if not messages:
            return None
        if (
            len(messages) != 1
            or messages[0].text != "<color=white>没找到符合条件的舰船</color>"
        ):
            raise SemanticGateClosed("official retirement no-candidate tip changed")
        return messages[0].text

    def _recover_retirement_network_reconnect(self) -> Optional[ActionReceipt]:
        """Resume only the independently reviewed exact reconnect prompt."""

        state, ui_state = self._retirement_records()
        confirm = self._matches(state, "overlay/network-reconnect/confirm")
        cancel = self._matches(state, "overlay/network-reconnect/cancel")
        if not confirm and not cancel:
            return None
        # Other reviewed retirement dialogs can reuse one of the generic
        # Msgbox button paths.  A reconnect prompt always owns the exact pair.
        if not confirm or not cancel:
            return None
        if len(confirm) != 1 or len(cancel) != 1:
            raise SemanticGateClosed("retirement reconnect prompt is ambiguous")
        content = self._active_retirement_texts(
            ui_state, "Msgbox(Clone)/window/msg_panel/content"
        )
        confirm_text = self._active_retirement_texts(
            ui_state,
            "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic",
        )
        cancel_text = self._active_retirement_texts(
            ui_state,
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic",
        )
        if len(content) != 1 or len(confirm_text) != 1 or len(cancel_text) != 1:
            return None
        plain = re.sub(r"<[^>]*>", "", content[0].text).strip()
        if not (
            re.fullmatch(
                r"服务器连接失败，是否重新连接？\s*"
                r"\[(?:NetworkDown|HostNotFound|ConnectionReset)\]",
                plain,
            )
            and "".join(confirm_text[0].text.split()) == "确定"
            and "".join(cancel_text[0].text.split()) == "取消"
        ):
            # Rarity/equipment dialogs own their own exact branches below.
            return None
        return self._click_retirement_button(
            "overlay/network-reconnect/confirm",
            "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
            identity_text_suffix="Msgbox(Clone)/window/msg_panel/content",
            identity_text=content[0].text,
        )

    def _retirement_reward_state(self) -> RetirementRewardState:
        state, ui_state = self._retirement_records()
        close = self._active_retirement_buttons(state, "AwardInfoUI(Clone)/items/close")
        prefix = "AwardInfoUI(Clone)/items/items_scroll/content/item_tpl(Clone)/bg/"
        names = tuple(
            item.text.strip()
            for item in ui_state.texts
            if item.path.endswith(prefix + "name_mask/name")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        counts = tuple(
            item.text.strip()
            for item in ui_state.texts
            if item.path.endswith(prefix + "icon_bg/count")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if (
            len(close) != 1
            or len(names) != len(counts)
            or not names
            or len(set(names)) != len(names)
            or any(re.fullmatch(r"[1-9][0-9]*", value) is None for value in counts)
        ):
            raise SemanticGateClosed("retirement reward dialog is incomplete")
        return RetirementRewardState(
            generation=ui_state.generation,
            rewards=tuple(sorted(zip(names, (int(value) for value in counts)))),
        )

    def _retirement_equipment_state(self, records=None) -> RetirementEquipmentState:
        state, ui_state = records if records is not None else self._retirement_records()
        cancel = self._active_retirement_buttons(
            state, "ResolveEquipmentUI(Clone)/main/cancel_btn"
        )
        title = self._active_retirement_texts(
            ui_state,
            "ResolveEquipmentUI(Clone)/main/title/Text",
            "请选择需要拆解的装备，未选的装备将放入仓库",
        )
        if len(cancel) != 1 or len(title) != 1:
            raise SemanticGateClosed("retirement equipment dialog is incomplete")
        quantity_pattern = re.compile(
            r"ResolveEquipmentUI\(Clone\)/main/frame/view/content/"
            r"([0-9]+)/frame/bg/icon_bg/count$"
        )
        selected_pattern = re.compile(
            r"ResolveEquipmentUI\(Clone\)/main/frame/view/content/"
            r"([0-9]+)/frame/bg/selected/reduce$"
        )
        quantities = []
        for item in ui_state.texts:
            match = quantity_pattern.search(item.path)
            if (
                match is not None
                and item.active_in_hierarchy
                and item.active_and_enabled
            ):
                if item.truncated or re.fullmatch(r"[1-9][0-9]*", item.text.strip()) is None:
                    raise SemanticGateClosed("equipment quantity is malformed")
                quantities.append((int(match.group(1)), int(item.text.strip())))
        selected = sorted(
            {
                int(match.group(1))
                for item in state.buttons
                if (match := selected_pattern.search(item.path)) is not None
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
            }
        )
        if not quantities or len(dict(quantities)) != len(quantities):
            raise SemanticGateClosed("equipment item list is ambiguous")
        slots = {slot for slot, _ in quantities}
        if not set(selected).issubset(slots):
            raise SemanticGateClosed("equipment selection is inconsistent")
        all_checked = (
            len(
                tuple(
                    item
                    for item in ui_state.images
                    if item.path.endswith(
                        "ResolveEquipmentUI(Clone)/main/options/ALL/Background/Checkmark"
                    )
                    and item.sprite == "toggle_on"
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                )
            )
            == 1
        )
        return RetirementEquipmentState(
            generation=ui_state.generation,
            item_quantities=tuple(sorted(quantities)),
            selected_slots=tuple(selected),
            all_checked=all_checked,
        )

    def _wait_retirement_equipment_clear(self, equipment, generation, deadline):
        """Observe delayed deselection without issuing a second toggle input."""
        while self._monotonic() < deadline:
            cleared = self._retirement_equipment_state()
            if cleared.item_quantities != equipment.item_quantities:
                raise SemanticGateClosed('equipment inventory changed during deselection')
            if (cleared.generation > generation and not cleared.selected_slots
                    and not cleared.all_checked):
                return
            self._sleep(0.2)
        raise SemanticGateClosed('equipment selection did not clear')

    def _finish_dock_equipment_disassembly(self, *, owner, timeout_seconds):
        """Adapt ALAS' two equipment confirmations, then prove their reward/return.

        This only handles equipment attached to the current ship transaction;
        it never opens the equipment depot or repeats an unresolved confirmation.
        """
        if owner not in ('enhancement', 'retirement'):
            raise ValueError('unknown equipment transaction owner')
        deadline = self._monotonic() + timeout_seconds
        actions, rewards = [], []
        quantities = None
        selection = destruction = None
        toggle = None
        clean_samples = 0
        prefix = owner + '/equipment/'
        panel = 'ResolveEquipmentUI(Clone)/'

        def validate_selected(state, ui):
            current = self._retirement_equipment_state((state, ui))
            if (current.item_quantities != quantities or not current.all_checked
                    or set(current.selected_slots) != {slot for slot, _ in quantities}):
                raise SemanticGateClosed('equipment disassembly selection changed before input')

        def validate_confirmation(state, ui):
            if selection is None or state.generation <= selection.generation:
                raise SemanticGateClosed('equipment disassembly has no fresh owned selection')
            for suffix, label in (('got/title', '将获得以下材料:'),
                                  ('actions/destroy_button/Image', '确 定'),
                                  ('actions/cancel_button/Image', '取 消')):
                values = self._active_retirement_texts(ui, panel + 'destroy_confirm/' + suffix)
                if len(values) != 1 or values[0].text.replace(' ', '') != label.replace(' ', ''):
                    raise SemanticGateClosed('equipment disassembly confirmation is not reviewed')

        while self._monotonic() < deadline:
            state, ui = self._retirement_records()
            paths = [b.path for b in state.buttons if b.active_in_hierarchy and b.active_and_enabled]
            if any('Msgbox(Clone)' in path for path in paths):
                raise SemanticGateClosed('unexpected dialog in equipment disassembly')
            if any(path.endswith(panel + 'destroy_confirm/actions/destroy_button') for path in paths):
                if destruction is None:
                    destruction = self._click_retirement_button(
                        prefix + 'disassemble/confirm', panel + 'destroy_confirm/actions/destroy_button',
                        identity_text_suffix=panel + 'destroy_confirm/got/title',
                        identity_text='将获得以下材料:', validate_records=validate_confirmation)
                    actions.append(destruction)
                self._sleep(.2)
                continue
            if any(path.endswith('AwardInfoUI(Clone)/items/close') for path in paths):
                if destruction is None or state.generation <= destruction.generation:
                    raise SemanticGateClosed('equipment reward has no owned disassembly')
                reward = self._retirement_reward_state()
                rewards.extend(reward.rewards)
                actions.append(self._click_retirement_button(
                    prefix + 'reward/close', 'AwardInfoUI(Clone)/items/close',
                    identity_text_suffix='AwardInfoUI(Clone)/items/items_scroll/content/item_tpl(Clone)/bg/name_mask/name',
                    identity_text=reward.rewards[0][0]))
                self._sleep(.2)
                continue
            if any(path.endswith(panel + 'main/cancel_btn') for path in paths):
                if selection is not None:
                    self._sleep(.2)
                    continue
                equipment = self._retirement_equipment_state((state, ui))
                if quantities is None:
                    quantities = equipment.item_quantities
                elif equipment.item_quantities != quantities:
                    raise SemanticGateClosed('equipment inventory changed before disassembly')
                selected_all = equipment.all_checked and set(equipment.selected_slots) == {slot for slot, _ in quantities}
                if not selected_all:
                    if toggle is None:
                        if equipment.all_checked:
                            raise SemanticGateClosed('equipment all-selection is inconsistent')
                        toggle = self._click_retirement_button(
                            prefix + 'select-all', panel + 'main/options/ALL',
                            identity_text_suffix=panel + 'main/options/ALL/Label', identity_text='全部')
                        actions.append(toggle)
                    self._sleep(.2)
                    continue
                if toggle is not None and equipment.generation <= toggle.generation:
                    self._sleep(.2)
                    continue
                selection = self._click_retirement_button(
                    prefix + 'confirm-selection', panel + 'main/ok_btn',
                    identity_text_suffix=panel + 'main/ok_btn/Image', identity_text='确 定',
                    validate_records=validate_selected)
                actions.append(selection)
                self._sleep(.2)
                continue
            settled = False
            try:
                if owner == 'enhancement':
                    returned = self.enhancement_preview()
                    settled = not returned.materials
                else:
                    returned = self.retirement_selection_state()
                    settled = returned.selected_count == 0
                if destruction is not None:
                    settled = settled and returned.generation > destruction.generation and bool(rewards)
                elif quantities is not None:
                    settled = False
            except SemanticOracleError:
                pass
            clean_samples = clean_samples + 1 if settled else 0
            if clean_samples >= 3:
                return quantities or (), tuple(actions), tuple(rewards)
            self._sleep(.2)
        raise SemanticGateClosed('equipment disassembly did not settle; do not retry')

    def retire_ships_one_click(
        self,
        keep_limit_break: bool,
        timeout_seconds: float = 60.0,
        *, preserve_equipment: bool = True,
    ) -> Union[RetirementExecutionReceipt, RetirementNoCandidateReceipt]:
        """Execute one official one-click retirement transaction fail closed."""

        if type(preserve_equipment) is not bool:
            raise TypeError('retirement equipment policy must be boolean')
        if not isinstance(keep_limit_break, bool):
            raise TypeError("retirement limit-break policy must be boolean")
        if timeout_seconds <= 0:
            raise ValueError("retirement timeout must be positive")
        before = self.retirement_selection_state()
        if before.selected_count:
            raise SemanticGateClosed("retirement transaction requires empty selection")
        actions: List[ActionReceipt] = [self.open_retirement_settings()]
        settings_deadline = self._monotonic() + min(timeout_seconds, 10.0)
        while True:
            reconnect = self._recover_retirement_network_reconnect()
            if reconnect is not None:
                actions.append(reconnect)
                self._sleep(0.2)
                continue
            try:
                self.retirement_settings_state()
                break
            except SemanticOracleError:
                if self._monotonic() >= settings_deadline:
                    raise SemanticGateClosed("retirement settings did not open")
                self._sleep(0.2)
        settings, setting_actions = self.configure_retirement_settings(keep_limit_break)
        actions.extend(setting_actions)
        actions.append(self.close_retirement_settings())
        selection_deadline = self._monotonic() + min(timeout_seconds, 10.0)
        while True:
            reconnect = self._recover_retirement_network_reconnect()
            if reconnect is not None:
                actions.append(reconnect)
                self._sleep(0.2)
                continue
            try:
                returned = self.retirement_selection_state()
                if (
                    returned.capacity_used != before.capacity_used
                    or returned.capacity_total != before.capacity_total
                    or returned.selected_count != 0
                ):
                    raise SemanticGateClosed(
                        "retirement selection changed while configuring settings"
                    )
                break
            except SemanticOracleError:
                pass
            if self._monotonic() >= selection_deadline:
                raise SemanticGateClosed("retirement settings did not close")
            self._sleep(0.2)

        actions.append(
            self._click_retirement_button(
                "retirement/one-click",
                "/blur_panel/select_panel/quick_select",
                identity_text_suffix="/blur_panel/select_panel/quick_select/confirm",
                identity_text="一键退役",
            )
        )
        confirmation_deadline = self._monotonic() + timeout_seconds
        selected_count: Optional[int] = None
        while self._monotonic() < confirmation_deadline:
            reconnect = self._recover_retirement_network_reconnect()
            if reconnect is not None:
                actions.append(reconnect)
                self._sleep(0.2)
                continue
            preconfirm = self._retirement_preconfirm()
            if preconfirm is not None:
                selected_count = preconfirm[0]
                break
            message = self._retirement_no_candidate_message()
            if message is not None:
                idle = self.retirement_selection_state()
                if (
                    idle.capacity_used != before.capacity_used
                    or idle.capacity_total != before.capacity_total
                    or idle.selected_count != 0
                ):
                    raise SemanticGateClosed(
                        "no-candidate retirement changed dock selection"
                    )
                return RetirementNoCandidateReceipt(
                    capacity_used=idle.capacity_used,
                    capacity_total=idle.capacity_total,
                    settings=settings,
                    official_message=message,
                    actions=tuple(actions),
                )
            self._sleep(0.25)
        if selected_count is None:
            raise SemanticGateClosed("official one-click selection did not settle")
        if selected_count > before.capacity_used:
            raise SemanticGateClosed("official retirement count exceeds dock usage")
        actions.append(
            self._click_retirement_button(
                "retirement/ships/confirm",
                "DestoryInfoUI(Clone)/frame/confirm_button",
                identity_text_suffix=("DestoryInfoUI(Clone)/frame/confirm_button/pic"),
                identity_text="确 定",
            )
        )

        return self._finish_retirement_transaction(before, selected_count, settings, actions, timeout_seconds,
                                                   preserve_equipment=preserve_equipment)

    def _finish_retirement_transaction(self, before, selected_count, settings, actions, timeout_seconds,
                                       *, preserve_equipment=True):
        """Finish reward/equipment dialogs; never select or submit ships."""
        rewards: Tuple[Tuple[str, int], ...] = ()
        warning_confirmed = False
        equipment_preserved = False
        equipment_disassembled = False
        equipment_quantities = ()
        equipment_rewards = ()
        equipment_seen = False
        idle_since = None
        completion_deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < completion_deadline:
            reconnect = self._recover_retirement_network_reconnect()
            if reconnect is not None:
                actions.append(reconnect)
                self._sleep(0.2)
                continue
            kind = self._retirement_screen_kind()
            if kind != 'selection':
                idle_since = None
            if kind in ("transition", "preconfirm"):
                self._sleep(0.2)
                continue
            if kind == "rarity-warning":
                state, ui_state = self._retirement_records()
                warning = self._active_retirement_texts(
                    ui_state,
                    "DestoryConfirmWindow(Clone)/window/content/Text",
                    "选择角色中有<color=#92fc63>精锐以上</color>的角色：",
                )
                if len(warning) != 1:
                    raise SemanticGateClosed("retirement rarity warning changed")
                actions.append(
                    self._click_retirement_button(
                        "retirement/rarity-warning/confirm",
                        "DestoryConfirmWindow(Clone)/window/confirm_btn",
                        identity_text_suffix=(
                            "DestoryConfirmWindow(Clone)/window/content/desc/label"
                        ),
                        identity_text="是否确认",
                    )
                )
                warning_confirmed = True
                self._sleep(0.2)
                continue
            if kind == "award":
                reward_state = self._retirement_reward_state()
                rewards = reward_state.rewards
                actions.append(
                    self._click_retirement_button(
                        "retirement/reward/close",
                        "AwardInfoUI(Clone)/items/close",
                        identity_text_suffix=(
                            "AwardInfoUI(Clone)/items/items_scroll/content/"
                            "item_tpl(Clone)/bg/name_mask/name"
                        ),
                        identity_text=rewards[0][0],
                    )
                )
                self._sleep(0.2)
                continue
            if kind == "equipment":
                equipment_seen = True
                if not preserve_equipment:
                    equipment_quantities, equipment_actions, equipment_rewards = self._finish_dock_equipment_disassembly(
                        owner='retirement', timeout_seconds=max(1.0, completion_deadline - self._monotonic()))
                    actions.extend(equipment_actions)
                    equipment_disassembled = bool(equipment_quantities)
                    continue
                equipment = self._retirement_equipment_state()
                if equipment.selected_slots:
                    if not equipment.all_checked or set(equipment.selected_slots) != {
                        slot for slot, _ in equipment.item_quantities
                    }:
                        raise SemanticGateClosed(
                            "equipment preservation requires exact all-selection"
                        )
                    actions.append(
                        self._click_retirement_button(
                            "retirement/equipment/deselect-all",
                            "ResolveEquipmentUI(Clone)/main/options/ALL",
                            identity_text_suffix=(
                                "ResolveEquipmentUI(Clone)/main/options/ALL/Label"
                            ),
                            identity_text="全部",
                        )
                    )
                    self._wait_retirement_equipment_clear(
                        equipment, actions[-1].generation, completion_deadline)
                    continue
                actions.append(
                    self._click_retirement_button(
                        "retirement/equipment/cancel-disassembly",
                        "ResolveEquipmentUI(Clone)/main/cancel_btn",
                        identity_text_suffix=(
                            "ResolveEquipmentUI(Clone)/main/cancel_btn/Image"
                        ),
                        identity_text="取 消",
                    )
                )
                self._sleep(0.2)
                continue
            if kind == "equipment-preserve-confirm":
                if not preserve_equipment:
                    raise SemanticGateClosed('preservation dialog conflicts with disassembly policy')
                actions.append(
                    self._click_retirement_button(
                        "retirement/equipment/preserve/confirm",
                        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
                        identity_text_suffix=("Msgbox(Clone)/window/msg_panel/content"),
                        identity_text=(
                            "不进行任何操作，所有装备会放入"
                            "<color=#5f984d>仓库</color>\n是否退出？"
                        ),
                    )
                )
                equipment_preserved = True
                self._sleep(0.2)
                continue
            if kind == "selection":
                # Unity briefly exposes the dock after the server removes
                # ships but before mounting awards. That is not completion.
                if not rewards or (equipment_seen and not (equipment_preserved or equipment_disassembled)):
                    self._sleep(0.2)
                    continue
                state, _ = self._retirement_records()
                if self._blocking_rules(state, 'retirement/page/back'):
                    idle_since = None
                    self._sleep(0.2)
                    continue
                if idle_since is None:
                    idle_since = self._monotonic()
                if self._monotonic() - idle_since < 1.0:
                    self._sleep(0.2)
                    continue
                after = self.retirement_selection_state()
                if after.selected_count != 0:
                    raise SemanticGateClosed("retirement selection did not clear")
                if after.capacity_total != before.capacity_total:
                    raise SemanticGateClosed(
                        "dock capacity limit changed during retirement"
                    )
                if before.capacity_used - after.capacity_used != selected_count:
                    raise SemanticGateClosed(
                        "retirement count and capacity delta disagree"
                    )
                return RetirementExecutionReceipt(
                    retired_count=selected_count,
                    capacity_before=before.capacity_used,
                    capacity_after=after.capacity_used,
                    capacity_total=after.capacity_total,
                    settings=settings,
                    rewards=rewards,
                    rarity_warning_confirmed=warning_confirmed,
                    equipment_preserved=equipment_preserved,
                    equipment_policy='preserve' if preserve_equipment else 'disassemble',
                    equipment_disassembled=equipment_disassembled,
                    equipment_quantities=equipment_quantities,
                    equipment_rewards=equipment_rewards,
                    actions=tuple(actions),
                )
        raise SemanticGateClosed("official retirement transaction did not close")
