import ast
import unittest
from pathlib import Path

from alas_headless.alas_supply_pack_config_contract import (
    validate_alas_supply_pack_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_supply_pack_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")


class AlasSupplyPackConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/freebies/supply_pack.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["accepted_case_count"], 14)
        self.assertEqual(result["invalid_case_count"], 10)
        self.assertEqual(
            result["original_decisions"]["enabled"]["calls"],
            ["mail", "supply_pack"],
        )
        self.assertEqual(
            result["original_decisions"]["disabled"]["calls"], ["mail"]
        )
        self.assertFalse(result["real_claim_method_called"])
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_all_boolean_and_weekday_combinations_are_accepted(self):
        for collect in (False, True):
            for day in range(7):
                with self.subTest(collect=collect, day=day):
                    snapshot = validate_alas_supply_pack_config(
                        collect=collect, day_of_week=day
                    )
                    self.assertIs(snapshot.collect, collect)
                    self.assertEqual(snapshot.day_of_week, day)

    def test_invalid_values_fail_closed(self):
        for field, value in (
            ("collect", 1),
            ("collect", "true"),
            ("collect", None),
            ("day", -1),
            ("day", 7),
            ("day", True),
            ("day", "0"),
            ("day", 0.0),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_supply_pack_config(
                    collect=value if field == "collect" else True,
                    day_of_week=value if field == "day" else 0,
                )

    def test_patch_gates_freebies_and_supply_pack_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0080-current-task-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/freebies/freebies.py", patch)
        self.assertEqual(patch.count("validate_alas_supply_pack_config("), 2)
        guard = patch.index("supply_pack_config = validate_alas_supply_pack_config(")
        mail = patch.index("if self.config.BattlePass_Collect:", guard)
        self.assertLess(guard, mail)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_supply_pack_config_contract.py",
            "python/alas_headless/alas_supply_pack_config_replay.py",
            "scripts/python/verify_alas_supply_pack_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
