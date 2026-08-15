import ast
import unittest
from pathlib import Path

from alas_headless.alas_coalition_config_contract import (
    COALITION_FLEETS,
    COALITION_MODES,
    validate_alas_coalition_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_coalition_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasCoalitionConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/coalition/coalition.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["accepted_case_count"], 8)
        self.assertEqual(result["invalid_case_count"], 14)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_exact_declared_pairs_are_admitted(self):
        for mode in COALITION_MODES:
            for fleet in COALITION_FLEETS:
                with self.subTest(mode=mode, fleet=fleet):
                    snapshot = validate_alas_coalition_config(mode=mode, fleet=fleet)
                    self.assertEqual((snapshot.mode, snapshot.fleet), (mode, fleet))

    def test_invalid_settings_fail_closed(self):
        for mode, fleet in (
            ("HARD", "single"),
            (True, "single"),
            ("hard", "SINGLE"),
            ("hard", 0),
        ):
            with self.subTest(mode=mode, fleet=fleet), self.assertRaises(SemanticGateClosed):
                validate_alas_coalition_config(mode=mode, fleet=fleet)

    def test_patch_gates_before_coalition_override_or_combat_preparation(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0175-coalition-config-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_coalition_config("), 3)
        self.assertLess(
            patch.index("validate_alas_coalition_config("),
            patch.index("self.config.override("),
        )
        self.assertLess(
            patch.rindex("validate_alas_coalition_config("),
            patch.index("self.combat_preparation("),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_coalition_config_contract.py",
            "python/alas_headless/alas_coalition_config_replay.py",
            "scripts/python/verify_alas_coalition_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
