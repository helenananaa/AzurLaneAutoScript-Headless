import ast
import copy
import unittest
from datetime import datetime
from pathlib import Path

from alas_headless.alas_scheduler_contract import (
    validate_alas_scheduler_config,
    validate_alas_task_hoarding_config,
)
from alas_headless.alas_scheduler_replay import verify_scheduler_contract
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


def scheduler(panel="Research"):
    return {
        panel: {
            "Scheduler": {
                "Enable": True,
                "NextRun": datetime(2026, 8, 15),
                "Command": panel,
                "SuccessInterval": "30-60",
                "FailureInterval": "30-60",
                "ServerUpdate": "00:00, 12:00",
            }
        }
    }


class AlasSchedulerContractTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/config/config.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_scheduler_contract(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["scheduler_panel_count"], 50)
        self.assertEqual(result["equivalence_class_count"], 15)
        self.assertTrue(result["temporary_config_only"])
        self.assertFalse(result["android_input_injected"])

    def test_shared_six_field_contract_accepts_valid_snapshot(self):
        snapshots = validate_alas_scheduler_config(scheduler())
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].command, "Research")

    def test_malformed_or_ambiguous_scheduler_fails_closed(self):
        fixtures = []
        missing = scheduler()
        del missing["Research"]["Scheduler"]["NextRun"]
        fixtures.append(missing)
        invalid_datetime = scheduler()
        invalid_datetime["Research"]["Scheduler"]["NextRun"] = "tomorrow"
        fixtures.append(invalid_datetime)
        wrong_command = scheduler()
        wrong_command["Research"]["Scheduler"]["Command"] = "Reward"
        fixtures.append(wrong_command)
        bad_range = scheduler()
        bad_range["Research"]["Scheduler"]["SuccessInterval"] = "60-30"
        fixtures.append(bad_range)
        duplicate_clock = scheduler()
        duplicate_clock["Research"]["Scheduler"]["ServerUpdate"] = "00:00, 00:00"
        fixtures.append(duplicate_clock)
        for fixture in fixtures:
            with self.subTest(fixture=fixture), self.assertRaises(SemanticGateClosed):
                validate_alas_scheduler_config(fixture)

    def test_unknown_field_does_not_silently_join_contract(self):
        value = copy.deepcopy(scheduler())
        value["Research"]["Scheduler"]["Unexpected"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "six-field"):
            validate_alas_scheduler_config(value)

    def test_patch_preserves_upstream_queue_without_global_qualification_gates(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0140-scheduler-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertNotIn("validate_alas_scheduler_config(self.data)", patch)
        self.assertNotIn("validate_alas_task_hoarding_config(self.data)", patch)

    def test_task_hoarding_is_bounded_before_scheduler_time_math(self):
        for minutes in (0, 1, 15, 1440):
            snapshot = validate_alas_task_hoarding_config(
                {"Alas": {"Optimization": {"TaskHoardingDuration": minutes}}}
            )
            self.assertEqual(snapshot.minutes, minutes)
            self.assertEqual(snapshot.duration.total_seconds(), minutes * 60)
        for value in (-1, 1441, True, 1.5, "15", None):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_task_hoarding_config(
                    {"Alas": {"Optimization": {"TaskHoardingDuration": value}}}
                )

    def test_replay_source_compiles(self):
        source = ROOT.joinpath(
            "python/alas_headless/alas_scheduler_replay.py"
        ).read_text(encoding="utf-8")
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
