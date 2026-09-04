"""Guild regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.adapter_cases import (
    AlasSemanticAdapterTestsSupport,
    GuildSemanticAdapterTestsSupport,
)
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_global_guild_overlay_hides_underlying_page_checks(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/guild-message/close"] = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))

    def test_login_closes_global_guild_message_overlay(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/guild-message/close"] = True
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))
        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(oracle.click_calls, ["overlay/guild-message/close"])

    def test_guild_shop_refresh_is_atomic_and_postconditioned(self):
        oracle = FakeOracle()
        state = {"balance": 110600, "prompt": False, "refreshed": False}

        def items():
            name = "BookT3" if state["refreshed"] else "PlateT4"
            return (
                SimpleNamespace(
                    index=0,
                    display_name=name,
                    canonical_name=name,
                    amount=1,
                    cost="GuildCoins",
                    price=80 if state["refreshed"] else 60,
                    remaining=None,
                    total=None,
                ),
            )

        oracle.shop_selected_nav_label = lambda: "补给商店"
        oracle.shop_selected_tab_label = lambda: "舰队"
        oracle.general_shop_items = items
        oracle.shop_currency_balance = lambda _currency: state["balance"]
        oracle.shop_refresh_available = lambda: not state["refreshed"]
        oracle.click_shop_refresh = lambda: state.update(prompt=True)
        oracle.shop_refresh_prompt = (
            lambda: ("GuildCoins", 50) if state["prompt"] else None
        )

        def confirm(_currency, _price):
            state["prompt"] = False
            state["refreshed"] = True
            state["balance"] -= 50
            return oracle.click_receipt("shop/refresh/confirm")

        oracle.click_shop_refresh_confirm = confirm
        adapter = AlasSemanticAdapter(oracle, lambda: None, shop_purchase_budget=1)

        receipt = adapter.refresh_shop_once()

        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(
            state, {"balance": 110550, "prompt": False, "refreshed": True}
        )
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_alas_owned_guild_popup_cancel_alias_uses_reviewed_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {"overlay/guild-message/close": True}
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))
        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("GUILD_POPUP_CONFIRM"))

    def test_global_guild_popup_probe_and_cancel_use_reviewed_close(self):
        adapter, oracle, _ = self.make_adapter()

        oracle.enabled_values["overlay/guild-message/close"] = False
        self.assertFalse(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        oracle.enabled_values["overlay/guild-message/close"] = True
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))

        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))
        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(oracle.click_calls, ["overlay/guild-message/close"])


class GuildSemanticAdapterTests(GuildSemanticAdapterTestsSupport, unittest.TestCase):
    def test_exchange_filter_selects_highest_ranked_eligible_typed_item(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.guild_logistics_state = lambda: SimpleNamespace(
            exchange_items=(
                SimpleNamespace(
                    index=0,
                    icon_sprite="gold",
                    enough=True,
                    button=SimpleNamespace(interactable=True),
                ),
                SimpleNamespace(
                    index=1,
                    icon_sprite="17023",
                    enough=True,
                    button=SimpleNamespace(interactable=True),
                ),
                SimpleNamespace(
                    index=2,
                    icon_sprite="17003",
                    enough=True,
                    button=SimpleNamespace(interactable=True),
                ),
            )
        )

        selected = adapter.select_guild_exchange_item(
            "PlateGeneralT3 > PlateTorpedoT3 > Coin"
        )

        self.assertEqual(selected.index, 2)

    def test_exchange_filter_rejects_duplicate_priorities(self):
        adapter, _, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "duplicates"):
            adapter.select_guild_exchange_item("Coin > Coin")
