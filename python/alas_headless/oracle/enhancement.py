"""Enhancement for the typed ALAS boundary."""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple, Union
from .contracts import (
    ActionReceipt,
    EnhancementAttributeState,
    EnhancementDockCandidate,
    EnhancementExecutionReceipt,
    EnhancementMaterialState,
    EnhancementNoMaterialReceipt,
    EnhancementPreview,
    ImageState,
    OracleState,
    Point,
    TextState,
    ToggleState,
    UiState,
)
from .errors import SemanticGateClosed


class EnhancementOracle:
    """Enhancement operations sharing the oracle frame and input boundary."""

    def enhancement_dock_visible(self) -> bool:
        state = self.read_state()
        path = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button'
        if not any(b.path == path and b.active_in_hierarchy and b.active_and_enabled
                   for b in state.buttons):
            return False
        self._enhancement_dock_records()
        return True

    def enhancement_dock_back_control(self):
        state = self.read_state()
        filter_path = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button'
        if not any(b.path == filter_path and b.active_in_hierarchy for b in state.buttons):
            return None
        state, ui = self._enhancement_dock_records()
        path = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back'
        matches = tuple(i for i in ui.images if i.path == path
                        and i.sprite == 'icon_bg_front_1920'
                        and i.active_in_hierarchy and i.active_and_enabled)
        if len(matches) != 1:
            raise SemanticGateClosed('Dock back Image is absent or ambiguous')
        target = matches[0]
        if (target.raycast_top is False or not target.raycast_target
                or target.truncated or target.bounds is None
                or self._blocking_rules(state, 'enhancement/dock/exit')):
            raise SemanticGateClosed('Dock back Image is not actionable')
        return state, target

    def click_enhancement_dock_back(self) -> ActionReceipt:
        control = self.enhancement_dock_back_control()
        if control is None:
            raise SemanticGateClosed('Dock page is absent')
        receipt = self._click_exact_image(*control, 'enhancement/dock/exit')

        def departed():
            state = self.read_state()
            if state.generation <= receipt.generation or any(
                b.active_in_hierarchy and 'DockyardUI(Clone)/' in b.path
                for b in state.buttons
            ):
                raise SemanticGateClosed('Dock exit has not advanced')
            return state

        self._retry_transition_read(departed, attempts=30, interval_seconds=0.1)
        return receipt

    def _enhancement_dock_records(self) -> Tuple[OracleState, UiState]:
        """Read a coherent Dock page before enhancement navigation."""

        capacity_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/Text"
        )
        label_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/label"
        )
        filter_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button"
        )
        def read_records() -> Tuple[OracleState, UiState]:
            state, ui_state = self._retirement_records()
            capacity = tuple(
                item
                for item in ui_state.texts
                if item.path == capacity_path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(r"[0-9]+/[0-9]+", item.text)
            )
            label = tuple(
                item
                for item in ui_state.texts
                if item.path == label_path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.text == "船坞容量:"
            )
            filter_buttons = tuple(
                item
                for item in state.buttons
                if item.path == filter_path
                and item.name == "index_button"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
                and item.point is not None
                and item.bounds is not None
                and item.bounds.contains(item.point)
            )
            filter_images = tuple(
                item
                for item in ui_state.images
                if item.path == filter_path
                and item.sprite in ("shaixuan_on", "shaixuan_off")
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.bounds is not None
            )
            if (
                state.generation <= ui_state.generation <= state.generation + 2
                and ui_state.method_mask & 0xF == 0xF
                and len(capacity) == len(label) == len(filter_buttons) == 1
                and len(filter_images) == 1
                and filter_images[0].bounds.contains(filter_buttons[0].point)
            ):
                return state, ui_state
            raise SemanticGateClosed("enhancement Dock identity is incomplete")

        # A leased screenshot is immutable. Its transition reader performs
        # one attempt, allowing ALAS to refresh at its next screenshot; live
        # readers retain the bounded settling retry.
        return self._retry_transition_read(
            read_records, attempts=8, interval_seconds=0.05
        )

    @staticmethod
    def _enhancement_filter_option(
        ui_state: UiState,
        group: str,
        option: str,
        label: str,
    ) -> ImageState:
        root = (
            "OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/"
            "layout/container/indexsort_{0}/bg/{1}"
        ).format(group, option)
        images = tuple(
            item
            for item in ui_state.images
            if item.path == root
            and item.sprite in ("btn_index_grey", "btn_index_blue", "btn_index_yellow")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        texts = tuple(
            item
            for item in ui_state.texts
            if item.path == root + "/Image"
            and item.text == label
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(images) != 1 or len(texts) != 1:
            raise SemanticGateClosed("enhancement Dock filter option is incomplete")
        return images[0]

    def _wait_enhancement_filter_option(
        self,
        group: str,
        option: str,
        label: str,
    ) -> Tuple[OracleState, UiState, ImageState]:
        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(30):
            try:
                state, ui_state = self._retirement_records()
                return (
                    state,
                    ui_state,
                    self._enhancement_filter_option(
                        ui_state, group, option, label
                    ),
                )
            except SemanticGateClosed as exc:
                last_error = exc
                if attempt < 29:
                    self._sleep(0.05)
        raise SemanticGateClosed(
            "enhancement Dock filter option did not stabilize"
        ) from last_error

    def set_enhancement_dock_favourite(self, enabled: bool) -> Optional[ActionReceipt]:
        """Set the Dock favourite scope using its currently rendered toggle."""

        if not isinstance(enabled, bool):
            raise TypeError("enhancement favourite scope must be boolean")
        root = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/switch/toggles/"
            "preference_toggle/"
        )
        state, ui_state = self._enhancement_dock_records()
        active = {
            suffix: tuple(
                item
                for item in ui_state.images
                if item.path == root + suffix
                and item.sprite == sprite
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            for suffix, sprite in (
                ("on", "changyong_butten01"),
                ("off", "changyong_butten02"),
            )
        }
        if len(active["on"]) > 1 or len(active["off"]) > 1:
            raise SemanticGateClosed("Dock favourite state is ambiguous")
        # The live client keeps the off layer active when favourite is on;
        # the on layer is therefore the positive state discriminator.
        current = bool(active["on"])
        if current == enabled:
            return None
        target_name = "on" if enabled else "off"
        current_name = "on" if current else "off"
        if len(active[current_name]) != 1:
            raise SemanticGateClosed("Dock favourite state is incomplete")
        receipt = self._click_exact_image(
            state,
            active[current_name][0],
            "enhancement/dock/favourite/" + target_name,
        )
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            _, after = self._enhancement_dock_records()
            visible = {
                suffix: tuple(
                    item
                    for item in after.images
                    if item.path == root + suffix
                    and item.sprite == sprite
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.bounds is not None
                )
                for suffix, sprite in (
                    ("on", "changyong_butten01"),
                    ("off", "changyong_butten02"),
                )
            }
            if enabled and len(visible["on"]) == 1:
                return receipt
            if (
                not enabled
                and not visible["on"]
                and len(visible["off"]) == 1
            ):
                return receipt
            self._sleep(0.05)
        raise SemanticGateClosed("Dock favourite state did not change")

    def set_enhancement_dock_filter(
        self,
        ship_type: Optional[str],
        *,
        enhanceable_only: bool = True,
    ) -> Tuple[ActionReceipt, ...]:
        """Apply ALAS's Dock type filter, optionally retaining maxed ships."""

        index_options = {
            None: ("tpl", "全部"),
            "dd": ("3", "驱逐"),
            "cl": ("4", "轻巡"),
            "ca": ("5", "重巡"),
            "bb": ("6", "战列"),
            "cv": ("7", "航母"),
            "repair": ("8", "维修"),
            "ss": ("9", "潜艇"),
            "others": ("10", "其他"),
        }
        if ship_type not in index_options:
            raise ValueError("enhancement ship type is unsupported")
        if not isinstance(enhanceable_only, bool):
            raise TypeError("enhancement Dock enhanceable_only must be boolean")
        state, ui_state = self._enhancement_dock_records()
        filter_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button"
        )
        opener = next(item for item in ui_state.images if item.path == filter_path)
        receipts = [
            self._click_exact_image(state, opener, "enhancement/dock/filter/open")
        ]
        self._sleep(0.1)
        choices = (
            ("sort", "1", "等级", "btn_index_yellow"),
            ("index", index_options[ship_type][0], index_options[ship_type][1], "btn_index_blue"),
            ("camp", "tpl", "全阵营", "btn_index_blue"),
            ("rarity", "tpl", "全部", "btn_index_blue"),
            (
                "extraindex",
                "3" if enhanceable_only else "tpl",
                "可强化" if enhanceable_only else "无限制",
                "btn_index_blue",
            ),
        )
        for group, option, label, selected_sprite in choices:
            semantic_id = "enhancement/dock/filter/{0}/{1}".format(
                group, option
            )
            for click_attempt in range(3):
                state, _, image = self._wait_enhancement_filter_option(
                    group, option, label
                )
                if image.sprite == selected_sprite:
                    break
                if image.sprite != "btn_index_grey":
                    raise SemanticGateClosed(
                        "enhancement Dock filter state is unknown"
                    )
                for _ in range(20):
                    if not self._blocking_rules(state, semantic_id):
                        break
                    self._sleep(0.05)
                    state, _, image = self._wait_enhancement_filter_option(
                        group, option, label
                    )
                    if image.sprite == selected_sprite:
                        break
                    if image.sprite != "btn_index_grey":
                        raise SemanticGateClosed(
                            "enhancement Dock filter state became unknown"
                        )
                else:
                    raise SemanticGateClosed(
                        "enhancement Dock filter input stayed blocked"
                    )
                if image.sprite == selected_sprite:
                    break
                receipts.append(
                    self._click_exact_image(state, image, semantic_id)
                )
                for _ in range(30):
                    self._sleep(0.05)
                    _, _, verified = self._wait_enhancement_filter_option(
                        group, option, label
                    )
                    if verified.sprite == selected_sprite:
                        break
                    if verified.sprite != "btn_index_grey":
                        raise SemanticGateClosed(
                            "enhancement Dock filter selection became unknown"
                        )
                else:
                    if click_attempt == 2:
                        raise SemanticGateClosed(
                            "enhancement Dock filter option did not select"
                        )
                    continue
                break
            else:
                raise SemanticGateClosed(
                    "enhancement Dock filter option did not select"
                )
        for _ in range(20):
            state, ui_state = self._retirement_records()
            if not self._blocking_rules(state, "enhancement/dock/filter/confirm"):
                break
            self._sleep(0.05)
        else:
            raise SemanticGateClosed("enhancement Dock filter confirm stayed blocked")
        confirm_path = (
            "OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/"
            "layout/btns/ok"
        )
        confirm = tuple(
            item
            for item in ui_state.images
            if item.path == confirm_path
            and item.sprite == "btn_big_blue"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        confirm_text = tuple(
            item
            for item in ui_state.texts
            if item.path == confirm_path + "/Image"
            and item.text == "确 定"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(confirm) != 1 or len(confirm_text) != 1:
            raise SemanticGateClosed("enhancement Dock filter confirm is incomplete")
        receipts.append(
            self._click_exact_image(state, confirm[0], "enhancement/dock/filter/confirm")
        )
        self._retry_transition_read(
            self._enhancement_dock_records,
            attempts=20,
            interval_seconds=0.1,
        )
        return tuple(receipts)

    def enhancement_dock_candidates(self) -> Tuple[EnhancementDockCandidate, ...]:
        """Read all currently visible enhanceable cards in Dock grid order."""

        state, ui_state = self._enhancement_dock_records()
        prefix = "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/ships/"
        buttons = tuple(
            item
            for item in state.buttons
            if re.fullmatch(r"[1-9][0-9]{5,7}", item.name)
            and item.path == prefix + item.name
            and item.actionable
            and item.bounds is not None
            and item.bounds.left >= 0
            and item.bounds.right <= self.fingerprint.width
            and item.bounds.top >= 0
            and item.bounds.bottom <= self.fingerprint.height + 20
        )
        ordered = tuple(
            sorted(buttons, key=lambda item: (item.bounds.top, item.bounds.left))
        )
        result = []
        for position, button in enumerate(ordered):
            root = button.path + "/content/"
            assert button.bounds is not None

            def belongs_to_button(item: TextState) -> bool:
                if item.bounds is None:
                    return False
                return button.bounds.contains(
                    Point(
                        (item.bounds.left + item.bounds.right) / 2.0,
                        (item.bounds.top + item.bounds.bottom) / 2.0,
                    )
                )

            name = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "info/name_mask/name"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.text.strip()
                and belongs_to_button(item)
            )
            level = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "dockyard/lv/Text"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(r"[1-9][0-9]{0,2}", item.text)
                and belongs_to_button(item)
            )
            if (
                not name
                or not level
                or len({item.text.strip() for item in name}) != 1
                or len({item.text for item in level}) != 1
            ):
                raise SemanticGateClosed("enhancement Dock card identity is incomplete")
            result.append(
                EnhancementDockCandidate(
                    position=position,
                    ship_id=int(button.name),
                    ship_name=name[0].text.strip(),
                    level=int(level[0].text),
                    button=button,
                )
            )
        return tuple(result)

    def open_enhancement_dock_candidate(
        self,
        position: int,
        ship_id: int,
        ship_name: str,
        level: int,
    ) -> ActionReceipt:
        """Enter one exact Dock card and switch to its enhancement page."""

        candidates = self.enhancement_dock_candidates()
        matches = tuple(
            item
            for item in candidates
            if item.position == position
            and item.ship_id == ship_id
            and item.ship_name == ship_name
            and item.level == level
        )
        if len(matches) != 1:
            raise SemanticGateClosed("enhancement Dock candidate changed")
        target = matches[0].button
        assert target.point is not None and target.bounds is not None
        state = self.read_state()
        current = tuple(
            item
            for item in state.buttons
            if item.path == target.path
            and item.actionable
            and item.bounds == target.bounds
        )
        if len(current) != 1:
            raise SemanticGateClosed("enhancement Dock candidate changed before input")
        if self._blocking_rules(state, "enhancement/dock/ship"):
            raise SemanticGateClosed("enhancement Dock candidate input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before Dock ship input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        receipt = ActionReceipt(
            semantic_id="enhancement/dock/ship/{0}".format(ship_id),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
        deadline = time.monotonic() + 5.0
        toggle_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/frame/root/"
            "intensify_toggle"
        )
        while time.monotonic() < deadline:
            ui_state = self._retirement_records()[1]
            toggles = tuple(
                item
                for item in ui_state.toggles
                if item.path == toggle_path
                and item.name == "intensify_toggle"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
                and item.point is not None
                and item.bounds is not None
                and item.bounds.contains(item.point)
            )
            if len(toggles) == 1:
                toggle = toggles[0]
                if not toggle.checked:
                    if self._foreground_component() != self.fingerprint.component:
                        raise SemanticGateClosed("game activity changed before enhancement tab input")
                    self._tap(int(round(toggle.point.x)), int(round(toggle.point.y)))
                self._retry_transition_read(
                    self.enhancement_preview,
                    attempts=30,
                    interval_seconds=0.1,
                )
                return receipt
            self._sleep(0.05)
        raise SemanticGateClosed("ship enhancement tab did not become available")

    @staticmethod
    def _enhancement_detail_toggle(
        ui_state: UiState,
        *,
        name: str,
        path: str,
    ) -> ToggleState:
        if ui_state.method_mask & 0x1 == 0:
            raise SemanticGateClosed("typed Unity Toggle snapshot is incomplete")
        toggles = tuple(
            item
            for item in ui_state.toggles
            if item.name == name
            and item.path == path
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.bounds is not None
        )
        if len(toggles) != 1:
            raise SemanticGateClosed("enhancement detail toggle is incomplete")
        return toggles[0]

    def _wait_enhancement_detail_toggle(
        self,
        *,
        name: str,
        path: str,
        checked: Optional[bool] = None,
    ) -> Tuple[OracleState, UiState, ToggleState]:
        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(30):
            try:
                state, ui_state = self._retirement_records()
                toggle = self._enhancement_detail_toggle(
                    ui_state, name=name, path=path
                )
                if checked is not None and toggle.checked is not checked:
                    raise SemanticGateClosed("enhancement detail toggle has not changed")
                return state, ui_state, toggle
            except SemanticGateClosed as exc:
                last_error = exc
                if attempt < 29:
                    self._sleep(0.05)
        raise SemanticGateClosed(
            "enhancement detail toggle did not stabilize"
        ) from last_error

    @staticmethod
    def _enhancement_detail_ship_name(
        ui_state: UiState,
    ) -> str:
        path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/name/"
            "nameRect/name_mask/Text"
        )
        names = tuple(
            item.text.strip()
            for item in ui_state.texts
            if item.path == path
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        if len(names) != 1:
            raise SemanticGateClosed("enhancement detail ship identity is incomplete")
        return names[0]

    def _return_from_enhancement_detail_to_dock(self) -> ActionReceipt:
        """Leave the ship detail tab and prove the original Dock grid returns."""

        state = self.read_state()
        suffix = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back_btn"
        buttons = tuple(
            item
            for item in state.buttons
            if item.path.endswith(suffix) and item.name == "back_btn" and item.actionable
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("enhancement detail back control is incomplete")
        target = buttons[0]
        assert target.point is not None and target.bounds is not None
        if self._blocking_rules(state, "enhancement/detail/back"):
            raise SemanticGateClosed("enhancement detail back input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "game activity changed before enhancement detail back input"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        receipt = ActionReceipt(
            semantic_id="enhancement/detail/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
        self._retry_transition_read(
            self._enhancement_dock_records,
            attempts=30,
            interval_seconds=0.1,
        )
        return receipt

    def set_enhancement_dock_candidate_favourite(
        self,
        position: int,
        ship_id: int,
        ship_name: str,
        level: int,
        enabled: bool,
    ) -> Tuple[ActionReceipt, ...]:
        """Set one exact Dock card's in-client common/favourite state.

        This is intentionally separate from the Dock scope toggle used by the
        task.  It gives live qualification a reversible way to seed and then
        restore a real favourite target without changing ALAS task control.
        """

        if not isinstance(enabled, bool):
            raise TypeError("enhancement candidate favourite must be boolean")
        receipts = [
            self.open_enhancement_dock_candidate(
                position, ship_id, ship_name, level
            )
        ]
        detail_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/frame/root/"
            "detail_toggle"
        )
        state, ui_state, detail = self._wait_enhancement_detail_toggle(
            name="detail_toggle", path=detail_path
        )
        if detail.checked is not True:
            receipts.append(
                self._click_exact_toggle(
                    state, detail, "enhancement/detail/tab"
                )
            )
        common_path = (
            "OverlayCamera/Overlay/UIMain/detail_container(Adapt)/detail_container/"
            "ShipDetailView(Clone)/common_toggle"
        )
        state, ui_state, common = self._wait_enhancement_detail_toggle(
            name="common_toggle", path=common_path
        )
        if self._enhancement_detail_ship_name(ui_state) != ship_name:
            raise SemanticGateClosed("enhancement detail ship changed")
        expected_sprite = "common_active" if enabled else "common_deactive"
        current_sprite = "common_active" if common.checked else "common_deactive"
        visible = tuple(
            item
            for item in ui_state.images
            if item.path == common_path + ("/on" if common.checked else "/off")
            and item.sprite == current_sprite
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(visible) != 1:
            raise SemanticGateClosed("enhancement candidate favourite state is incomplete")
        if common.checked != enabled:
            # The detail toggle exposes the control before its hit target is
            # ready on the live client.  Refresh the typed state once after
            # the panel has settled, then use its exact input point.
            self._sleep(0.2)
            state, ui_state, common = self._wait_enhancement_detail_toggle(
                name="common_toggle", path=common_path
            )
            if common.checked != enabled:
                if self._enhancement_detail_ship_name(ui_state) != ship_name:
                    raise SemanticGateClosed("enhancement detail ship changed")
                receipts.append(
                    self._click_exact_toggle(
                        state,
                        common,
                        "enhancement/detail/favourite/"
                        + ("on" if enabled else "off"),
                    )
                )
            _, after, common = self._wait_enhancement_detail_toggle(
                name="common_toggle", path=common_path, checked=enabled
            )
            after_visible = tuple(
                item
                for item in after.images
                if item.path == common_path + ("/on" if enabled else "/off")
                and item.sprite == expected_sprite
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(after_visible) != 1:
                raise SemanticGateClosed(
                    "enhancement candidate favourite did not change"
                )
        receipts.append(self._return_from_enhancement_detail_to_dock())
        return tuple(receipts)

    def return_to_enhancement_dock(self) -> ActionReceipt:
        """Leave a completed/empty enhancement target and prove Dock recovery."""

        state, _ = self._enhancement_records()
        suffix = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back_btn"
        buttons = tuple(
            item
            for item in state.buttons
            if item.path.endswith(suffix) and item.name == "back_btn" and item.actionable
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("enhancement back control is incomplete")
        target = buttons[0]
        assert target.point is not None and target.bounds is not None
        if self._blocking_rules(state, "enhancement/dock/back"):
            raise SemanticGateClosed("enhancement back input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before enhancement back input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        receipt = ActionReceipt(
            semantic_id="enhancement/dock/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
        self._retry_transition_read(
            self._enhancement_dock_records,
            attempts=30,
            interval_seconds=0.1,
        )
        return receipt

    def reset_enhancement_dock(self) -> Tuple[ActionReceipt, ...]:
        """Restore ALAS's normal Dock filter after an enhancement task."""

        receipts = list(self.set_enhancement_dock_filter(None))
        favourite = self.set_enhancement_dock_favourite(False)
        if favourite is not None:
            receipts.append(favourite)
        # set_enhancement_dock_filter(None) intentionally selects enhanceable;
        # reset the final extra option to the official no-limit default.
        state, ui_state = self._enhancement_dock_records()
        opener = next(
            item
            for item in ui_state.images
            if item.path.endswith("/adapt/top/index_button")
        )
        receipts.append(
            self._click_exact_image(state, opener, "enhancement/dock/reset/open")
        )
        self._sleep(0.1)
        no_limit_error: Optional[SemanticGateClosed] = None
        for attempt in range(20):
            state, ui_state = self._retirement_records()
            try:
                no_limit = self._enhancement_filter_option(
                    ui_state, "extraindex", "tpl", "无限制"
                )
            except SemanticGateClosed as exc:
                no_limit_error = exc
                self._sleep(0.05)
                continue
            if no_limit.sprite == "btn_index_blue":
                break
            if no_limit.sprite != "btn_index_grey":
                raise SemanticGateClosed("Dock reset extra filter is unknown")
            if self._blocking_rules(state, "enhancement/dock/reset/no-limit"):
                self._sleep(0.05)
                continue
            receipts.append(
                self._click_exact_image(
                    state, no_limit, "enhancement/dock/reset/no-limit"
                )
            )
            break
        else:
            raise SemanticGateClosed(
                "Dock reset extra filter did not stabilize"
            ) from no_limit_error
        for attempt in range(20):
            state, ui_state = self._retirement_records()
            if not self._blocking_rules(state, "enhancement/dock/reset/confirm"):
                break
            self._sleep(0.05)
        else:
            raise SemanticGateClosed("Dock reset confirmation stayed blocked")
        confirm_path = (
            "OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/"
            "layout/btns/ok"
        )
        confirm = tuple(
            item
            for item in ui_state.images
            if item.path == confirm_path
            and item.sprite == "btn_big_blue"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(confirm) != 1:
            raise SemanticGateClosed("Dock reset confirmation is incomplete")
        receipts.append(
            self._click_exact_image(state, confirm[0], "enhancement/dock/reset/confirm")
        )
        self._retry_transition_read(
            self._enhancement_dock_records,
            attempts=20,
            interval_seconds=0.1,
        )
        return tuple(receipts)

    def _enhancement_records(self) -> Tuple[OracleState, UiState]:
        """Read one coherent official enhancement-page slice."""

        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(8):
            state = self.read_state()
            ui_state = self.read_ui_state()
            if not state.generation <= ui_state.generation <= state.generation + 2:
                last_error = SemanticGateClosed(
                    "enhancement button and UI snapshots are not coherent"
                )
            elif ui_state.method_mask & 0xF != 0xF:
                last_error = SemanticGateClosed(
                    "typed enhancement UI access is incomplete"
                )
            else:
                target_path = (
                    "OverlayCamera/Overlay/UIMain/blur_panel/adapt/name/"
                    "nameRect/name_mask/Text"
                )
                target = tuple(
                    item
                    for item in ui_state.texts
                    if item.path.endswith(target_path)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.text.strip()
                )
                toggle = tuple(
                    item
                    for item in ui_state.toggles
                    if item.name == "intensify_toggle"
                    and item.path.endswith(
                        "OverlayCamera/Overlay/UIMain/blur_panel/adapt/"
                        "left_length/frame/root/intensify_toggle"
                    )
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and item.checked
                )
                title = tuple(
                    item
                    for item in ui_state.texts
                    if item.path.endswith(
                        "blur_panel(Adapt)/blur_panel/main/bg/"
                        "add_ship_panel/title/Image"
                    )
                    and item.text == "添 加 素 材"
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                if len(target) == len(toggle) == len(title) == 1:
                    return state, ui_state
                last_error = SemanticGateClosed(
                    "official enhancement page identity is incomplete"
                )
            if attempt < 7:
                self._sleep(0.05)
        raise SemanticGateClosed(
            "enhancement snapshots did not stabilize"
        ) from last_error

    def enhancement_preview(self) -> EnhancementPreview:
        """Read target, attributes, and selected materials without consuming ships."""

        state, ui_state = self._enhancement_records()
        target_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/name/nameRect/name_mask/Text"
        )
        target = next(
            item.text.strip()
            for item in ui_state.texts
            if item.path.endswith(target_path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.text.strip()
        )
        attribute_root = (
            "OverlayCamera/Overlay/UIMain/blur_panel(Adapt)/blur_panel/main/"
            "bg/property_panel/attrs/attr_"
        )
        grouped: Dict[int, Dict[str, str]] = {}
        for item in ui_state.texts:
            if (
                not item.path.startswith(attribute_root)
                or not item.active_in_hierarchy
                or not item.active_and_enabled
                or item.truncated
            ):
                continue
            match = re.match(re.escape(attribute_root) + r"([0-9]+)/(.+)$", item.path)
            if match is None:
                continue
            index = int(match.group(1))
            suffix = match.group(2)
            keys = {
                "info/info_container/name": "name",
                "info/info_container/value": "current",
                "info/info_container/addition": "addition",
                "info/max_container/Text": "maximum",
                "exp_container/Text": "exp",
            }
            key = keys.get(suffix)
            if key is not None:
                grouped.setdefault(index, {})[key] = item.text.strip()
        attributes: List[EnhancementAttributeState] = []
        for index, values in sorted(grouped.items()):
            if set(values) != {"name", "current", "addition", "maximum", "exp"}:
                raise SemanticGateClosed("enhancement attribute row is incomplete")
            addition_match = re.fullmatch(r"\+([0-9]+)", values["addition"])
            if (
                addition_match is None
                or not values["current"].isdigit()
                or not values["maximum"].isdigit()
            ):
                raise SemanticGateClosed("enhancement attribute values are malformed")
            exp_current: Optional[int]
            exp_total: Optional[int]
            if values["exp"] == "MAX":
                exp_current = exp_total = None
            else:
                exp_match = re.fullmatch(r"([0-9]+)/([0-9]+)", values["exp"])
                if exp_match is None:
                    raise SemanticGateClosed("enhancement experience is malformed")
                exp_current, exp_total = map(int, exp_match.groups())
            attributes.append(
                EnhancementAttributeState(
                    index=index,
                    name=values["name"],
                    current=int(values["current"]),
                    maximum=int(values["maximum"]),
                    addition=int(addition_match.group(1)),
                    exp_current=exp_current,
                    exp_total=exp_total,
                )
            )
        if not attributes:
            raise SemanticGateClosed("enhancement attributes are absent")

        ship_root = (
            "OverlayCamera/Overlay/UIMain/blur_panel(Adapt)/blur_panel/main/"
            "bg/add_ship_panel/ships/shiptpl"
        )
        selected = tuple(
            button
            for button in state.buttons
            if re.fullmatch(re.escape(ship_root) + r"(?: \(([0-9]+)\))?", button.path)
            and button.name.startswith("shiptpl")
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        materials: List[EnhancementMaterialState] = []
        material_shapes: List[bool] = []
        for button in sorted(
            selected,
            key=lambda item: item.bounds.left if item.bounds is not None else 9999,
        ):
            suffix_match = re.fullmatch(
                re.escape(ship_root) + r"(?: \(([0-9]+)\))?", button.path
            )
            assert suffix_match is not None
            slot = 0 if suffix_match.group(1) is None else int(suffix_match.group(1))
            level = tuple(
                item
                for item in ui_state.texts
                if item.path == button.path + "/IconTpl/icon_bg/lv/Text"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.text.isdigit()
            )
            # Unity keeps the material-slot Button objects active after the
            # official clear action.  The populated card identity is the
            # exact level Text plus rarity/icon Images, not the retained
            # parent Button alone.
            if not level:
                continue
            rarity = tuple(
                item
                for item in ui_state.images
                if item.path == button.path + "/IconTpl/icon_bg"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            icon = tuple(
                item
                for item in ui_state.images
                if item.path == button.path + "/IconTpl/icon_bg/icon"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.sprite
            )
            if len(level) != 1 or len(rarity) != 1 or len(icon) != 1:
                raise SemanticGateClosed("enhancement material identity is incomplete")
            child_images = tuple(
                item
                for item in ui_state.images
                if item.path.startswith(button.path + "/")
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            exact_signatures = {
                "/IconTpl/icon_bg/lv/lv_bg": "bg_lv",
                "/IconTpl/icon_bg/frame": "frame",
                "/IconTpl/bg": "white_dot",
                "/IconTpl": "white_dot",
                "/add": "sucai_butten",
            }
            observed_exact = {
                suffix: tuple(
                    item
                    for item in child_images
                    if item.path == button.path + suffix
                    and item.sprite == expected_sprite
                )
                for suffix, expected_sprite in exact_signatures.items()
            }
            star_background = tuple(
                item
                for item in child_images
                if re.fullmatch(
                    re.escape(button.path)
                    + r"/IconTpl/icon_bg/stars/startpl(?:\(Clone\))?",
                    item.path,
                )
                and item.sprite == "star_bg"
            )
            stars = tuple(
                item
                for item in child_images
                if re.fullmatch(
                    re.escape(button.path)
                    + r"/IconTpl/icon_bg/stars/startpl(?:\(Clone\))?/star",
                    item.path,
                )
                and item.sprite == "star"
            )
            allowed_paths = {button.path + suffix for suffix in exact_signatures} | {
                button.path + "/IconTpl/icon_bg",
                button.path + "/IconTpl/icon_bg/icon",
            }
            unexpected = tuple(
                item
                for item in child_images
                if item.path not in allowed_paths
                and item not in star_background
                and item not in stars
            )
            material_shapes.append(
                rarity[0].sprite == "bg1"
                and int(level[0].text) == 1
                and all(len(matches) == 1 for matches in observed_exact.values())
                and len(star_background) == 1
                and len(stars) == 1
                and not unexpected
            )
            materials.append(
                EnhancementMaterialState(
                    slot=slot,
                    level=int(level[0].text),
                    rarity_sprite=rarity[0].sprite,
                    ship_sprite=icon[0].sprite,
                )
            )
        source_complete = bool(
            not ui_state.image_truncated
            and ui_state.image_source_count is not None
            and ui_state.image_source_capacity is not None
            and ui_state.image_source_count <= ui_state.image_source_capacity
        )
        # A complete source enumeration plus a closed card-child whitelist
        # turns icon absence into positive evidence: any lock, favourite,
        # equipment, or other overlay adds an unexpected active child Image.
        return EnhancementPreview(
            generation=max(state.generation, ui_state.generation),
            target_name=target,
            attributes=tuple(attributes),
            materials=tuple(materials),
            image_snapshot_truncated=ui_state.image_truncated,
            material_protection_proven=bool(
                materials and source_complete and all(material_shapes)
            ),
            image_source_count=ui_state.image_source_count,
            image_source_capacity=ui_state.image_source_capacity,
        )

    def _click_enhancement_control(
        self, semantic_id: str, name: str, sprite: str
    ) -> ActionReceipt:
        state, ui_state = self._enhancement_records()
        path = "OverlayCamera/Overlay/UIMain/blur_panel(Adapt)/blur_panel/main/" + name
        buttons = tuple(
            item
            for item in state.buttons
            if item.name == name
            and item.path == path
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.point is not None
            and item.bounds is not None
            and item.bounds.contains(item.point)
        )
        images = tuple(
            item
            for item in ui_state.images
            if item.name == name
            and item.path == path
            and item.sprite == sprite
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.raycast_target
            and item.bounds is not None
        )
        if len(buttons) != 1 or len(images) != 1:
            raise SemanticGateClosed("enhancement control identity is incomplete")
        button = buttons[0]
        assert button.point is not None and button.bounds is not None
        if not images[0].bounds.contains(button.point):
            raise SemanticGateClosed("enhancement control layers disagree")
        # These controls may omit optional raycast metadata on the qualified
        # client. An explicit negative result or a known overlay still closes
        # this action boundary; the underlying panel can remain mounted.
        if button.raycast_top is False or images[0].raycast_top is False:
            raise SemanticGateClosed("enhancement control is obscured")
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("enhancement control is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before enhancement input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after enhancement input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=max(state.generation, ui_state.generation),
            point=button.point,
            bounds=button.bounds,
            path=button.path,
        )

    def recommend_enhancement_materials(
        self, timeout_seconds: float = 5.0
    ) -> EnhancementPreview:
        """Ask the official client to select materials, without confirming."""

        if timeout_seconds <= 0:
            raise ValueError("enhancement timeout must be positive")
        if self.enhancement_preview().materials:
            raise SemanticGateClosed("enhancement recommendation requires empty slots")
        self._click_enhancement_control(
            "enhancement/recommend", "select_btn", "recommand"
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                preview = self.enhancement_preview()
            except SemanticGateClosed:
                preview = None
            if preview is not None and preview.materials:
                return preview
            self._sleep(0.05)
        raise SemanticGateClosed(
            "official enhancement recommendation found no material"
        )

    def clear_enhancement_materials(
        self, timeout_seconds: float = 5.0
    ) -> ActionReceipt:
        """Clear a recommendation and prove that no material was consumed."""

        if timeout_seconds <= 0:
            raise ValueError("enhancement timeout must be positive")
        if not self.enhancement_preview().materials:
            raise SemanticGateClosed("enhancement material slots are already empty")
        receipt = self._click_enhancement_control(
            "enhancement/clear", "cancel_btn", "qingkong_butten"
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                preview = self.enhancement_preview()
            except SemanticGateClosed:
                preview = None
            if preview is not None and not preview.materials:
                return receipt
            self._sleep(0.05)
        raise SemanticGateClosed("enhancement materials did not clear")

    def enhance_with_official_recommendation(
        self, timeout_seconds: float = 5.0
    ) -> Union[EnhancementExecutionReceipt, EnhancementNoMaterialReceipt]:
        """Use the official recommendation and confirm one protected enhancement.

        No material is a successful skip. Any incomplete card, non-level-1 or
        non-N material, unknown overlay, target change, or attribute mismatch
        closes the gate before another destructive input can be sent.
        """

        if timeout_seconds <= 0:
            raise ValueError("enhancement timeout must be positive")
        initial = self.enhancement_preview()
        if initial.materials:
            raise SemanticGateClosed("official enhancement requires empty slots")
        recommendation = self._click_enhancement_control(
            "enhancement/recommend", "select_btn", "recommand"
        )
        deadline = time.monotonic() + timeout_seconds
        selected: Optional[EnhancementPreview] = None
        last_stable = initial
        while time.monotonic() < deadline:
            try:
                preview = self.enhancement_preview()
            except SemanticGateClosed:
                preview = None
            if preview is not None:
                last_stable = preview
                if preview.materials:
                    selected = preview
                    break
            self._sleep(0.05)
        if selected is None:
            if last_stable.target_name != initial.target_name or last_stable.materials:
                raise SemanticGateClosed(
                    "official enhancement no-material state is incoherent"
                )
            return EnhancementNoMaterialReceipt(
                generation=last_stable.generation,
                target_name=last_stable.target_name,
                recommendation=recommendation,
            )
        initial_attributes = {item.index: item for item in initial.attributes}

        def partial_experience_gain(item: EnhancementAttributeState) -> int:
            before = initial_attributes.get(item.index)
            if (before is None or item.addition != 0
                    or item.name != before.name or item.current != before.current
                    or item.maximum != before.maximum
                    or item.exp_total is None or item.exp_total != before.exp_total
                    or item.exp_current is None or before.exp_current is None
                    or not 0 <= before.exp_current < item.exp_current < item.exp_total):
                return 0
            return item.exp_current - before.exp_current

        materials_safe = bool(
            selected.material_protection_proven
            and all(
                material.level == 1 and material.rarity_sprite == "bg1"
                for material in selected.materials
            )
            and any(attribute.addition > 0 or partial_experience_gain(attribute) > 0
                    for attribute in selected.attributes)
        )
        if not materials_safe:
            try:
                self.clear_enhancement_materials(timeout_seconds=timeout_seconds)
            finally:
                raise SemanticGateClosed(
                    "official enhancement recommendation is not consumption-safe"
                )
        confirmation = self._click_enhancement_control(
            "enhancement/confirm", "ok_btn", "qianghua_butten"
        )

        def result_gain(preview: EnhancementPreview) -> Optional[int]:
            """Return the exact observed gain once the client has settled."""

            if preview.target_name != selected.target_name:
                return None
            before_by_index = {item.index: item for item in selected.attributes}
            after_by_index = {item.index: item for item in preview.attributes}
            if before_by_index.keys() != after_by_index.keys():
                return None
            gain = 0
            for index, before in before_by_index.items():
                after = after_by_index[index]
                expected = min(before.maximum, before.current + before.addition)
                if (
                    after.name != before.name
                    or after.maximum != before.maximum
                    or after.current != expected
                    or after.addition != 0
                ):
                    return None
                gain += after.current - before.current
                experience_gain = partial_experience_gain(before)
                if experience_gain:
                    if (after.exp_current != before.exp_current
                            or after.exp_total != before.exp_total):
                        return None
                    gain += experience_gain
            return gain if gain > 0 else None

        deadline = time.monotonic() + timeout_seconds
        completed: Optional[EnhancementPreview] = None
        equipment_result: Optional[
            Tuple[Tuple[Tuple[int, int], ...], Tuple[ActionReceipt, ...]]
        ] = None
        while time.monotonic() < deadline:
            try:
                preview = self.enhancement_preview()
            except SemanticGateClosed:
                preview = None
            # The live client clears its material slots one observer frame
            # before applying the corresponding attribute values.  Do not
            # mistake that transitional empty panel for the completed order.
            if (
                preview is not None
                and not preview.materials
                and result_gain(preview) is not None
            ):
                completed = preview
                break
            if preview is not None:
                # This remains the known enhancement panel, so avoid mixing
                # in a second page probe while its rows are still animating.
                self._sleep(0.05)
                continue
            state, ui_state = self._retirement_records()
            active_paths = tuple(
                item.path
                for item in state.buttons
                if item.active_in_hierarchy and item.active_and_enabled
            )
            equipment_visible = any(
                path.endswith("ResolveEquipmentUI(Clone)/main/cancel_btn")
                for path in active_paths
            )
            preserve_visible = bool(
                self._active_retirement_texts(
                    ui_state,
                    "Msgbox(Clone)/window/msg_panel/content",
                    "不进行任何操作，所有装备会放入"
                    "<color=#5f984d>仓库</color>\n是否退出？",
                )
            )
            if equipment_visible or preserve_visible:
                # The stock client's equipment-resolution handoff is visibly
                # slower than recommendation/confirmation (and has exceeded
                # the five-second transaction window on the live client).
                # It is an already-confirmed order at this point, so wait for
                # its normal preservation exit rather than misclassifying the
                # completed enhancement as retryable.
                equipment_result = self._finish_enhancement_equipment_preservation(
                    timeout_seconds=max(timeout_seconds, 30.0)
                )
                completed = self.enhancement_preview()
                if completed.materials:
                    raise SemanticGateClosed(
                        "enhancement material slots remained populated"
                    )
                break
            self._sleep(0.05)
        if completed is None:
            raise SemanticGateClosed(
                "official enhancement result was not observed; do not retry"
            )
        observed_gain = result_gain(completed)
        if observed_gain is None:
            raise SemanticGateClosed(
                "enhancement attribute result does not match the preview"
            )
        if equipment_result is None:
            equipment_result = self._finish_enhancement_equipment_preservation(
                timeout_seconds=max(timeout_seconds, 30.0)
            )
        equipment_quantities, equipment_actions = equipment_result
        return EnhancementExecutionReceipt(
            target_name=completed.target_name,
            materials=selected.materials,
            attributes_before=selected.attributes,
            attributes_after=completed.attributes,
            confirmation=confirmation,
            equipment_quantities=equipment_quantities,
            equipment_actions=equipment_actions,
            equipment_preserved=True,
            generation_after=completed.generation,
        )

    def _finish_enhancement_equipment_preservation(
        self, timeout_seconds: float
    ) -> Tuple[Tuple[Tuple[int, int], ...], Tuple[ActionReceipt, ...]]:
        """Preserve every piece of equipment after material consumption."""

        deadline = self._monotonic() + timeout_seconds
        actions: List[ActionReceipt] = []
        quantities: Optional[Tuple[Tuple[int, int], ...]] = None
        clean_samples = 0
        awaiting_preserve_completion = False
        while self._monotonic() < deadline:
            state, ui_state = self._retirement_records()
            active_paths = tuple(
                item.path
                for item in state.buttons
                if item.active_in_hierarchy and item.active_and_enabled
            )
            preserve_message = self._active_retirement_texts(
                ui_state,
                "Msgbox(Clone)/window/msg_panel/content",
                "不进行任何操作，所有装备会放入<color=#5f984d>仓库</color>\n是否退出？",
            )
            if preserve_message:
                actions.append(
                    self._click_retirement_button(
                        "enhancement/equipment/preserve/confirm",
                        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
                        identity_text_suffix=("Msgbox(Clone)/window/msg_panel/content"),
                        identity_text=(
                            "不进行任何操作，所有装备会放入"
                            "<color=#5f984d>仓库</color>\n是否退出？"
                        ),
                    )
                )
                awaiting_preserve_completion = True
                clean_samples = 0
                self._sleep(0.2)
                continue
            if any("Msgbox(Clone)" in path for path in active_paths):
                raise SemanticGateClosed(
                    "unknown dialog interrupted enhancement equipment handling"
                )
            if awaiting_preserve_completion:
                # The resolve panel can remain reported for one observer
                # generation behind the preservation prompt.  Once its
                # affirmative exit is sent, only accept the settled
                # enhancement panel; do not issue a second cancellation.
                try:
                    preview = self.enhancement_preview()
                except SemanticGateClosed:
                    preview = None
                if preview is not None and not preview.materials:
                    clean_samples += 1
                    if clean_samples >= 3:
                        return quantities or (), tuple(actions)
                else:
                    clean_samples = 0
                self._sleep(0.2)
                continue
            if any(
                path.endswith("ResolveEquipmentUI(Clone)/main/cancel_btn")
                for path in active_paths
            ):
                equipment = self._retirement_equipment_state()
                if quantities is None:
                    quantities = equipment.item_quantities
                elif quantities != equipment.item_quantities:
                    raise SemanticGateClosed("enhancement equipment quantities changed")
                if equipment.selected_slots:
                    if not equipment.all_checked or set(equipment.selected_slots) != {
                        slot for slot, _ in equipment.item_quantities
                    }:
                        raise SemanticGateClosed(
                            "equipment preservation requires exact all-selection"
                        )
                    actions.append(
                        self._click_retirement_button(
                            "enhancement/equipment/deselect-all",
                            "ResolveEquipmentUI(Clone)/main/options/ALL",
                            identity_text_suffix=(
                                "ResolveEquipmentUI(Clone)/main/options/ALL/Label"
                            ),
                            identity_text="全部",
                        )
                    )
                else:
                    actions.append(
                        self._click_retirement_button(
                            "enhancement/equipment/cancel-disassembly",
                            "ResolveEquipmentUI(Clone)/main/cancel_btn",
                            identity_text_suffix=(
                                "ResolveEquipmentUI(Clone)/main/cancel_btn/Image"
                            ),
                            identity_text="取 消",
                        )
                    )
                    awaiting_preserve_completion = True
                clean_samples = 0
                self._sleep(0.2)
                continue
            try:
                preview = self.enhancement_preview()
            except SemanticGateClosed:
                preview = None
            if preview is not None and not preview.materials:
                clean_samples += 1
                if clean_samples >= 3:
                    return quantities or (), tuple(actions)
            else:
                clean_samples = 0
            self._sleep(0.2)
        raise SemanticGateClosed(
            "enhancement equipment preservation did not complete; do not retry"
        )
