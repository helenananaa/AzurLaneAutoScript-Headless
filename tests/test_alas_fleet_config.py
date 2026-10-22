import ast
import unittest
from pathlib import Path

from alas_headless.alas_fleet_config_contract import validate_alas_fleet_config
from alas_headless.alas_fleet_config_replay import verify_fleet_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


def defaults():
    return {
        "fleet1": 1,
        "fleet1_formation": "double_line",
        "fleet1_mode": "combat_auto",
        "fleet1_step": 3,
        "fleet2": 2,
        "fleet2_formation": "double_line",
        "fleet2_mode": "combat_auto",
        "fleet2_step": 2,
        "fleet_order": "fleet1_mob_fleet2_boss",
    }


class AlasFleetConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/map/fleet.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_fleet_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 9)
        self.assertGreaterEqual(result["case_count"], 50)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_steps_and_fleet_indices_are_exhaustively_accepted(self):
        for field, values in (
            ("fleet1", range(1, 7)),
            ("fleet2", range(0, 7)),
            ("fleet1_step", range(2, 6)),
            ("fleet2_step", range(2, 6)),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    config = defaults()
                    config[field] = value
                    self.assertEqual(
                        getattr(validate_alas_fleet_config(**config), field), value
                    )

    def test_valid_but_unqualified_values_fail_before_navigation(self):
        for field, value in (
            ("fleet1_mode", "combat_manual"),
            ("fleet2_mode", "hide_in_upper_left"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                config = defaults()
                config[field] = value
                validate_alas_fleet_config(**config)

    def test_single_fleet_all_order_requires_an_empty_second_fleet(self):
        config = defaults()
        config["fleet2"] = 0
        config["fleet_order"] = "fleet1_all_fleet2_standby"
        self.assertEqual(
            validate_alas_fleet_config(**config).fleet_order,
            "fleet1_all_fleet2_standby",
        )

        config["fleet2"] = 2
        self.assertEqual(validate_alas_fleet_config(**config).fleet_order,
                         "fleet1_all_fleet2_standby")

    def test_hardfleet_two_reversed_all_order_requires_two_fleets(self):
        config = defaults()
        config["fleet_order"] = "fleet1_standby_fleet2_all"
        self.assertEqual(
            validate_alas_fleet_config(**config).fleet_order,
            "fleet1_standby_fleet2_all",
        )

        config["fleet2"] = 0
        with self.assertRaises(SemanticGateClosed):
            validate_alas_fleet_config(**config)

    def test_invalid_values_fail_closed(self):
        for field, value in (
            ("fleet1", 0),
            ("fleet1", True),
            ("fleet2", 7),
            ("fleet1_step", 1),
            ("fleet1_mode", "unknown"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                config = defaults()
                config[field] = value
                validate_alas_fleet_config(**config)

    def test_patch_validates_before_campaign_context(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("semantic_adapter.validate_campaign_fleet_config(", patch)
        self.assertLess(
            patch.index("semantic_adapter.validate_campaign_fleet_config("),
            patch.index("semantic_adapter.begin_campaign_pre_sortie("),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_fleet_config_contract.py",
            "python/alas_headless/alas_fleet_config_replay.py",
            "scripts/python/verify_alas_fleet_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
