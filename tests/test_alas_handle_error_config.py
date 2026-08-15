import ast
import unittest
from pathlib import Path

from alas_headless.alas_handle_error_config_contract import (
    validate_alas_handle_error_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_handle_error_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasHandleErrorConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/device/device.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 1)
        self.assertEqual(result["accepted_case_count"], 2)
        self.assertEqual(result["invalid_case_count"], 7)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertEqual(result["app_restart_requests"], 0)
        self.assertEqual(result["withdrawal_requests"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_only_boolean_values_are_admitted(self):
        self.assertIs(validate_alas_handle_error_config(True), True)
        self.assertIs(validate_alas_handle_error_config(False), False)
        for value in (None, 0, "true", []):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_handle_error_config(value)

    def test_all_direct_reads_are_guarded(self):
        core = ROOT.joinpath("integration/alas/series/0002-session-lifecycle.patch").read_text(
            encoding="utf-8"
        )
        combat = ROOT.joinpath("integration/alas/series/0050-combat-flow-ports.patch").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            core.count("validate_alas_handle_error_config(self.config.Error_HandleError)"),
            2,
        )
        self.assertEqual(
            combat.count("validate_alas_handle_error_config(self.config.Error_HandleError)"),
            2,
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_handle_error_config_contract.py",
            "python/alas_headless/alas_handle_error_config_replay.py",
            "scripts/python/verify_alas_handle_error_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
