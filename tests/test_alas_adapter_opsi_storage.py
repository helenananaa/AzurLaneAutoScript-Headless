"""Opsi storage regression cases for the adapter."""

import unittest
from alas_headless import SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_operation_siren_storage_checkout_owns_exact_exit_confirmation(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_exit_prompt_visible = lambda: True

        self.assertTrue(adapter.operation_siren_storage_checkout_prompt_visible())
        receipt = adapter.click_operation_siren_storage_checkout_confirm()

        self.assertEqual(receipt.semantic_id, "os/exit/confirm")
        self.assertEqual(oracle.click_calls, ["os/exit/confirm"])
        self.assertGreater(adapter._operation_siren_entry_transition_until, 0.0)

        oracle.operation_siren_exit_prompt_visible = lambda: False
        with self.assertRaisesRegex(
            SemanticGateClosed,
            "operation siren exit prompt is absent",
        ):
            adapter.click_operation_siren_storage_checkout_confirm()
