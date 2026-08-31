import ast
import unittest
from pathlib import Path

from alas_headless.alas_awaken_config_contract import validate_alas_awaken_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_awaken_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")


class AlasAwakenConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/awaken/awaken.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["accepted_case_count"], 4)
        self.assertEqual(result["invalid_case_count"], 12)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_awaken_run_called"])
        self.assertFalse(result["android_input_injected"])

    def test_exact_enum_and_boolean_are_admitted(self):
        for level_cap in ("level120", "level125"):
            for favourite in (False, True):
                snapshot = validate_alas_awaken_config(
                    level_cap=level_cap, favourite=favourite
                )
                self.assertEqual(snapshot.level_cap, level_cap)
                self.assertIs(snapshot.favourite, favourite)

    def test_invalid_values_fail_before_the_dispatcher(self):
        for level_cap, favourite in (
            ("level_120", False),
            ("LEVEL120", False),
            (None, False),
            (True, False),
            ("level120", None),
            ("level120", 0),
            ("level120", "false"),
        ):
            with self.subTest(level_cap=level_cap, favourite=favourite), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_awaken_config(
                    level_cap=level_cap, favourite=favourite
                )

    def test_patch_gates_before_any_awaken_run(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0160-awaken-config-contract.patch"
        ).read_text(encoding="utf-8")
        guard = patch.index("awaken_config = validate_alas_awaken_config(")
        first_run = patch.index("result = self.awaken_run", guard)
        self.assertLess(guard, first_run)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_awaken_config_contract.py",
            "python/alas_headless/alas_awaken_config_replay.py",
            "scripts/python/verify_alas_awaken_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
