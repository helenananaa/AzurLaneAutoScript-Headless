"""Guild regression cases for the adapter."""

import unittest
import time
from unittest.mock import Mock, patch
from alas_headless.adapter import (ActionLedger, DEFAULT_CAPABILITY_INVENTORY,
    RecoveryPolicy, compatibility_profile, compatibility_policy_sha256)
from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.adapter_cases import (
    AlasSemanticAdapterTestsSupport,
    GuildSemanticAdapterTestsSupport,
)
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_inherited_loading_hides_reward_probe_but_foreign_modal_does_not(self):
        adapter, oracle, _ = self.make_adapter()
        oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id='loading')]
        self.assertFalse(adapter._appear_priority('GET_ITEMS_1'))
        from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
        for names in (('msgbox',), ('loading', 'msgbox')):
            oracle._blocking_rules = lambda *_, names=names: [
                SimpleNamespace(blocker_id=name) for name in names]
            self.assertIs(adapter._appear_priority('GET_ITEMS_1'), UNHANDLED)
        self.assertEqual(oracle.click_calls, [])

    def test_incoherent_guild_presence_yields_to_next_native_screenshot_then_expires(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._appear_once = Mock(side_effect=SemanticGateClosed('guild page snapshots are not coherent'))
        with patch('alas_headless.adapter.semantic.observation.time.monotonic', return_value=100):
            self.assertFalse(adapter.appear(NamedButton('GUILD_CHECK')))
        with patch('alas_headless.adapter.semantic.observation.time.monotonic', return_value=106):
            with self.assertRaises(SemanticGateClosed):
                adapter.appear(NamedButton('GUILD_CHECK'))
        self.assertEqual(oracle.click_calls, [])

    def test_guild_return_withdraw_probe_yields_only_during_owned_transition(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values['meowfficer/page/back'] = False
        adapter._guild_return_transition_until = time.monotonic() + 12
        self.assertFalse(adapter.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM')))
        oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id='msgbox')]
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))

    def test_guild_entry_withdraw_absence_requires_fresh_owned_transition(self):
        from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
        for failure in (None, 'loading', 'stale', 'expired', 'foreign'):
            with self.subTest(failure=failure):
                adapter, oracle, _ = self.make_adapter()
                oracle.guild_page_visible = Mock(return_value=False)
                oracle.main_page_visible = Mock(return_value=False)
                oracle.read_state = Mock(return_value=SimpleNamespace(
                    generation=10 if failure == 'stale' else 11))
                oracle._blocking_rules = Mock(return_value=(
                    [SimpleNamespace(blocker_id='msgbox' if failure == 'foreign' else 'loading')]
                    if failure in ('loading', 'foreign') else []))
                adapter._main_guild_entry_receipt = SimpleNamespace(generation=10)
                adapter._main_guild_entry_until = time.monotonic() + (12 if failure != 'expired' else -1)
                result = adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM')
                if failure in (None, 'loading'):
                    self.assertIs(result, False)
                else:
                    self.assertIs(result, UNHANDLED)
                self.assertEqual(oracle.click_calls, [])

    def test_report_claim_waits_for_mounted_reward_without_repeating_claim(self):
        oracle = FakeOracle()
        oracle.read_state = Mock(return_value=SimpleNamespace(generation=8))
        grants = {'guild.claim': 1}
        ledger = ActionLedger(profile=compatibility_profile('guild-runtime', grants),
            inventory=DEFAULT_CAPABILITY_INVENTORY, grants=grants,
            recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
            policy_sha256=compatibility_policy_sha256('guild-runtime', grants))
        adapter = AlasSemanticAdapter(oracle, lambda: None, action_ledger=ledger)
        adapter._award_close_target = Mock(side_effect=[None, 'reward/award-info/close'])
        with patch('alas_headless.adapter.semantic.guild.time.sleep'):
            receipt = adapter.claim_all_guild_reports()
        self.assertEqual(receipt.semantic_id, 'guild/report/claim-all')
        self.assertEqual(oracle.click_calls, ['guild/report/claim-all'])
        self.assertEqual(adapter._award_close_target.call_count, 2)

    def test_retained_report_home_recovers_exact_award_and_rejects_obscured_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.award_info_page_visible = lambda: True
        oracle.exists_values['guild/report/close'] = True
        oracle.enabled_values['reward/award-info/close'] = True
        adapter._award_close_target = Mock(return_value='reward/award-info/close')
        # Native ui_additional owns the foreground reward before the home
        # page graph runs. Direct recovery still closes only this award.
        self.assertFalse(adapter.appear(NamedButton('GOTO_MAIN')))
        self.assertTrue(adapter.appear(NamedButton('GET_ITEMS_1')))
        receipt = adapter.click(NamedButton('GOTO_MAIN'))
        self.assertEqual(receipt.semantic_id, 'reward/award-info/close')
        receipt = adapter.click(NamedButton('GET_ITEMS_1'))
        self.assertEqual(receipt.semantic_id, 'reward/award-info/close')
        adapter._award_close_target = Mock(return_value=None)
        oracle.enabled_values['reward/award-info/close'] = False
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton('GOTO_MAIN'))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton('GET_ITEMS_1'))
        self.assertEqual(oracle.click_calls, ['reward/award-info/close'] * 2)

    def test_guild_entry_unmapped_presence_probes_keep_unknown_input_closed(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["meowfficer/page/back"] = False
        oracle.guild_page_visible = lambda: True
        self.assertFalse(adapter.appear(NamedButton("MONTHLY_PASS_NOTICE")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("MONTHLY_PASS_NOTICE"))
        oracle.guild_page_visible = lambda: False
        adapter._main_guild_entry_until = time.monotonic() + 12
        self.assertFalse(adapter.appear(NamedButton("MONTHLY_PASS_NOTICE")))
        oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id="msgbox")]
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("MONTHLY_PASS_NOTICE"))

    def test_cn_oxygen_cola_sprite_uses_existing_exchange_filter_name(self):
        self.assertEqual(AlasSemanticAdapter.guild_exchange_item_name('suansukele'),
                         'OxyCola')

    def test_guild_claim_waits_for_same_logistics_page_to_return(self):
        oracle = FakeOracle()
        calls = 0
        stable = SimpleNamespace(supply_claimable=True)

        def read_logistics():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise SemanticGateClosed("guild logistics snapshots are not coherent")
            return stable

        oracle.guild_logistics_state = read_logistics
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter._guild_logistics_transition_until = time.monotonic() + 1.0
        self.assertIs(adapter.guild_logistics_state(), stable)
        self.assertIs(adapter.guild_logistics_state(), stable)
        self.assertEqual(calls, 3)

        adapter._guild_logistics_transition_until = 0.0
        oracle.guild_logistics_state = lambda: (_ for _ in ()).throw(
            SemanticGateClosed("guild logistics page identity is absent"))
        with self.assertRaises(SemanticGateClosed):
            adapter.guild_logistics_state()

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
