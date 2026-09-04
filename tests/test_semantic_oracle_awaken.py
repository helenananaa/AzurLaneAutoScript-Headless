"""Awaken regression cases for the oracle."""

import dataclasses
import unittest
from alas_headless.semantic_oracle import (
    ActionReceipt,
    AwakenExecutionReceipt,
    Bounds,
    Point,
)
from tests.semantic_support.oracle_cases import AwakenSemanticStateTestsSupport


class AwakenSemanticStateTests(AwakenSemanticStateTestsSupport, unittest.TestCase):
    def test_awaken_cost_requires_every_exact_resource(self):
        self.assertTrue(self.cost().sufficient)
        self.assertFalse(self.cost(arrays_available=99).sufficient)
        chip_only = dataclasses.replace(
            self.cost(),
            current_level=115,
            target_level=120,
            arrays_available=None,
            arrays_required=None,
        )
        self.assertFalse(chip_only.use_array)
        self.assertTrue(chip_only.sufficient)

    def test_awaken_execution_receipt_requires_authoritative_completion(self):
        action = ActionReceipt(
            semantic_id="awaken/confirm/commit",
            generation=21,
            point=Point(100, 100),
            bounds=Bounds(50, 50, 150, 150),
            path="root/confirm",
        )
        with self.assertRaisesRegex(ValueError, "commit and completion"):
            AwakenExecutionReceipt(
                ship_id=100001,
                ship_name="fixture",
                current_level=120,
                target_level=125,
                observed_level=120,
                cost=self.cost(),
                actions=(action,),
            )
