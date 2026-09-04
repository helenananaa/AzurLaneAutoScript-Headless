"""Exercise regression cases for the adapter."""

import unittest
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

    def test_campaign_menu_makes_exercise_page_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
