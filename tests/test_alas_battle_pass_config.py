import ast
import json
import unittest
from pathlib import Path

from alas_headless.alas_battle_pass_config_contract import (
    validate_alas_battle_pass_config,
)
from alas_headless.alas_battle_pass_config_replay import verify_battle_pass_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasBattlePassConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/freebies/freebies.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_battle_pass_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["accepted_case_count"], 2)
        self.assertEqual(result["invalid_case_count"], 7)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_battle_pass_run_called"])
        self.assertFalse(result["android_input_injected"])

    def test_both_values_are_classified(self):
        for value in (False, True):
            self.assertEqual(
                validate_alas_battle_pass_config(collect=value).collect, value
            )

    def test_invalid_values_fail_closed(self):
        for value in (0, 1, None, "true", "false", [], {}):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_battle_pass_config(collect=value)

    def test_patch_gates_original_freebies_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0080-current-task-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_battle_pass_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_battle_pass_config_contract.py",
            "python/alas_headless/alas_battle_pass_config_replay.py",
            "scripts/python/verify_alas_battle_pass_config.py",
            "scripts/python/run_alas_freebies_remaining_live_validation.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))

    def test_live_ordinary_claim_receipt_excludes_paid_input(self):
        receipt = json.loads(
            ROOT.joinpath(
                "integration/alas/freebies-battle-pass-live-validation-receipt-20260825-r1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(receipt["passed"])
        self.assertEqual(
            [action["semantic_id"] for action in receipt["actions"]],
            [
                "reward/battle-pass/enter",
                "battle-pass/claim-all",
                "reward/award-info/close",
            ],
        )
        self.assertFalse(receipt["postcondition"]["ordinary_claim_all_available"])
        self.assertFalse(receipt["postcondition"]["paid_upgrade_control_clicked"])
        self.assertFalse(receipt["postcondition"]["premium_currency_input"])

    def test_combined_freebies_live_receipt_is_zero_purchase(self):
        receipt = json.loads(
            ROOT.joinpath(
                "integration/alas/freebies-remaining-live-validation-receipt-20260825-r1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(receipt["passed"])
        self.assertTrue(receipt["task_result"])
        self.assertEqual(receipt["configured"]["DataKey.ForceCollect"], False)
        self.assertEqual(receipt["actions"], [])
        self.assertIn(
            {"method": "free_weekly_supply_pack_available", "value": False},
            receipt["observations"],
        )
        self.assertTrue(receipt["temporary_config_removed"])


if __name__ == "__main__":
    unittest.main()
