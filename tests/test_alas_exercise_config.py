import ast
import itertools
import unittest
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
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 128)
        self.assertEqual(result["strategy_hour_case_count"], 488)
        self.assertEqual(result["invalid_case_count"], 19)
        self.assertEqual(result["trial_domain"], "positive_int")
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_exercise_attempt_consumed"])
        self.assertFalse(result["real_combat_started"])
        self.assertFalse(result["android_input_injected"])

    def test_all_strategy_mode_and_representative_trial_cases_are_classified(self):
        for strategy, mode, trial in itertools.product(
            EXERCISE_STRATEGIES,
            EXERCISE_OPPONENT_MODES,
            (1, 2, 10, 2**31),
        ):
            snapshot = validate_alas_exercise_config(
                strategy=strategy,
                opponent_mode=mode,
                opponent_trial=trial,
            )
            self.assertEqual(
                (snapshot.strategy, snapshot.opponent_mode, snapshot.opponent_trial),
                (strategy, mode, trial),
            )

    def test_invalid_single_fields_fail_closed(self):
        for field in ("strategy", "opponent_mode"):
            for value in (None, True, 1, "", "unknown", []):
                case = {
                    "strategy": "aggressive",
                    "opponent_mode": "max_exp",
                    "opponent_trial": 1,
                }
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_exercise_config(**case)
        for value in (0, -1, True, 1.0, "1", None, []):
            with self.subTest(opponent_trial=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_exercise_config(
                    strategy="aggressive",
                    opponent_mode="max_exp",
                    opponent_trial=value,
                )

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
