import ast
import unittest
from pathlib import Path

from alas_headless.alas_hard_config_contract import (
    HARD_STAGES,
    validate_alas_hard_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_hard_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasHardConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/hard/hard.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["catalog_count"], 64)
        self.assertEqual(result["accepted_case_count"], 68)
        self.assertEqual(result["invalid_case_count"], 17)
        self.assertEqual(
            result["original_decisions"]["fleet_one"]["campaign_runs"], 3
        )
        self.assertEqual(
            result["original_decisions"]["fleet_two"]["campaign_runs"], 0
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_all_pinned_stage_modules_and_both_fleets_are_accepted(self):
        self.assertEqual(len(HARD_STAGES), 64)
        for stage in HARD_STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(
                    validate_alas_hard_config(
                        hard_stage=stage, hard_fleet=1
                    ).hard_stage,
                    stage,
                )
        self.assertEqual(
            validate_alas_hard_config(hard_stage="11-4", hard_fleet=2).hard_fleet,
            2,
        )

    def test_supported_original_spellings_are_canonicalized(self):
        for value in (" campaign_11_4 ", "11_4", "011-04"):
            with self.subTest(value=value):
                self.assertEqual(
                    validate_alas_hard_config(
                        hard_stage=value, hard_fleet=1
                    ).hard_stage,
                    "11-4",
                )

    def test_invalid_stage_and_fleet_values_fail_closed(self):
        for field, value in (
            ("stage", "17-1"),
            ("stage", "1-5"),
            ("stage", "campaign_1_1junk"),
            ("stage", None),
            ("fleet", 0),
            ("fleet", 3),
            ("fleet", True),
            ("fleet", "1"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_hard_config(
                    hard_stage=value if field == "stage" else "11-4",
                    hard_fleet=value if field == "fleet" else 1,
                )

    def test_patch_gates_before_semantic_scope_and_original_run(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0080-current-task-flow-ports.patch"
        ).read_text(encoding="utf-8")
        guard = patch.index("hard_config = validate_alas_hard_config(")
        scope = patch.index("semantic_adapter.begin_campaign_pre_sortie(", guard)
        run = patch.index("return self._run_hard(", scope)
        self.assertLess(guard, scope)
        self.assertLess(scope, run)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_hard_config_contract.py",
            "python/alas_headless/alas_hard_config_replay.py",
            "scripts/python/verify_alas_hard_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
