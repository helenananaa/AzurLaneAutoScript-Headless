"""Dorm for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    DormFeedState,
    DormFoodState,
    DormFoodShopState,
    DormFurniturePurchaseState,
    DormFurnitureShopBalance,
    DormFurnitureThemePurchaseState,
    DormState,
    OracleState,
    Point,
    UiState,
)
from .errors import SemanticGateClosed


class DormOracle:
    """Dorm operations sharing the oracle frame and input boundary."""

    def _dorm_food_shop_control_proven(self, state, semantic_id, ui_state=None):
        if semantic_id not in ('dorm/feed/shop/open', 'dorm/feed/shop/plus',
                               'dorm/feed/shop/minus', 'dorm/feed/shop/cancel', 'dorm/feed/shop/confirm'):
            return False
        if not self._matches(state, semantic_id):
            return False
        target = self._unique(state, semantic_id)
        if (target.raycast_top is False or not target.active_in_hierarchy
                or not target.active_and_enabled or not target.interactable
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or not (0 <= target.point.x < self.fingerprint.width
                        and 0 <= target.point.y < self.fingerprint.height)
                or self._blocking_rules(state, semantic_id)):
            return False
        if target.actionable:
            return True
        owner_id = ('dorm/feed/close' if semantic_id.endswith('/open')
                    else 'dorm/feed/shop/cancel')
        if not self._matches(state, owner_id):
            return False
        owner = self._unique(state, owner_id)
        if (not owner.active_in_hierarchy or not owner.active_and_enabled
                or not owner.interactable or owner.point is None or owner.bounds is None
                or not owner.bounds.contains(owner.point) or owner.raycast_top is False):
            return False
        ui = ui_state if ui_state is not None else self.read_ui_state()
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('dorm food control snapshots are incomplete')
        for button in (target, owner):
            if button.actionable:
                continue
            images = tuple(i for i in ui.images if i.path == button.path
                           and i.active_in_hierarchy and i.active_and_enabled)
            if len(images) != 1:
                raise SemanticGateClosed('dorm food control image is absent or ambiguous')
            image = images[0]
            if (image.truncated or not image.sprite or not image.raycast_target
                    or image.raycast_top is False or image.bounds is None
                    or not image.bounds.contains(button.point)):
                return False
        return True

    def dorm_food_shop_visible(self) -> bool:
        return self.enabled('dorm/feed/shop/cancel')

    def dorm_food_shop_curry_stock(self):
        ui = self.read_ui_state()
        counts = tuple(text for text in ui.texts if text.path.endswith(
            'BackYardFeedUI(Clone)/frame/food_50004/icon_bg/count')
            and text.active_in_hierarchy and text.active_and_enabled
            and not text.truncated and text.bounds is not None)
        if len(counts) != 1 or not re.fullmatch(r'[0-9]+', counts[0].text.strip()):
            raise SemanticGateClosed('dorm purchase curry stock is absent or ambiguous')
        return int(counts[0].text.strip())

    def dorm_food_shop_state(self) -> DormFoodShopState:
        state = self.read_state()
        cancel = self._unique(state, 'dorm/feed/shop/cancel')
        ui = self.read_ui_state()
        if (not cancel.actionable and not self._dorm_food_shop_control_proven(
                state, 'dorm/feed/shop/cancel', ui)) or self._blocking_rules(state, 'dorm/feed/shop/cancel'):
            raise SemanticGateClosed('dorm food shop identity is not proven')
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('dorm food shop snapshots are not coherent')
        prefix = 'BackYardFeedUI(Clone)/BackYardFeedShopPanel(Clone)/frame/'
        def text(suffix):
            matches = [t for t in ui.texts if t.path.endswith(prefix + suffix)
                       and t.active_in_hierarchy and t.active_and_enabled
                       and not t.truncated and t.bounds is not None]
            if len(matches) != 1:
                raise SemanticGateClosed('dorm food shop text is absent or ambiguous: ' + suffix)
            return re.sub(r'<[^>]*>', '', matches[0].text).strip()
        def sprite(suffix):
            matches = [i for i in ui.images if i.path.endswith(prefix + suffix)
                       and i.active_in_hierarchy and i.active_and_enabled
                       and not i.truncated and i.sprite]
            if ui.image_truncated or len(matches) != 1:
                raise SemanticGateClosed('dorm food shop sprite is absent or ambiguous: ' + suffix)
            return matches[0].sprite
        quantity, total = text('cal_panel/value/Text'), text('cal_panel/total/Text')
        if not re.fullmatch(r'[1-9][0-9]*', quantity) or not re.fullmatch(r'[0-9]+', total):
            raise SemanticGateClosed('dorm food shop quantity or cost is malformed')
        return DormFoodShopState(state.generation, text('name'), int(quantity), int(total),
                                 sprite('cal_panel/total/icon'), sprite('icon_bg/icon'))

    def dorm_state(self) -> DormState:
        """Read the dorm summary without opening a mutating sub-page."""

        # A one-click collection briefly covers the summary with native tips.
        # Wait for the complete read to pass; never repeat the collection input.
        return self._retry_transition_read(self._dorm_state_once, attempts=24)

    def _dorm_state_once(self) -> DormState:

        button_state = self.read_state()
        page = self._unique(button_state, "dorm/page/manage")
        if (
            self._blocking_rules(button_state, "dorm/page/manage")
            or not page.active_in_hierarchy
            or not page.active_and_enabled
            or not page.interactable
            or page.raycast_top not in (True, False)
            or page.point is None
            or page.bounds is None
            or not page.bounds.contains(page.point)
        ):
            raise SemanticGateClosed("dorm page identity is not proven")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm snapshots are not coherent")

        root = "CourtYardUI(Clone)/main/"
        suffixes = {
            "slots": root + "bottomPanel/bottomleft/train_btn/Text",
            "food": root + "bottomPanel/bottomleft/feed_btn/Text",
            "comfort": root + "topPanel/btns/topright/comfortable/Text",
            "floor": root + "topPanel/btns/topright/switch/Text",
            "countdown": root + "bottomPanel/bottomleft/feed_btn/time",
        }
        values: Dict[str, str] = {}
        for key, suffix in suffixes.items():
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed("dorm text is absent or ambiguous: " + key)
            values[key] = matches[0].text.strip()

        slots = re.fullmatch(r"([0-9]{1,2})/([1-9][0-9]?)", values["slots"])
        food = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", values["food"])
        floor = re.fullmatch(r"([1-9][0-9]*)F", values["floor"])
        if (
            slots is None
            or food is None
            or floor is None
            or re.fullmatch(r"[0-9]+", values["comfort"]) is None
        ):
            raise SemanticGateClosed("dorm summary is malformed")

        occupied_slots, total_slots = map(int, slots.groups())
        current_food, food_capacity = map(int, food.groups())
        if occupied_slots > total_slots or current_food > food_capacity:
            raise SemanticGateClosed("dorm summary is inconsistent")
        countdown = (
            None
            if not values["countdown"]
            else self.parse_countdown_seconds(values["countdown"])
        )
        return DormState(
            occupied_slots=occupied_slots,
            total_slots=total_slots,
            food=current_food,
            food_capacity=food_capacity,
            comfort=int(values["comfort"]),
            floor=int(floor.group(1)),
            food_countdown_seconds=countdown,
        )

    def click_dorm_furniture_shop(self) -> ActionReceipt:
        """Open the furniture shop from one proven normal dorm page."""

        self.dorm_state()
        state = self.read_state()
        target = self._unique(state, "dorm/furniture/shop")
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("dorm furniture shop control is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture shop")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/shop",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_dorm_furniture_theme(self, index: int) -> ActionReceipt:
        """Open one exact visible theme in the current furniture shop."""

        if index not in range(7):
            raise ValueError("dorm furniture theme index must be 0 through 6")
        state = self.read_state()
        back = tuple(
            button
            for button in state.buttons
            if button.name == "fanhui"
            and button.path.endswith("NewBackYardShopUI(Clone)/adpter/top/fanhui")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        root = (
            "NewBackYardShopUI(Clone)/pages/BackYardThemePage(Clone)/list/"
            "frame/mask/content/{0}"
        ).format(index)
        matches = tuple(
            button
            for button in state.buttons
            if button.name == str(index)
            and button.path.endswith(root)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        theme_roots = tuple(
            button
            for button in state.buttons
            if button.path.startswith(
                "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/pages/"
                "BackYardThemePage(Clone)/list/frame/mask/content/"
            )
            and button.name in {str(candidate) for candidate in range(7)}
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        if len(back) != 1 or len(matches) != 1 or len(theme_roots) != 7:
            raise SemanticGateClosed("dorm furniture theme list is not proven")
        target = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture theme")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/theme/{0}".format(index),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_dorm_furniture_theme_details(self) -> ActionReceipt:
        """Open the selected theme through its exact typed purchase-detail image."""

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm furniture theme snapshots are not coherent")
        theme_prefix = (
            "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/pages/"
            "BackYardThemePage(Clone)/list/frame/mask/content/"
        )
        themes = tuple(
            button
            for button in button_state.buttons
            if button.path == theme_prefix + button.name
            and button.name in {str(index) for index in range(7)}
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        path = "OverlayCamera/Overlay/UIMain/adpter/descript/btn_goumai"
        matches = tuple(
            image
            for image in ui_state.images
            if image.path == path
            and image.sprite == "buy_bg"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.bounds is not None
        )
        if len(themes) != 7 or len(matches) != 1:
            raise SemanticGateClosed("dorm furniture theme detail control is not proven")
        target = matches[0]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point):
            raise SemanticGateClosed("dorm furniture theme detail point is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture details")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/theme/details",
            generation=button_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_dorm_furniture_theme_purchase_option(
        self, buy_option: str
    ) -> ActionReceipt:
        """Open the exact set/all payment dialog for the selected theme."""

        if buy_option not in ("set", "all"):
            raise ValueError("dorm furniture buy option must be set or all")
        state = self.read_state()
        roots_allowed = (
            "OverlayCamera/Overlay/UIMain/BackYardThemeInfoPage(Clone)",
            "UICamera/Canvas/UIOrigin/BackYardThemeInfoPage(Clone)",
        )
        suffix = "purchase_btn" if buy_option == "set" else "purchase_all_btn"
        matches = tuple(
            button
            for button in state.buttons
            if button.path in {root + "/frame/" + suffix for root in roots_allowed}
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        roots = tuple(
            button
            for button in state.buttons
            if button.path in roots_allowed
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if len(matches) != 1 or len(roots) != 1:
            raise SemanticGateClosed("dorm furniture theme purchase control is not proven")
        target = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "foreground changed before dorm furniture theme purchase option"
            )
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/theme/" + buy_option,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def dorm_furniture_theme_is_time_limited(self) -> bool:
        """Prove that every visible item in the selected theme has a time marker."""

        button_state = self.read_state()
        ui_state = self.read_text_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm furniture theme item snapshots are not coherent")
        roots_allowed = (
            "OverlayCamera/Overlay/UIMain/BackYardThemeInfoPage(Clone)",
            "UICamera/Canvas/UIOrigin/BackYardThemeInfoPage(Clone)",
        )
        roots = tuple(
            button.path
            for button in button_state.buttons
            if button.path in roots_allowed
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if len(roots) != 1:
            raise SemanticGateClosed("dorm furniture theme detail root is not proven")
        prefix = roots[0] + "/frame/list/content/"
        cards = tuple(
            button
            for button in button_state.buttons
            if button.path == prefix + button.name
            and button.name in {str(index) for index in range(8)}
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        if len(cards) != 8:
            raise SemanticGateClosed("dorm furniture theme item list is not proven")
        for card in cards:
            root = prefix + card.name
            names = tuple(
                text
                for text in ui_state.texts
                if text.path == root + "/name"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.text.strip()
            )
            markers = tuple(
                text
                for text in ui_state.texts
                if text.path == root + "/time/Text"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.text.strip()
            )
            if len(names) != 1 or len(markers) != 1:
                return False
        return True

    def close_dorm_furniture_theme_details(self) -> ActionReceipt:
        """Close the exact current theme-detail overlay."""

        state = self.read_state()
        paths = {
            "OverlayCamera/Overlay/UIMain/BackYardThemeInfoPage(Clone)/frame/back",
            "UICamera/Canvas/UIOrigin/BackYardThemeInfoPage(Clone)/frame/back",
        }
        matches = tuple(
            button
            for button in state.buttons
            if button.path in paths
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("dorm furniture theme back control is not proven")
        target = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture theme back")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/theme/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def dorm_furniture_theme_purchase_state(
        self,
    ) -> DormFurnitureThemePurchaseState:
        """Read the exact gold-only theme payment dialog."""

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm furniture theme dialog snapshots are not coherent")
        roots_allowed = (
            "OverlayCamera/Overlay/UIMain/ThemeMsgboxPage(Clone)",
            "UICamera/Canvas/UIOrigin/ThemeMsgboxPage(Clone)",
        )
        roots = tuple(
            button.path
            for button in button_state.buttons
            if button.path in roots_allowed
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if len(roots) != 1:
            raise SemanticGateClosed("dorm furniture theme dialog root is not proven")
        prefix = roots[0] + "/frame/"

        def exact_button(suffix: str) -> ButtonState:
            matches = tuple(
                button
                for button in button_state.buttons
                if button.path == prefix + suffix
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "dorm furniture theme dialog button is absent or ambiguous: "
                    + suffix
                )
            return matches[0]

        def exact_text(suffix: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path == prefix + suffix
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "dorm furniture theme dialog text is absent or ambiguous: "
                    + suffix
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        theme_name = exact_text("name")
        quantity_text = exact_text("count/Text")
        gold_text = exact_text("price/gold_text")
        if (
            not theme_name
            or re.fullmatch(r"[1-9][0-9]*", quantity_text) is None
            or re.fullmatch(r"[1-9][0-9]*", gold_text) is None
        ):
            raise SemanticGateClosed("dorm furniture theme dialog values are malformed")
        return DormFurnitureThemePurchaseState(
            generation=button_state.generation,
            theme_name=theme_name,
            quantity=int(quantity_text),
            gold_price=int(gold_text),
            gold_purchase_button=exact_button("btns/gold_purchase_btn"),
            close_button=exact_button("close_btn"),
        )

    def click_dorm_furniture_theme_purchase_gold(self) -> ActionReceipt:
        """Submit the currently proven theme payment with furniture coins."""

        purchase = self.dorm_furniture_theme_purchase_state()
        target = purchase.gold_purchase_button
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture theme payment")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/theme/purchase/gold",
            generation=purchase.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def close_dorm_furniture_theme_purchase(self) -> ActionReceipt:
        """Close a theme payment dialog without spending furniture coins."""

        purchase = self.dorm_furniture_theme_purchase_state()
        target = purchase.close_button
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture theme close")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/theme/purchase/close",
            generation=purchase.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_dorm_furniture_tag(self, index: int) -> ActionReceipt:
        """Choose a current furniture-shop category by its typed tag sprite."""

        if index not in range(7):
            raise ValueError("dorm furniture tag index must be 0 through 6")
        state = self.read_state()
        ui = self.read_ui_state()
        prefix = "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/adpter/tag/list/"
        tag_images = tuple(
            image
            for image in ui.images
            if image.path.startswith(prefix)
            and image.sprite == "text_tag{0}".format(index)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
        )
        all_tag_images = tuple(
            image
            for image in ui.images
            if image.path.startswith(prefix)
            and re.fullmatch(r"text_tag[0-6]", image.sprite) is not None
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
        )
        candidates = tuple(
            button
            for button in state.buttons
            if button.path.endswith("NewBackYardShopUI(Clone)/adpter/tag/list/tpl(Clone)")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and any(
                button.bounds.contains(
                    Point(
                        (image.bounds.left + image.bounds.right) / 2.0,
                        (image.bounds.top + image.bounds.bottom) / 2.0,
                    )
                )
                for image in tag_images
            )
        )
        all_tags = tuple(
            button
            for button in state.buttons
            if button.path.endswith("NewBackYardShopUI(Clone)/adpter/tag/list/tpl(Clone)")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        if (
            not tag_images
            or {image.sprite for image in all_tag_images}
            != {"text_tag{0}".format(candidate) for candidate in range(7)}
            or len(candidates) != 1
            or len(all_tags) != 7
        ):
            raise SemanticGateClosed("dorm furniture category tags are not proven")
        target = candidates[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture tag")
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/tag/{0}".format(index),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def close_dorm_furniture_shop(self) -> ActionReceipt:
        """Return from the current furniture shop to the proven dorm page."""

        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "fanhui"
            and button.path.endswith("NewBackYardShopUI(Clone)/adpter/top/fanhui")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("dorm furniture shop back control is not proven")
        target = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture shop back")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_dorm_furniture_item(self, index: int) -> ActionReceipt:
        """Open one exact visible item in the current furniture list."""

        if index not in range(8):
            raise ValueError("dorm furniture item index must be 0 through 7")
        state = self.read_state()
        ui = self.read_text_state()
        root = (
            "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/pages/"
            "BackYardFurniturePage(Clone)/adpter/frame/bg/content/{0}"
        ).format(index)
        matches = tuple(
            button
            for button in state.buttons
            if button.name == str(index)
            and button.path.endswith(root)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        all_items = tuple(
            button
            for button in state.buttons
            if re.fullmatch(r"[0-7]", button.name) is not None
            and button.path.startswith(
                "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/pages/"
                "BackYardFurniturePage(Clone)/adpter/frame/bg/content/"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        names = tuple(
            text
            for text in ui.texts
            if text.path.endswith(root + "/name")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and text.text.strip()
        )
        if len(matches) != 1 or len(all_items) != 8 or len(names) != 1:
            raise SemanticGateClosed("dorm furniture item list is not proven")
        target = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture item")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/item/{0}".format(index),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def dorm_furniture_time_limited_item_indices(self) -> Tuple[int, ...]:
        """Return the visible current furniture cards carrying an exact time marker."""

        button_state = self.read_state()
        ui_state = self.read_text_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm furniture list snapshots are not coherent")
        prefix = (
            "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/pages/"
            "BackYardFurniturePage(Clone)/adpter/frame/bg/content/"
        )
        cards = tuple(
            button
            for button in button_state.buttons
            if re.fullmatch(r"[0-7]", button.name) is not None
            and button.path == prefix + button.name
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(cards) != 8 or {int(card.name) for card in cards} != set(range(8)):
            raise SemanticGateClosed("dorm furniture list is incomplete")
        limited: list[int] = []
        for card in cards:
            index = int(card.name)
            root = prefix + str(index)
            names = tuple(
                text
                for text in ui_state.texts
                if text.path == root + "/name"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and text.text.strip()
            )
            markers = tuple(
                text
                for text in ui_state.texts
                if text.path == root + "/time/Text"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and text.text.strip()
            )
            if len(names) != 1 or len(markers) > 1:
                raise SemanticGateClosed("dorm furniture card text is ambiguous")
            if (
                markers
                and card.bounds.top >= 0
                and card.bounds.bottom <= self.fingerprint.height
            ):
                limited.append(index)
        return tuple(sorted(limited))

    def dorm_furniture_purchase_state(self) -> DormFurniturePurchaseState:
        """Read one current furniture-purchase dialog without spending currency."""

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm furniture dialog snapshots are not coherent")
        prefix = "OverlayCamera/Overlay/UIMain/FurnitureMsgboxPage(Clone)/frame/"

        def exact_button(suffix: str) -> ButtonState:
            matches = tuple(
                button
                for button in button_state.buttons
                if button.path == prefix + suffix
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "dorm furniture dialog button is absent or ambiguous: " + suffix
                )
            return matches[0]

        def exact_text(suffix: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path == prefix + suffix
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "dorm furniture dialog text is absent or ambiguous: " + suffix
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        gold_button = exact_button("btns/gold_purchase_btn")
        gem_button = exact_button("btns/gem_purchase_btn")
        close_button = exact_button("close_btn")
        item_name = exact_text("name")
        quantity_text = exact_text("count/Text")
        maximum_text = exact_text("max_cnt")
        gold_text = exact_text("price/gold_text")
        gem_text = exact_text("price/gem_text")
        if not item_name or re.fullmatch(r"[1-9][0-9]*", quantity_text) is None:
            raise SemanticGateClosed("dorm furniture dialog quantity is malformed")
        if maximum_text and re.fullmatch(r"[1-9][0-9]*", maximum_text) is None:
            raise SemanticGateClosed("dorm furniture dialog maximum is malformed")
        if (
            re.fullmatch(r"[1-9][0-9]*", gold_text) is None
            or re.fullmatch(r"[1-9][0-9]*", gem_text) is None
        ):
            raise SemanticGateClosed("dorm furniture dialog price is malformed")
        quantity = int(quantity_text)
        maximum_quantity = int(maximum_text) if maximum_text else None
        if maximum_quantity is not None and quantity > maximum_quantity:
            raise SemanticGateClosed("dorm furniture quantity exceeds the maximum")
        return DormFurniturePurchaseState(
            generation=button_state.generation,
            item_name=item_name,
            quantity=quantity,
            maximum_quantity=maximum_quantity,
            gold_price=int(gold_text),
            gem_price=int(gem_text),
            gold_purchase_button=gold_button,
            gem_purchase_button=gem_button,
            close_button=close_button,
        )

    def dorm_furniture_shop_balance(self) -> DormFurnitureShopBalance:
        """Read the two exact current furniture-shop currency counters."""

        ui_state = self.read_text_state()
        prefix = "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/adpter/top/"

        def exact_counter(suffix: str) -> int:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path == prefix + suffix
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1 or re.fullmatch(r"[0-9]+", matches[0].text) is None:
                raise SemanticGateClosed(
                    "dorm furniture currency is absent or malformed: " + suffix
                )
            return int(matches[0].text)

        dorm_coins = exact_counter("res_gold/Text")
        gems = exact_counter("res_gem/Text")
        return DormFurnitureShopBalance(
            generation=ui_state.generation,
            dorm_coins=dorm_coins,
            gems=gems,
        )

    def click_dorm_furniture_purchase(self, currency: str) -> ActionReceipt:
        """Submit one dialog purchase through an exact declared currency button."""

        if currency not in ("gold", "gem"):
            raise ValueError("dorm furniture currency must be gold or gem")
        purchase = self.dorm_furniture_purchase_state()
        target = (
            purchase.gold_purchase_button
            if currency == "gold"
            else purchase.gem_purchase_button
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture purchase")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/purchase/" + currency,
            generation=purchase.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_dorm_furniture_quantity(self, direction: str) -> ActionReceipt:
        """Change the current furniture quantity without submitting a purchase."""

        if direction not in ("increase", "decrease"):
            raise ValueError("dorm furniture quantity direction must increase or decrease")
        purchase = self.dorm_furniture_purchase_state()
        suffix = "count/right_arr" if direction == "increase" else "count/left_arr"
        state = self.read_state()
        prefix = "OverlayCamera/Overlay/UIMain/FurnitureMsgboxPage(Clone)/frame/"
        matches = tuple(
            button
            for button in state.buttons
            if button.path == prefix + suffix
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("dorm furniture quantity control is not proven")
        target = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture quantity")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/quantity/" + direction,
            generation=purchase.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def close_dorm_furniture_purchase(self) -> ActionReceipt:
        """Close an open furniture-purchase dialog without committing a purchase."""

        purchase = self.dorm_furniture_purchase_state()
        target = purchase.close_button
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before dorm furniture close")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="dorm/furniture/purchase/close",
            generation=purchase.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def dorm_feed_state(self) -> DormFeedState:
        """Read the open dorm feed panel without changing inventory."""

        button_state = self.read_state()
        close = self._unique(button_state, "dorm/feed/close")
        if not close.actionable or self._blocking_rules(
            button_state, "dorm/feed/close"
        ):
            raise SemanticGateClosed("dorm feed panel identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("dorm feed snapshots are not coherent")

        def exact_text(path: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "dorm feed text is absent or ambiguous: " + path
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        fill = re.fullmatch(
            r"([0-9]+)/([1-9][0-9]*)",
            exact_text("BackYardFeedUI(Clone)/frame/Text"),
        )
        if fill is None:
            raise SemanticGateClosed("dorm feed capacity is malformed")
        food, capacity = map(int, fill.groups())
        if food > capacity:
            raise SemanticGateClosed("dorm feed capacity is inconsistent")

        items = []
        for item_id in range(50001, 50007):
            root = "BackYardFeedUI(Clone)/frame/food_{0}/".format(item_id)
            value_match = re.fullmatch(r"食物([1-9][0-9]*)", exact_text(root + "Text"))
            count_text = exact_text(root + "icon_bg/count")
            if value_match is None or re.fullmatch(r"[0-9]+", count_text) is None:
                raise SemanticGateClosed("dorm feed inventory is malformed")
            semantic_id = "dorm/feed/item/{0}".format(item_id)
            images = tuple(
                image
                for image in ui_state.images
                if image.name == "icon_bg"
                and image.path.endswith(root + "icon_bg")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.raycast_target
                and image.raycast_top is True
                and not image.truncated
                and image.bounds is not None
            )
            if len(images) != 1:
                raise SemanticGateClosed("dorm feed item image is absent or ambiguous")
            image = images[0]
            if self._blocking_rules(button_state, semantic_id):
                raise SemanticGateClosed("dorm feed item is not safely actionable")
            assert image.bounds is not None
            button = ButtonState(
                name=image.name,
                path=image.path,
                active_in_hierarchy=image.active_in_hierarchy,
                active_and_enabled=image.active_and_enabled,
                interactable=True,
                raycast_top=image.raycast_top,
                point=Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                ),
                bounds=image.bounds,
                raw=image.raw,
            )
            items.append(
                DormFoodState(
                    item_id=item_id,
                    value=int(value_match.group(1)),
                    count=int(count_text),
                    button=button,
                )
            )
        return DormFeedState(food=food, capacity=capacity, items=tuple(items))

    def click_dorm_food(self, item_id: int) -> ActionReceipt:
        """Click one ALAS dorm food card after exact typed revalidation."""

        if item_id not in range(50001, 50007):
            raise ValueError("dorm food item id must be 50001 through 50006")
        feed = self._retry_transition_read(
            self.dorm_feed_state,
            attempts=20,
            interval_seconds=0.25,
        )
        matches = tuple(item for item in feed.items if item.item_id == item_id)
        if len(matches) != 1:
            raise SemanticGateClosed("dorm feed item identity is ambiguous")
        target = matches[0].button
        semantic_id = "dorm/feed/item/{0}".format(item_id)
        button_state = self.read_state()
        if (
            not target.actionable
            or target.point is None
            or target.bounds is None
            or self._blocking_rules(button_state, semantic_id)
        ):
            raise SemanticGateClosed("dorm feed item is not safely actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _dorm_back_delegated_raycast_proven(
        self, state: OracleState, ui_state: Optional[UiState] = None
    ) -> bool:
        matches = self._matches(state, "dorm/page/back")
        if len(matches) > 1:
            raise SemanticGateClosed("dorm back target is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, "dorm/page/back"):
            return False
        if target.actionable:
            return True
        if (
            target.raycast_top is not False
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False

        # CourtYardUI's reviewed return control delegates raycasts to the
        # decorative Images on the Button and its children.  Keep this escape
        # hatch local to the exact path and exact 9.7.10 sprite composition.
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("dorm back snapshots are incomplete")
        expected = {
            target.path: "back_btn_bg",
            target.path + "/Image": "return",
            target.path + "/s": "back_btn_s1",
        }
        proven = set()
        for image in ui_state.images:
            sprite = expected.get(image.path)
            if sprite is None or image.sprite != sprite:
                continue
            if (
                not image.active_in_hierarchy
                or not image.active_and_enabled
                or not image.raycast_target
                or image.truncated
                or image.bounds is None
                or not image.bounds.contains(target.point)
            ):
                return False
            if image.path in proven:
                raise SemanticGateClosed("dorm back image is ambiguous")
            proven.add(image.path)
        return proven == set(expected)

    def _dorm_empty_food_cancel_proven(
        self, state: OracleState, ui_state: Optional[UiState] = None
    ) -> bool:
        matches = self._matches(state, "dorm/empty-food/cancel")
        if len(matches) > 1:
            raise SemanticGateClosed("dorm empty-food cancel target is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, "dorm/empty-food/cancel"):
            return False
        if (
            target.raycast_top is not None
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("dorm empty-food snapshots are incomplete")
        root = target.path.rsplit("/frame/cancel_btn", 1)[0]
        expected = {
            target.path: "btn_yellow",
            root + "/frame/Image": "hungry",
            root + "/frame": "msg_bg",
        }
        proven = set()
        for image in ui_state.images:
            sprite = expected.get(image.path)
            if sprite is None or image.sprite != sprite:
                continue
            if (
                not image.active_in_hierarchy
                or not image.active_and_enabled
                or not image.raycast_target
                or image.truncated
                or image.bounds is None
            ):
                return False
            if image.path == target.path and not image.bounds.contains(target.point):
                return False
            if image.path in proven:
                raise SemanticGateClosed("dorm empty-food image is ambiguous")
            proven.add(image.path)
        return proven == set(expected)

    def dorm_empty_food_cancel_available(self) -> bool:
        state = self.read_state()
        return self._dorm_empty_food_cancel_proven(state)

    def _dorm_page_control_proven(
        self,
        state: OracleState,
        semantic_id: str,
        ui_state: Optional[UiState] = None,
    ) -> bool:
        if semantic_id not in ("dorm/feed", "dorm/collect"):
            raise ValueError("unsupported delegated dorm page control")
        matches = self._matches(state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed("dorm page control is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, semantic_id):
            return False
        if target.actionable:
            return True
        if (
            target.raycast_top is not False
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False
        page_back = self._matches(state, "dorm/page/back")
        manage = self._matches(state, "dorm/page/manage")
        if (
            len(page_back) != 1
            or not page_back[0].active_in_hierarchy
            or len(manage) != 1
            or not manage[0].active_in_hierarchy
        ):
            return False
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.snapshot.get("text_truncated") is not False
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("dorm page-control snapshots are incomplete")

        feed_root = (
            target.path
            if semantic_id == "dorm/feed"
            else target.path.rsplit("/rightPanel/onekey", 1)[0]
            + "/bottomPanel/bottomleft/feed_btn"
        )
        labels = tuple(
            value
            for value in ui_state.texts
            if value.path in (feed_root + "/label", feed_root + "/Text")
            and value.active_in_hierarchy
            and value.active_and_enabled
            and not value.truncated
        )
        if len(labels) != 2:
            return False
        by_path = {value.path: value.text for value in labels}
        if (
            by_path.get(feed_root + "/label") != "食量"
            or re.fullmatch(r"[0-9]+/[1-9][0-9]*", by_path.get(feed_root + "/Text", ""))
            is None
        ):
            return False

        if semantic_id == "dorm/feed":
            expected_images = {
                target.path + "/icon": "btn_feed",
                target.path + "/bg": "btn_72",
            }
            images = tuple(
                image
                for image in ui_state.images
                if image.path in expected_images
                and image.sprite == expected_images[image.path]
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and target.bounds.contains(
                    Point(
                        (image.bounds.left + image.bounds.right) / 2.0,
                        (image.bounds.top + image.bounds.bottom) / 2.0,
                    )
                )
            )
            return len(images) == len(expected_images) and len(
                {image.path for image in images}
            ) == len(expected_images)

        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == "onekey"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        if len(images) > 1:
            raise SemanticGateClosed("dorm collect image is ambiguous")
        return len(images) == 1
