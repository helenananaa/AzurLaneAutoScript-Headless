import ast
import unittest
from pathlib import Path

from alas_headless.alas_enemy_priority_config_contract import (
    ENEMY_PRIORITY_MODES,
    validate_alas_enemy_priority_config,
)
from alas_headless.alas_enemy_priority_config_replay import (
    verify_enemy_priority_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasEnemyPriorityConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/map/map.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_enemy_priority_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["panel_count"], 11)
        self.assertEqual(result["accepted_modes"], list(ENEMY_PRIORITY_MODES))
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_complete_enum_is_accepted_without_rewriting(self):
        for mode in ENEMY_PRIORITY_MODES:
            with self.subTest(mode=mode):
                snapshot = validate_alas_enemy_priority_config(
                    enemy_scale_balance_weight=mode
                )
                self.assertEqual(snapshot.enemy_scale_balance_weight, mode)

    def test_unknown_or_wrong_type_values_fail_closed(self):
        for value in ("", "unknown", "s1_enemy_first", None, 1, True):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_enemy_priority_config(
                    enemy_scale_balance_weight=value
                )

    def test_patch_validates_before_campaign_context(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        validation = patch.index(
            "semantic_adapter.validate_campaign_enemy_priority_config("
        )
        self.assertLess(
            validation,
            patch.index("semantic_adapter.begin_campaign_pre_sortie("),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_enemy_priority_config_contract.py",
            "python/alas_headless/alas_enemy_priority_config_replay.py",
            "scripts/python/verify_alas_enemy_priority_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
