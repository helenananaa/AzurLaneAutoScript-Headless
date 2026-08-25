import ast
import itertools
import json
import unittest
from pathlib import Path

from alas_headless.alas_data_key_config_contract import (
    validate_alas_data_key_config,
)
from alas_headless.alas_data_key_config_replay import verify_data_key_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasDataKeyConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/freebies/data_key.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_data_key_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["accepted_case_count"], 4)
        self.assertEqual(result["invalid_case_count"], 12)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_collect_method_called"])
        self.assertFalse(result["android_input_injected"])

    def test_all_boolean_combinations_are_classified(self):
        for collect, force_collect in itertools.product((False, True), repeat=2):
            with self.subTest(collect=collect, force_collect=force_collect):
                snapshot = validate_alas_data_key_config(
                    collect=collect,
                    force_collect=force_collect,
                )
                self.assertEqual(
                    (snapshot.collect, snapshot.force_collect),
                    (collect, force_collect),
                )

    def test_invalid_single_fields_fail_closed(self):
        for field in ("collect", "force_collect"):
            for value in (0, 1, None, "true", [], {}):
                values = {"collect": True, "force_collect": False}
                values[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_data_key_config(**values)

    def test_patch_gates_original_freebies_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0080-current-task-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_data_key_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_data_key_config_contract.py",
            "python/alas_headless/alas_data_key_config_replay.py",
            "scripts/python/verify_alas_data_key_config.py",
            "scripts/python/run_alas_freebies_data_key_live_validation.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))

    def test_live_full_capacity_receipt_is_scoped_and_zero_claim(self):
        receipt = json.loads(
            ROOT.joinpath(
                "integration/alas/freebies-data-key-capacity-live-validation-receipt-20260825-r1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(receipt["passed"])
        self.assertTrue(receipt["task_result"])
        self.assertEqual(receipt["observations"], [
            {"kind": "collected", "value": False},
            {"kind": "counter", "value": "300/300"},
        ])
        self.assertEqual(receipt["collect_calls"], [])
        self.assertTrue(receipt["temporary_config_removed"])


if __name__ == "__main__":
    unittest.main()
