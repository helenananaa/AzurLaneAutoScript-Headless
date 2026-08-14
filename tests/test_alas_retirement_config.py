import ast
import unittest
from pathlib import Path

from alas_headless.alas_retirement_config_contract import (
    RETIREMENT_MODES,
    validate_alas_retirement_config,
)
from alas_headless.alas_retirement_config_replay import verify_retirement_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasRetirementConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/retire/retirement.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_retirement_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 1)
        self.assertEqual(result["accepted_case_count"], 3)
        self.assertEqual(result["invalid_case_count"], 7)
        self.assertEqual(
            result["semantic_admission"],
            {"one_click_retire": True, "enhance": True, "old_retire": False},
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_retirement_performed"])
        self.assertFalse(result["real_enhancement_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_all_declared_modes_are_classified(self):
        snapshots = {
            mode: validate_alas_retirement_config(mode=mode)
            for mode in RETIREMENT_MODES
        }
        self.assertTrue(snapshots["one_click_retire"].semantic_admitted)
        self.assertTrue(snapshots["enhance"].semantic_admitted)
        self.assertFalse(snapshots["old_retire"].semantic_admitted)
        with self.assertRaises(SemanticGateClosed):
            snapshots["old_retire"].require_semantic_entry()

    def test_invalid_modes_fail_closed(self):
        for value in (None, True, 1, "", "unknown", [], {}):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_retirement_config(mode=value)

    def test_patch_gates_original_retirement_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0120-retirement-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_retirement_config("), 1)
        self.assertEqual(patch.count("retirement_config.require_semantic_entry()"), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_retirement_config_contract.py",
            "python/alas_headless/alas_retirement_config_replay.py",
            "scripts/python/verify_alas_retirement_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
