import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_benchmark_config_contract import (
    BENCHMARK_DEVICE_TYPES,
    BENCHMARK_TEST_SCENES,
    validate_alas_benchmark_config,
)
from alas_headless.alas_benchmark_config_replay import verify_benchmark_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasBenchmarkConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/daemon/benchmark.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_benchmark_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["accepted_case_count"], 15)
        self.assertEqual(result["invalid_case_count"], 12)
        self.assertEqual(len(result["semantic_scene_decisions"]), 15)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_benchmark_method_called"])
        self.assertFalse(result["android_input_injected"])

    def test_all_declared_combinations_are_classified(self):
        for device_type, test_scene in itertools.product(
            BENCHMARK_DEVICE_TYPES, BENCHMARK_TEST_SCENES
        ):
            snapshot = validate_alas_benchmark_config(
                device_type=device_type,
                test_scene=test_scene,
            )
            self.assertEqual((snapshot.device_type, snapshot.test_scene), (device_type, test_scene))

    def test_invalid_single_fields_fail_closed(self):
        for field in ("device_type", "test_scene"):
            for value in (None, True, 1, "", "unknown", []):
                values = {"device_type": "emulator", "test_scene": "screenshot_click"}
                values[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(SemanticGateClosed):
                    validate_alas_benchmark_config(**values)

    def test_patch_gates_original_benchmark_entry(self):
        patch = ROOT.joinpath("integration/alas/series/0100-tool-flow-ports.patch").read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_benchmark_config("), 1)

    def test_benchmark_returns_to_main_after_an_odd_control_sample_count(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0250-benchmark-return-main-flow-port.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("oracle.exists('settings/back')", patch)
        self.assertIn("self.semantic_ensure_main()", patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_benchmark_config_contract.py",
            "python/alas_headless/alas_benchmark_config_replay.py",
            "scripts/python/verify_alas_benchmark_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
