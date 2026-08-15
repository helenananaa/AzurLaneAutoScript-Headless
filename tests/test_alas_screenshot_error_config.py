import ast
import unittest
from pathlib import Path

from alas_headless.alas_screenshot_error_config_contract import (
    validate_alas_error_screenshot_length,
    validate_alas_screenshot_capture_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_screenshot_error_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasScreenshotErrorConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/device/screenshot.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 12)
        self.assertEqual(result["invalid_case_count"], 11)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_screenshot_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_valid_values_preserve_capture_decisions(self):
        for dedithering in (False, True):
            for save_error in (False, True):
                snapshot = validate_alas_screenshot_capture_config(
                    screenshot_dedithering=dedithering,
                    save_error=save_error,
                    screenshot_length="301",
                )
                self.assertEqual(snapshot.screenshot_length, 300)
        for value, expected in ((0, 1), ("1", 1), (300, 300), (301, 300), (1.8, 1)):
            self.assertEqual(
                validate_alas_error_screenshot_length(screenshot_length=value),
                expected,
            )

    def test_invalid_values_fail_before_frame_access(self):
        for field, value in (
            ("screenshot_dedithering", "true"),
            ("save_error", "false"),
            ("screenshot_length", "invalid"),
        ):
            values = {
                "screenshot_dedithering": False,
                "save_error": True,
                "screenshot_length": 1,
            }
            values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_screenshot_capture_config(**values)
        for value in ("", None, [], {}):
            with self.subTest(field="screenshot_length", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_error_screenshot_length(screenshot_length=value)

    def test_patch_gates_screenshot_capture_before_semantic_frame_access(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0001-core-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_screenshot_capture_config("), 1)
        self.assertEqual(patch.count("validate_alas_error_screenshot_length("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_screenshot_error_config_contract.py",
            "python/alas_headless/alas_screenshot_error_config_replay.py",
            "scripts/python/verify_alas_screenshot_error_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
