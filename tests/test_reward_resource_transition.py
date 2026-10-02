"""Resource presence retries remain passive and bounded by ALAS screenshots."""
import unittest
from unittest.mock import Mock, patch
from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import SemanticTargetMissing
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


class RewardResourceTransitionTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_mission_popup_disappearance_is_missing_but_coverage_remains_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mission_reward(daily=True, weekly=False)
        oracle.enabled_values = {"task/page/back": True,
            "reward/award-info/close": False, "reward/award-info1/close": False}
        with self.assertRaises(SemanticTargetMissing):
            adapter._click_mission("GET_ITEMS_1")
        oracle.exists_values = {"reward/award-info/close": True}
        with self.assertRaises(SemanticGateClosed):
            adapter._click_mission("GET_ITEMS_1")
        self.assertEqual(oracle.click_calls, [])

    def test_covered_close_yields_then_recovers_without_input(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._appear_once = Mock(side_effect=[
            SemanticGateClosed("reward resource page close is temporarily covered"), True])
        with patch("alas_headless.adapter.semantic.observation.time.monotonic", return_value=100):
            self.assertFalse(adapter.appear(NamedButton("COIN")))
        self.assertTrue(adapter.appear(NamedButton("COIN")))
        self.assertIsNone(adapter._observer_stale_since)
        self.assertEqual(oracle.click_calls, [])

    def test_exact_loading_resource_probe_waits_but_unknown_blocker_stays_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._appear_once = Mock(side_effect=SemanticGateClosed(
            "reward resource page identity is not proven: blockers=loading"))
        with patch("alas_headless.adapter.semantic.observation.time.monotonic", return_value=100):
            self.assertFalse(adapter.appear(NamedButton("EXP")))
        with patch("alas_headless.adapter.semantic.observation.time.monotonic", return_value=106):
            with self.assertRaises(SemanticGateClosed):
                adapter.appear(NamedButton("EXP"))
        adapter._appear_once = Mock(side_effect=SemanticGateClosed(
            "reward resource page identity is not proven: blockers=loading,msgbox"))
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("EXP"))
        self.assertEqual(oracle.click_calls, [])

    def test_persistent_coverage_expires_and_foreign_blocker_is_not_transient(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._appear_once = Mock(side_effect=SemanticGateClosed(
            "reward resource page close is temporarily covered"))
        with patch("alas_headless.adapter.semantic.observation.time.monotonic", return_value=100):
            self.assertFalse(adapter.appear(NamedButton("COIN")))
        with patch("alas_headless.adapter.semantic.observation.time.monotonic", return_value=106):
            with self.assertRaises(SemanticGateClosed):
                adapter.appear(NamedButton("COIN"))
        adapter._appear_once = Mock(side_effect=SemanticGateClosed(
            "reward resource page identity is not proven"))
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("COIN"))
        self.assertEqual(oracle.click_calls, [])
