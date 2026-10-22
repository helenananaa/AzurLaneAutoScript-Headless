import ast
from datetime import datetime, timezone
import itertools
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from alas_headless.alas_shipyard_config_contract import (
    SHIPYARD_DR_SERIES,
    SHIPYARD_INDICES,
    SHIPYARD_PR_SERIES,
    SHIPYARD_VERIFIED_BUY_AMOUNTS,
    validate_alas_shipyard_config,
)
from alas_headless.alas_shipyard_config_replay import verify_shipyard_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasShipyardConfigTests(unittest.TestCase):
    def test_native_entry_passes_installed_series_options_to_the_contract(self):
        from tests.test_alas_config_branch_compatibility import method

        config = SimpleNamespace(
            Shipyard_ResearchSeries=9, Shipyard_ShipIndex=1, Shipyard_BuyAmount=2,
            Shipyard_LastRun=datetime(2020, 1, 1),
            ShipyardDr_ResearchSeries=8, ShipyardDr_ShipIndex=1, ShipyardDr_BuyAmount=2,
            ShipyardDr_LastRun=datetime(2020, 1, 1), task_delay=Mock(),
            args={"Shipyard": {
                "Shipyard": {"ResearchSeries": {"option": [1, 9]}},
                "ShipyardDr": {"ResearchSeries": {"option": [2, 8]}},
            }},
        )
        host = SimpleNamespace(config=config, shipyard_run=Mock())
        run = method("module/shipyard/shipyard_reward.py", "RewardShipyard", "run",
                     get_server_last_update=lambda _: datetime(2026, 10, 2))
        run(host)
        self.assertEqual(
            [call.kwargs for call in host.shipyard_run.call_args_list],
            [{"series": 8, "index": 1, "count": 2},
             {"series": 9, "index": 1, "count": 2}],
        )
        # ALAS still owns dispatch. An undeclared choice stops before either
        # branch, while this controlled test never navigates or buys anything.
        config.args = {}
        host.shipyard_run.reset_mock()
        with self.assertRaises(SemanticGateClosed):
            run(host)
        host.shipyard_run.assert_not_called()

    def test_installed_upstream_options_admit_new_series_without_enabling_unproven_costs(self):
        case = dict(pr_series=9, pr_index=1, pr_buy_amount=2, pr_last_run=datetime(2020, 1, 1),
                    dr_series=8, dr_index=1, dr_buy_amount=2, dr_last_run=datetime(2020, 1, 1))
        with self.assertRaises(SemanticGateClosed):
            validate_alas_shipyard_config(**case)
        options = dict(pr_options={'ResearchSeries': {'option': [1, 9]}},
                       dr_options={'ResearchSeries': {'option': [2, 8]}})
        state = validate_alas_shipyard_config(**case, **options)
        self.assertEqual((state.pr_series, state.dr_series), (9, 8))
        for change in ({'pr_series': 10}, {'pr_series': True}, {'pr_buy_amount': 16}):
            with self.subTest(change=change), self.assertRaises(SemanticGateClosed):
                validate_alas_shipyard_config(**{**case, **change}, **options)

    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/shipyard/shipyard_reward.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_shipyard_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 8)
        self.assertEqual(result["accepted_case_count"], 1_437)
        self.assertEqual(result["invalid_case_count"], 58)
        self.assertEqual(
            result["focus_matrix"],
            {"success": 32, "disabled": 6, "series_restricted": 4},
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_blueprints_consumed"])
        self.assertFalse(result["real_coin_consumed"])
        self.assertFalse(result["real_navigation_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_all_declared_focus_combinations_are_classified(self):
        for pr_series, pr_index, dr_series, dr_index in itertools.product(
            SHIPYARD_PR_SERIES,
            SHIPYARD_INDICES,
            SHIPYARD_DR_SERIES,
            SHIPYARD_INDICES,
        ):
            snapshot = validate_alas_shipyard_config(
                pr_series=pr_series,
                pr_index=pr_index,
                pr_buy_amount=2,
                pr_last_run=datetime(2020, 1, 1),
                dr_series=dr_series,
                dr_index=dr_index,
                dr_buy_amount=2,
                dr_last_run=datetime(2020, 1, 1),
            )
            self.assertEqual(
                (
                    snapshot.pr_series,
                    snapshot.pr_index,
                    snapshot.pr_buy_amount,
                    snapshot.dr_series,
                    snapshot.dr_index,
                    snapshot.dr_buy_amount,
                ),
                (pr_series, pr_index, 2, dr_series, dr_index, 2),
            )

    def test_verified_buy_amounts_and_record_boundaries_are_classified(self):
        for pr_amount, dr_amount in itertools.product(
            SHIPYARD_VERIFIED_BUY_AMOUNTS, repeat=2
        ):
            snapshot = validate_alas_shipyard_config(
                pr_series=1,
                pr_index=1,
                pr_buy_amount=pr_amount,
                pr_last_run=datetime(2000, 1, 1),
                dr_series=2,
                dr_index=1,
                dr_buy_amount=dr_amount,
                dr_last_run=datetime(2100, 1, 1),
            )
            self.assertEqual(
                (snapshot.pr_buy_amount, snapshot.dr_buy_amount),
                (pr_amount, dr_amount),
            )

    def test_invalid_single_fields_fail_closed(self):
        invalid = {
            "pr_series": (0, 7, True, 1.0, "1", None, []),
            "pr_index": (-1, 7, True, 1.0, "1", None, []),
            "pr_buy_amount": (-1, 16, True, 1.0, "2", None, [], {}),
            "pr_last_run": (
                None,
                "2020-01-01 00:00:00",
                datetime(1999, 12, 31, 23, 59, 59),
                datetime(2100, 1, 1, 0, 0, 1),
                datetime(2026, 8, 15, tzinfo=timezone.utc),
            ),
            "dr_series": (1, 6, True, 2.0, "2", None, []),
            "dr_index": (-1, 7, True, 1.0, "1", None, []),
            "dr_buy_amount": (-1, 16, True, 1.0, "2", None, [], {}),
            "dr_last_run": (
                None,
                "2020-01-01 00:00:00",
                datetime(1999, 12, 31, 23, 59, 59),
                datetime(2100, 1, 1, 0, 0, 1),
                datetime(2026, 8, 15, tzinfo=timezone.utc),
            ),
        }
        for field, values in invalid.items():
            for value in values:
                case = {
                    "pr_series": 1,
                    "pr_index": 1,
                    "pr_buy_amount": 2,
                    "pr_last_run": datetime(2020, 1, 1),
                    "dr_series": 2,
                    "dr_index": 1,
                    "dr_buy_amount": 2,
                    "dr_last_run": datetime(2020, 1, 1),
                }
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_shipyard_config(**case)

    def test_disabled_rarity_does_not_block_the_other_shipyard_branch(self):
        defaults = {
            "pr_series": 1,
            "pr_index": 1,
            "pr_buy_amount": 2,
            "pr_last_run": datetime(2020, 1, 1),
            "dr_series": 2,
            "dr_index": 1,
            "dr_buy_amount": 2,
            "dr_last_run": datetime(2020, 1, 1),
        }
        for disabled, active in (("pr", "dr"), ("dr", "pr")):
            with self.subTest(disabled=disabled):
                case = {
                    **defaults,
                    f"{disabled}_buy_amount": 0,
                    f"{disabled}_series": "obsolete-series",
                    f"{disabled}_index": None,
                }
                snapshot = validate_alas_shipyard_config(**case)
                self.assertIsNone(getattr(snapshot, f"{disabled}_series"))
                self.assertIsNone(getattr(snapshot, f"{disabled}_index"))
                self.assertEqual(getattr(snapshot, f"{active}_buy_amount"), 2)
                # Re-enabling the branch restores its identity checks.
                with self.assertRaises(SemanticGateClosed):
                    validate_alas_shipyard_config(**{**case, f"{disabled}_buy_amount": 2})
                # The original run still reads both LastRun fields even when
                # only one rarity is enabled.
                with self.assertRaises(SemanticGateClosed):
                    validate_alas_shipyard_config(**{**case, f"{disabled}_last_run": None})

    def test_patch_gates_original_shipyard_entry(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0070-shipyard-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_shipyard_config("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_shipyard_config_contract.py",
            "python/alas_headless/alas_shipyard_config_replay.py",
            "scripts/python/verify_alas_shipyard_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
