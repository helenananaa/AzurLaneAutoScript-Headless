import ast
import unittest
from pathlib import Path

from alas_headless.alas_emulator_info_config_contract import (
    validate_alas_emulator_info_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_emulator_info_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasEmulatorInfoConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/device/platform/platform_base.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["accepted_case_count"], 10)
        self.assertEqual(result["invalid_case_count"], 8)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["filesystem_probed"])
        self.assertFalse(result["emulator_started"])
        self.assertFalse(result["android_input_injected"])

    def test_valid_values_preserve_upstream_normalization(self):
        for name, path, expected_name, expected_path in (
            (None, None, "", ""),
            (" Nox\n", " C:\\Emulator\\player.exe ", "Nox", "C:\\Emulator\\player.exe"),
            ("False", "True", "", ""),
        ):
            snapshot = validate_alas_emulator_info_config(name=name, path=path)
            self.assertEqual(snapshot.name, expected_name)
            self.assertEqual(snapshot.path, expected_path)

    def test_invalid_types_fail_before_platform_discovery(self):
        for field, value in (("name", True), ("path", 0), ("name", []), ("path", {})):
            values = {"name": None, "path": None}
            values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_emulator_info_config(**values)

    def test_patch_gates_emulator_info_property(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0001-core-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_emulator_info_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_emulator_info_config_contract.py",
            "python/alas_headless/alas_emulator_info_config_replay.py",
            "scripts/python/verify_alas_emulator_info_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
