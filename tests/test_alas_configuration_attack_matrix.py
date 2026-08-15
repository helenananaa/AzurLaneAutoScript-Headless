import ast
import unittest
from pathlib import Path

from alas_headless.alas_configuration_attack_matrix import (
    FIXED_SEED,
    verify_configuration_attack_matrix,
)


ROOT = Path(__file__).resolve().parents[1]
CLEAN_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasConfigurationAttackMatrixTests(unittest.TestCase):
    def test_clean_pinned_upstream_matrix_is_deterministic_and_zero_input(self):
        if not CLEAN_UPSTREAM.joinpath("module/config/config.py").is_file():
            self.skipTest("clean pinned ALAS checkout is unavailable")
        result = verify_configuration_attack_matrix(CLEAN_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["seed"], FIXED_SEED)
        self.assertGreater(result["campaign_pairwise_case_count"], 0)
        self.assertGreater(result["scheduler_pairwise_case_count"], 0)
        self.assertEqual(result["seeded_sequence_count"], 32)
        self.assertGreaterEqual(result["invalid_case_count"], 8)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])
        self.assertFalse(result["pixel_fallback_used"])
        self.assertEqual(
            set(result["original_method_replays"]),
            {
                "scheduler",
                "fleet",
                "hp_control",
                "emotion",
                "submarine",
                "event_general",
                "optimization",
            },
        )

    def test_attack_matrix_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_configuration_attack_matrix.py",
            "scripts/python/verify_alas_configuration_attack_matrix.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
