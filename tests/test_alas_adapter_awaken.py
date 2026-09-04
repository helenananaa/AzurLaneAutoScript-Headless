"""Awaken regression cases for the adapter."""

import unittest
from alas_headless import SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_awaken_level120_honours_favourite_and_single_use_budget(self):
        adapter, oracle, gate_calls = self.make_adapter(awaken_budget=1)

        completed = self.run_awaken_ports(adapter, "level120", True)
        receipts = adapter.awaken_receipts()

        self.assertEqual(completed, 1)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].current_level, 115)
        self.assertEqual(receipts[0].target_level, 120)
        self.assertEqual(receipts[0].capability_id, "awaken.execute")
        self.assertEqual(len(receipts[0].policy_sha256), 64)
        self.assertEqual(
            oracle.awaken_calls,
            [
                ("favourite", True),
                ("filter", False),
                ("candidates", False),
                ("open", 100003),
                ("modal", 100003),
                ("commit", 100003),
                ("back", False),
                ("reset", None),
            ],
        )
        self.assertEqual(adapter._action_ledger.remaining("awaken.execute"), 0)
        self.assertEqual(len(gate_calls), 1)

    def test_awaken_level125_prefers_array_candidates(self):
        adapter, oracle, _ = self.make_adapter(awaken_budget=1)

        self.assertEqual(self.run_awaken_ports(adapter, "level125", False), 1)

        receipt = adapter.awaken_receipts()[0]
        self.assertEqual((receipt.current_level, receipt.target_level), (120, 125))
        self.assertTrue(receipt.cost.use_array)
        self.assertEqual(
            oracle.awaken_calls[:5],
            [
                ("favourite", False),
                ("filter", True),
                ("candidates", True),
                ("open", 100004),
                ("modal", 100004),
            ],
        )

    def test_awaken_is_default_denied_before_navigation(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "positive transaction budget"):
            adapter.begin_awaken_task(False)

        self.assertEqual(oracle.awaken_calls, [])

    def test_awaken_insufficient_modal_cancels_without_consuming_grant(self):
        adapter, oracle, gate_calls = self.make_adapter(awaken_budget=1)
        oracle.awaken_sufficient = False

        self.assertEqual(self.run_awaken_ports(adapter, "level120", False), 0)

        self.assertEqual(adapter.awaken_receipts(), ())
        self.assertEqual(len(adapter.awaken_cost_observations()), 1)
        self.assertFalse(adapter.awaken_cost_observations()[0].sufficient)
        self.assertIn(("cancel", 100003), oracle.awaken_calls)
        self.assertEqual(adapter._action_ledger.remaining("awaken.execute"), 1)
        self.assertEqual(gate_calls, [True])
