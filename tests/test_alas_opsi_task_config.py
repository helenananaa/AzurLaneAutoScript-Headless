import ast
import unittest
from pathlib import Path

from alas_headless.alas_opsi_task_config_contract import (
    OPSI_MONTH_BOSS_MODES,
    validate_alas_opsi_daily_config,
    validate_alas_opsi_month_boss_config,
    validate_alas_opsi_obscure_config,
)
from alas_headless.alas_opsi_task_config_replay import verify_opsi_task_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasOpsiTaskConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/os/tasks/month_boss.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_opsi_task_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 4)
        self.assertEqual(result["accepted_case_count"], 8)
        self.assertEqual(result["invalid_case_count"], 25)
        self.assertEqual(
            result["zero_runtime_consumers"],
            {
                "OpsiExplore_ForceRun": [],
                "OpsiAbyssal_ForceRun": [],
                "OpsiMonthBoss_ForceRun": [],
                "OpsiDaily_DoMission": [],
            },
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_valid_values_are_classified(self):
        for mode in OPSI_MONTH_BOSS_MODES:
            for check in (False, True):
                snapshot = validate_alas_opsi_month_boss_config(
                    mode=mode, check_adaptability=check
                )
                self.assertEqual((snapshot.mode, snapshot.check_adaptability), (mode, check))
        for force in (False, True):
            self.assertEqual(
                validate_alas_opsi_obscure_config(force_run=force).force_run,
                force,
            )
        for use_tuning_sample in (False, True):
            self.assertEqual(
                validate_alas_opsi_daily_config(
                    use_tuning_sample=use_tuning_sample
                ).use_tuning_sample,
                use_tuning_sample,
            )

    def test_invalid_values_fail_closed(self):
        for mode in ("", "hard", None, 0, True, [], {}):
            with self.subTest(mode=mode), self.assertRaises(SemanticGateClosed):
                validate_alas_opsi_month_boss_config(
                    mode=mode, check_adaptability=True
                )
        for value in (0, 1, "true", None, [], {}):
            with self.subTest(field="check", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_month_boss_config(
                    mode="normal", check_adaptability=value
                )
            with self.subTest(field="force", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_obscure_config(force_run=value)
            with self.subTest(field="daily", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_daily_config(use_tuning_sample=value)

    def test_patch_gates_original_task_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0090-operation-siren-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_opsi_month_boss_config("), 2)
        self.assertEqual(patch.count("validate_alas_opsi_obscure_config("), 2)
        self.assertEqual(patch.count("validate_alas_opsi_daily_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_opsi_task_config_contract.py",
            "python/alas_headless/alas_opsi_task_config_replay.py",
            "scripts/python/verify_alas_opsi_task_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
