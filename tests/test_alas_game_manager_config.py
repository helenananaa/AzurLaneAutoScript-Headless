import ast
import unittest
from pathlib import Path

from alas_headless.alas_game_manager_config_contract import (
    validate_alas_game_manager_config,
)
from alas_headless.alas_game_manager_config_replay import (
    verify_game_manager_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasGameManagerConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/daemon/game_manager.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_game_manager_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 1)
        self.assertEqual(result["accepted_case_count"], 2)
        self.assertEqual(result["invalid_case_count"], 6)
        self.assertEqual(
            result["semantic_cleanup_cases"],
            {
                "stop": ["stop", "semantic_close"],
                "restart": ["restart", "semantic_close"],
                "login": ["restart", "login", "semantic_close"],
            },
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_app_lifecycle_called"])
        self.assertFalse(result["android_input_injected"])

    def test_both_boolean_values_are_classified(self):
        self.assertFalse(
            validate_alas_game_manager_config(auto_restart=False).auto_restart
        )
        self.assertTrue(
            validate_alas_game_manager_config(auto_restart=True).auto_restart
        )

    def test_invalid_values_fail_closed(self):
        for value in (0, 1, None, "true", [], {}):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_game_manager_config(auto_restart=value)

    def test_patch_gates_original_game_manager_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0100-tool-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_game_manager_config("), 1)
        self.assertIn("semantic_adapter.close()", patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_game_manager_config_contract.py",
            "python/alas_headless/alas_game_manager_config_replay.py",
            "scripts/python/verify_alas_game_manager_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
