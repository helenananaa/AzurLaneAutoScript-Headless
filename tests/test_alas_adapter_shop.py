"""Shop regression cases for the adapter."""

import time
import unittest
from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_regular_shop_purchase_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"remaining": 4, "balance": 3626, "dialog": False}

        def items():
            return (
                SimpleNamespace(
                    index=6,
                    canonical_name="DR",
                    display_name="高级定向蓝图・八期",
                    amount=1,
                    cost="Medal",
                    price=20,
                    remaining=state["remaining"],
                    total=5,
                ),
            )

        oracle.general_shop_items = items
        oracle.shop_currency_balance = lambda _currency: state["balance"]
        oracle.click_shop_item = lambda _index: state.update(dialog=True)
        oracle.shop_purchase_dialog_quantity = (
            lambda _name: 1 if state["dialog"] else None
        )

        def confirm(_name, _quantity):
            state["dialog"] = False
            state["remaining"] -= 1
            state["balance"] -= 20
            return oracle.click_receipt("shop/purchase/confirm")

        oracle.click_shop_purchase_confirm = confirm
        adapter = AlasSemanticAdapter(oracle, lambda: None, shop_purchase_budget=1)

        receipt = adapter.purchase_shop_item_once(6, "DR", "Medal", 20)

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(state, {"remaining": 3, "balance": 3606, "dialog": False})
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_battle_pass_navigation_recovers_from_existing_shop(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.recommendation_shop_visible_value = True
        adapter.begin_battle_pass()

        self.assertTrue(adapter.appear(NamedButton("SHOP_CHECK")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "shop/home")
        self.assertIs(adapter.click(NamedButton("GOTO_MAIN")), receipt)
        adapter._battle_pass_context.passive_transition_until = time.monotonic() - 1
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        adapter.end_battle_pass()
        with self.assertRaisesRegex(AlasSemanticUnmapped, "EVENT_LIST_CHECK"):
            adapter.appear(NamedButton("EVENT_LIST_CHECK"))
