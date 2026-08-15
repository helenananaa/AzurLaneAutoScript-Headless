import ast
import unittest
from itertools import product
from pathlib import Path

from alas_headless.alas_opsi_task_config_contract import (
    OPSI_HAZARD1_TARGET_ZONES,
    OPSI_MEOWFFICER_HAZARD_LEVELS,
    OPSI_MONTH_BOSS_MODES,
    validate_alas_opsi_daily_config,
    validate_alas_opsi_delay_task_config,
    validate_alas_opsi_explore_config,
    validate_alas_opsi_hazard1_config,
    validate_alas_opsi_meowfficer_config,
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
        self.assertEqual(result["field_count"], 10)
        self.assertEqual(result["accepted_case_count"], 48)
        self.assertEqual(result["invalid_case_count"], 77)
        self.assertEqual(
            result["zero_runtime_consumers"],
            {
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
        for target_zone in OPSI_HAZARD1_TARGET_ZONES:
            self.assertEqual(
                validate_alas_opsi_hazard1_config(
                    target_zone=target_zone
                ).target_zone,
                target_zone,
            )
        for hazard_level in OPSI_MEOWFFICER_HAZARD_LEVELS:
            self.assertEqual(
                validate_alas_opsi_meowfficer_config(
                    hazard_level=hazard_level
                ).hazard_level,
                hazard_level,
            )
        fields = (
            "explore_force_run",
            "obscure_force_run",
            "abyssal_force_run",
            "stronghold_force_run",
            "special_radar",
        )
        for values in product((False, True), repeat=5):
            kwargs = dict(zip(fields, values, strict=True))
            snapshot = validate_alas_opsi_delay_task_config(**kwargs)
            self.assertEqual(
                snapshot.force_run,
                any(values[:4]),
            )
            self.assertEqual(snapshot.special_radar, values[4])
            self.assertEqual(
                validate_alas_opsi_explore_config(
                    special_radar=values[4]
                ).special_radar,
                values[4],
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
        for value in (-1, 1, 23, 45, None, True, "22", 22.0, [], {}):
            with self.subTest(field="hazard_target", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_hazard1_config(target_zone=value)
        for value in (0, 1, 2, 7, 9, 11, None, True, "5", 5.0, [], {}):
            with self.subTest(field="meow_hazard", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_meowfficer_config(hazard_level=value)
        fields = (
            "explore_force_run",
            "obscure_force_run",
            "abyssal_force_run",
            "stronghold_force_run",
            "special_radar",
        )
        for value in (0, 1, "true", None, [], {}):
            for field in fields:
                kwargs = {name: False for name in fields}
                kwargs[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_opsi_delay_task_config(**kwargs)

    def test_patch_gates_original_task_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0090-operation-siren-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_opsi_month_boss_config("), 2)
        self.assertEqual(patch.count("validate_alas_opsi_obscure_config("), 2)
        self.assertEqual(patch.count("validate_alas_opsi_daily_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_hazard1_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_meowfficer_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_explore_config("), 1)
        scheduler_patch = ROOT.joinpath(
            "integration/alas/series/0140-scheduler-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            scheduler_patch.count("validate_alas_opsi_delay_task_config("), 1
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_opsi_task_config_contract.py",
            "python/alas_headless/alas_opsi_task_config_replay.py",
            "scripts/python/verify_alas_opsi_task_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
