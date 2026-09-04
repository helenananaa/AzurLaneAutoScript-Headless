"""Shop for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    GeneralShopItemState,
    ImageState,
    OracleState,
    Point,
    TextState,
    UiState,
)
from .errors import SemanticGateClosed


class ShopOracle:
    """Shop operations sharing the oracle frame and input boundary."""

    def academy_munitions_available(self) -> bool:
        if not self.academy_page_visible():
            return False
        state = self.read_state()
        matches = self._matches(state, "academy/munitions")
        if len(matches) != 1:
            return False
        target = matches[0]
        return bool(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "academy/munitions")
        )

    def munitions_page_visible(self) -> bool:
        """Identify the exact post-2025 Supply Shop surface."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("shop snapshots are not coherent")
        controls = {
            "closeBtn": "buttonList/top/closeBtn",
            "homeBtn": "buttonList/top/homeBtn",
        }
        for name, suffix in controls.items():
            matches = tuple(
                button
                for button in state.buttons
                if button.name == name
                and button.path.endswith(suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
            )
            if len(matches) != 1:
                return False
        title = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("buttonList/top/title/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip() == "商店"
        )
        slots = tuple(
            button
            for button in state.buttons
            if re.fullmatch(r"[0-9]+", button.name)
            and re.search(
                r"ShopSupplyShopUI\(Clone\)/scroll/content/[0-9]+$",
                button.path,
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        slot_indexes = sorted(int(button.name) for button in slots)
        return bool(
            len(title) == 1
            and len(slot_indexes) >= 10
            and len(slot_indexes) % 5 == 0
            and slot_indexes == list(range(len(slot_indexes)))
        )

    def recommendation_shop_visible(self) -> bool:
        """Identify the exact top-level post-2025 Shop shell."""

        return self._retry_transition_read(self._recommendation_shop_visible_once)

    def _recommendation_shop_visible_once(self) -> bool:
        state = self.read_state()
        ui_state = self.read_ui_state()
        return self._recommendation_shop_visible_from_states(state, ui_state)

    def _recommendation_shop_visible_from_states(
        self, state: OracleState, ui_state: UiState
    ) -> bool:
        """Check the Shop shell from one coherent Button/UI frame pair."""

        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("shop shell snapshots are not coherent")
        controls = tuple(
            button
            for button in state.buttons
            if button.name in ("homeBtn", "closeBtn")
            and button.path.endswith("buttonList/top/" + button.name)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        title = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("buttonList/top/title/Text")
            and text.text.strip() == "商店"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        gift = self._toggle_matches(ui_state, "shop/gift-pack")
        return len(controls) == 2 and len(title) == 1 and len(gift) == 1

    def click_recommendation_shop_home(self) -> ActionReceipt:
        """Leave the exact Shop shell through its top home control."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("shop home snapshots are not coherent")
        if not self._recommendation_shop_visible_from_states(state, ui_state):
            raise SemanticGateClosed("shop shell identity is absent")
        targets = tuple(
            button
            for button in state.buttons
            if button.name == "homeBtn"
            and button.path.endswith("buttonList/top/homeBtn")
        )
        if len(targets) != 1:
            raise SemanticGateClosed("shop home target is absent or ambiguous")
        target = targets[0]
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "shop/home")
        ):
            raise SemanticGateClosed("shop home target is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="shop/home",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def shop_oil(self) -> int:
        return self._retry_transition_read(self._shop_oil_once)

    def _shop_oil_once(self) -> int:
        state = self.read_state()
        ui_state = self.read_ui_state()
        if not self._recommendation_shop_visible_from_states(state, ui_state):
            raise SemanticGateClosed("shop shell identity is absent")
        matches = tuple(
            text
            for text in ui_state.texts
            if (
                text.path.endswith("/adapt/top/resources/oil/Text")
                or text.path.endswith("buttonList/top/resources/oil/Text")
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]+", text.text.strip())
        )
        if len(matches) != 1:
            raise SemanticGateClosed("shop oil counter is absent or ambiguous")
        return int(matches[0].text.strip())

    def gift_pack_page_visible(self) -> bool:
        return self._retry_transition_read(self._gift_pack_page_visible_once)

    def _gift_pack_page_visible_once(self) -> bool:
        state = self.read_state()
        ui_state = self.read_ui_state()
        return self._gift_pack_page_visible_from_states(state, ui_state)

    def _gift_pack_page_visible_from_states(
        self, state: OracleState, ui_state: UiState
    ) -> bool:
        if not self._recommendation_shop_visible_from_states(state, ui_state):
            return False
        selected = tuple(
            toggle
            for toggle in self._toggle_matches(ui_state, "shop/gift-pack")
            if toggle.checked
        )
        labels = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(
                "ChargeGiftShopUI(Clone)/toggleGroup/Toggle/selected/Label"
            )
            and text.text.strip() == "全部"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        return len(selected) == 1 and len(labels) == 1

    def free_weekly_supply_pack_available(self) -> bool:
        """Require one exact zero-price weekly pack; paid cards are never matches."""

        return self._retry_transition_read(self._free_weekly_supply_pack_available_once)

    def _free_weekly_supply_pack_available_once(self) -> bool:
        state = self.read_state()
        ui_state = self.read_ui_state()
        if not self._gift_pack_page_visible_from_states(state, ui_state):
            return False
        return self._free_weekly_supply_pack_root(state, ui_state) is not None

    def _free_weekly_supply_pack_root(
        self, state: OracleState, ui_state: UiState
    ) -> Optional[str]:
        roots = tuple(
            button.path
            for button in state.buttons
            if re.fullmatch(r"[0-9]+", button.name)
            and "ChargeGiftShopUI(Clone)/lScrollRect/content/" in button.path
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        matches = []
        for root in roots:
            name = tuple(
                text.text.strip()
                for text in ui_state.texts
                if text.path == root + "/real_tpl/item_name_mask/item_name"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            price = tuple(
                text.text.strip()
                for text in ui_state.texts
                if text.path == root + "/real_tpl/Price/Text"
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if (
                name
                and len(name) == 1
                and re.search(r"(?:免费|每周|周常)", name[0])
                and price in (("0",), ("免费",))
            ):
                matches.append(root)
        if len(matches) > 1:
            raise SemanticGateClosed("free weekly supply pack is ambiguous")
        return matches[0] if matches else None

    def click_free_weekly_supply_pack(self) -> ActionReceipt:
        """Open only the exact zero-price weekly pack card."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("free weekly supply pack snapshots are not coherent")
        if not self._gift_pack_page_visible_from_states(state, ui_state):
            raise SemanticGateClosed("gift pack page identity is absent")
        root = self._free_weekly_supply_pack_root(state, ui_state)
        if root is None:
            raise SemanticGateClosed("free weekly supply pack is unavailable")
        targets = tuple(button for button in state.buttons if button.path == root)
        if len(targets) != 1:
            raise SemanticGateClosed("free weekly supply pack target is ambiguous")
        target = targets[0]
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "shop/free-weekly-pack")
        ):
            raise SemanticGateClosed("free weekly supply pack is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="shop/free-weekly-pack",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def shop_general_nav_selected(self) -> bool:
        return self.shop_selected_nav_label() == "补给商店"

    def shop_selected_nav_label(self) -> str:
        if not self.munitions_page_visible():
            return ""
        state = self.read_ui_state()
        selected = tuple(
            text.text.strip()
            for text in state.texts
            if text.path.endswith("/selected/name")
            and "buttonList/shop1List/supplyShop/shop2List/" in text.path
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip()
        )
        if len(selected) > 1:
            raise SemanticGateClosed("selected shop navigation is ambiguous")
        return selected[0] if selected else ""

    def click_shop_nav(self, label: str) -> ActionReceipt:
        names = {"补给商店": "supplyShop", "月度商店": "monthShop"}
        toggle_name = names.get(label)
        if toggle_name is None:
            raise SemanticGateClosed("shop navigation label is invalid")
        if not self.munitions_page_visible():
            raise SemanticGateClosed("shop page identity is absent")
        state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("shop navigation snapshots are not coherent")
        label_path = (
            "buttonList/shop1List/supplyShop/shop2List/" + toggle_name + "/name"
        )
        labels = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(label_path)
            and text.text.strip() == label
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        toggle_path = "buttonList/shop1List/supplyShop/shop2List/" + toggle_name
        toggles = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.path.endswith(toggle_path)
            and toggle.name == toggle_name
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.interactable
            and toggle.raycast_top is not False
            and toggle.point is not None
            and toggle.bounds is not None
            and toggle.bounds.contains(toggle.point)
        )
        if len(labels) != 1 or len(toggles) != 1:
            raise SemanticGateClosed("shop navigation control is absent or ambiguous")
        target = toggles[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="shop/navigation/" + label,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def shop_refresh_available(self) -> bool:
        """Read the exact refresh control state without pixel-color guessing."""

        if not self.munitions_page_visible():
            raise SemanticGateClosed("shop page identity is absent")
        state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("shop refresh snapshots are not coherent")
        path = "ShopSupplyShopUI(Clone)/timeBtn"
        buttons = tuple(
            button
            for button in state.buttons
            if button.name == "timeBtn"
            and button.path.endswith(path)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.raycast_top is not False
            and button.bounds is not None
        )
        icons = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(path)
            and image.name == "timeBtn"
            and image.sprite == "item_refresh"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        countdowns = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(path + "/Text")
            and re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}后刷新", text.text.strip())
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(buttons) != 1 or len(icons) != 1 or len(countdowns) != 1:
            raise SemanticGateClosed("shop refresh control is absent or ambiguous")
        return buttons[0].interactable

    def shop_general_tab_selected(self) -> bool:
        if not self.munitions_page_visible():
            return False
        state = self.read_ui_state()
        selected = tuple(
            text
            for text in state.texts
            if text.path.endswith(
                "ShopSupplyShopUI(Clone)/toggleGroup/Toggle/selected/Label"
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip() == "军火"
        )
        return len(selected) == 1

    def shop_selected_tab_label(self) -> str:
        if not self.munitions_page_visible():
            raise SemanticGateClosed("shop page identity is absent")
        state = self.read_ui_state()
        labels = tuple(
            re.sub(r"<[^>]*>", "", text.text).strip()
            for text in state.texts
            if text.path.endswith("/selected/Label")
            and "ShopSupplyShopUI(Clone)/toggleGroup/" in text.path
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.sub(r"<[^>]*>", "", text.text).strip()
        )
        if len(labels) != 1:
            raise SemanticGateClosed("selected shop tab is absent or ambiguous")
        return labels[0]

    def click_shop_tab(self, label: str) -> ActionReceipt:
        if not isinstance(label, str) or not label:
            raise SemanticGateClosed("shop tab label is invalid")
        if not self.munitions_page_visible():
            raise SemanticGateClosed("shop page identity is absent")
        state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("shop tab snapshots are not coherent")
        labels = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("/unselected/Label")
            and "ShopSupplyShopUI(Clone)/toggleGroup/" in text.path
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.sub(r"<[^>]*>", "", text.text).strip() == label
        )
        if len(labels) != 1 or labels[0].bounds is None:
            raise SemanticGateClosed("shop tab label is absent or ambiguous")
        label_bounds = labels[0].bounds
        controls = tuple(
            button
            for button in state.buttons
            if button.name == "Toggle(Clone)"
            and button.path.endswith(
                "ShopSupplyShopUI(Clone)/toggleGroup/Toggle(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
            and button.bounds.left <= label_bounds.left
            and button.bounds.right >= label_bounds.right
            and button.bounds.top <= label_bounds.top
            and button.bounds.bottom >= label_bounds.bottom
        )
        if len(controls) != 1:
            raise SemanticGateClosed("shop tab control is absent or ambiguous")
        bounds = controls[0].bounds
        assert bounds is not None
        point = Point(
            (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="shop/tab/" + label,
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=controls[0].path,
        )

    @staticmethod
    def _canonical_general_shop_name(display_name: str) -> str:
        book = re.fullmatch(r"舰艇(攻击|防御|辅助)教材T([1-4])", display_name)
        if book is not None:
            genre = {"攻击": "Red", "防御": "Blue", "辅助": "Yellow"}[book.group(1)]
            return f"Book{genre}T{book.group(2)}"
        box = re.fullmatch(r"(?:.+)?科技箱T([1-5])", display_name)
        if box is not None:
            return f"BoxT{box.group(1)}"
        plate = re.fullmatch(
            r"(主炮|鱼雷|防空炮|舰载机|通用)部件T([1-4])", display_name
        )
        if plate is not None:
            kind = {
                "主炮": "Gun",
                "鱼雷": "Torpedo",
                "防空炮": "Antiair",
                "舰载机": "Plane",
                "通用": "General",
            }[plate.group(1)]
            return f"Plate{kind}T{plate.group(2)}"
        if display_name == "心智魔方":
            return "Cube"
        if display_name == "心智单元":
            return "Chip"
        if display_name in ("心智单元Ⅱ", "心智单元II"):
            return "Array"
        if display_name == "九三式纯氧鱼雷":
            return "Type93PureOxygenTorpedo"
        if display_name == "一式穿甲弹":
            return "Type1ArmorPiercingShell"
        if display_name == "超重弹":
            return "SuperHeavyShell"
        if re.fullmatch(r"高级定向蓝图・[^・]+", display_name):
            return "DR"
        if re.fullmatch(r"定向蓝图・[^・]+", display_name):
            return "PR"
        if display_name == "满汉全席":
            return "FoodT6"
        if display_name == "皇家料理":
            return "FoodT5"
        if display_name == "快速完成工具":
            return "Drill"
        generic_book = re.fullmatch(r"舰艇教材T([1-4])", display_name)
        if generic_book is not None:
            return f"BookT{generic_book.group(1)}"
        generic_plate = re.fullmatch(r"强化部件T([1-4])", display_name)
        if generic_plate is not None:
            return f"PlateT{generic_plate.group(1)}"
        generic_retrofit = re.fullmatch(r"改造图纸T([1-4])", display_name)
        if generic_retrofit is not None:
            return f"RetrofitT{generic_retrofit.group(1)}"
        return "DefaultItem"

    def general_shop_items(self) -> Tuple[GeneralShopItemState, ...]:
        """Return the ten exact cards from the selected Supply Shop tab."""

        if not self.munitions_page_visible():
            raise SemanticGateClosed("supply shop is not selected")
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("general-shop item snapshots are not coherent")

        def one_text(suffix: str, *, digits: bool = False) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and (not digits or re.fullmatch(r"[0-9]+", text.text.strip()))
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "general-shop item text is absent or ambiguous"
                )
            return matches[0].text.strip()

        def one_image(suffix: str) -> ImageState:
            matches = tuple(
                image
                for image in ui_state.images
                if image.path.endswith(suffix)
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "general-shop item image is absent or ambiguous"
                )
            return matches[0]

        items = []
        for index in range(10):
            root = f"ShopSupplyShopUI(Clone)/scroll/content/{index}"
            buttons = tuple(
                button
                for button in button_state.buttons
                if button.name == str(index)
                and button.path.endswith(root)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.bounds is not None
            )
            if len(buttons) != 1:
                raise SemanticGateClosed(
                    "general-shop item card is absent or ambiguous"
                )
            display_name = one_text(root + "/name_mask/name")
            amount = int(one_text(root + "/itemBg/item/icon_bg/count", digits=True))
            price = int(one_text(root + "/consume/contain/Text", digits=True))
            cost_sprite = one_image(root + "/consume/contain/icon").sprite
            cost_names = {
                "gold": "Coins",
                "gem": "Gems",
                "exploit": "Merit",
                "guildicon": "GuildCoins",
                "guild_coin": "GuildCoins",
                "res_guildicon": "GuildCoins",
                "core": "Core",
                "shuju": "Core",
                "medal": "Medal",
            }
            if cost_sprite not in cost_names:
                raise SemanticGateClosed("general-shop item currency is unknown")
            icon_sprite = one_image(root + "/itemBg/item/icon_bg/icon").sprite
            stock = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(root + "/count_contain/label")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(stock) > 1:
                raise SemanticGateClosed("shop item stock is ambiguous")
            remaining = total = None
            if stock:
                match = re.fullmatch(
                    r"(?:可兑换次数)?([0-9]+)/([1-9][0-9]*)",
                    "".join(stock[0].text.split()),
                )
                if match is None:
                    raise SemanticGateClosed("shop item stock is malformed")
                remaining, total = map(int, match.groups())
                if remaining > total:
                    raise SemanticGateClosed("shop item stock exceeds its limit")
            items.append(
                GeneralShopItemState(
                    generation=ui_state.generation,
                    index=index,
                    display_name=display_name,
                    canonical_name=self._canonical_general_shop_name(display_name),
                    amount=amount,
                    cost=cost_names[cost_sprite],
                    price=price,
                    icon_sprite=icon_sprite,
                    bounds=buttons[0].bounds,
                    remaining=remaining,
                    total=total,
                )
            )
        return tuple(items)

    def shop_currency_balance(self, currency: str) -> int:
        """Read the exact balance for the selected ordinary shop currency."""

        if not self.munitions_page_visible():
            raise SemanticGateClosed("shop page identity is absent")
        nav = self.shop_selected_nav_label()
        tab = self.shop_selected_tab_label()
        allowed = {
            "Coins": ("补给商店", "军火"),
            "Gems": ("补给商店", "军火"),
            "Merit": ("补给商店", "军需"),
            "GuildCoins": ("补给商店", "舰队"),
            "Core": ("月度商店", "核心月度"),
            "Medal": ("月度商店", "勋章"),
        }
        if allowed.get(currency) != (nav, tab):
            raise SemanticGateClosed("shop currency does not match the selected tab")
        paths = {
            "Coins": "OverlayCamera/Overlay/UIMain/buttonList/top/resources/gold/Text",
            "Gems": "OverlayCamera/Overlay/UIMain/buttonList/top/resources/gem/Text",
            "Merit": "OverlayCamera/Overlay/UIMain/ShopSupplyShopUI(Clone)/bg/resList/res(Clone)/Text",
            "GuildCoins": "OverlayCamera/Overlay/UIMain/ShopSupplyShopUI(Clone)/bg/resList/res(Clone)/Text",
            "Core": "OverlayCamera/Overlay/UIMain/ShopSupplyShopUI(Clone)/bg/resList/res(Clone)/Text",
            "Medal": "OverlayCamera/Overlay/UIMain/ShopSupplyShopUI(Clone)/bg/resList/res(Clone)/Text",
        }
        state = self.read_ui_state()
        matches = tuple(
            text
            for text in state.texts
            if text.path.endswith(paths[currency])
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("shop currency balance is absent or ambiguous")
        return int(matches[0].text.strip())

    def click_shop_refresh(self) -> ActionReceipt:
        """Open the exact selected shop's refresh confirmation."""

        if not self.shop_refresh_available():
            raise SemanticGateClosed("shop refresh is not available")
        state = self.read_state()
        path = "OverlayCamera/Overlay/UIMain/ShopSupplyShopUI(Clone)/timeBtn"
        buttons = tuple(
            button
            for button in state.buttons
            if button.path == path
            and button.name == "timeBtn"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is not False
            and button.bounds is not None
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("shop refresh control is absent or ambiguous")
        bounds = buttons[0].bounds
        assert bounds is not None
        point = Point(
            (bounds.left + bounds.right) / 2.0,
            (bounds.top + bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="shop/refresh/open",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=buttons[0].path,
        )

    def shop_refresh_prompt(self) -> Optional[Tuple[str, int]]:
        """Return the exact currency and price from a supported refresh prompt."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("shop refresh prompt snapshots are not coherent")
        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        controls = {
            "confirm": root + "button_container/custom_button_1(Clone)",
            "cancel": root + "button_container/custom_button_2(Clone)",
        }
        buttons = {
            key: tuple(button for button in state.buttons if button.path.endswith(path))
            for key, path in controls.items()
        }
        contents = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(root + "msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if not contents and not any(buttons.values()):
            return None
        if any(len(value) != 1 for value in buttons.values()) or len(contents) != 1:
            raise SemanticGateClosed("shop refresh prompt is incomplete or ambiguous")
        labels = {
            key: tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(path + "/pic")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            for key, path in controls.items()
        }
        if (
            any(len(value) != 1 for value in labels.values())
            or "".join(labels["confirm"][0].text.split()) != "确定"
            or "".join(labels["cancel"][0].text.split()) != "取消"
        ):
            raise SemanticGateClosed("shop refresh prompt labels changed")
        for button in (value[0] for value in buttons.values()):
            if not (
                button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.bounds is not None
            ):
                raise SemanticGateClosed("shop refresh prompt is not actionable")
        message = "".join(contents[0].text.split())
        match = re.fullmatch(
            r"是否花费([1-9][0-9]*)<color=#[0-9A-Fa-f]{6}>([^<]+)</color>刷新商品列表",
            message,
        )
        if match is None:
            raise SemanticGateClosed("shop refresh prompt cost is malformed")
        currency_names = {"舰队币": "GuildCoins"}
        currency = currency_names.get(match.group(2))
        if currency is None:
            raise SemanticGateClosed("shop refresh currency is unsupported")
        if self.shop_selected_tab_label() != "舰队":
            raise SemanticGateClosed("shop refresh prompt is on an unsupported tab")
        return currency, int(match.group(1))

    def click_shop_refresh_confirm(
        self, expected_currency: str, expected_price: int
    ) -> ActionReceipt:
        if self.shop_refresh_prompt() != (expected_currency, expected_price):
            raise SemanticGateClosed("shop refresh prompt changed")
        state = self.read_state()
        path = (
            "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
            "button_container/custom_button_1(Clone)"
        )
        buttons = tuple(button for button in state.buttons if button.path.endswith(path))
        if len(buttons) != 1 or not buttons[0].actionable:
            raise SemanticGateClosed("shop refresh confirmation is not actionable")
        bounds = buttons[0].bounds
        point = buttons[0].point
        assert bounds is not None and point is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="shop/refresh/confirm",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=buttons[0].path,
        )

    def click_shop_item(self, index: int) -> ActionReceipt:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 10:
            raise SemanticGateClosed("shop item index is invalid")
        items = self.general_shop_items()
        item = next(
            (candidate for candidate in items if candidate.index == index), None
        )
        if item is None or item.bounds is None:
            raise SemanticGateClosed("shop item is absent")
        state = self.read_state()
        root = f"ShopSupplyShopUI(Clone)/scroll/content/{index}"
        buttons = tuple(
            button
            for button in state.buttons
            if button.name == str(index)
            and button.path.endswith(root)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is not False
            and button.bounds is not None
        )
        if len(buttons) != 1:
            raise SemanticGateClosed("shop item control is absent or ambiguous")
        bounds = buttons[0].bounds
        assert bounds is not None
        point = Point(
            x=(bounds.left + bounds.right) / 2,
            y=(bounds.top + bounds.bottom) / 2,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=f"shop/item/{index}/{item.canonical_name}",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=buttons[0].path,
        )

    def shop_purchase_dialog_quantity(
        self, expected_display_name: str
    ) -> Optional[int]:
        state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("shop purchase snapshots are not coherent")
        root = "OverlayCamera/Overlay/UIMain/ShopsUIMsgbox(Clone)"
        controls = {
            "confirm_button": root + "/actions/confirm_button",
            "cancel_button": root + "/actions/cancel_button",
        }
        matched_controls = {
            name: tuple(button for button in state.buttons if button.path == path)
            for name, path in controls.items()
        }
        name_path = root + "/item/panel_bg/display_panel/name_container/name/Text"
        names = tuple(text for text in ui_state.texts if text.path == name_path)
        if not names and not any(matched_controls.values()):
            return None
        if any(len(value) != 1 for value in matched_controls.values()):
            raise SemanticGateClosed("shop purchase controls are ambiguous")
        for button in (value[0] for value in matched_controls.values()):
            if not (
                button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.raycast_top is None
                and button.bounds is not None
            ):
                raise SemanticGateClosed("shop purchase control is not actionable")

        def exact_text(
            path: str, expected: Optional[str] = None
        ) -> Tuple[TextState, ...]:
            return tuple(
                text
                for text in ui_state.texts
                if text.path == path
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and (expected is None or "".join(text.text.split()) == expected)
            )

        confirm = exact_text(controls["confirm_button"] + "/label", "兑换")
        cancel = exact_text(controls["cancel_button"] + "/label", "取消")
        names = exact_text(name_path)
        values = exact_text(root + "/count/number_panel/value")
        if (
            len(confirm) != 1
            or len(cancel) != 1
            or len(names) != 1
            or not (
                names[0].text.strip() == expected_display_name
                or (
                    expected_display_name.endswith("..")
                    and names[0].text.strip().startswith(
                        expected_display_name[:-2]
                    )
                )
            )
            or len(values) != 1
            or re.fullmatch(r"[1-9][0-9]*", values[0].text.strip()) is None
        ):
            raise SemanticGateClosed("shop purchase dialog identity changed")
        return int(values[0].text.strip())

    def click_shop_purchase_confirm(
        self, expected_display_name: str, expected_quantity: int
    ) -> ActionReceipt:
        quantity = self.shop_purchase_dialog_quantity(expected_display_name)
        if quantity != expected_quantity:
            raise SemanticGateClosed("shop purchase quantity changed")
        state = self.read_state()
        path = (
            "OverlayCamera/Overlay/UIMain/ShopsUIMsgbox(Clone)/actions/confirm_button"
        )
        buttons = tuple(button for button in state.buttons if button.path == path)
        if len(buttons) != 1:
            raise SemanticGateClosed("shop purchase confirmation is ambiguous")
        button = buttons[0]
        if not (
            button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.bounds is not None
        ):
            raise SemanticGateClosed("shop purchase confirmation is not actionable")
        bounds = button.bounds
        assert bounds is not None
        point = Point(
            (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="shop/purchase/confirm",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=button.path,
        )
