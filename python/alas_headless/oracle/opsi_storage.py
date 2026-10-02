"""Opsi storage for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
from .contracts import (
    ActionReceipt,
    Bounds,
    ButtonState,
    OperationSirenStorageItemState,
    OperationSirenStorageScrollReceipt,
    OperationSirenStorageState,
    Point,
)
from .errors import SemanticGateClosed, SemanticTargetMissing


class OpsiStorageOracle:
    """Opsi storage operations sharing the oracle frame and input boundary."""

    def operation_siren_storage_loggers_absent(self) -> bool:
        """Prove the complete current inventory contains only reviewed non-loggers."""

        state = self.read_state()
        back = self._unique(state, "os/storage/back")
        if not (back.active_in_hierarchy and back.active_and_enabled):
            raise SemanticGateClosed("operation siren storage identity is absent")
        ui = self.read_ui_state()
        if (not state.generation <= ui.generation <= state.generation + 2
                or ui.skipped_count):
            raise SemanticGateClosed("operation siren inventory is incomplete")
        root = "OverlayCamera/Overlay/UIMain/WorldInventoryUI(Clone)/adapt/item_scrollview/Viewport/item_grid/"
        ids = [int(match.group(1)) for button in state.buttons
               if (match := re.fullmatch(re.escape(root) + r"([0-9]+)", button.path))]
        if not ids or len(ids) != len(set(ids)):
            raise SemanticGateClosed("operation siren inventory cards are absent or ambiguous")
        nonlogger_sprites = {
            "jingtidianchi", "Wdashijiezhaungbeibi", "Wdashijiehuobi",
            "Wshengminghuifu1", "Wshengminghuifu2", "Wshengminghuifu3",
            "Wshengminghuifu4", "Wshengminghuifu5", "Wxingdonglihuifu1",
            "Wxingdonglihuifu2", "Wxingdonglihuifu3",
            "Wyangben1", "Wyangben2", "Wyangben3", "Wyangben4",
            "Wyangben5", "Wyangben6",
        }
        for item_id in ids:
            path = root + str(item_id) + "/bg/icon_bg/icon"
            icons = [image for image in ui.images if image.path == path
                     and image.active_in_hierarchy and image.active_and_enabled
                     and not image.truncated]
            if len(icons) != 1:
                raise SemanticGateClosed("operation siren inventory icon is missing or ambiguous")
            if icons[0].sprite not in nonlogger_sprites:
                # Activated obscure coordinates belong to coordinate checkout,
                # not the original logger activation flow. Require the same
                # typed name identity used by operation_siren_storage_state;
                # the sprite alone must not admit an unopened logger.
                if icons[0].sprite == "Wluopanjihuo2":
                    names = [text for text in ui.texts
                             if text.path == root + str(item_id) + "/bg/name"
                             and text.active_in_hierarchy and text.active_and_enabled
                             and not text.truncated and text.bounds is not None]
                    if (len(names) == 1 and re.sub(r"<[^>]*>", "", names[0].text)
                            .strip().startswith("海域坐标:")):
                        continue
                raise SemanticGateClosed("operation siren logger inventory requires typed use support")
        return True

    def operation_siren_storage_visible(self) -> bool:
        """Recognize the Operation Siren inventory by its exact page back control."""

        try:
            state = self.read_state()
            back = self._unique(state, "os/storage/back")
        except (SemanticGateClosed, SemanticTargetMissing):
            return False
        return bool(
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.bounds is not None
        )

    def operation_siren_sample_buttons(self, template_name):
        from ..opsi_monthstart import sample_buttons
        return sample_buttons(self, template_name)

    def click_operation_siren_sample(self, selected):
        from ..opsi_monthstart import select_sample
        return select_sample(self, selected)

    def operation_siren_storage_state(self) -> OperationSirenStorageState:
        """Read visible coordinate records from the typed inventory hierarchy."""

        button_state = self.read_state()
        back = self._unique(button_state, "os/storage/back")
        if not (
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.bounds is not None
        ):
            raise SemanticGateClosed("operation siren storage identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "operation siren storage snapshots are not coherent"
            )

        suffix = "/WorldInventoryUI(Clone)/adapt/item_scrollview/Viewport/item_grid/"
        item_buttons: Dict[int, ButtonState] = {}
        for button in button_state.buttons:
            match = re.search(re.escape(suffix) + r"([0-9]+)$", button.path)
            if match is None:
                continue
            item_id = int(match.group(1))
            if item_id in item_buttons:
                raise SemanticGateClosed("operation siren storage item is ambiguous")
            item_buttons[item_id] = button

        items = []
        for item_id, button in sorted(item_buttons.items()):
            root = button.path + "/bg/"
            names = tuple(
                text
                for text in ui_state.texts
                if text.path == root + "name"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            counts = tuple(
                text
                for text in ui_state.texts
                if text.path == root + "icon_bg/count"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(names) != 1 or len(counts) != 1:
                raise SemanticGateClosed(
                    "operation siren storage item text is incomplete"
                )
            display_name = re.sub(r"<[^>]*>", "", names[0].text).strip()
            count_text = counts[0].text.strip()
            sample_types = {
                301: ("SAMPLE_OFFENSE", "Wyangben1"),
                302: ("SAMPLE_SURVIVAL", "Wyangben3"),
                303: ("SAMPLE_COMBAT", "Wyangben5"),
                304: ("SAMPLE_QUALITY_OFFENSE", "Wyangben2"),
                305: ("SAMPLE_QUALITY_SURVIVAL", "Wyangben4"),
                306: ("SAMPLE_QUALITY_COMBAT", "Wyangben6"),
            }
            if item_id in sample_types:
                item_type, expected_sprite = sample_types[item_id]
                icons = tuple(
                    image
                    for image in ui_state.images
                    if image.path == root + "icon_bg/icon"
                    and image.active_in_hierarchy
                    and image.active_and_enabled
                    and not image.truncated
                    and image.bounds is not None
                )
                if len(icons) != 1 or icons[0].sprite != expected_sprite:
                    raise SemanticGateClosed(
                        "operation siren tuning sample identity changed"
                    )
            elif display_name.startswith("海域坐标:"):
                item_type = "OBSCURE"
            elif display_name.startswith("塞壬坐标:"):
                item_type = "ABYSSAL"
            else:
                # Other inventory objects belong to logger flows and
                # must not be inferred as a coordinate from their numeric id.
                continue
            if re.fullmatch(r"[1-9][0-9]*", count_text) is None:
                raise SemanticGateClosed(
                    "operation siren coordinate count is malformed"
                )
            bounds = button.bounds
            if bounds is None:
                raise SemanticGateClosed("operation siren coordinate bounds are absent")
            actionable = bool(
                button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.point is not None
                and bounds.contains(button.point)
                and 0 <= button.point.x < self.fingerprint.width
                and 0 <= button.point.y < self.fingerprint.height
                and 80 <= bounds.top < bounds.bottom <= 602
                and 0 <= bounds.left < bounds.right <= 1230
                and not self._blocking_rules(button_state, "os/storage/back")
            )
            items.append(
                OperationSirenStorageItemState(
                    generation=button_state.generation,
                    item_id=item_id,
                    item_type=item_type,
                    display_name=display_name,
                    count=int(count_text),
                    bounds=bounds,
                    actionable=actionable,
                )
            )
        return OperationSirenStorageState(
            generation=button_state.generation,
            items=tuple(items),
        )

    def click_operation_siren_storage_item(self, item_type: str) -> ActionReceipt:
        """Select one fully visible coordinate card without confirming its use."""

        if item_type not in ("OBSCURE", "ABYSSAL"):
            raise ValueError("operation siren storage item type is invalid")
        storage = self.operation_siren_storage_state()
        candidates = tuple(
            item
            for item in storage.items
            if item.item_type == item_type and item.actionable
        )
        if not candidates:
            raise SemanticTargetMissing(
                "actionable operation siren coordinate is absent: " + item_type
            )
        selected = candidates[0]
        state = self.read_state()
        path_suffix = (
            "/WorldInventoryUI(Clone)/adapt/item_scrollview/Viewport/"
            "item_grid/" + str(selected.item_id)
        )
        matches = tuple(
            button for button in state.buttons if button.path.endswith(path_suffix)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("operation siren coordinate changed before input")
        button = matches[0]
        if button.bounds is None or button.point is None:
            raise SemanticGateClosed("operation siren coordinate geometry disappeared")
        if not (
            button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds.contains(button.point)
            and 80 <= button.bounds.top < button.bounds.bottom <= 602
            and 0 <= button.bounds.left < button.bounds.right <= 1230
        ):
            raise SemanticGateClosed(
                "operation siren coordinate is no longer actionable"
            )
        visible = Bounds(
            max(0.0, button.bounds.left),
            max(0.0, button.bounds.top),
            min(float(self.fingerprint.width), button.bounds.right),
            min(float(self.fingerprint.height), button.bounds.bottom),
        )
        if visible.left >= visible.right or visible.top >= visible.bottom:
            raise SemanticGateClosed("operation siren coordinate is outside the screen")
        point = Point(
            (visible.left + visible.right) / 2.0,
            (visible.top + visible.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/storage/item/" + item_type.lower(),
            generation=state.generation,
            point=point,
            bounds=button.bounds,
            path=button.path,
        )

    def operation_siren_storage_scroll_for_abyssal(
        self, timeout_seconds: float = 5.0
    ) -> OperationSirenStorageScrollReceipt:
        """Move the inventory viewport until an abyssal coordinate is fully visible."""

        if self._swipe is None:
            raise SemanticGateClosed("operation siren storage swipe backend is absent")
        before = self.operation_siren_storage_state()
        if any(
            item.item_type == "ABYSSAL" and item.actionable for item in before.items
        ):
            raise SemanticGateClosed(
                "operation siren abyssal coordinate already actionable"
            )
        if not any(item.item_type == "ABYSSAL" for item in before.items):
            raise SemanticTargetMissing("operation siren abyssal coordinate is absent")
        start = (640, 560)
        end = (640, 260)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before storage scroll")
        self._swipe(start[0], start[1], end[0], end[1], 450)
        deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < deadline:
            self._sleep(0.25)
            after = self.operation_siren_storage_state()
            actionable = tuple(
                item
                for item in after.items
                if item.item_type == "ABYSSAL" and item.actionable
            )
            if after.generation > before.generation and actionable:
                return OperationSirenStorageScrollReceipt(
                    semantic_id="os/storage/scroll/abyssal",
                    pre_generation=before.generation,
                    post_generation=after.generation,
                    start=start,
                    end=end,
                    visible_abyssal_count=len(actionable),
                )
        raise SemanticGateClosed("operation siren storage scroll was not proven")

    def click_operation_siren_storage_back(self) -> ActionReceipt:
        """Leave the proven Operation Siren inventory through its exact back control."""

        if not self.operation_siren_storage_visible():
            raise SemanticGateClosed("operation siren storage identity is absent")
        state = self.read_state()
        target = self._unique(state, "os/storage/back")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "os/storage/back")
        ):
            raise SemanticGateClosed("operation siren storage back is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/storage/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def operation_siren_storage_detail(self) -> Optional[Tuple[str, str, int]]:
        """Return the selected coordinate detail without authorizing checkout."""

        state = self.read_state()
        close_matches = self._matches(state, "os/storage/detail/close")
        checkout_matches = self._matches(state, "os/storage/detail/checkout")
        if not close_matches and not checkout_matches:
            return None
        if len(close_matches) != 1 or len(checkout_matches) != 1:
            raise SemanticGateClosed("operation siren storage detail is ambiguous")
        for target in (close_matches[0], checkout_matches[0]):
            if not (
                target.active_in_hierarchy
                and target.active_and_enabled
                and target.interactable
                and target.point is not None
                and target.bounds is not None
                and target.bounds.contains(target.point)
            ):
                raise SemanticGateClosed(
                    "operation siren storage detail is not actionable"
                )
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed(
                "operation siren storage detail snapshots are not coherent"
            )

        def exact_text(suffix: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "operation siren storage detail text is incomplete"
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        name = exact_text(
            "item_usage_panel/window/item/display_panel/name_container/name/Text"
        )
        description = exact_text("item_usage_panel/window/item/display_panel/desc/Text")
        count = exact_text("item_usage_panel/window/item/left/IconTpl/icon_bg/count")
        if not (
            name.startswith(("海域坐标:", "塞壬坐标:"))
            and description
            and re.fullmatch(r"[1-9][0-9]*", count)
        ):
            raise SemanticGateClosed("operation siren storage detail is malformed")
        return name, description, int(count)

    def click_operation_siren_storage_detail_close(self) -> ActionReceipt:
        """Close the proven coordinate detail without consuming its item."""

        if self.operation_siren_storage_detail() is None:
            raise SemanticGateClosed("operation siren storage detail is absent")
        state = self.read_state()
        target = self._unique(state, "os/storage/detail/close")
        assert target.point is not None and target.bounds is not None
        if self._blocking_rules(state, "os/storage/detail/close"):
            raise SemanticGateClosed("operation siren storage detail close is blocked")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/storage/detail/close",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_storage_detail_checkout(self) -> ActionReceipt:
        """Commit the selected coordinate through its exact blue checkout button."""

        if self.operation_siren_storage_detail() is None:
            raise SemanticGateClosed("operation siren storage detail is absent")
        state = self.read_state()
        target = self._unique(state, "os/storage/detail/checkout")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.bounds is not None
            and not self._blocking_rules(state, "os/storage/detail/checkout")
        ):
            raise SemanticGateClosed(
                "operation siren storage checkout is not actionable"
            )
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/storage/detail/checkout",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )
