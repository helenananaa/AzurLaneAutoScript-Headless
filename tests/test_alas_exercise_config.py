import ast
import itertools
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alas_headless.alas_exercise_config_contract import (
    EXERCISE_OPPONENT_MODES,
    EXERCISE_STRATEGIES,
    validate_alas_exercise_config,
)
from alas_headless.alas_exercise_config_replay import verify_exercise_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasExerciseConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/exercise/exercise.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_exercise_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 7)
        self.assertEqual(result["accepted_case_count"], 53_760)
        self.assertEqual(result["strategy_hour_case_count"], 488)
        self.assertEqual(result["invalid_case_count"], 48)
        self.assertEqual(result["declared_unused_fields"], [])
        self.assertEqual(result["trial_domain"], "positive_int")
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_exercise_attempt_consumed"])
        self.assertFalse(result["real_combat_started"])
        self.assertFalse(result["android_input_injected"])

    def test_all_representative_consumed_fields_are_classified(self):
        for strategy, mode, trial, threshold, confirm_wait, refresh_value, refresh_record in itertools.product(
            EXERCISE_STRATEGIES,
            EXERCISE_OPPONENT_MODES,
            (1, 2, 10, 2**31),
            (0.0, 0.01, 0.4, 1.0),
            (0.0, 0.1, 1.0, 3.0, 299.0),
            range(7),
            (datetime(2000, 1, 1), datetime(2026, 8, 15), datetime(2100, 1, 1)),
        ):
            snapshot = validate_alas_exercise_config(
                strategy=strategy,
                opponent_mode=mode,
                opponent_trial=trial,
                low_hp_threshold=threshold,
                low_hp_confirm_wait=confirm_wait,
                opponent_refresh_value=refresh_value,
                opponent_refresh_record=refresh_record,
            )
            self.assertEqual(
                (
                    snapshot.strategy,
                    snapshot.opponent_mode,
                    snapshot.opponent_trial,
                    snapshot.low_hp_threshold,
                    snapshot.low_hp_confirm_wait,
                    snapshot.opponent_refresh_value,
                    snapshot.opponent_refresh_record,
                ),
                (strategy, mode, trial, threshold, confirm_wait, refresh_value, refresh_record),
            )

    @staticmethod
    def _valid_case():
        return {
            "strategy": "aggressive",
            "opponent_mode": "max_exp",
            "opponent_trial": 1,
            "low_hp_threshold": 0.4,
            "low_hp_confirm_wait": 0.1,
            "opponent_refresh_value": 0,
            "opponent_refresh_record": datetime(2026, 8, 15),
        }

    def test_invalid_single_fields_fail_closed(self):
        for field in ("strategy", "opponent_mode"):
            for value in (None, True, 1, "", "unknown", []):
                case = self._valid_case()
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_exercise_config(**case)
        for value in (0, -1, True, 1.0, "1", None, []):
            with self.subTest(opponent_trial=value), self.assertRaises(
                SemanticGateClosed
            ):
                case = self._valid_case()
                case["opponent_trial"] = value
                validate_alas_exercise_config(**case)
        invalid = {
            "low_hp_threshold": (-0.01, 1.01, True, float("nan"), float("inf"), "0.4", None, []),
            "low_hp_confirm_wait": (-0.01, 300.0, True, float("nan"), float("inf"), "0.1", None, []),
            "opponent_refresh_value": (-1, 7, True, 1.0, "1", None, []),
            "opponent_refresh_record": (
                datetime(1999, 12, 31),
                datetime(2100, 1, 2),
                datetime(2026, 8, 15, tzinfo=timezone.utc),
                "2026-08-15 00:00:00",
                None,
                [],
            ),
        }
        for field, values in invalid.items():
            for value in values:
                case = self._valid_case()
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_exercise_config(**case)

    def test_patch_gates_original_exercise_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_exercise_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_exercise_config_contract.py",
            "python/alas_headless/alas_exercise_config_replay.py",
            "scripts/python/verify_alas_exercise_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
