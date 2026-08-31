import ast
import math
import unittest
from pathlib import Path

from alas_headless.alas_optimization_config_contract import (
    WHEN_TASK_QUEUE_EMPTY,
    validate_alas_screenshot_interval_config,
    validate_alas_when_task_queue_empty,
)
from alas_headless.alas_optimization_config_replay import verify_optimization_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasOptimizationConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/device/screenshot.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_optimization_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 9)
        self.assertEqual(result["invalid_case_count"], 25)
        self.assertTrue(result["screenshot_dedithering_semantic_bypass"])
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_valid_values_are_classified(self):
        for value in (-1, 0, 0.1, 0.3, 1, 2):
            snapshot = validate_alas_screenshot_interval_config(
                screenshot_interval=value,
                combat_screenshot_interval=value,
            )
            self.assertEqual(snapshot.screenshot_interval, value)
            self.assertEqual(snapshot.combat_screenshot_interval, value)
        for value in WHEN_TASK_QUEUE_EMPTY:
            self.assertEqual(validate_alas_when_task_queue_empty(value), value)

    def test_invalid_values_fail_closed(self):
        invalid_numbers = (
            True,
            False,
            "0.3",
            None,
            math.nan,
            math.inf,
            -math.inf,
            [],
            {},
        )
        for field in ("screenshot_interval", "combat_screenshot_interval"):
            for value in invalid_numbers:
                case = {"screenshot_interval": 0.3, "combat_screenshot_interval": 1.0}
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_screenshot_interval_config(**case)
        for value in ("", "invalid", None, 0, True, [], {}):
            with self.subTest(field="idle", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_when_task_queue_empty(value)

    def test_patch_gates_both_original_entries(self):
        core = ROOT.joinpath(
            "integration/alas/series/0001-core-ports.patch"
        ).read_text(encoding="utf-8")
        runtime = ROOT.joinpath(
            "integration/alas/series/0150-runtime-optimization-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(core.count("validate_alas_screenshot_interval_config("), 1)
        self.assertEqual(runtime.count("validate_alas_when_task_queue_empty("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_optimization_config_contract.py",
            "python/alas_headless/alas_optimization_config_replay.py",
            "scripts/python/verify_alas_optimization_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
