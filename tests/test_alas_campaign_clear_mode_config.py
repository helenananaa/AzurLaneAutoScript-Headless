import ast
import unittest
from pathlib import Path

from alas_headless.alas_campaign_clear_mode_config_contract import (
    validate_alas_campaign_clear_mode_config,
)
from alas_headless.alas_campaign_clear_mode_config_replay import (
    verify_campaign_clear_mode_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasCampaignClearModeConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/handler/fast_forward.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_campaign_clear_mode_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 1)
        self.assertEqual(result["panel_count"], 16)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_both_boolean_values_are_classified(self):
        self.assertFalse(
            validate_alas_campaign_clear_mode_config(
                use_clear_mode=False
            ).use_clear_mode
        )
        self.assertTrue(
            validate_alas_campaign_clear_mode_config(
                use_clear_mode=True
            ).use_clear_mode
        )

    def test_non_boolean_values_fail_closed(self):
        for value in (0, 1, None, "true", [], {}):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_campaign_clear_mode_config(use_clear_mode=value)

    def test_patch_gates_original_clear_mode_method(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0110-stop-condition-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            patch.count("self._validate_campaign_clear_mode_config()"), 1
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_campaign_clear_mode_config_contract.py",
            "python/alas_headless/alas_campaign_clear_mode_config_replay.py",
            "scripts/python/verify_alas_campaign_clear_mode_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
