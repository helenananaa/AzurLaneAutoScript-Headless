import ast
import itertools
import json
import unittest
from pathlib import Path

from alas_headless.alas_reward_config_contract import validate_alas_reward_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_reward_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")
DAILY_MISSION_EVIDENCE_ADAPTER_SHA256 = (
    "e02aae0a20cc8e63dfc219185e0f9645ff7ab8fa05632382f9e9dd66e6b54ff1"
)
DAILY_MISSION_EVIDENCE_ORACLE_SHA256 = (
    "96b7b240be56bac8a0262c503e2e9b65b42a5f5eba80eaad623adfebae2d7f40"
)
WEEKLY_MISSION_ENABLED_EVIDENCE_ADAPTER_SHA256 = (
    "60dead556a4ffc2c6bac18a30dba1afc936ccc2ed3034afee614b6cfa69d9c99"
)
WEEKLY_MISSION_ENABLED_EVIDENCE_ORACLE_SHA256 = (
    "bd56ff524debd651b7b116d33e896792f51a23f272c3f9af965ac177ef5bb237"
)
WEEKLY_MISSION_DISABLED_EVIDENCE_ADAPTER_SHA256 = (
    "99cfc62760cf28ec52ef306624eb0b76fb5d32bbd4e2a1041137e3ee744e0358"
)
WEEKLY_MISSION_DISABLED_EVIDENCE_ORACLE_SHA256 = (
    "5f8ad8130ddf55f233fb8f883f2acb95a848876bebb2af63744c5618c71df443"
)
RESOURCE_EVIDENCE_ADAPTER_SHA256 = (
    "f85437ec16f4d425bad9fb589476f957330f91de56946b624487265a6847a999"
)
RESOURCE_EVIDENCE_ORACLE_SHA256 = (
    "9632075433eca0a9d71842b3ad2dee148b84b4c25218a565fcfd97997eff50ae"
)
EXP_RESOURCE_EVIDENCE_ADAPTER_SHA256 = (
    "993c9776e05985561192c9b4725ef39181509a488a00f7e6010d37b4a9e6d172"
)
EXP_RESOURCE_EVIDENCE_ORACLE_SHA256 = (
    "c696a1c8e34225e254cfacb61fef2e120ecf54f7cb31c82ed81c3f141883be0e"
)


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "collect_oil": True,
        "collect_coin": True,
        "collect_exp": True,
        "collect_mission": True,
        "collect_weekly_mission": True,
    }
    values.update(overrides)
    return values


class AlasRewardConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/reward/reward.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 5)
        self.assertEqual(result["accepted_case_count"], 32)
        self.assertEqual(result["invalid_case_count"], 20)
        self.assertEqual(len(result["original_decisions"]["reward_cases"]), 32)
        self.assertEqual(
            result["original_decisions"]["raid_ex_disabled"]["events"][3],
            ["reward_mission", {"daily": False, "weekly": False}],
        )
        self.assertFalse(result["real_claim_method_called"])
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])
        self.assertEqual(
            result["semantic_claim_budget"],
            {"claimed": True, "input_count": 1, "budget_checks": 2},
        )

    def test_all_boolean_combinations_are_accepted(self):
        keys = tuple(_values())
        for combination in itertools.product((False, True), repeat=5):
            with self.subTest(combination=combination):
                snapshot = validate_alas_reward_config(
                    **dict(zip(keys, combination))
                )
                self.assertEqual(
                    tuple(getattr(snapshot, key) for key in keys), combination
                )

    def test_non_boolean_values_fail_closed_for_every_field(self):
        for field in _values():
            for value in (0, 1, "true", None):
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_reward_config(**_values(**{field: value}))

    def test_patch_gates_reward_and_raid_daily_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0010-mission-mail-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/raid/daily.py", patch)
        self.assertEqual(patch.count("validate_alas_reward_config("), 2)
        raid_guard = patch.index("reward_config = validate_alas_reward_config(")
        raid_rpg = patch.index("if self.is_raid_rpg():", raid_guard)
        self.assertLess(raid_guard, raid_rpg)

    def test_daily_mission_live_evidence_covers_enabled_and_disabled_values(self):
        receipt_paths = {
            True: ROOT
            / "integration/alas/reward-daily-mission-r2-live-validation-receipt.json",
            False: ROOT
            / "integration/alas/reward-daily-mission-disabled-live-validation-receipt.json",
        }
        receipts = {
            enabled: json.loads(path.read_text(encoding="utf-8"))
            for enabled, path in receipt_paths.items()
        }
        for enabled, receipt in receipts.items():
            with self.subTest(enabled=enabled):
                self.assertTrue(receipt["passed"])
                self.assertEqual(
                    receipt["configured"],
                    {
                        "Reward.CollectOil": False,
                        "Reward.CollectCoin": False,
                        "Reward.CollectExp": False,
                        "Reward.CollectMission": enabled,
                        "Reward.CollectWeeklyMission": False,
                    },
                )
                self.assertEqual(receipt["mission_claim_grant_remaining"], 0)
                self.assertTrue(receipt["main_page_visible_after_cleanup"])
                self.assertTrue(receipt["temporary_config_removed"])
                # A daily claim is consumptive and its original adapter hash
                # identifies the actual run.  Do not invalidate that
                # non-repeatable field evidence when an unrelated feature
                # (such as Dorm feed) changes another adapter method; current
                # Reward behavior is covered by the contract/replay tests in
                # this module and the adapter unit suite.
                self.assertEqual(
                    receipt["source_sha256"]["adapter"],
                    DAILY_MISSION_EVIDENCE_ADAPTER_SHA256,
                )
                self.assertEqual(
                    receipt["source_sha256"]["oracle"],
                    DAILY_MISSION_EVIDENCE_ORACLE_SHA256,
                )
        enabled_dispatches = receipts[True]["dispatches"]
        self.assertEqual(len(enabled_dispatches), 1)
        self.assertEqual(enabled_dispatches[0]["capability"], "mission.claim")
        self.assertEqual(enabled_dispatches[0]["semantic_id"], "task/claim/all")
        self.assertEqual(receipts[False]["dispatches"], [])
        self.assertEqual(
            {receipt["source_sha256"]["reward"] for receipt in receipts.values()},
            {"73af538ae1df6361941422ccc60dc1816c2e57ed00125adb102f0ff0400c3a8d"},
        )

    def test_weekly_mission_live_evidence_covers_enabled_and_disabled_values(self):
        receipt_paths = {
            True: ROOT / "integration/alas/reward-weekly-mission-live-validation-receipt.json",
            False: ROOT
            / "integration/alas/reward-weekly-mission-disabled-r1-live-validation-receipt.json",
        }
        receipts = {
            enabled: json.loads(path.read_text(encoding="utf-8"))
            for enabled, path in receipt_paths.items()
        }
        for enabled, receipt in receipts.items():
            with self.subTest(enabled=enabled):
                self.assertTrue(receipt["passed"])
                self.assertEqual(
                    receipt["configured"],
                    {
                        "Reward.CollectOil": False,
                        "Reward.CollectCoin": False,
                        "Reward.CollectExp": False,
                        "Reward.CollectMission": False,
                        "Reward.CollectWeeklyMission": enabled,
                    },
                )
                self.assertEqual(receipt["mission_claim_grant_remaining"], 0)
                self.assertTrue(receipt["main_page_visible_after_cleanup"])
                self.assertTrue(receipt["temporary_config_removed"])
        # The enabled weekly branch is consumptive.  Pin its original adapter
        # and Oracle source digests rather than requiring a repeat claim after
        # subsequent unrelated adapter/oracle improvements.
        enabled_receipt = receipts[True]
        self.assertEqual(
            enabled_receipt["source_sha256"]["adapter"],
            WEEKLY_MISSION_ENABLED_EVIDENCE_ADAPTER_SHA256,
        )
        self.assertEqual(
            enabled_receipt["source_sha256"]["oracle"],
            WEEKLY_MISSION_ENABLED_EVIDENCE_ORACLE_SHA256,
        )
        self.assertEqual(
            enabled_receipt["dispatches"],
            [
                {
                    "capability": "mission.claim",
                    "semantic_id": "task/weekly-progress/claim",
                    "generation": 102118,
                    "path": "UICamera/Canvas/UIMain/TaskScene(Clone)/pages/TaskListForWeekPage(Clone)/task_progress/get_btn",
                    "policy_sha256": "87caf7f4380a2e5cf1b2f0b63408cfa04b439a28c62d73d98f2c716038b6ac86",
                    "remaining_after_dispatch": None,
                }
            ],
        )
        disabled_receipt = receipts[False]
        self.assertEqual(disabled_receipt["dispatches"], [])
        # This older non-mutating weekly-disabled receipt is historical
        # evidence.  Pin its sources instead of coupling it to later unrelated
        # Reward adapter/oracle improvements.
        self.assertEqual(
            disabled_receipt["source_sha256"]["adapter"],
            WEEKLY_MISSION_DISABLED_EVIDENCE_ADAPTER_SHA256,
        )
        self.assertEqual(
            disabled_receipt["source_sha256"]["oracle"],
            WEEKLY_MISSION_DISABLED_EVIDENCE_ORACLE_SHA256,
        )
        self.assertEqual(
            {receipt["source_sha256"]["reward"] for receipt in receipts.values()},
            {"73af538ae1df6361941422ccc60dc1816c2e57ed00125adb102f0ff0400c3a8d"},
        )

    def test_resource_live_evidence_completes_oil_and_coin_only(self):
        cases = {
            "Reward.CollectOil": (
                ROOT / "integration/alas/reward-oil-live-validation-receipt.json",
                "OIL",
                "reward/resource/oil",
            ),
            "Reward.CollectCoin": (
                ROOT / "integration/alas/reward-coin-live-validation-receipt.json",
                "COIN",
                "reward/resource/coin",
            ),
        }
        for field, (path, button, semantic_id) in cases.items():
            with self.subTest(field=field):
                receipt = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(receipt["passed"])
                self.assertEqual(
                    receipt["configured"],
                    {
                        "Reward.CollectOil": field == "Reward.CollectOil",
                        "Reward.CollectCoin": field == "Reward.CollectCoin",
                        "Reward.CollectExp": False,
                        "Reward.CollectMission": False,
                        "Reward.CollectWeeklyMission": False,
                    },
                )
                self.assertGreater(receipt["resource_state_before"][field]["amount"], 0)
                self.assertTrue(receipt["resource_state_before"][field]["available"])
                self.assertEqual(receipt["resource_state_after"][field], {
                    "amount": 0,
                    "available": False,
                })
                self.assertEqual(len(receipt["resource_dispatches"]), 1)
                dispatch = receipt["resource_dispatches"][0]
                self.assertEqual(dispatch["button"], button)
                self.assertEqual(dispatch["semantic_id"], semantic_id)
                self.assertIsInstance(dispatch["generation"], int)
                self.assertTrue(
                    dispatch["path"].endswith(
                        {
                            "OIL": "/canteen/bubble",
                            "COIN": "/merchant/bubble",
                        }[button]
                    )
                )
                self.assertEqual(set(dispatch["point"]), {"x", "y"})
                for coordinate in dispatch["point"].values():
                    self.assertIsInstance(coordinate, (int, float))
                self.assertTrue(receipt["cleanup"]["main_page_visible"])
                self.assertTrue(receipt["temporary_config_removed"])
                self.assertEqual(
                    receipt["source_sha256"]["adapter"],
                    RESOURCE_EVIDENCE_ADAPTER_SHA256,
                )
                self.assertEqual(
                    receipt["source_sha256"]["oracle"],
                    RESOURCE_EVIDENCE_ORACLE_SHA256,
                )

        disabled = json.loads(
            (
                ROOT
                / "integration/alas/reward-resource-disabled-live-validation-receipt.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(disabled["passed"])
        self.assertEqual(
            disabled["configured"],
            {
                "Reward.CollectOil": False,
                "Reward.CollectCoin": False,
                "Reward.CollectExp": False,
                "Reward.CollectMission": False,
                "Reward.CollectWeeklyMission": False,
            },
        )
        self.assertEqual(disabled["resource_dispatches"], [])
        self.assertTrue(disabled["cleanup"]["main_page_visible"])
        self.assertTrue(disabled["temporary_config_removed"])
        self.assertEqual(
            disabled["source_sha256"]["adapter"],
            RESOURCE_EVIDENCE_ADAPTER_SHA256,
        )
        self.assertEqual(
            disabled["source_sha256"]["oracle"],
            RESOURCE_EVIDENCE_ORACLE_SHA256,
        )

    def test_exp_resource_live_evidence_covers_enabled_and_disabled_values(self):
        enabled = json.loads(
            (
                ROOT / "integration/alas/reward-exp-live-validation-receipt.json"
            ).read_text(encoding="utf-8")
        )
        disabled = json.loads(
            (
                ROOT
                / "integration/alas/reward-exp-disabled-live-validation-receipt.json"
            ).read_text(encoding="utf-8")
        )
        for configured, receipt in ((True, enabled), (False, disabled)):
            with self.subTest(configured=configured):
                self.assertTrue(receipt["passed"])
                self.assertEqual(
                    receipt["configured"],
                    {
                        "Reward.CollectOil": False,
                        "Reward.CollectCoin": False,
                        "Reward.CollectExp": configured,
                        "Reward.CollectMission": False,
                        "Reward.CollectWeeklyMission": False,
                    },
                )
                self.assertTrue(receipt["cleanup"]["main_page_visible"])
                self.assertTrue(receipt["temporary_config_removed"])
                self.assertEqual(
                    receipt["source_sha256"]["adapter"],
                    EXP_RESOURCE_EVIDENCE_ADAPTER_SHA256,
                )
                self.assertEqual(
                    receipt["source_sha256"]["oracle"],
                    EXP_RESOURCE_EVIDENCE_ORACLE_SHA256,
                )

        self.assertGreater(
            enabled["resource_state_before"]["Reward.CollectExp"]["amount"], 0
        )
        self.assertTrue(
            enabled["resource_state_before"]["Reward.CollectExp"]["available"]
        )
        self.assertEqual(
            enabled["resource_state_after"]["Reward.CollectExp"],
            {"amount": 0, "available": False},
        )
        self.assertEqual(len(enabled["resource_dispatches"]), 1)
        dispatch = enabled["resource_dispatches"][0]
        self.assertEqual(dispatch["button"], "EXP")
        self.assertEqual(dispatch["semantic_id"], "reward/resource/exp")
        self.assertTrue(dispatch["path"].endswith("/class/bubble"))
        self.assertEqual(set(dispatch["point"]), {"x", "y"})
        self.assertEqual(disabled["resource_dispatches"], [])
        self.assertEqual(
            disabled["resource_state_before"]["Reward.CollectExp"],
            disabled["resource_state_after"]["Reward.CollectExp"],
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_reward_config_contract.py",
            "python/alas_headless/alas_reward_config_replay.py",
            "scripts/python/verify_alas_reward_config.py",
            "scripts/python/run_alas_reward_mission_live_validation.py",
            "scripts/python/run_alas_reward_resource_live_validation.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
