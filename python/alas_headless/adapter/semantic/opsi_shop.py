"""Opsi shop for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import ActionReceipt, ObserverTransportError, SemanticGateClosed


class OpsiShopAdapterPorts:
    """Opsi shop ports on the shared adapter context."""

    def purchase_operation_siren_shop_item_once(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
    ) -> ActionReceipt:
        """Purchase exactly one proven unified Operation Siren shop item."""

        self._require_action_grant("shop.purchase")
        before_items = self.oracle._retry_transition_read(
            self.oracle.operation_siren_shop_items,
            attempts=8,
            interval_seconds=0.2,
        )
        matches = tuple(item for item in before_items if item.index == index)
        if len(matches) != 1:
            raise SemanticGateClosed("selected Operation Siren shop item is absent")
        before = matches[0]
        if before.canonical_name != expected_name or before.price != expected_price:
            raise SemanticGateClosed("selected Operation Siren shop item identity changed")
        if before.currency != "SpecialExchangeTicket":
            raise SemanticGateClosed(
                "selected Operation Siren shop currency is not qualified"
            )
        if before.remaining <= 0:
            raise SemanticGateClosed("selected Operation Siren shop item is sold out")
        before_currency = self.oracle._retry_transition_read(
            self.oracle.operation_siren_shop_currency,
            attempts=8,
            interval_seconds=0.2,
        )
        if before_currency < expected_price:
            raise SemanticGateClosed("Operation Siren shop currency is insufficient")

        try:
            self.oracle.click_operation_siren_shop_item(
                index, expected_name, expected_price
            )
        except ObserverTransportError:
            # ``adb shell input tap`` can execute on-device while its host
            # acknowledgement times out.  Continue only when the exact
            # quantity-one dialog proves that this item click committed.
            if self.oracle.shop_purchase_dialog_quantity(before.display_name) != 1:
                raise
        deadline = time.monotonic() + 5.0
        while True:
            quantity = self.oracle.shop_purchase_dialog_quantity(before.display_name)
            if quantity is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren shop purchase dialog did not open"
                )
            time.sleep(0.2)
        if quantity != 1:
            raise SemanticGateClosed(
                "Operation Siren shop purchase did not default to one item"
            )
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_purchase_confirm(before.display_name, 1),
        )
        deadline = time.monotonic() + 120.0
        while True:
            if self.oracle.shop_purchase_dialog_quantity(before.display_name) is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                try:
                    after_items = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_items,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                    after_currency = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_currency,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next(
                    (item for item in after_items if item.index == index), None
                )
                if after is None:
                    raise SemanticGateClosed(
                        "purchased Operation Siren shop item disappeared"
                    )
                if (
                    after.canonical_name != before.canonical_name
                    or after.price != before.price
                    or after.remaining != before.remaining - 1
                    or after_currency != before_currency - before.price
                ):
                    raise SemanticGateClosed(
                        "Operation Siren shop purchase postcondition changed"
                    )
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren shop purchase confirmation did not settle"
                )
            time.sleep(0.25)

    def resume_operation_siren_shop_purchase_once(
        self,
        index: int,
        expected_name: str,
        expected_display_name: str,
        expected_price: int,
        before_remaining: int,
        before_currency: int,
    ) -> ActionReceipt:
        """Resume an exact quantity-one dialog after an ambiguous item tap."""

        self._require_action_grant("shop.purchase")
        if self.oracle.shop_purchase_dialog_quantity(expected_display_name) != 1:
            raise SemanticGateClosed(
                "Operation Siren shop recovery dialog is absent or changed"
            )
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_purchase_confirm(expected_display_name, 1),
        )
        deadline = time.monotonic() + 120.0
        while True:
            if self.oracle.shop_purchase_dialog_quantity(expected_display_name) is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                try:
                    items = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_items,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                    currency = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_currency,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next((item for item in items if item.index == index), None)
                if (
                    after is None
                    or after.canonical_name != expected_name
                    or after.price != expected_price
                    or after.remaining != before_remaining - 1
                    or currency != before_currency - expected_price
                ):
                    raise SemanticGateClosed(
                        "Operation Siren shop recovery postcondition changed"
                    )
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren shop recovery confirmation did not settle"
                )
            time.sleep(0.25)

    def purchase_operation_siren_voucher_item_once(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
        expected_currency: str = "Voucher",
    ) -> ActionReceipt:
        """Exchange exactly one proven Operation Siren voucher item."""

        self._require_action_grant("shop.purchase")
        if expected_currency != "Voucher":
            raise SemanticGateClosed(
                "Operation Siren voucher Oil exchange is not qualified"
            )
        before_items = self.oracle._retry_transition_read(
            self.oracle.operation_siren_voucher_items,
            attempts=8,
            interval_seconds=0.2,
        )
        before = next((item for item in before_items if item.index == index), None)
        if before is None:
            raise SemanticGateClosed("selected Operation Siren voucher item is absent")
        if (
            before.canonical_name != expected_name
            or before.price != expected_price
            or before.currency != expected_currency
        ):
            raise SemanticGateClosed(
                "selected Operation Siren voucher item identity changed"
            )
        if before.sold_out or before.remaining <= 0:
            raise SemanticGateClosed("selected Operation Siren voucher item is sold out")
        before_currency = self.oracle._retry_transition_read(
            self.oracle.operation_siren_voucher_currency,
            attempts=8,
            interval_seconds=0.2,
        )
        if before_currency < before.price:
            raise SemanticGateClosed(
                "Operation Siren voucher currency is insufficient"
            )

        try:
            self.oracle.click_operation_siren_voucher_item(
                index, expected_name, expected_price, expected_currency
            )
        except ObserverTransportError:
            if self.oracle.operation_siren_voucher_purchase_dialog_quantity(
                before.display_name, before.icon_sprite
            ) != 1:
                raise
        deadline = time.monotonic() + 5.0
        while True:
            try:
                quantity = (
                    self.oracle.operation_siren_voucher_purchase_dialog_quantity(
                        before.display_name, before.icon_sprite
                    )
                )
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
                continue
            if quantity is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren voucher exchange dialog did not open"
                )
            time.sleep(0.2)
        if quantity != 1:
            raise SemanticGateClosed(
                "Operation Siren voucher exchange did not default to one item"
            )
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_operation_siren_voucher_purchase_confirm(
                before.display_name, before.icon_sprite, 1
            ),
        )
        deadline = time.monotonic() + 120.0
        while True:
            try:
                dialog_quantity = (
                    self.oracle.operation_siren_voucher_purchase_dialog_quantity(
                        before.display_name, before.icon_sprite
                    )
                )
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
                continue
            if dialog_quantity is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                try:
                    after_items = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_voucher_items,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                    after_currency = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_voucher_currency,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next(
                    (item for item in after_items if item.index == index), None
                )
                if (
                    after is None
                    or after.canonical_name != before.canonical_name
                    or after.price != before.price
                    or after.currency != before.currency
                    or after.remaining != before.remaining - 1
                    or after_currency != before_currency - before.price
                ):
                    raise SemanticGateClosed(
                        "Operation Siren voucher exchange postcondition changed"
                    )
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren voucher exchange confirmation did not settle"
                )
            time.sleep(0.25)
