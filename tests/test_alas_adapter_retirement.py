"""Retirement regression cases for the adapter."""

import unittest
from alas_headless import SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_official_retirement_budget_is_single_use_and_receipted(self):
        adapter, oracle, gate_calls = self.make_adapter(retirement_budget=1)

        retired = adapter.retire_ships_one_click(True)
        receipt = adapter.retirement_receipt()

        self.assertEqual(retired, 68)
        self.assertTrue(oracle.retirement_keep_limit_break)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(receipt.capability_id, "retirement.execute")
        self.assertEqual(len(receipt.policy_sha256), 64)
        self.assertEqual(adapter._action_ledger.remaining("retirement.execute"), 0)
        self.assertEqual(len(gate_calls), 1)
        with self.assertRaises(SemanticGateClosed):
            adapter.retire_ships_one_click(True)

    def test_official_retirement_is_default_denied(self):
        adapter, _, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "positive transaction budget"):
            adapter.retire_ships_one_click(True)
