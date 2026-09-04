"""Rewards regression cases for the adapter."""

import time
import unittest
from alas_headless import AlasSemanticUnmapped, MissionDisposition, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_alas_owned_reward_popup_alias_uses_exact_semantic_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_alas_owned_reward_popup_alias_rejects_ambiguity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": True,
        }
        adapter.begin_mission_reward(daily=True, weekly=False)

        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("GET_ITEMS_1"))
        self.assertEqual(oracle.click_calls, [])

    def test_weekly_progress_claim_closes_deferred_new_ship_reward(self):
        adapter, oracle, _ = self.make_adapter(allow_mission_claim_once=True)
        oracle.weekly_mission_progress_claim_available_value = True
        oracle.wait_any_results = [
            (
                "reward/award-info/close",
                SimpleNamespace(path="root/AwardInfoUI(Clone)/items/close"),
            ),
            (
                "reward/new-ship/continue",
                SimpleNamespace(path="root/NewShipUI(Clone)/shake_panel/click"),
            ),
            SemanticGateClosed("semantic wait timed out"),
        ]
        adapter.begin_mission_reward(daily=False, weekly=True)

        receipt = adapter.claim_weekly_mission_progress_once()

        self.assertEqual(receipt.semantic_id, "task/weekly-progress/claim")
        self.assertEqual(
            oracle.click_calls,
            [
                "task/weekly-progress/claim",
                "reward/award-info/close",
                "reward/new-ship/continue",
            ],
        )

    def test_reward_surface_owns_passive_page_scan_after_task_context_ends(self):
        adapter, oracle, _ = self.make_adapter()

        self.assertFalse(adapter.mission_reward_active())
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertTrue(adapter.mission_reward_active())
        oracle.exists_values["reward/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

        adapter.end_mission_reward()
        self.assertFalse(adapter.mission_reward_active())
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("FLEET_CHECK"))

    def test_reward_summary_entry_alias_is_idempotent(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mission_reward(daily=True, weekly=False)

        first = adapter.click(NamedButton("MAIN_GOTO_REWARD"))
        duplicate = adapter.click(NamedButton("MAIN_GOTO_REWARD_WHITE"))

        self.assertEqual(first, duplicate)
        self.assertEqual(oracle.click_calls, ["main/more"])

    def test_reward_hook_claim_requires_policy_and_call_opt_in(self):
        adapter, oracle, gate_calls = self.make_adapter(
            allow_mission_claim_once=True
        )
        oracle.mission_dispositions = [
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.UNFINISHED,
        ]

        receipt = adapter.run_mission_reward(
            timeout_seconds=12,
            allow_claim_once=True,
        )

        self.assertEqual(receipt.outcome, "claimed-all-once")
        self.assertEqual(receipt.claim_input_count, 1)
        self.assertIn("task/claim/all", oracle.click_calls)
        self.assertEqual(len(gate_calls), 1)

    def test_reward_hook_call_opt_in_cannot_bypass_zero_input_policy(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.mission_dispositions = [MissionDisposition.CLAIMABLE_ALL]

        with self.assertRaises(SemanticGateClosed):
            adapter.run_mission_reward(
                timeout_seconds=12,
                allow_claim_once=True,
            )

        self.assertEqual(oracle.click_calls, ["main/task"])

    def test_battle_pass_context_claims_only_reviewed_claim_all(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.battle_pass_reward_available_value = True
        oracle.battle_pass_claim_available_value = True
        adapter.begin_battle_pass()

        self.assertTrue(adapter.appear(NamedButton("REWARD_GOTO_BATTLE_PASS")))
        entrance = adapter.click(NamedButton("REWARD_GOTO_BATTLE_PASS"))
        self.assertEqual(entrance.semantic_id, "reward/battle-pass/enter")
        self.assertTrue(adapter.appear(NamedButton("BATTLE_PASS_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("REWARD_RECEIVE_WHITE")))
        claim = adapter.click(NamedButton("REWARD_RECEIVE_WHITE"))
        self.assertEqual(claim.semantic_id, "battle-pass/claim-all")
        self.assertFalse(adapter.appear(NamedButton("REWARD_RECEIVE_WHITE")))
        with self.assertRaisesRegex(SemanticGateClosed, "outside the reviewed"):
            adapter.click(NamedButton("REWARD_RECEIVE_SP"))

    def test_battle_pass_page_recovers_through_exact_home(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.battle_pass_page_visible_value = True
        adapter.begin_battle_pass()

        self.assertTrue(adapter.appear(NamedButton("BATTLE_PASS_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "battle-pass/home")
        self.assertFalse(oracle.battle_pass_page_visible_value)

        # A delayed page transition must be idempotent rather than dispatching
        # another input after the reviewed target has already unmounted.
        self.assertIs(adapter.click(NamedButton("GOTO_MAIN")), receipt)

    def test_supply_pack_click_admits_only_exact_free_card(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.recommendation_shop_visible_value = True
        oracle.gift_pack_page_visible_value = True
        oracle.free_weekly_supply_pack_available_value = True
        adapter.begin_supply_pack()

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("SHOP_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("FREE_SUPPLY_PACK")))
        receipt = adapter.click(NamedButton("FREE_SUPPLY_PACK"))

        self.assertEqual(receipt.semantic_id, "shop/free-weekly-pack")
        self.assertFalse(adapter.appear(NamedButton("FREE_SUPPLY_PACK")))
        with self.assertRaisesRegex(SemanticGateClosed, "confirmation"):
            adapter.click(NamedButton("BUY_CONFIRM"))

    def test_data_key_limit_confirm_requires_force_and_preceding_claim(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.war_archives_visible_value = True
        oracle.enabled_values.update(
            {
                "reward/award-info/close": False,
                "reward/award-info1/close": False,
            }
        )
        adapter.begin_data_key(force_collect=True)

        claim = adapter.click(NamedButton("DATA_KEY_COLLECT"))
        oracle.data_key_limit_prompt_value = True

        self.assertEqual(claim.semantic_id, "archive/key/collect")
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        confirm = adapter.click(NamedButton("POPUP_CONFIRM_DATA_KEY_LIMIT"))
        self.assertEqual(confirm.semantic_id, "archive/key-limit/confirm")
        oracle.war_archives_visible_value = False
        self.assertFalse(adapter.appear(NamedButton("DATA_KEY_COLLECT")))
        self.assertFalse(adapter.appear(NamedButton("DATA_KEY_COLLECTED")))

        adapter.end_data_key()
        oracle.war_archives_collected_value = False
        oracle.data_key_limit_prompt_value = True
        adapter.begin_data_key(force_collect=False)
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))
        with self.assertRaisesRegex(SemanticGateClosed, "ForceCollect"):
            adapter.click(NamedButton("POPUP_CONFIRM"))

    def test_data_key_navigation_closes_only_exact_award_popup(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values.update(
            {
                "reward/award-info/close": True,
                "reward/award-info1/close": False,
            }
        )
        adapter.begin_data_key(force_collect=True)

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

        navigation_receipt = adapter.click(
            NamedButton("CAMPAIGN_MENU_GOTO_WAR_ARCHIVES")
        )
        self.assertEqual(
            navigation_receipt.semantic_id, "reward/award-info/close"
        )

        adapter._data_key_context.passive_transition_until = time.monotonic() - 1
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        adapter.end_data_key()
        with self.assertRaisesRegex(AlasSemanticUnmapped, "FLEET_CHECK"):
            adapter.appear(NamedButton("FLEET_CHECK"))
