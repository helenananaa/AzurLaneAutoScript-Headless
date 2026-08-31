import ast
import unittest
from pathlib import Path

from alas_headless.alas_private_quarters_config_contract import (
    PRIVATE_QUARTERS_SHIPS,
    validate_alas_private_quarters_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_private_quarters_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")


class AlasPrivateQuartersConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/private_quarters/private_quarters.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 4)
        self.assertEqual(result["accepted_case_count"], 56)
        self.assertEqual(result["invalid_case_count"], 25)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_exact_declared_values_are_admitted(self):
        for target_ship in PRIVATE_QUARTERS_SHIPS:
            with self.subTest(target_ship=target_ship):
                snapshot = validate_alas_private_quarters_config(
                    buy_roses=True,
                    buy_cake=False,
                    target_interact=True,
                    target_ship=target_ship,
                )
                self.assertEqual(snapshot.target_ship, target_ship)

    def test_invalid_settings_fail_closed(self):
        for settings in (
            {"buy_roses": 1},
            {"buy_cake": "false"},
            {"target_interact": None},
            {"target_ship": "Anchorage"},
        ):
            with self.subTest(settings=settings), self.assertRaises(SemanticGateClosed):
                values = {
                    "buy_roses": True,
                    "buy_cake": False,
                    "target_interact": True,
                    "target_ship": "anchorage",
                }
                values.update(settings)
                validate_alas_private_quarters_config(**values)

    def test_patch_gates_before_private_quarters_ui_or_currency_branches(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0180-private-quarters-config-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_private_quarters_config("), 3)
        self.assertLess(
            patch.index("validate_alas_private_quarters_config("),
            patch.index("self.ui_ensure("),
        )
        self.assertLess(
            patch.rindex("validate_alas_private_quarters_config("),
            patch.rindex("if private_quarters_config.buy_roses:"),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_private_quarters_config_contract.py",
            "python/alas_headless/alas_private_quarters_config_replay.py",
            "scripts/python/verify_alas_private_quarters_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
