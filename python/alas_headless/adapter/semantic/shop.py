"""Shop for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import ActionReceipt, ObserverTransportError, SemanticGateClosed
from .contracts import AlasSemanticActionDeferred


class ShopAdapterPorts:
    """Shop ports on the shared adapter context."""

    def purchase_shop_item_once(
        self,
        index: int,
        expected_name: str,
        expected_cost: str,
        expected_price: int,
    ) -> ActionReceipt:
        if not self._action_ledger.allowed("shop.purchase"):
            raise AlasSemanticActionDeferred(
                "shop purchase requires a positive transaction budget"
            )
        items = self.oracle.general_shop_items()
        matches = tuple(item for item in items if item.index == index)
        if len(matches) != 1:
            raise SemanticGateClosed("selected shop item is absent")
        item = matches[0]
        if (
            item.canonical_name != expected_name
            or item.cost != expected_cost
            or item.price != expected_price
        ):
            raise SemanticGateClosed("selected shop item identity changed")
        if item.canonical_name == "DefaultItem":
            raise SemanticGateClosed("unknown shop item cannot be purchased")
        if item.remaining is not None and item.remaining <= 0:
            raise SemanticGateClosed("selected shop item is sold out")
        before_balance = self.oracle.shop_currency_balance(item.cost)
        if before_balance < item.price:
            raise SemanticGateClosed("shop currency is insufficient")
        try:
            self.oracle.click_shop_item(index)
        except ObserverTransportError:
            if self.oracle.shop_purchase_dialog_quantity(item.display_name) != 1:
                raise
        deadline = time.monotonic() + 5.0
        while True:
            try:
                quantity = self.oracle.shop_purchase_dialog_quantity(
                    item.display_name
                )
            except SemanticGateClosed as exc:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
                continue
            if quantity is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop purchase dialog did not open")
            time.sleep(0.2)
        if quantity != 1:
            raise SemanticGateClosed("shop purchase did not default to one item")
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_purchase_confirm(item.display_name, 1),
        )
        deadline = time.monotonic() + 30.0
        while True:
            if self.oracle.shop_purchase_dialog_quantity(item.display_name) is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                    continue
                try:
                    after_items = self.oracle.general_shop_items()
                    after_balance = self.oracle.shop_currency_balance(item.cost)
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next(
                    (candidate for candidate in after_items if candidate.index == index),
                    None,
                )
                if (
                    after is None
                    or after.canonical_name != item.canonical_name
                    or after.cost != item.cost
                    or after.price != item.price
                    or after_balance != before_balance - item.price
                ):
                    raise SemanticGateClosed("shop purchase postcondition changed")
                if item.remaining is not None and (
                    after.remaining != item.remaining - 1
                    or after.total != item.total
                ):
                    raise SemanticGateClosed("shop item stock did not decrease by one")
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop purchase confirmation did not settle")
            time.sleep(0.25)

    def refresh_shop_once(self) -> ActionReceipt:
        """Spend one bounded grant on the exact current GuildShop refresh."""

        if not self._action_ledger.allowed("shop.purchase"):
            raise AlasSemanticActionDeferred(
                "shop refresh requires a positive transaction budget"
            )
        if self.oracle.shop_selected_nav_label() != "补给商店":
            raise SemanticGateClosed("shop refresh navigation changed")
        if self.oracle.shop_selected_tab_label() != "舰队":
            raise SemanticGateClosed("only GuildShop refresh is qualified")
        before_items = self.oracle.general_shop_items()
        before_balance = self.oracle.shop_currency_balance("GuildCoins")
        if not self.oracle.shop_refresh_available():
            raise SemanticGateClosed("GuildShop refresh is unavailable")
        self.oracle.click_shop_refresh()
        deadline = time.monotonic() + 5.0
        while True:
            try:
                prompt = self.oracle.shop_refresh_prompt()
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
                continue
            if prompt is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop refresh prompt did not open")
            time.sleep(0.2)
        currency, price = prompt
        if currency != "GuildCoins" or price != 50:
            raise SemanticGateClosed("GuildShop refresh cost changed")
        if before_balance < price:
            raise SemanticGateClosed("GuildShop currency is insufficient")
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_refresh_confirm(currency, price),
        )
        deadline = time.monotonic() + 30.0
        before_signature = tuple(
            (
                item.display_name,
                item.canonical_name,
                item.amount,
                item.cost,
                item.price,
                item.remaining,
                item.total,
            )
            for item in before_items
        )
        while True:
            try:
                prompt = self.oracle.shop_refresh_prompt()
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
                continue
            if prompt is None:
                try:
                    after_items = self.oracle.general_shop_items()
                    after_balance = self.oracle.shop_currency_balance("GuildCoins")
                    refresh_available = self.oracle.shop_refresh_available()
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after_signature = tuple(
                    (
                        item.display_name,
                        item.canonical_name,
                        item.amount,
                        item.cost,
                        item.price,
                        item.remaining,
                        item.total,
                    )
                    for item in after_items
                )
                if after_balance != before_balance - price:
                    raise SemanticGateClosed("shop refresh balance did not decrease")
                if after_signature == before_signature and refresh_available:
                    raise SemanticGateClosed("shop refresh inventory did not change")
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop refresh confirmation did not settle")
            time.sleep(0.25)
