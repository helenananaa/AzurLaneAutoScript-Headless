"""Awaken for the typed ALAS boundary."""

from __future__ import annotations

import re
import time
from typing import Dict, Optional, Tuple
from .contracts import (
    ActionReceipt,
    AwakenCostState,
    AwakenDetailState,
    AwakenExecutionReceipt,
    ButtonState,
    EnhancementDockCandidate,
    OracleState,
    Point,
    TextState,
    UiState,
)
from .errors import SemanticGateClosed


class AwakenOracle:
    """Awaken operations sharing the oracle frame and input boundary."""

    def set_awaken_dock_filter(
        self, use_array: bool
    ) -> Tuple[ActionReceipt, ...]:
        """Select the official cognitive-awakening Dock filter."""

        if not isinstance(use_array, bool):
            raise TypeError("awaken use_array must be boolean")
        state, ui_state = self._enhancement_dock_records()
        opener = next(
            item
            for item in ui_state.images
            if item.path.endswith("/adapt/top/index_button")
        )
        receipts = [
            self._click_exact_image(state, opener, "awaken/dock/filter/open")
        ]
        self._sleep(0.1)
        extra_option = "7" if use_array else "6"
        extra_label = (
            "<size=36>可认知觉醒</size><size=30>II</size>"
            if use_array
            else "<size=36>可认知觉醒</size>"
        )
        choices = (
            ("sort", "1", "等级", "btn_index_yellow"),
            ("index", "tpl", "全部", "btn_index_blue"),
            ("camp", "tpl", "全阵营", "btn_index_blue"),
            ("rarity", "tpl", "全部", "btn_index_blue"),
            ("extraindex", extra_option, extra_label, "btn_index_blue"),
        )
        for group, option, label, selected_sprite in choices:
            state, _, image = self._wait_enhancement_filter_option(
                group, option, label
            )
            if image.sprite == selected_sprite:
                continue
            if image.sprite != "btn_index_grey":
                raise SemanticGateClosed("awaken Dock filter state is unknown")
            receipts.append(
                self._click_exact_image(
                    state,
                    image,
                    "awaken/dock/filter/{0}/{1}".format(group, option),
                )
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
                        "awaken Dock filter selection became unknown"
                    )
            else:
                raise SemanticGateClosed("awaken Dock filter option did not select")
        state, ui_state = self._retirement_records()
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
            raise SemanticGateClosed("awaken Dock filter confirm is incomplete")
        receipts.append(
            self._click_exact_image(
                state, confirm[0], "awaken/dock/filter/confirm"
            )
        )
        empty_reads = 0
        expected_levels = {120} if use_array else {100, 105, 110, 115}
        for _ in range(80):
            self._sleep(0.1)
            candidates = self.awaken_dock_candidates()
            if candidates and all(
                item.level in expected_levels for item in candidates
            ):
                break
            if not candidates:
                empty_reads += 1
                if empty_reads >= 20:
                    break
            else:
                empty_reads = 0
        else:
            raise SemanticGateClosed(
                "awaken Dock filter results did not match the requested mode"
            )
        return tuple(receipts)

    def awaken_dock_candidates(self) -> Tuple[EnhancementDockCandidate, ...]:
        """Return exact visible cards admitted by the active Awaken filter."""

        return self.enhancement_dock_candidates()

    @staticmethod
    def _awaken_text(
        ui_state: UiState,
        suffix: str,
        *,
        pattern: Optional[str] = None,
        exact: Optional[str] = None,
    ) -> TextState:
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and (exact is None or item.text == exact)
            and (pattern is None or re.fullmatch(pattern, item.text) is not None)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("awaken text identity is incomplete")
        return matches[0]

    def _awaken_detail_state(
        self,
        ship_id: int,
        ship_name: str,
        *,
        expected_level: Optional[int] = None,
        require_entry: bool = True,
    ) -> AwakenDetailState:
        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("awaken detail snapshots are not coherent")
        name = self._awaken_text(
            ui_state,
            "/blur_panel/adapt/name/nameRect/name_mask/Text",
        )
        compact_name = ship_name.strip()
        if compact_name.endswith(".."):
            name_matches = name.text.startswith(compact_name[:-2])
        elif compact_name.endswith("…"):
            name_matches = name.text.startswith(compact_name[:-1])
        else:
            name_matches = name.text == compact_name
        if not name_matches:
            raise SemanticGateClosed("awaken detail ship identity changed")
        level_text = self._awaken_text(
            ui_state,
            "/ShipDetailView(Clone)/attrs/attrs/property/level_bg/level_label/Text",
            pattern=r"[1-9][0-9]{1,2}",
        )
        level = int(level_text.text)
        if expected_level is not None and level != expected_level:
            raise SemanticGateClosed("awaken detail level changed")
        exp = self._awaken_text(
            ui_state,
            "/ShipDetailView(Clone)/attrs/attrs/property/level_bg/exp_info",
            pattern=r"[0-9]+/(?:Max|[0-9]+)",
        )
        tip_path = (
            "/ShipDetailView(Clone)/attrs/attrs/property/level_bg/tip"
        )
        tips = tuple(
            item
            for item in ui_state.images
            if item.path.endswith(tip_path)
            and item.sprite == "renzhijuexing_icon"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.color[3] > 0.2
        )
        if require_entry and len(tips) != 1:
            raise SemanticGateClosed("awaken detail entry is incomplete")
        return AwakenDetailState(
            generation=max(state.generation, ui_state.generation),
            ship_id=ship_id,
            ship_name=name.text,
            level=level,
            exp_maxed=exp.text.endswith("/Max"),
            use_array=level >= 120,
        )

    def _close_awaken_help_if_present(self) -> Optional[ActionReceipt]:
        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(30):
            state = self.read_state()
            try:
                ui_state = self.read_ui_state()
                break
            except SemanticGateClosed as exc:
                last_error = exc
                if attempt < 29:
                    self._sleep(0.05)
        else:
            raise SemanticGateClosed(
                "awaken detail UI did not stabilize after Dock entry"
            ) from last_error
        help_images = tuple(
            item
            for item in ui_state.images
            if item.path.endswith("/Msgbox(Clone)/window/help_panel/list/help_tpl(Clone)/icon")
            and item.sprite == "maxlevel"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if not help_images:
            return None
        backgrounds = tuple(
            item
            for item in state.buttons
            if item.path.endswith("/Msgbox(Clone)/bg")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.bounds is not None
        )
        if len(help_images) != 1 or len(backgrounds) != 1:
            raise SemanticGateClosed("awaken help overlay is ambiguous")
        background = backgrounds[0]
        assert background.bounds is not None
        point = Point(
            background.bounds.left + 100.0,
            (background.bounds.top + background.bounds.bottom) / 2.0,
        )
        if not background.bounds.contains(point):
            raise SemanticGateClosed("awaken help close point is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before awaken help close")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="awaken/help/close",
            generation=state.generation,
            point=point,
            bounds=background.bounds,
            path=background.path,
        )

    def open_awaken_dock_candidate(
        self,
        position: int,
        ship_id: int,
        ship_name: str,
        level: int,
    ) -> Tuple[AwakenDetailState, Tuple[ActionReceipt, ...]]:
        """Open one stable Awaken Dock card and prove its detail identity."""

        candidates = self.awaken_dock_candidates()
        matches = tuple(
            item
            for item in candidates
            if item.position == position
            and item.ship_id == ship_id
            and item.ship_name == ship_name
            and item.level == level
        )
        if len(matches) != 1:
            raise SemanticGateClosed("awaken Dock candidate changed")
        target = matches[0].button
        assert target.point is not None and target.bounds is not None
        state = self.read_state()
        if self._blocking_rules(state, "awaken/dock/ship"):
            raise SemanticGateClosed("awaken Dock candidate input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before awaken ship input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        receipts = [
            ActionReceipt(
                semantic_id="awaken/dock/ship/{0}".format(ship_id),
                generation=state.generation,
                point=target.point,
                bounds=target.bounds,
                path=target.path,
            )
        ]
        self._sleep(0.5)
        help_receipt = self._close_awaken_help_if_present()
        if help_receipt is not None:
            receipts.append(help_receipt)
            self._sleep(0.5)
        detail = self._retry_transition_read(
            lambda: self._awaken_detail_state(
                ship_id, ship_name, expected_level=level
            ),
            attempts=40,
            interval_seconds=0.1,
        )
        return detail, tuple(receipts)

    def open_awaken_confirmation(
        self, detail: AwakenDetailState
    ) -> Tuple[AwakenCostState, ActionReceipt]:
        """Open and parse the official modal without committing resources."""

        if not isinstance(detail, AwakenDetailState):
            raise TypeError("awaken detail state is not typed")
        verified = self._awaken_detail_state(
            detail.ship_id,
            detail.ship_name,
            expected_level=detail.level,
        )
        state = self.read_state()
        ui_state = self.read_ui_state()
        tip_path = "/ShipDetailView(Clone)/attrs/attrs/property/level_bg/tip"
        tips = tuple(
            item
            for item in ui_state.images
            if item.path.endswith(tip_path)
            and item.sprite == "renzhijuexing_icon"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.bounds is not None
            and item.color[3] > 0.2
        )
        parents = tuple(
            item
            for item in state.buttons
            if item.path.endswith(
                "/ShipDetailView(Clone)/attrs/attrs/property/level_bg"
            )
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.bounds is not None
        )
        if len(tips) != 1 or len(parents) != 1:
            raise SemanticGateClosed("awaken entry target is incomplete")
        tip = tips[0]
        parent = parents[0]
        assert tip.bounds is not None and parent.bounds is not None
        point = Point(
            (tip.bounds.left + tip.bounds.right) / 2.0,
            (tip.bounds.top + tip.bounds.bottom) / 2.0,
        )
        if not parent.bounds.contains(point):
            raise SemanticGateClosed("awaken entry point escaped its parent")
        if self._blocking_rules(state, "awaken/detail/open"):
            raise SemanticGateClosed("awaken detail input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before awaken entry")
        self._tap(int(round(point.x)), int(round(point.y)))
        receipt = ActionReceipt(
            semantic_id="awaken/detail/open",
            generation=verified.generation,
            point=point,
            bounds=tip.bounds,
            path=tip.path,
        )
        cost = self._retry_transition_read(
            lambda: self.awaken_cost_state(
                detail.ship_id, detail.ship_name
            ),
            attempts=40,
            interval_seconds=0.1,
        )
        if cost.current_level != detail.level or cost.use_array != detail.use_array:
            raise SemanticGateClosed("awaken modal changed the requested mode")
        return cost, receipt

    def awaken_cost_state(self, ship_id: int, ship_name: str) -> AwakenCostState:
        """Read exact currencies and level transition from the open modal."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("awaken modal snapshots are not coherent")
        root = "OverlayCamera/Overlay/UIMain/ShipCustomMsgBox(Clone)"
        self._awaken_text(
            ui_state,
            root + "/frame/top/title_list/infomation/title",
            exact="认知觉醒",
        )
        transition = self._awaken_text(
            ui_state,
            root + "/frame/bg/item_panel/content_num",
            pattern=r"[0-9]{3}->[0-9]{3}",
        )
        current_level, target_level = (
            int(value) for value in transition.text.split("->", 1)
        )
        if target_level not in (105, 110, 115, 120, 125):
            raise SemanticGateClosed("awaken target level is unsupported")
        icon_root = root + "/frame/bg/item_panel/items/"
        icons = tuple(
            item
            for item in ui_state.images
            if item.path.startswith(icon_root)
            and item.path.endswith("/icon_bg/icon")
            and item.sprite in ("gold", "15008", "15012")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        counts = tuple(
            item
            for item in ui_state.texts
            if item.path.startswith(icon_root)
            and item.path.endswith("/icon_bg/count")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and re.fullmatch(
                r"<color=#[0-9A-Fa-f]{8}>[0-9]+</color>/[0-9]+",
                item.text,
            )
        )
        if len(icons) not in (2, 3) or len(counts) != len(icons):
            raise SemanticGateClosed("awaken resource rows are incomplete")
        resources: Dict[str, Tuple[int, int]] = {}
        for icon in icons:
            assert icon.bounds is not None
            center = (icon.bounds.left + icon.bounds.right) / 2.0
            aligned = tuple(
                item
                for item in counts
                if item.bounds is not None
                and abs(
                    (item.bounds.left + item.bounds.right) / 2.0 - center
                ) < 8.0
            )
            if len(aligned) != 1:
                raise SemanticGateClosed("awaken resource count is ambiguous")
            match = re.fullmatch(
                r"<color=#[0-9A-Fa-f]{8}>([0-9]+)</color>/([0-9]+)",
                aligned[0].text,
            )
            assert match is not None
            resources[icon.sprite] = (int(match.group(1)), int(match.group(2)))
        if set(resources) not in ({"gold", "15008"}, {"gold", "15008", "15012"}):
            raise SemanticGateClosed("awaken resource identity is incomplete")
        coins = resources["gold"]
        chips = resources["15008"]
        arrays = resources.get("15012")
        return AwakenCostState(
            generation=max(state.generation, ui_state.generation),
            ship_id=ship_id,
            ship_name=ship_name,
            current_level=current_level,
            target_level=target_level,
            coins_available=coins[0],
            coins_required=coins[1],
            chips_available=chips[0],
            chips_required=chips[1],
            arrays_available=arrays[0] if arrays is not None else None,
            arrays_required=arrays[1] if arrays is not None else None,
        )

    def _awaken_modal_button(
        self, semantic_id: str, name: str, label: str
    ) -> ActionReceipt:
        state = self.read_state()
        ui_state = self.read_ui_state()
        path = (
            "OverlayCamera/Overlay/UIMain/ShipCustomMsgBox(Clone)/frame/btns/"
            + name
        )
        buttons = tuple(
            item
            for item in state.buttons
            if item.path == path
            and item.name == name
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.point is not None
            and item.bounds is not None
            and item.bounds.contains(item.point)
        )
        labels = tuple(
            item
            for item in ui_state.texts
            if item.path == path + "/Image"
            and item.text == label
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(buttons) != 1 or len(labels) != 1:
            raise SemanticGateClosed(semantic_id + " is incomplete")
        target = buttons[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before awaken modal input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=max(state.generation, ui_state.generation),
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _same_awaken_cost(left: AwakenCostState, right: AwakenCostState) -> bool:
        return (
            left.ship_id,
            left.ship_name,
            left.current_level,
            left.target_level,
            left.coins_available,
            left.coins_required,
            left.chips_available,
            left.chips_required,
            left.arrays_available,
            left.arrays_required,
        ) == (
            right.ship_id,
            right.ship_name,
            right.current_level,
            right.target_level,
            right.coins_available,
            right.coins_required,
            right.chips_available,
            right.chips_required,
            right.arrays_available,
            right.arrays_required,
        )

    def cancel_awaken_confirmation(
        self, cost: AwakenCostState
    ) -> ActionReceipt:
        if not isinstance(cost, AwakenCostState):
            raise TypeError("awaken cost state is not typed")
        current = self.awaken_cost_state(cost.ship_id, cost.ship_name)
        if not self._same_awaken_cost(current, cost):
            raise SemanticGateClosed("awaken cost changed before cancellation")
        receipt = self._awaken_modal_button(
            "awaken/confirm/cancel", "cancel_btn", "取 消"
        )
        self._retry_transition_read(
            lambda: self._awaken_detail_state(
                cost.ship_id,
                cost.ship_name,
                expected_level=cost.current_level,
            ),
            attempts=30,
            interval_seconds=0.1,
        )
        return receipt

    def commit_awaken_confirmation(
        self, cost: AwakenCostState
    ) -> AwakenExecutionReceipt:
        """Commit one sufficient modal and prove the target level afterward."""

        if not isinstance(cost, AwakenCostState):
            raise TypeError("awaken cost state is not typed")
        current = self.awaken_cost_state(cost.ship_id, cost.ship_name)
        if not self._same_awaken_cost(current, cost):
            raise SemanticGateClosed("awaken cost changed before confirmation")
        if not current.sufficient:
            raise SemanticGateClosed("awaken resources are insufficient")
        actions = [
            self._awaken_modal_button(
                "awaken/confirm/commit", "confirm_btn", "确 定"
            )
        ]
        completion_state: Optional[OracleState] = None
        completion_button: Optional[ButtonState] = None
        deadline = time.monotonic() + 35.0
        expected_text = (
            "认知觉醒完成\n等级上限提升为"
            "<color=#92fc63FF>{0}</color>".format(cost.target_level)
        )
        while time.monotonic() < deadline:
            state = self.read_state()
            ui_state = self.read_ui_state()
            messages = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith("/AwakenCompleteWindows(Clone)/window/desc")
                and item.text == expected_text
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            buttons = tuple(
                item
                for item in state.buttons
                if item.path.endswith("/AwakenCompleteWindows(Clone)")
                and item.name == "AwakenCompleteWindows(Clone)"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
                and item.point is not None
                and item.bounds is not None
                and item.bounds.contains(item.point)
            )
            if len(messages) == 1 and len(buttons) == 1:
                completion_state = state
                completion_button = buttons[0]
                break
            self._sleep(0.1)
        if completion_state is None or completion_button is None:
            raise SemanticGateClosed("awaken completion was not observed")
        assert completion_button.point is not None
        assert completion_button.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before awaken completion")
        self._tap(
            int(round(completion_button.point.x)),
            int(round(completion_button.point.y)),
        )
        actions.append(
            ActionReceipt(
                semantic_id="awaken/completion/close",
                generation=completion_state.generation,
                point=completion_button.point,
                bounds=completion_button.bounds,
                path=completion_button.path,
            )
        )
        after = self._retry_transition_read(
            lambda: self._awaken_detail_state(
                cost.ship_id,
                cost.ship_name,
                require_entry=False,
            ),
            attempts=50,
            interval_seconds=0.1,
        )
        if not cost.current_level <= after.level <= cost.target_level:
            raise SemanticGateClosed("awaken post-level is outside the new cap")
        return AwakenExecutionReceipt(
            ship_id=cost.ship_id,
            ship_name=after.ship_name,
            current_level=cost.current_level,
            target_level=cost.target_level,
            observed_level=after.level,
            cost=cost,
            actions=tuple(actions),
        )

    def return_from_awaken_detail_to_dock(self) -> ActionReceipt:
        """Leave the ship detail and prove the filtered Dock returns."""

        receipt: Optional[ActionReceipt] = None
        for _ in range(8):
            state = self.read_state()
            targets = tuple(
                item
                for item in state.buttons
                if item.path.endswith("/blur_panel/adapt/top/back_btn")
                and item.name == "back_btn"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
                and item.point is not None
                and item.bounds is not None
                and item.bounds.contains(item.point)
            )
            if len(targets) != 1:
                raise SemanticGateClosed("awaken detail back control is incomplete")
            target = targets[0]
            assert target.point is not None and target.bounds is not None
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed("game activity changed before awaken detail back")
            self._tap(int(round(target.point.x)), int(round(target.point.y)))
            receipt = ActionReceipt(
                semantic_id="awaken/detail/back",
                generation=state.generation,
                point=target.point,
                bounds=target.bounds,
                path=target.path,
            )
            try:
                self._retry_transition_read(
                    self._enhancement_dock_records,
                    attempts=20,
                    interval_seconds=0.1,
                )
                return receipt
            except SemanticGateClosed:
                self._sleep(0.5)
        assert receipt is not None
        raise SemanticGateClosed("awaken detail back did not restore Dock")

    def return_from_awaken_dock_to_main(self) -> ActionReceipt:
        """Leave the official Dock through its exact top-left control."""

        state, _ = self._enhancement_dock_records()
        targets = tuple(
            item
            for item in state.buttons
            if item.path.endswith("/blur_panel/adapt/top/back")
            and item.name == "back"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.point is not None
            and item.bounds is not None
            and item.bounds.contains(item.point)
        )
        if len(targets) != 1:
            raise SemanticGateClosed("awaken Dock back control is incomplete")
        target = targets[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before awaken Dock back")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        receipt = ActionReceipt(
            semantic_id="awaken/dock/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

        def require_main() -> bool:
            if not self.main_page_visible():
                raise SemanticGateClosed(
                    "main page is not visible after awaken Dock back"
                )
            return True

        self._retry_transition_read(
            require_main,
            attempts=50,
            interval_seconds=0.1,
        )
        return receipt
