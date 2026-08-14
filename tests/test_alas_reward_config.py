import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_reward_config_contract import validate_alas_reward_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_reward_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "collect_oil": True,
        "collect_coin": True,
        "collect_exp": True,
        "collect_mission": True,
        "collect_weekly_mission": True,
    }
    values.update(overrides)
    return values


class AlasRewardConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/reward/reward.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 5)
        self.assertEqual(result["accepted_case_count"], 32)
        self.assertEqual(result["invalid_case_count"], 20)
        self.assertEqual(len(result["original_decisions"]["reward_cases"]), 32)
        self.assertEqual(
            result["original_decisions"]["raid_ex_disabled"]["events"][3],
            ["reward_mission", {"daily": False, "weekly": False}],
        )
        self.assertFalse(result["real_claim_method_called"])
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_all_boolean_combinations_are_accepted(self):
        keys = tuple(_values())
        for combination in itertools.product((False, True), repeat=5):
            with self.subTest(combination=combination):
                snapshot = validate_alas_reward_config(
                    **dict(zip(keys, combination))
                )
                self.assertEqual(
                    tuple(getattr(snapshot, key) for key in keys), combination
                )

    def test_non_boolean_values_fail_closed_for_every_field(self):
        for field in _values():
            for value in (0, 1, "true", None):
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_reward_config(**_values(**{field: value}))

    def test_patch_gates_reward_and_raid_daily_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0010-mission-mail-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/raid/daily.py", patch)
        self.assertEqual(patch.count("validate_alas_reward_config("), 2)
        raid_guard = patch.index("reward_config = validate_alas_reward_config(")
        raid_rpg = patch.index("if self.is_raid_rpg():", raid_guard)
        self.assertLess(raid_guard, raid_rpg)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_reward_config_contract.py",
            "python/alas_headless/alas_reward_config_replay.py",
            "scripts/python/verify_alas_reward_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
