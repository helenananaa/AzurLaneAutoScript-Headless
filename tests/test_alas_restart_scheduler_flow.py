import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AlasRestartSchedulerFlowTests(unittest.TestCase):
    def test_restart_skips_only_the_pre_restart_screenshot(self):
        patch = ROOT / "integration/alas/series/0210-restart-scheduler-flow-port.patch"
        text = patch.read_text(encoding="utf-8")
        self.assertIn("skip_first_screenshot=(task == 'Restart')", text)
        self.assertIn("LoginHandler.app_restart()", text)
        self.assertIn("semantic_adapter.restart_game_for_manager()", text)

    def test_live_runner_is_parseable(self):
        source = ROOT / "scripts/python/run_alas_restart_live_validation.py"
        ast.parse(source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
