import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_gacha_config_contract import (
    GACHA_AMOUNTS,
    GACHA_POOLS,
    validate_alas_gacha_config,
)
from alas_headless.alas_gacha_config_replay import verify_gacha_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasGachaConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/gacha/gacha_reward.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_gacha_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 4)
        self.assertEqual(result["accepted_case_count"], 200)
        self.assertEqual(result["invalid_case_count"], 25)
        self.assertEqual(result["decision_matrix"]["cases"], 200)
        self.assertEqual(result["decision_matrix"]["ticket_cube_split_cases"], 14)
        self.assertEqual(result["mutation_budget"], 0)
        for field in (
            "real_build_submitted",
            "real_ticket_consumed",
            "real_cube_consumed",
            "real_coin_consumed",
            "real_drill_consumed",
            "android_input_injected",
        ):
            self.assertFalse(result[field])

    def test_all_declared_combinations_are_classified(self):
        for pool, amount, use_ticket, use_drill in itertools.product(
            GACHA_POOLS, GACHA_AMOUNTS, (False, True), (False, True)
        ):
            snapshot = validate_alas_gacha_config(
                pool=pool,
                amount=amount,
                use_ticket=use_ticket,
                use_drill=use_drill,
            )
            self.assertEqual(
                (snapshot.pool, snapshot.amount, snapshot.use_ticket, snapshot.use_drill),
                (pool, amount, use_ticket, use_drill),
            )

    def test_invalid_single_fields_fail_closed(self):
        invalid = {
            "pool": (None, True, 1, "", "unknown", []),
            "amount": (0, 11, True, 1.0, "1", None, []),
            "use_ticket": (None, 0, 1, "true", [], {}),
            "use_drill": (None, 0, 1, "true", [], {}),
        }
        for field, values in invalid.items():
            for value in values:
                case = {
                    "pool": "light",
                    "amount": 1,
                    "use_ticket": True,
                    "use_drill": False,
                }
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_gacha_config(**case)

    def test_patch_gates_original_gacha_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0030-research-dorm-build-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_gacha_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_gacha_config_contract.py",
            "python/alas_headless/alas_gacha_config_replay.py",
            "scripts/python/verify_alas_gacha_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
