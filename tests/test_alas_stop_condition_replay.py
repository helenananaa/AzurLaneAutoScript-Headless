import ast
import tempfile
import textwrap
import unittest
from pathlib import Path

from alas_headless.alas_stop_condition_replay import verify_stop_conditions


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasStopConditionReplayTests(unittest.TestCase):
    def test_exact_live_patched_tree_when_available(self):
        if not LIVE_ALAS.joinpath("module/campaign/run.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_stop_conditions(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["map_achievement_truth_table_rows"], 40)
        self.assertGreaterEqual(result["case_count"], 70)
        self.assertEqual(result["run_method"], "_run")
        instances = result["main_task_instances"]
        self.assertEqual(instances["task_count"], 3)
        self.assertEqual(instances["scenario_count"], 15)
        self.assertEqual(set(instances["instances"]), {"Main", "Main2", "Main3"})
        for task_name, instance in instances["instances"].items():
            with self.subTest(task_name=task_name):
                self.assertEqual(instance["scheduler_command"], task_name)
                self.assertEqual(instance["campaign_event"], "campaign_main")
                self.assertEqual(instance["campaign_mode"], "normal")
                self.assertEqual(
                    instance["scenarios"]["interrupted"]["remaining"], 2
                )
                self.assertEqual(
                    instance["scenarios"]["interrupted"]["successful_runs"], 0
                )
                self.assertEqual(
                    instance["scenarios"]["two"]["campaign_run_calls"], 2
                )
        self.assertEqual(instances["mutation_budget"], 0)
        self.assertFalse(instances["android_input_injected"])
        self.assertEqual(
            result["new_ship_live_test"],
            "skipped-nondeterministic-first-acquisition",
        )
        self.assertFalse(result["input_injected"])

    def test_patch_keeps_semantic_achievement_and_level_ports(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0110-stop-condition-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("campaign_map_achievement_state", patch)
        self.assertIn("campaign_fleet_levels", patch)

    def test_verifier_compiles(self):
        source = ROOT.joinpath(
            "python/alas_headless/alas_stop_condition_replay.py"
        ).read_text(encoding="utf-8")
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
