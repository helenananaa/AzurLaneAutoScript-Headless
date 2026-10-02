"""Dorm regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticUnmapped,
    BuildPool,
    SemanticGateClosed,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_observed_feed_panel_waits_for_close_without_opening_underlay(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        adapter._dorm_context.feed_panel_observed = True
        oracle.enabled = Mock(side_effect=[False, True, True])
        with patch("alas_headless.adapter.semantic.dorm.time.sleep") as sleep:
            receipt = adapter.click(NamedButton("DORM_FEED_ENTER"))
        sleep.assert_called_once_with(0.25)
        self.assertEqual(receipt.semantic_id, "dorm/feed/close")

    def test_observed_feed_panel_with_persistently_blocked_close_fails_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        adapter._dorm_context.feed_panel_observed = True
        oracle.enabled = Mock(return_value=False)
        oracle.click = Mock()
        with patch("alas_headless.adapter.semantic.dorm.time.sleep"):
            with self.assertRaisesRegex(SemanticGateClosed, "close is not actionable"):
                adapter.click(NamedButton("DORM_FEED_ENTER"))
        oracle.click.assert_not_called()

    def test_build_dorm_and_menu_page_checks_are_presence_only(self):
        cases = (
            ("build/page/start", "BUILD_CHECK"),
            ("dorm-menu/page/root", "DORMMENU_CHECK"),
            ("research-menu/page/back", "RESHMENU_CHECK"),
            ("research/page/back", "RESEARCH_CHECK"),
            ("dorm/page/manage", "DORM_CHECK"),
        )
        for semantic_id, resource in cases:
            with self.subTest(resource=resource):
                adapter, oracle, _ = self.make_adapter()
                oracle.exists_values[semantic_id] = True
                if resource == "DORM_CHECK":
                    oracle.enabled_values["dorm/feed/close"] = False
                if resource == "RESEARCH_CHECK":
                    # Research requires the native five-card inventory, not
                    # just a back button in an otherwise empty fake page.
                    oracle.research_project_values = [SimpleNamespace() for _ in range(5)]
                self.assertTrue(adapter.appear(NamedButton(resource)))
        self.assertEqual(
            adapter.semantic_id_for("DORM_GOTO_MAIN"), "dorm/page/back"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORM_INFO"), "dorm/statistics/confirm"
        )
        self.assertEqual(
            adapter.semantic_id_for("DORM_FEED_CANCEL"),
            "dorm/empty-food/cancel",
        )
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("BUILD_CHECK"))

        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["research/page/back"] = True
        self.assertFalse(adapter.appear(NamedButton("RESEARCH_CHECK")))

    def test_retained_dorm_summary_classifies_next_task_page_sweep(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = False
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_CHECK")))
        oracle.dorm_state = Mock(side_effect=SemanticGateClosed("foreign blocker"))
        self.assertFalse(adapter.appear(NamedButton("DORM_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("FLEET_CHECK"))

    def test_navigation_main_withdraw_confirmation_probe_is_absent(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.main_page_visible_value = True
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM")))
        oracle.main_page_visible_value = False
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM"))

    def test_meow_return_withdraw_probe_keeps_foreign_blocker_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._meowfficer_return_transition_until = time.monotonic() + 12
        oracle._blocking_rules = Mock(return_value=[SimpleNamespace(blocker_id="meowfficer-dock")])
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM")))
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))
        for name in ("MAP_PREPARATION", "FLEET_PREPARATION", "RAID_FLEET_PREPARATION",
                     "AUTO_SEARCH_MENU_EXIT", "AUTO_SEARCH_REWARD", "WITHDRAW"):
            self.assertFalse(adapter.appear(NamedButton(name)))
        oracle._blocking_rules = Mock(return_value=[SimpleNamespace(blocker_id="msgbox")])
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM"))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("GET_ITEMS_1"))

    def test_dorm_page_check_keeps_owned_page_visible_under_empty_food_modal(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = False
        oracle.dorm_empty_food_cancel_value = True

        self.assertTrue(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        receipt = adapter.click(NamedButton("DORM_FEED_CANCEL"))

        self.assertEqual(receipt.semantic_id, "dorm/empty-food/cancel")

    def test_dorm_page_check_treats_incomplete_empty_food_probe_as_absent(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = False

        def incomplete_empty_food_modal():
            raise SemanticGateClosed("dorm empty-food snapshots are incomplete")

        oracle.dorm_empty_food_cancel_available = incomplete_empty_food_modal

        self.assertTrue(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("DORM_FEED_CANCEL")))

    def test_dorm_page_check_yields_to_statistics_confirm(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.exists_values["dorm/statistics/confirm"] = True
        oracle.enabled_values["dorm/feed/close"] = False
        oracle.enabled_values["dorm/statistics/confirm"] = True
        self.assertFalse(adapter.appear(NamedButton("DORM_CHECK")))
        for name in ("GOTO_MAIN", "GOTO_MAIN_WHITE", "RPG_HOME"):
            self.assertFalse(adapter.appear(NamedButton(name)))
        self.assertTrue(adapter.appear(NamedButton("DORM_INFO")))
        receipt = adapter.click(NamedButton("DORM_INFO"))
        self.assertEqual(receipt.semantic_id, "dorm/statistics/confirm")

    def test_dorm_page_check_yields_to_feed_panel_close(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm/page/manage"] = True
        oracle.enabled_values["dorm/feed/close"] = True

        self.assertFalse(adapter.appear(NamedButton("DORM_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        receipt = adapter.click(NamedButton("DORM_FEED_CANCEL"))

        self.assertEqual(receipt.semantic_id, "dorm/feed/close")

    def test_dorm_feed_entry_suppresses_only_transition_close(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["dorm/feed/close"] = False

        entry = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertGreater(
            adapter._dorm_context.passive_transition_until,
            time.monotonic() + 40.0,
        )
        oracle.enabled_values["dorm/feed/close"] = True
        self.assertFalse(adapter.appear(NamedButton("DORM_FEED_CANCEL")))
        duplicate = adapter.click(NamedButton("DORM_FEED_ENTER"))

        self.assertEqual(duplicate, entry)
        self.assertEqual(oracle.click_calls, ["dorm/feed"])

        self.assertTrue(adapter.appear(NamedButton("DORM_FEED_CHECK")))
        close = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertEqual(close.semantic_id, "dorm/feed/close")
        self.assertEqual(oracle.click_calls, ["dorm/feed", "dorm/feed/close"])

    def test_dorm_empty_food_cancel_allows_a_fresh_entry(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["dorm/feed/close"] = False

        adapter.click(NamedButton("DORM_FEED_ENTER"))
        duplicate = adapter.click(NamedButton("DORM_FEED_ENTER"))
        self.assertEqual(duplicate.semantic_id, "dorm/feed")
        self.assertEqual(oracle.click_calls, ["dorm/feed"])

        oracle.dorm_empty_food_cancel_value = True
        adapter.click(NamedButton("DORM_FEED_CANCEL"))
        oracle.dorm_empty_food_cancel_value = False
        adapter.click(NamedButton("DORM_FEED_ENTER"))

        self.assertEqual(
            oracle.click_calls,
            ["dorm/feed", "dorm/empty-food/cancel", "dorm/feed"],
        )

    def test_build_and_dorm_typed_state_is_exposed_without_mutation(self):
        adapter, oracle, _ = self.make_adapter()

        self.assertEqual(adapter.build_selected_pool(), BuildPool.LIGHT)
        self.assertEqual(adapter.build_costs().cubes_owned, 10)
        self.assertEqual(adapter.dorm_state().occupied_slots, 2)
        self.assertEqual(oracle.click_calls, [])

    def test_dorm_feed_budget_requires_inventory_and_food_mutation_proof(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 1)

        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].semantic_id, "dorm/feed/item/50001")
        self.assertEqual(adapter._action_ledger.remaining("dorm.feed"), 0)
        self.assertEqual(oracle.dorm_feed_state_value.food, 1000)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 4)
        with self.assertRaises(SemanticGateClosed):
            adapter.dorm_feed_food(0, 1)

    def test_dorm_feed_refreshes_an_immutable_frame_for_each_card_boundary(self):
        oracle = FakeOracle()
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=2,
            frame_observation_oracle=lambda: oracle,
            input_frame_refresher=refresh,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 2)

        self.assertEqual(len(receipts), 2)
        self.assertEqual(refresh.call_count, 4)
        self.assertEqual(
            oracle.click_calls,
            ["dorm/feed/item/50001", "dorm/feed/item/50001"],
        )
        self.assertEqual(oracle.dorm_feed_state_value.food, 2000)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 3)

    def test_fresh_feed_waits_for_panel_identity_without_input(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        refresh = Mock()
        adapter._input_frame_refresher = refresh
        adapter._frame_observation_oracle = lambda: oracle
        oracle.dorm_feed_state = Mock(side_effect=[
            SemanticGateClosed("dorm feed panel identity is not proven"),
            oracle.dorm_feed_state_value,
        ])
        oracle.click = Mock()
        with patch("alas_headless.adapter.semantic.dorm.time.sleep"):
            self.assertEqual(adapter._fresh_dorm_feed_state(), oracle.dorm_feed_state_value)
        self.assertEqual(refresh.call_count, 2)
        oracle.click.assert_not_called()

    def test_fresh_feed_keeps_other_errors_and_persistent_cover_closed(self):
        for message in ("dorm feed capacity is malformed", "dorm feed panel identity is not proven"):
            adapter, oracle, _ = self.make_adapter()
            adapter.begin_dorm()
            adapter._input_frame_refresher = Mock()
            adapter._frame_observation_oracle = lambda: oracle
            oracle.dorm_feed_state = Mock(side_effect=SemanticGateClosed(message))
            oracle.click = Mock()
            with patch("alas_headless.adapter.semantic.dorm.time.monotonic", side_effect=[0, 6]):
                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter._fresh_dorm_feed_state()
            oracle.click.assert_not_called()

    def test_dorm_feed_postcondition_tolerates_transient_card_animation(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()
        original = oracle.dorm_feed_state
        transient = {"raised": False}

        def flaky_state():
            if oracle.click_calls and not transient["raised"]:
                transient["raised"] = True
                raise SemanticGateClosed("dorm feed item image is absent or ambiguous")
            return original()

        oracle.dorm_feed_state = flaky_state
        receipts = adapter.dorm_feed_food(0, 1)

        self.assertTrue(transient["raised"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.click_calls, ["dorm/feed/item/50001"])

    def test_dorm_feed_precondition_waits_for_stable_panel(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()
        original = oracle.dorm_feed_state
        transient = {"raised": False}

        def flaky_state():
            if not transient["raised"]:
                transient["raised"] = True
                raise SemanticGateClosed("dorm feed panel identity is not proven")
            return original()

        oracle.dorm_feed_state = flaky_state
        receipts = adapter.dorm_feed_food(0, 1)

        self.assertTrue(transient["raised"])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.click_calls, ["dorm/feed/item/50001"])

    def test_dorm_feed_state_waits_for_complete_typed_panel(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        original = oracle.dorm_feed_state
        attempts = 0

        def flaky_state():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise SemanticGateClosed("dorm feed panel identity is not proven")
            return original()

        oracle.dorm_feed_state = flaky_state
        state = adapter.dorm_feed_state()

        self.assertEqual(state.food, 0)
        self.assertEqual(attempts, 3)

    def test_dorm_furniture_gold_purchase_uses_shop_authority(self):
        oracle = FakeOracle()
        oracle.dorm_furniture_purchase_state = lambda: SimpleNamespace(
            gold_price=150,
            quantity=1,
        )
        oracle.dorm_furniture_shop_balance = lambda: SimpleNamespace(
            dorm_coins=4512,
            gems=5422,
        )
        oracle.click_dorm_furniture_purchase = lambda currency: oracle.click_receipt(
            "dorm/furniture/purchase/" + currency
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.buy_dorm_furniture_with_gold()

        self.assertEqual(receipt.semantic_id, "dorm/furniture/purchase/gold")
        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.buy_dorm_furniture_with_gold()

    def test_dorm_furniture_theme_purchase_uses_shop_authority(self):
        oracle = FakeOracle()
        oracle.dorm_furniture_theme_purchase_state = lambda: SimpleNamespace(
            gold_price=1330,
        )
        oracle.dorm_furniture_shop_balance = lambda: SimpleNamespace(
            dorm_coins=4693,
            gems=5022,
        )
        oracle.click_dorm_furniture_theme_purchase_gold = lambda: oracle.click_receipt(
            "dorm/furniture/theme/purchase/gold"
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            shop_purchase_budget=1,
        )

        receipt = adapter.buy_dorm_furniture_theme_with_gold()

        self.assertEqual(receipt.semantic_id, "dorm/furniture/theme/purchase/gold")
        self.assertEqual(receipt.capability_id, "shop.purchase")
        self.assertEqual(adapter._action_ledger.remaining("shop.purchase"), 0)

    def test_dorm_furniture_flow_clears_exact_empty_food_popup_before_shop(self):
        oracle = FakeOracle()
        oracle.dorm_empty_food_cancel_value = True
        oracle.click_dorm_furniture_shop = Mock(
            side_effect=SemanticGateClosed("stop after proved popup recovery")
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None)

        with patch("alas_headless.alas_adapter.time.sleep"), self.assertRaises(
            SemanticGateClosed
        ):
            adapter.run_current_dorm_furniture_purchase("set")

        self.assertEqual(oracle.click_calls, ["dorm/empty-food/cancel"])
        oracle.click_dorm_furniture_shop.assert_called_once_with()

    def test_dorm_furniture_theme_flow_preserves_set_and_all_options(self):
        for buy_option in ("set", "all"):
            with self.subTest(buy_option=buy_option):
                oracle = FakeOracle()
                calls = []
                balances = iter((4693, 4693, 3363))
                oracle.dorm_empty_food_cancel_value = False
                oracle.click_dorm_furniture_shop = lambda: calls.append("shop")
                oracle.click_dorm_furniture_tag = lambda index: calls.append(
                    "tag:{0}".format(index)
                )
                oracle.click_dorm_furniture_theme = lambda index: calls.append(
                    "theme:{0}".format(index)
                )
                oracle.click_dorm_furniture_theme_details = lambda: calls.append(
                    "details"
                )
                oracle.dorm_furniture_theme_is_time_limited = lambda: True
                oracle.click_dorm_furniture_theme_purchase_option = (
                    lambda option: calls.append("option:" + option)
                )
                oracle.dorm_furniture_theme_purchase_state = lambda: SimpleNamespace(
                    gold_price=1330
                )
                oracle.dorm_state_value = SimpleNamespace(floor=1)
                oracle.dorm_furniture_shop_balance = lambda: SimpleNamespace(
                    dorm_coins=next(balances), gems=5022
                )
                oracle.click_dorm_furniture_theme_purchase_gold = (
                    lambda: oracle.click_receipt(
                        "dorm/furniture/theme/purchase/gold"
                    )
                )
                oracle.close_dorm_furniture_theme_details = lambda: calls.append(
                    "theme-back"
                )
                oracle.close_dorm_furniture_shop = lambda: calls.append("shop-back")
                oracle._retry_transition_read = lambda reader, **_: reader()
                adapter = AlasSemanticAdapter(
                    oracle,
                    lambda: None,
                    shop_purchase_budget=1,
                )

                with patch("alas_headless.alas_adapter.time.sleep"):
                    receipts = adapter.run_current_dorm_furniture_purchase(buy_option)

                self.assertEqual(len(receipts), 1)
                self.assertEqual(receipts[0].capability_id, "shop.purchase")
                self.assertIn("option:" + buy_option, calls)
                self.assertEqual(calls[-2:], ["theme-back", "shop-back"])

    def test_dorm_feed_proof_allows_only_bounded_ship_consumption(self):
        oracle = FakeOracle()
        original_click = oracle.click_dorm_food

        def click_with_one_consumption_tick(item_id):
            receipt = original_click(item_id)
            state = oracle.dorm_feed_state_value
            oracle.dorm_feed_state_value = SimpleNamespace(
                food=state.food - 18,
                capacity=state.capacity,
                items=state.items,
            )
            return receipt

        oracle.click_dorm_food = click_with_one_consumption_tick
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            dorm_feed_budget=1,
        )
        adapter.begin_dorm()

        receipts = adapter.dorm_feed_food(0, 1)

        self.assertEqual(len(receipts), 1)
        self.assertEqual(oracle.dorm_feed_state_value.food, 982)
        self.assertEqual(oracle.dorm_feed_state_value.items[0].count, 4)

    def test_dorm_navigation_is_idempotent_during_page_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()

        main = adapter.click(NamedButton("MAIN_GOTO_DORMMENU"))
        main_duplicate = adapter.click(NamedButton("MAIN_GOTO_DORMMENU_WHITE"))
        entry = adapter.click(NamedButton("DORMMENU_GOTO_DORM"))
        entry_duplicate = adapter.click(NamedButton("DORMMENU_GOTO_DORM"))
        back = adapter.click(NamedButton("DORM_GOTO_MAIN"))
        back_duplicate = adapter.click(NamedButton("DORM_GOTO_MAIN"))

        self.assertEqual(main_duplicate, main)
        self.assertEqual(entry_duplicate, entry)
        self.assertEqual(back_duplicate, back)
        self.assertEqual(
            oracle.click_calls,
            ["main/live", "dorm-menu/dorm", "dorm/page/back"],
        )

    def test_dorm_page_discovery_grace_covers_slow_device_startup(self):
        adapter, _, _ = self.make_adapter()
        before = time.monotonic()

        adapter.begin_dorm()

        self.assertGreaterEqual(
            adapter._dorm_context.passive_transition_until - before,
            59.0,
        )
        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))

    def test_dorm_can_recover_prior_game_room_through_typed_home(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.game_room_page_visible_value = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "game-room/home")
        self.assertEqual(oracle.click_calls, ["game-room/home"])

    def test_dorm_menu_overlay_owns_page_discovery_over_mounted_main(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["dorm-menu/page/root"] = True
        oracle.enabled_values["main/formation"] = True

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_FLEET")))
        self.assertTrue(adapter.appear(NamedButton("DORMMENU_CHECK")))

    def test_dorm_menu_overlay_owns_shared_page_discovery_without_flow_context(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["dorm-menu/page/root"] = True

        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DORMMENU_CHECK")))

    def test_dorm_generic_reward_probe_requires_exact_award_popup(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.enabled_values["reward/award-info/close"] = False
        oracle.enabled_values["reward/award-info1/close"] = False

        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))
        oracle.enabled_values["reward/award-info/close"] = True
        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_dorm_recovers_server_rollover_activity_through_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_dorm()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])
