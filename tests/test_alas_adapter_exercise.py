"""Exercise regression cases for the adapter."""

import unittest
import time
from alas_headless import AlasSemanticUnmapped
from alas_headless import SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_typed_main_or_reward_page_hides_exercise_page_check(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.main_page_visible_value = True
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

        oracle.main_page_visible_value = False
        oracle.enabled_values["reward/meta/enter"] = True
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_generic_back_leaves_exercise_page_through_exact_typed_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exercise_page_visible = lambda: True
        oracle.exists_values["exercise/page/back"] = True

        receipt = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(receipt.semantic_id, "exercise/page/back")
        self.assertEqual(oracle.click_calls, ["exercise/page/back"])
        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))
        oracle.campaign_menu_value = True
        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))

        oracle.campaign_menu_value = False
        adapter._exercise_page_back_transition_until = 0.0
        with self.assertRaisesRegex(AlasSemanticUnmapped, "DOCK_CHECK"):
            adapter.appear(NamedButton("DOCK_CHECK"))

    def test_campaign_menu_makes_exercise_page_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_campaign_chapter_makes_exercise_page_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

        oracle.campaign_page_value = False
        with self.assertRaisesRegex(AlasSemanticUnmapped, "EXERCISE_CHECK"):
            adapter.appear(NamedButton("EXERCISE_CHECK"))

    def test_submitted_exercise_start_does_not_invite_second_click(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._exercise_execution_active = True
        adapter._exercise_pending = False
        adapter._exercise_start_transition_until = time.monotonic() + 15.0
        oracle.daily_precombat_visible = lambda: True

        self.assertFalse(adapter.appear(NamedButton("BATTLE_PREPARATION")))
        self.assertEqual(oracle.click_calls, [])

        adapter._exercise_start_transition_until = time.monotonic() - 1.0
        with self.assertRaisesRegex(SemanticGateClosed, "did not leave preparation"):
            adapter.appear(NamedButton("BATTLE_PREPARATION"))

    def test_chapter_back_only_leases_passive_page_scan(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        receipt = adapter.click(NamedButton("BACK_ARROW"))
        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        oracle.campaign_page_value = False
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("SP_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("FLEET_CHECK"))

        oracle.campaign_menu_value = True
        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))
        oracle.campaign_menu_value = False

        adapter._exercise_chapter_back_transition_until = 0.0
        with self.assertRaisesRegex(AlasSemanticUnmapped, "FLEET_CHECK"):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_exercise_entry_only_leases_absent_reward_probe(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True
        oracle.click_campaign_exercise_entrance = lambda: oracle.click("campaign-menu/exercise")

        receipt = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_EXERCISE"))
        self.assertEqual(receipt.semantic_id, "campaign-menu/exercise")
        oracle.campaign_menu_value = False
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_2")))
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_3")))
        self.assertFalse(adapter.appear(NamedButton("GET_SHIP")))
        self.assertFalse(adapter.appear(NamedButton("DOCK_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.enabled_values["reward/award-info/close"] = True
        with self.assertRaisesRegex(AlasSemanticUnmapped, "GET_ITEMS_1"):
            adapter.appear(NamedButton("GET_ITEMS_1"))
        oracle.enabled_values["reward/award-info/close"] = False
        with self.assertRaisesRegex(SemanticGateClosed, "outside ALAS mission flow"):
            adapter.click(NamedButton("GET_ITEMS_1"))

        adapter._exercise_entry_transition_until = 0.0
        oracle.exercise_page_visible = lambda: True
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.exercise_page_visible = lambda: False
        with self.assertRaisesRegex(AlasSemanticUnmapped, "GET_ITEMS_1"):
            adapter.appear(NamedButton("GET_ITEMS_1"))

    def test_chapter_entry_only_leases_absent_urgent_commission_probe(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True

        receipt = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_CAMPAIGN"))
        self.assertEqual(receipt.semantic_id, "campaign-menu/normal")
        oracle.campaign_menu_value = False
        self.assertFalse(adapter.appear(NamedButton("GET_MISSION")))
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_2")))

        oracle._campaign_urgent_notice_matches = lambda state: True
        with self.assertRaisesRegex(SemanticGateClosed, "urgent commission notice"):
            adapter.appear(NamedButton("GET_MISSION"))

        oracle._campaign_urgent_notice_matches = lambda state: False
        adapter._exercise_chapter_entry_transition_until = 0.0
        oracle.campaign_page_value = True
        self.assertFalse(adapter.appear(NamedButton("GET_MISSION")))
        oracle.campaign_page_value = False
        with self.assertRaisesRegex(AlasSemanticUnmapped, "GET_MISSION"):
            adapter.appear(NamedButton("GET_MISSION"))

    def test_stable_chapter_hides_unrelated_optional_popup_probe(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True

        self.assertFalse(adapter.appear(NamedButton("MONTHLY_PASS_NOTICE")))
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))

        oracle.campaign_page_value = False
        with self.assertRaisesRegex(AlasSemanticUnmapped, "MONTHLY_PASS_NOTICE"):
            adapter.appear(NamedButton("MONTHLY_PASS_NOTICE"))
