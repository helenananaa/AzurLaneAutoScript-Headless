import ast
import unittest
from pathlib import Path

from alas_headless.alas_equipment_code_config_contract import (
    validate_alas_equipment_code_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_equipment_code_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")


class AlasEquipmentCodeConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/equipment/equipment_code.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 1)
        self.assertEqual(result["accepted_case_count"], 5)
        self.assertEqual(result["invalid_case_count"], 8)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertEqual(result["config_writebacks"], 0)
        self.assertEqual(result["device_navigation"], 0)
        self.assertEqual(result["equipment_imports"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_valid_values_preserve_yaml_mapping_streams(self):
        self.assertEqual(
            validate_alas_equipment_code_config("---\nbogue: old\n---\nbogue: new\nDD: code-dd"),
            {"bogue": "new", "DD": "code-dd"},
        )

    def test_invalid_values_close_before_equipment_or_writeback(self):
        for value in (None, True, "[", "- item", "7: value"):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_equipment_code_config(value)

    def test_patch_gates_both_equipment_code_paths(self):
        patch = ROOT.joinpath("integration/alas/series/0001-core-ports.patch").read_text(
            encoding="utf-8"
        )
        self.assertEqual(patch.count("validate_alas_equipment_code_config("), 2)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_equipment_code_config_contract.py",
            "python/alas_headless/alas_equipment_code_config_replay.py",
            "scripts/python/verify_alas_equipment_code_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
