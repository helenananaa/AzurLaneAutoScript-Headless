"""Opsi resources regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_operation_siren_shop_purchase_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"remaining": 3, "currency": 1200, "dialog": False}

        def items():
            return (
                SimpleNamespace(
                    index=7,
                    canonical_name="METARedBook",
                    display_name="META通用战术教材",
                    price=100,
                    remaining=state["remaining"],
                    currency="SpecialExchangeTicket",
                ),
            )

        oracle.operation_siren_shop_items = items
        oracle.operation_siren_shop_currency = lambda: state["currency"]
        oracle.click_operation_siren_shop_item = (
            lambda index, name, price: state.update(dialog=True)
        )
        oracle.shop_purchase_dialog_quantity = (
            lambda _name: 1 if state["dialog"] else None
        )

        def confirm(_name, _quantity):
            state["dialog"] = False
            state["remaining"] -= 1
            state["currency"] -= 100
            return oracle.click_receipt("shop/purchase/confirm")

        oracle.click_shop_purchase_confirm = confirm
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.purchase_operation_siren_shop_item_once(
            7, "METARedBook", 100
        )

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(state, {"remaining": 2, "currency": 1100, "dialog": False})
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_operation_siren_shop_purchase_refuses_insufficient_currency(self):
        oracle = FakeOracle()
        oracle.operation_siren_shop_items = lambda: (
            SimpleNamespace(
                index=7,
                canonical_name="METARedBook",
                display_name="META通用战术教材",
                price=100,
                remaining=3,
                currency="SpecialExchangeTicket",
            ),
        )
        oracle.operation_siren_shop_currency = lambda: 99
        oracle.click_operation_siren_shop_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "currency is insufficient"):
            adapter.purchase_operation_siren_shop_item_once(
                7, "METARedBook", 100
            )

        oracle.click_operation_siren_shop_item.assert_not_called()

    def test_operation_siren_voucher_exchange_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"remaining": 30, "currency": 21792, "dialog": False}

        def items():
            return (
                SimpleNamespace(
                    index=1,
                    canonical_name="HECombatPlan",
                    display_name="高效作战指令书",
                    icon_sprite="tebiezuozhan",
                    price=100,
                    remaining=state["remaining"],
                    currency="Voucher",
                    sold_out=False,
                ),
            )

        oracle.operation_siren_voucher_items = items
        oracle.operation_siren_voucher_currency = lambda: state["currency"]
        oracle.click_operation_siren_voucher_item = (
            lambda index, name, price, currency: state.update(dialog=True)
        )
        oracle.operation_siren_voucher_purchase_dialog_quantity = (
            lambda _name, _icon: 1 if state["dialog"] else None
        )

        def confirm(_name, _icon, _quantity):
            state["dialog"] = False
            state["remaining"] -= 1
            state["currency"] -= 100
            return oracle.click_receipt("os/voucher/purchase/confirm")

        oracle.click_operation_siren_voucher_purchase_confirm = confirm
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.purchase_operation_siren_voucher_item_once(
            1, "HECombatPlan", 100
        )

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(
            state, {"remaining": 29, "currency": 21692, "dialog": False}
        )
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_operation_siren_voucher_exchange_refuses_insufficient_currency(self):
        oracle = FakeOracle()
        oracle.operation_siren_voucher_items = lambda: (
            SimpleNamespace(
                index=1,
                canonical_name="HECombatPlan",
                display_name="高效作战指令书",
                icon_sprite="tebiezuozhan",
                price=100,
                remaining=30,
                currency="Voucher",
                sold_out=False,
            ),
        )
        oracle.operation_siren_voucher_currency = lambda: 99
        oracle.click_operation_siren_voucher_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "currency is insufficient"):
            adapter.purchase_operation_siren_voucher_item_once(
                1, "HECombatPlan", 100
            )

        oracle.click_operation_siren_voucher_item.assert_not_called()

    def test_operation_siren_voucher_exchange_refuses_identity_drift_and_oil(self):
        oracle = FakeOracle()
        oracle.operation_siren_voucher_items = lambda: (
            SimpleNamespace(
                index=1,
                canonical_name="HECombatPlan",
                display_name="高效作战指令书",
                icon_sprite="tebiezuozhan",
                price=101,
                remaining=30,
                currency="Voucher",
                sold_out=False,
            ),
        )
        oracle.click_operation_siren_voucher_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            adapter.purchase_operation_siren_voucher_item_once(
                1, "HECombatPlan", 100
            )
        with self.assertRaisesRegex(SemanticGateClosed, "Oil exchange"):
            adapter.purchase_operation_siren_voucher_item_once(
                0, "LoggerUnlockT2", 5000, "Oil"
            )

        oracle.click_operation_siren_voucher_item.assert_not_called()

    def test_operation_siren_voucher_exchange_refuses_sold_out_item(self):
        oracle = FakeOracle()
        oracle.operation_siren_voucher_items = lambda: (
            SimpleNamespace(
                index=10,
                canonical_name="Coin",
                display_name="物资",
                icon_sprite="gold",
                price=250,
                remaining=0,
                currency="Voucher",
                sold_out=True,
            ),
        )
        oracle.click_operation_siren_voucher_item = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "sold out"):
            adapter.purchase_operation_siren_voucher_item_once(10, "Coin", 250)

        oracle.click_operation_siren_voucher_item.assert_not_called()
