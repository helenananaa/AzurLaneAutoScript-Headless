import ast
import unittest
from pathlib import Path

from alas_headless.alas_submarine_config_contract import (
    SUBMARINE_AUTO_SEARCH_MODES,
    SUBMARINE_BOSS_DISTANCES,
    SUBMARINE_MODES,
    validate_alas_submarine_config,
)
from alas_headless.alas_submarine_config_replay import verify_submarine_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasSubmarineConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/combat/submarine.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_submarine_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 4)
        self.assertEqual(result["panel_count"], 12)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_all_inactive_enum_combinations_are_classified(self):
        count = 0
        for mode in SUBMARINE_MODES:
            for auto in SUBMARINE_AUTO_SEARCH_MODES:
                for distance in SUBMARINE_BOSS_DISTANCES:
                    snapshot = validate_alas_submarine_config(
                        fleet=0,
                        mode=mode,
                        auto_search_mode=auto,
                        distance_to_boss=distance,
                    )
                    self.assertEqual(snapshot.fleet, 0)
                    count += 1
        self.assertEqual(count, 40)

    def test_active_fleets_and_invalid_values_fail_closed(self):
        for fleet in (1, 2):
            with self.assertRaisesRegex(SemanticGateClosed, "unqualified"):
                validate_alas_submarine_config(
                    fleet=fleet,
                    mode="every_combat",
                    auto_search_mode="sub_auto_call",
                    distance_to_boss="to_boss_position",
                )
        for field, value in (
            ("fleet", -1),
            ("fleet", 3),
            ("fleet", True),
            ("mode", "unknown"),
            ("auto_search_mode", "unknown"),
            ("distance_to_boss", "unknown"),
        ):
            values = {
                "fleet": 0,
                "mode": "do_not_use",
                "auto_search_mode": "sub_standby",
                "distance_to_boss": "2_grid_to_boss",
            }
            values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_submarine_config(**values)

    def test_patch_validates_before_campaign_context(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        validation = patch.index("validate_campaign_submarine_config(")
        self.assertLess(
            validation,
            patch.index("semantic_adapter.begin_campaign_pre_sortie("),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_submarine_config_contract.py",
            "python/alas_headless/alas_submarine_config_replay.py",
            "scripts/python/verify_alas_submarine_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
