import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_shipyard_config_contract import (
    SHIPYARD_DR_SERIES,
    SHIPYARD_INDICES,
    SHIPYARD_PR_SERIES,
    validate_alas_shipyard_config,
)
from alas_headless.alas_shipyard_config_replay import verify_shipyard_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasShipyardConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/shipyard/shipyard_reward.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_shipyard_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 4)
        self.assertEqual(result["accepted_case_count"], 1_176)
        self.assertEqual(result["invalid_case_count"], 28)
        self.assertEqual(
            result["focus_matrix"],
            {"success": 32, "disabled": 6, "series_restricted": 4},
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_blueprints_consumed"])
        self.assertFalse(result["real_coin_consumed"])
        self.assertFalse(result["real_navigation_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_all_declared_focus_combinations_are_classified(self):
        for pr_series, pr_index, dr_series, dr_index in itertools.product(
            SHIPYARD_PR_SERIES,
            SHIPYARD_INDICES,
            SHIPYARD_DR_SERIES,
            SHIPYARD_INDICES,
        ):
            snapshot = validate_alas_shipyard_config(
                pr_series=pr_series,
                pr_index=pr_index,
                dr_series=dr_series,
                dr_index=dr_index,
            )
            self.assertEqual(
                (
                    snapshot.pr_series,
                    snapshot.pr_index,
                    snapshot.dr_series,
                    snapshot.dr_index,
                ),
                (pr_series, pr_index, dr_series, dr_index),
            )

    def test_invalid_single_fields_fail_closed(self):
        invalid = {
            "pr_series": (0, 7, True, 1.0, "1", None, []),
            "pr_index": (-1, 7, True, 1.0, "1", None, []),
            "dr_series": (1, 6, True, 2.0, "2", None, []),
            "dr_index": (-1, 7, True, 1.0, "1", None, []),
        }
        for field, values in invalid.items():
            for value in values:
                case = {
                    "pr_series": 1,
                    "pr_index": 1,
                    "dr_series": 2,
                    "dr_index": 1,
                }
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_shipyard_config(**case)

    def test_patch_gates_original_shipyard_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0070-shipyard-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_shipyard_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_shipyard_config_contract.py",
            "python/alas_headless/alas_shipyard_config_replay.py",
            "scripts/python/verify_alas_shipyard_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
