import ast
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from alas_headless.alas_buy_furniture_config_contract import (
    BUY_FURNITURE_OPTIONS,
    validate_alas_buy_furniture_config,
)
from alas_headless.alas_buy_furniture_config_replay import verify_buy_furniture_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasBuyFurnitureConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/dorm/buy_furniture.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_buy_furniture_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 20)
        self.assertEqual(result["invalid_case_count"], 19)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_furniture_coin_consumed"])
        self.assertFalse(result["real_purchase_confirmed"])
        self.assertFalse(result["real_navigation_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_all_declared_options_and_boundaries_are_classified(self):
        for enable in (False, True):
            for option in BUY_FURNITURE_OPTIONS:
                for record in (
                    datetime(2000, 1, 1),
                    datetime(2020, 1, 1),
                    datetime(2100, 1, 1),
                ):
                    snapshot = validate_alas_buy_furniture_config(
                        enable=enable, buy_option=option, last_run=record
                    )
                    self.assertEqual(
                        (snapshot.enable, snapshot.buy_option, snapshot.last_run),
                        (enable, option, record),
                    )

    def test_invalid_single_fields_fail_closed(self):
        base = {
            "enable": True,
            "buy_option": "all",
            "last_run": datetime(2020, 1, 1),
        }
        invalid = {
            "enable": (0, 1, None, "true", [], {}),
            "buy_option": (None, True, 1, "", "unknown", []),
            "last_run": (
                None,
                True,
                "2020-01-01 00:00:00",
                date(2020, 1, 1),
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                datetime(1999, 12, 31, 23, 59, 59),
                datetime(2100, 1, 1, 0, 0, 1),
            ),
        }
        for field, values in invalid.items():
            for value in values:
                case = dict(base)
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_buy_furniture_config(**case)

    def test_patch_gates_dorm_and_furniture_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0030-research-dorm-build-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_buy_furniture_config("), 2)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_buy_furniture_config_contract.py",
            "python/alas_headless/alas_buy_furniture_config_replay.py",
            "scripts/python/verify_alas_buy_furniture_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
