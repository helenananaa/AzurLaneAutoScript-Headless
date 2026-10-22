"""Opsi shop for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    OperationSirenShopItemState,
    OperationSirenVoucherItemState,
    Point,
)
from .errors import SemanticGateClosed


class OpsiShopOracle:
    """Opsi shop operations sharing the oracle frame and input boundary."""

    @staticmethod
    def _canonical_operation_siren_shop_name(
        display_name: str, icon_sprite: str
    ) -> str:
        names = {
            "超空泡发生器": "SupercavitationGenerator",
            "可塑性机械臂": "NeuroplasticProstheticArm",
            "纳米陶铝合金": "NanoceramicAlloy",
            "结晶化热强钢": "CrystallizedHeatResistantSteel",
        }
        sprite_names = {
            "Wdashijiezhaungbeibi": "PurpleCoins",
            "Wsucaixiang1": "DevelopmentMaterialT1",
            "Wsucaixiang2": "DevelopmentMaterialT2",
            "Wsucaixiang3": "DevelopmentMaterialT3",
            "Wxingdonglihuifu1": "ActionPoint20",
            "Wxingdonglihuifu2": "ActionPoint50",
            "Wxingdonglihuifu3": "ActionPoint100",
        }
        if icon_sprite in sprite_names:
            return sprite_names[icon_sprite]
        if display_name in names:
            return names[display_name]
        if display_name.startswith("META通用战术") and icon_sprite in (
            "16031",
            "16032",
        ):
            return "METARedBook"
        raise SemanticGateClosed("Operation Siren shop item name is unknown")

    def operation_siren_shop_items(
        self,
    ) -> Tuple[OperationSirenShopItemState, ...]:
        """Read the post-2026 unified four-port exchange page."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("Operation Siren shop snapshots are not coherent")
        root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/new_shop/"
        currency_names = tuple(
            text
            for text in ui_state.texts
            if text.path == root + "frame/content/right/page/title/res/icon/name"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.text.strip() == "特别兑换凭证"
        )
        currency_values = tuple(
            text
            for text in ui_state.texts
            if text.path == root + "frame/content/right/page/title/res/Text"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[0-9]+", text.text.strip())
        )
        ports = sorted(
            text.text.strip()
            for text in ui_state.texts
            if text.path.startswith(root + "frame/content/left/port_tpl")
            and text.path.endswith("/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if (
            len(currency_names) != 1
            or len(currency_values) != 1
            or ports != sorted(("NY", "利维浦", "圣彼得伯格", "直布罗特"))
        ):
            raise SemanticGateClosed(
                "unified Operation Siren shop identity is not proven"
            )

        anchors = {}
        for button in state.buttons:
            if not (
                button.path.startswith(root)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
                and (
                    (
                        button.name in ("item_tpl", "item_tpl(Clone)")
                        and "/container/item_tpl" in button.path
                    )
                    or (
                        button.name == "mask"
                        and "/container/item_tpl" in button.path
                        and button.path.endswith("/mask")
                    )
                )
            ):
                continue
            anchors.setdefault(button.bounds, button)
        cards = sorted(
            anchors.values(), key=lambda button: (button.bounds.top, button.bounds.left)
        )
        if not 4 <= len(cards) <= 20:
            raise SemanticGateClosed(
                "unified Operation Siren shop card count is outside 4..20"
            )

        def centered_text(card: ButtonState, suffix: str, pattern: str) -> str:
            assert card.bounds is not None
            matches = []
            for text in ui_state.texts:
                if (
                    not text.path.endswith(suffix)
                    or not text.active_in_hierarchy
                    or not text.active_and_enabled
                    or text.truncated
                    or text.bounds is None
                    or re.fullmatch(pattern, text.text.strip()) is None
                ):
                    continue
                x = (text.bounds.left + text.bounds.right) / 2.0
                y = (text.bounds.top + text.bounds.bottom) / 2.0
                if (
                    card.bounds.left <= x <= card.bounds.right
                    and card.bounds.top <= y <= card.bounds.bottom + 30.0
                ):
                    matches.append(text.text.strip())
            if len(matches) != 1:
                raise SemanticGateClosed("Operation Siren shop card text is ambiguous")
            return matches[0]

        def centered_icon(card: ButtonState, suffix: str) -> str:
            assert card.bounds is not None
            matches = []
            for image in ui_state.images:
                if (
                    not image.path.endswith(suffix)
                    or not image.active_in_hierarchy
                    or not image.active_and_enabled
                    or image.truncated
                    or image.bounds is None
                ):
                    continue
                x = (image.bounds.left + image.bounds.right) / 2.0
                y = (image.bounds.top + image.bounds.bottom) / 2.0
                if card.bounds.contains(Point(x=x, y=y)):
                    matches.append(image.sprite)
            if len(matches) != 1:
                raise SemanticGateClosed("Operation Siren shop card icon is ambiguous")
            return matches[0]

        result = []
        for index, card in enumerate(cards):
            display_name = centered_text(card, "/name_mask/name", r".+")
            amount = int(centered_text(card, "/IconTpl/icon_bg/count", r"[0-9]+"))
            price = int(centered_text(card, "/consume/contain/Text", r"[0-9]+"))
            counter = centered_text(card, "/count_contain/count", r"[0-9]+/[0-9]+")
            remaining, total = map(int, counter.split("/"))
            if remaining > total:
                raise SemanticGateClosed("Operation Siren shop counter is inconsistent")
            currency_sprite = centered_icon(card, "/consume/contain/icon")
            currency_names = {
                "Wdashijiezhaungbeibi": "SpecialExchangeTicket",
                "Wdashijiehuobi": "YellowCoins",
            }
            if currency_sprite not in currency_names:
                raise SemanticGateClosed("Operation Siren shop currency is unknown")
            icon_sprite = centered_icon(card, "/IconTpl/icon_bg/icon")
            result.append(
                OperationSirenShopItemState(
                    generation=ui_state.generation,
                    index=index,
                    display_name=display_name,
                    canonical_name=self._canonical_operation_siren_shop_name(
                        display_name, icon_sprite
                    ),
                    amount=amount,
                    remaining=remaining,
                    total=total,
                    price=price,
                    currency=currency_names[currency_sprite],
                    icon_sprite=icon_sprite,
                    bounds=card.bounds,
                )
            )
        return tuple(result)

    def operation_siren_shop_currency(self) -> int:
        self._retry_transition_read(
            self.operation_siren_shop_items,
            attempts=8,
            interval_seconds=0.2,
        )
        ui_state = self.read_ui_state()
        matches = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("new_shop/frame/content/right/page/title/res/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[0-9]+", text.text.strip())
        )
        if len(matches) != 1:
            raise SemanticGateClosed("Operation Siren shop currency is ambiguous")
        return int(matches[0].text.strip())

    def click_operation_siren_shop_item(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
    ) -> ActionReceipt:
        """Open one exact item on the unified Operation Siren exchange page."""

        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 20:
            raise SemanticGateClosed("Operation Siren shop item index is invalid")
        items = self._retry_transition_read(
            self.operation_siren_shop_items,
            attempts=8,
            interval_seconds=0.2,
        )
        item = next((candidate for candidate in items if candidate.index == index), None)
        if item is None or item.bounds is None:
            raise SemanticGateClosed("Operation Siren shop item is absent")
        if item.canonical_name != expected_name or item.price != expected_price:
            raise SemanticGateClosed("Operation Siren shop item identity changed")
        if item.remaining <= 0:
            raise SemanticGateClosed("Operation Siren shop item is sold out")

        state = self.read_state()
        root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/new_shop/"
        controls = tuple(
            button
            for button in state.buttons
            if button.path.startswith(root)
            and button.name in ("item_tpl", "item_tpl(Clone)")
            and "/container/item_tpl" in button.path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds == item.bounds
        )
        if len(controls) != 1:
            raise SemanticGateClosed(
                "Operation Siren shop item control is absent or ambiguous"
            )
        bounds = item.bounds
        point = Point(
            x=(bounds.left + bounds.right) / 2,
            y=(bounds.top + bounds.bottom) / 2,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=f"os/shop/item/{index}/{expected_name}",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=controls[0].path,
        )

    @staticmethod
    def _canonical_operation_siren_voucher_name(icon_sprite: str) -> str:
        fixed = {
            "xinxizhongduan4": "LoggerUnlockT2",
            "tebiezuozhan": "HECombatPlan",
            "W120": "HiddenZoneDataLogger",
            "gold": "Coin",
            "16004": "BookRedT4",
            "16014": "BookBlueT4",
            "16024": "BookYellowT4",
            "21000": "Fragment",
            "Wluopanputong5": "LoggerObscureT5",
            "Wluopanputong6": "LoggerObscureT6",
            "Wsairenluopanputong5": "LoggerAbyssalT5",
            "Wsairenluopanputong6": "LoggerAbyssalT6",
            "Wyangben2": "TuningOffenseT2",
            "Wyangben4": "TuningSurvivalT2",
            "Wyangben6": "TuningCombatT2",
        }
        if icon_sprite in fixed:
            return fixed[icon_sprite]
        archive = re.fullmatch(r"Wdanganluopan([2-9])", icon_sprite)
        if archive is not None:
            return "LoggerArchiveT" + archive.group(1)
        raise SemanticGateClosed("Operation Siren voucher item icon is unknown")

    def operation_siren_voucher_items(
        self,
    ) -> Tuple[OperationSirenVoucherItemState, ...]:
        """Read the current WorldShopUI voucher catalog without scrolling."""

        state = self.read_state()
        back = self._unique(state, "os/voucher/back")
        if not (
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.interactable
            and back.raycast_top is None
            and back.bounds is not None
        ):
            raise SemanticGateClosed("Operation Siren voucher identity is absent")
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed(
                "Operation Siren voucher snapshots are not coherent"
            )
        root = "OverlayCamera/Overlay/UIMain/WorldShopUI(Clone)/"
        balance = tuple(
            text
            for text in ui_state.texts
            if text.path == root + "adapt/middle/content/res/number"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[0-9]+", text.text.strip())
        )
        currency_icons = tuple(
            image
            for image in ui_state.images
            if image.path == root + "adapt/middle/content/res/icon"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.sprite == "Wdashijiezhanbeiwuzi"
        )
        reset_days = tuple(
            text
            for text in ui_state.texts
            if text.path == root + "adapt/middle/content/resetTimer/number"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[0-9]+", text.text.strip())
        )
        if len(balance) != 1 or len(currency_icons) != 1 or len(reset_days) != 1:
            raise SemanticGateClosed("Operation Siren voucher header is malformed")

        card_root = root + "adapt/middle/content/world_shop/content/"
        cards = sorted(
            (
                button
                for button in state.buttons
                if button.path.startswith(card_root)
                and button.name in ("item_tpl", "item_tpl(Clone)")
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.bounds is not None
            ),
            key=lambda button: (button.bounds.top, button.bounds.left),
        )
        if not cards:
            raise SemanticGateClosed("Operation Siren voucher has no identifiable cards")

        def card_text(card: ButtonState, suffix: str, pattern: str) -> str:
            assert card.bounds is not None
            matches = []
            for text in ui_state.texts:
                if (
                    not text.path.startswith(card_root)
                    or not text.path.endswith(suffix)
                    or not text.active_in_hierarchy
                    or not text.active_and_enabled
                    or text.truncated
                    or text.bounds is None
                    or re.fullmatch(pattern, text.text.strip()) is None
                ):
                    continue
                point = Point(
                    (text.bounds.left + text.bounds.right) / 2.0,
                    (text.bounds.top + text.bounds.bottom) / 2.0,
                )
                if (
                    card.bounds.left <= point.x <= card.bounds.right
                    and card.bounds.top - 20.0 <= point.y <= card.bounds.bottom + 30.0
                ):
                    matches.append(text.text.strip())
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "Operation Siren voucher card text is ambiguous"
                )
            return matches[0]

        def card_image(card: ButtonState, suffix: str) -> str:
            assert card.bounds is not None
            matches = []
            for image in ui_state.images:
                if (
                    not image.path.startswith(card_root)
                    or not image.path.endswith(suffix)
                    or not image.active_in_hierarchy
                    or not image.active_and_enabled
                    or image.truncated
                    or image.bounds is None
                ):
                    continue
                point = Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                )
                if (
                    card.bounds.left <= point.x <= card.bounds.right
                    and card.bounds.top - 20.0 <= point.y <= card.bounds.bottom + 30.0
                ):
                    matches.append(image.sprite)
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "Operation Siren voucher card icon is ambiguous"
                )
            return matches[0]

        items = []
        for index, card in enumerate(cards):
            display_name = card_text(card, "/name_mask/name", r".+")
            amount = int(card_text(card, "/icon_bg/count", r"[0-9]+"))
            counter = card_text(card, "/count_contain/count", r"[0-9]+/[0-9]+")
            remaining, total = map(int, counter.split("/"))
            price = int(card_text(card, "/consume/contain/Text", r"[0-9]+"))
            icon = card_image(card, "/icon_bg/icon")
            cost_icon = card_image(card, "/consume/contain/icon")
            currency = (
                "Oil"
                if cost_icon == "oil"
                else "Voucher"
                if cost_icon == "Wdashijiezhanbeiwuzi"
                else ""
            )
            if not currency or remaining > total:
                raise SemanticGateClosed("Operation Siren voucher card is inconsistent")
            sold_out = remaining == 0
            sellout = tuple(
                text
                for text in ui_state.texts
                if text.path.startswith(card_root)
                and text.path.endswith("/mask/tag/sellout_tag")
                and text.active_in_hierarchy
                and text.bounds is not None
                and text.text.strip() == "已售罄"
                and card.bounds.left
                <= (text.bounds.left + text.bounds.right) / 2.0
                <= card.bounds.right
                and card.bounds.top - 20.0
                <= (text.bounds.top + text.bounds.bottom) / 2.0
                <= card.bounds.bottom + 30.0
            )
            if sold_out != (len(sellout) == 1):
                raise SemanticGateClosed(
                    "Operation Siren voucher sellout state conflicts"
                )
            items.append(
                OperationSirenVoucherItemState(
                    generation=ui_state.generation,
                    index=index,
                    display_name=display_name,
                    canonical_name=self._canonical_operation_siren_voucher_name(icon),
                    amount=amount,
                    remaining=remaining,
                    total=total,
                    price=price,
                    currency=currency,
                    icon_sprite=icon,
                    sold_out=sold_out,
                    bounds=card.bounds,
                )
            )
        return tuple(items)

    def operation_siren_voucher_currency(self) -> int:
        self.operation_siren_voucher_items()
        ui_state = self.read_ui_state()
        matches = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("WorldShopUI(Clone)/adapt/middle/content/res/number")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[0-9]+", text.text.strip())
        )
        if len(matches) != 1:
            raise SemanticGateClosed("Operation Siren voucher balance is ambiguous")
        return int(matches[0].text.strip())

    def click_operation_siren_voucher_item(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
        expected_currency: str,
    ) -> ActionReceipt:
        """Open one exact, visible Operation Siren voucher card."""

        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise SemanticGateClosed("Operation Siren voucher item index is invalid")
        items = self._retry_transition_read(
            self.operation_siren_voucher_items,
            attempts=8,
            interval_seconds=0.2,
        )
        item = next((candidate for candidate in items if candidate.index == index), None)
        if item is None or item.bounds is None:
            raise SemanticGateClosed("Operation Siren voucher item is absent")
        if (
            item.canonical_name != expected_name
            or item.price != expected_price
            or item.currency != expected_currency
        ):
            raise SemanticGateClosed("Operation Siren voucher item identity changed")
        if item.sold_out or item.remaining <= 0:
            raise SemanticGateClosed("Operation Siren voucher item is sold out")
        if not 0.0 <= item.bounds.left < item.bounds.right <= 1280.0 or not (
            0.0 <= item.bounds.top < item.bounds.bottom <= 720.0
        ):
            raise SemanticGateClosed("Operation Siren voucher item is outside viewport")

        state = self.read_state()
        root = "OverlayCamera/Overlay/UIMain/WorldShopUI(Clone)/adapt/middle/content/world_shop/content/"
        controls = tuple(
            button
            for button in state.buttons
            if button.path.startswith(root)
            and button.name in ("item_tpl", "item_tpl(Clone)")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds == item.bounds
        )
        if len(controls) != 1:
            raise SemanticGateClosed(
                "Operation Siren voucher item control is absent or ambiguous"
            )
        bounds = item.bounds
        point = Point(
            x=(bounds.left + bounds.right) / 2.0,
            y=(bounds.top + bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=f"os/voucher/item/{index}/{expected_name}",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=controls[0].path,
        )

    def operation_siren_voucher_purchase_dialog_quantity(
        self,
        expected_display_name: str,
        expected_icon_sprite: str,
    ) -> Optional[int]:
        """Read an exact voucher exchange dialog without trusting localized labels."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed(
                "Operation Siren voucher dialog snapshots are not coherent"
            )
        single_root = "OverlayCamera/Overlay/UIMain/ShopsUISinglebox(Clone)/window"
        single_control_paths = (
            single_root + "/actions/confirm_btn",
            single_root + "/actions/cancel_btn",
        )
        single_controls = tuple(
            tuple(button for button in state.buttons if button.path == path)
            for path in single_control_paths
        )
        single_names = tuple(
            text
            for text in ui_state.texts
            if text.path
            == single_root + "/item/display_panel/name_container/name/Text"
        )
        if single_names or any(single_controls):
            if any(len(matches) != 1 for matches in single_controls):
                raise SemanticGateClosed(
                    "Operation Siren voucher single exchange controls are ambiguous"
                )
            for button in (matches[0] for matches in single_controls):
                if not (
                    button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.interactable
                    and button.raycast_top is None
                    and button.bounds is not None
                ):
                    raise SemanticGateClosed(
                        "Operation Siren voucher single exchange control is not actionable"
                    )
            single_names = tuple(
                text
                for text in single_names
                if text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(single_names) != 1 or not (
                single_names[0].text.strip() == expected_display_name
                or (
                    expected_display_name.endswith("..")
                    and single_names[0].text.strip().startswith(
                        expected_display_name[:-2]
                    )
                )
            ):
                raise SemanticGateClosed(
                    "Operation Siren voucher single exchange item name changed"
                )
            single_icons = tuple(
                image
                for image in ui_state.images
                if image.path
                == single_root + "/item/left/IconTpl/icon_bg/icon"
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.sprite == expected_icon_sprite
            )
            if len(single_icons) != 1:
                raise SemanticGateClosed(
                    "Operation Siren voucher single exchange item icon changed"
                )
            single_counts = tuple(
                text
                for text in ui_state.texts
                if text.path == single_root + "/item/left/IconTpl/icon_bg/count"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and re.fullmatch(r"[1-9][0-9]*", text.text.strip())
            )
            if len(single_counts) != 1:
                raise SemanticGateClosed(
                    "Operation Siren voucher single exchange quantity is ambiguous"
                )
            return int(single_counts[0].text.strip())

        root = "OverlayCamera/Overlay/UIMain/ShopsUIMsgbox(Clone)"
        control_paths = (
            root + "/actions/confirm_button",
            root + "/actions/cancel_button",
        )
        controls = tuple(
            tuple(button for button in state.buttons if button.path == path)
            for path in control_paths
        )
        name_path = root + "/item/panel_bg/display_panel/name_container/name/Text"
        names = tuple(text for text in ui_state.texts if text.path == name_path)
        if not names and not any(controls):
            return None
        if any(len(matches) != 1 for matches in controls):
            raise SemanticGateClosed(
                "Operation Siren voucher dialog controls are ambiguous"
            )
        for button in (matches[0] for matches in controls):
            if not (
                button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.raycast_top is None
                and button.bounds is not None
            ):
                raise SemanticGateClosed(
                    "Operation Siren voucher dialog control is not actionable"
                )
        names = tuple(
            text
            for text in names
            if text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(names) != 1 or not (
            names[0].text.strip() == expected_display_name
            or (
                expected_display_name.endswith("..")
                and names[0].text.strip().startswith(expected_display_name[:-2])
            )
        ):
            raise SemanticGateClosed(
                "Operation Siren voucher dialog item name changed"
            )
        icon_paths = (
            root + "/item/panel_bg/left/IconTpl/icon_bg/icon",
            root + "/got/panel_bg/list/item/icon_bg/icon",
        )
        for path in icon_paths:
            matches = tuple(
                image
                for image in ui_state.images
                if image.path == path
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.sprite == expected_icon_sprite
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "Operation Siren voucher dialog item icon changed"
                )
        values = tuple(
            text
            for text in ui_state.texts
            if text.path == root + "/count/number_panel/value"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and re.fullmatch(r"[1-9][0-9]*", text.text.strip())
        )
        if len(values) != 1:
            raise SemanticGateClosed(
                "Operation Siren voucher dialog quantity is ambiguous"
            )
        return int(values[0].text.strip())

    def click_operation_siren_voucher_purchase_confirm(
        self,
        expected_display_name: str,
        expected_icon_sprite: str,
        expected_quantity: int,
    ) -> ActionReceipt:
        quantity = self.operation_siren_voucher_purchase_dialog_quantity(
            expected_display_name, expected_icon_sprite
        )
        if quantity != expected_quantity:
            raise SemanticGateClosed("Operation Siren voucher quantity changed")
        state = self.read_state()
        paths = (
            "OverlayCamera/Overlay/UIMain/ShopsUIMsgbox(Clone)/actions/confirm_button",
            "OverlayCamera/Overlay/UIMain/ShopsUISinglebox(Clone)/window/actions/confirm_btn",
        )
        buttons = tuple(button for button in state.buttons if button.path in paths)
        if len(buttons) != 1:
            raise SemanticGateClosed(
                "Operation Siren voucher confirmation is ambiguous"
            )
        button = buttons[0]
        if not (
            button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.bounds is not None
        ):
            raise SemanticGateClosed(
                "Operation Siren voucher confirmation is not actionable"
            )
        bounds = button.bounds
        point = Point(
            (bounds.left + bounds.right) / 2.0,
            (bounds.top + bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/voucher/purchase/confirm",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=button.path,
        )

    def operation_siren_reset_shop_visible(self) -> bool:
        from ..opsi_monthstart import reset_shop
        return reset_shop(self) is not None

    def click_operation_siren_reset_shop(self) -> ActionReceipt:
        from ..opsi_monthstart import click_reset_shop
        return click_reset_shop(self)

    def click_operation_siren_voucher(self) -> ActionReceipt:
        """Open the voucher shop from the proven world-map footer."""

        self.operation_siren_globe_state()
        state = self.read_state()
        target = self._unique(state, "os/globe/voucher")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.bounds is not None
            and 0 <= target.bounds.left < target.bounds.right <= self.fingerprint.width
            and 0 <= target.bounds.top < target.bounds.bottom <= self.fingerprint.height
            and not self._blocking_rules(state, "os/globe/voucher")
        ):
            raise SemanticGateClosed(
                "operation siren voucher entrance is not actionable"
            )
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/globe/voucher",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )
