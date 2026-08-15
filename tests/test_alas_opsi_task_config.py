import ast
import unittest
from itertools import product
from pathlib import Path

from alas_headless.alas_opsi_task_config_contract import (
    OPSI_HAZARD1_TARGET_ZONES,
    OPSI_FLEET_INDEXES,
    OPSI_MEOWFFICER_HAZARD_LEVELS,
    OPSI_MONTH_BOSS_MODES,
    validate_alas_opsi_daily_config,
    validate_alas_opsi_action_point_purchase,
    validate_alas_opsi_delay_task_config,
    validate_alas_opsi_explore_config,
    validate_alas_opsi_fleet_selection,
    validate_alas_opsi_hazard1_config,
    validate_alas_opsi_meowfficer_config,
    validate_alas_opsi_month_boss_config,
    validate_alas_opsi_order,
    validate_alas_opsi_obscure_config,
    validate_alas_opsi_repair_config,
    validate_alas_opsi_rescan_config,
    validate_alas_opsi_storage_config,
)
from alas_headless.alas_opsi_task_config_replay import verify_opsi_task_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasOpsiTaskConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/os/tasks/month_boss.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_opsi_task_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 19)
        self.assertEqual(result["accepted_case_count"], 92)
        self.assertEqual(result["invalid_case_count"], 155)
        self.assertEqual(
            result["zero_runtime_consumers"],
            {
                "OpsiMonthBoss_ForceRun": [],
                "OpsiDaily_DoMission": [],
            },
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])
        self.assertEqual(
            result["validated_runtime_boundaries"],
            {
                "OpsiFleet.Fleet": "OSFleet.fleet_set",
                "OpsiFleet.Submarine": "MapOrderHandler.os_order_execute",
                "OpsiMeowfficerFarming.ActionPointPreserve": (
                    "OpsiMeowfficerFarming.os_meowfficer_farming"
                ),
                "OpsiMeowfficerFarming.TargetZone": (
                    "ZoneManager.name_to_zone -> "
                    "OpsiMeowfficerFarming.os_meowfficer_farming"
                ),
                "OpsiGeneral.UseLogger": "StorageHandler.storage_get_next_item",
                "OpsiGeneral.BuyActionPointLimit": (
                    "ActionPointHandler.action_point_buy"
                ),
                "OpsiGeneral.OilLimit": "ActionPointHandler.action_point_buy",
                "OpsiGeneral.RepairThreshold": "OSMap.handle_fleet_repair",
                "OpsiGeneral.DoRandomMapEvent": "OSMap.run_auto_search",
            },
        )

    def test_valid_values_are_classified(self):
        for mode in OPSI_MONTH_BOSS_MODES:
            for check in (False, True):
                snapshot = validate_alas_opsi_month_boss_config(
                    mode=mode, check_adaptability=check
                )
                self.assertEqual((snapshot.mode, snapshot.check_adaptability), (mode, check))
        for force in (False, True):
            self.assertEqual(
                validate_alas_opsi_obscure_config(force_run=force).force_run,
                force,
            )
        for use_tuning_sample in (False, True):
            self.assertEqual(
                validate_alas_opsi_daily_config(
                    use_tuning_sample=use_tuning_sample
                ).use_tuning_sample,
                use_tuning_sample,
            )
        for target_zone in OPSI_HAZARD1_TARGET_ZONES:
            self.assertEqual(
                validate_alas_opsi_hazard1_config(
                    target_zone=target_zone
                ).target_zone,
                target_zone,
            )
        for hazard_level in OPSI_MEOWFFICER_HAZARD_LEVELS:
            self.assertEqual(
                validate_alas_opsi_meowfficer_config(
                    action_point_preserve=1000,
                    hazard_level=hazard_level,
                    target_zone=0,
                ).hazard_level,
                hazard_level,
            )
        for action_point_preserve in (0, 1000, 2500):
            self.assertEqual(
                validate_alas_opsi_meowfficer_config(
                    action_point_preserve=action_point_preserve,
                    hazard_level=5,
                    target_zone=0,
                ).action_point_preserve,
                action_point_preserve,
            )
        for target_zone in (
            0,
            51,
            "51",
            "东南洋脊A",
            "Southeast Ocean Ridge A",
            "南東海嶺A",
            "東南洋脊A",
        ):
            self.assertEqual(
                validate_alas_opsi_meowfficer_config(
                    action_point_preserve=1000,
                    hazard_level=5,
                    target_zone=target_zone,
                ).target_zone,
                target_zone,
            )
        fields = (
            "explore_force_run",
            "obscure_force_run",
            "abyssal_force_run",
            "stronghold_force_run",
            "special_radar",
        )
        for values in product((False, True), repeat=5):
            kwargs = dict(zip(fields, values, strict=True))
            snapshot = validate_alas_opsi_delay_task_config(**kwargs)
            self.assertEqual(
                snapshot.force_run,
                any(values[:4]),
            )
            self.assertEqual(snapshot.special_radar, values[4])
            self.assertEqual(
                validate_alas_opsi_explore_config(
                    special_radar=values[4]
                ).special_radar,
                values[4],
            )
        for fleet in OPSI_FLEET_INDEXES:
            self.assertEqual(
                validate_alas_opsi_fleet_selection(fleet=fleet).fleet,
                fleet,
            )
        for recon_scan, submarine_call in product((False, True), repeat=2):
            snapshot = validate_alas_opsi_order(
                recon_scan=recon_scan,
                submarine_call=submarine_call,
            )
            self.assertEqual(
                (snapshot.recon_scan, snapshot.submarine_call),
                (recon_scan, submarine_call),
            )
        for use_logger in (False, True):
            self.assertEqual(
                validate_alas_opsi_storage_config(
                    use_logger=use_logger
                ).use_logger,
                use_logger,
            )
        for buy_limit, oil_limit in product(range(6), (0, 1000, 50_000)):
            snapshot = validate_alas_opsi_action_point_purchase(
                buy_limit=buy_limit,
                oil_limit=oil_limit,
            )
            self.assertEqual((snapshot.buy_limit, snapshot.oil_limit), (buy_limit, oil_limit))
        for threshold in (-1, 0, 0.4, 1):
            self.assertEqual(
                validate_alas_opsi_repair_config(
                    threshold=threshold
                ).threshold,
                float(threshold),
            )
        for do_random_map_event in (False, True):
            self.assertEqual(
                validate_alas_opsi_rescan_config(
                    do_random_map_event=do_random_map_event
                ).do_random_map_event,
                do_random_map_event,
            )

    def test_invalid_values_fail_closed(self):
        for mode in ("", "hard", None, 0, True, [], {}):
            with self.subTest(mode=mode), self.assertRaises(SemanticGateClosed):
                validate_alas_opsi_month_boss_config(
                    mode=mode, check_adaptability=True
                )
        for value in (0, 1, "true", None, [], {}):
            with self.subTest(field="check", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_month_boss_config(
                    mode="normal", check_adaptability=value
                )
            with self.subTest(field="force", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_obscure_config(force_run=value)
            with self.subTest(field="daily", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_daily_config(use_tuning_sample=value)
        for value in (-1, 1, 23, 45, None, True, "22", 22.0, [], {}):
            with self.subTest(field="hazard_target", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_hazard1_config(target_zone=value)
        for value in (0, 1, 2, 7, 9, 11, None, True, "5", 5.0, [], {}):
            with self.subTest(field="meow_hazard", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_meowfficer_config(
                    action_point_preserve=1000,
                    hazard_level=value,
                    target_zone=0,
                )
        for value in (-1, None, True, False, "1000", 1000.0, [], {}):
            with self.subTest(field="meow_preserve", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_meowfficer_config(
                    action_point_preserve=value,
                    hazard_level=5,
                    target_zone=0,
                )
        for value in (-1, "", "   ", None, True, False, 51.0, [], {}):
            with self.subTest(field="meow_target", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_meowfficer_config(
                    action_point_preserve=1000,
                    hazard_level=5,
                    target_zone=value,
                )
        fields = (
            "explore_force_run",
            "obscure_force_run",
            "abyssal_force_run",
            "stronghold_force_run",
            "special_radar",
        )
        for value in (0, 1, "true", None, [], {}):
            for field in fields:
                kwargs = {name: False for name in fields}
                kwargs[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_opsi_delay_task_config(**kwargs)
        for value in (-1, 0, 5, None, True, False, "1", 1.0, [], {}):
            with self.subTest(field="fleet", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_fleet_selection(fleet=value)
        for value in (0, 1, "true", None, [], {}):
            for field in ("recon_scan", "submarine_call"):
                kwargs = {"recon_scan": False, "submarine_call": False}
                kwargs[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_opsi_order(**kwargs)
            with self.subTest(field="use_logger", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_storage_config(use_logger=value)
        for value in (-1, 6, None, True, False, "1", 1.0, [], {}):
            with self.subTest(field="buy_limit", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_action_point_purchase(
                    buy_limit=value,
                    oil_limit=1000,
                )
        for value in (-1, None, True, False, "1000", 1000.0, [], {}):
            with self.subTest(field="oil_limit", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_action_point_purchase(
                    buy_limit=0,
                    oil_limit=value,
                )
        for value in (1.1, float("nan"), float("inf"), float("-inf"), None, True, False, "0.4", [], {}):
            with self.subTest(field="repair_threshold", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_repair_config(threshold=value)
        for value in (0, 1, "true", None, [], {}):
            with self.subTest(field="do_random_map_event", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_opsi_rescan_config(do_random_map_event=value)

    def test_patch_gates_original_task_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0090-operation-siren-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_opsi_month_boss_config("), 2)
        self.assertEqual(patch.count("validate_alas_opsi_obscure_config("), 2)
        self.assertEqual(patch.count("validate_alas_opsi_daily_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_hazard1_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_meowfficer_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_explore_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_fleet_selection("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_order("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_storage_config("), 1)
        self.assertEqual(
            patch.count("validate_alas_opsi_action_point_purchase("), 1
        )
        self.assertEqual(patch.count("validate_alas_opsi_repair_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_rescan_config("), 1)
        scheduler_patch = ROOT.joinpath(
            "integration/alas/series/0140-scheduler-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            scheduler_patch.count("validate_alas_opsi_delay_task_config("), 1
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_opsi_task_config_contract.py",
            "python/alas_headless/alas_opsi_task_config_replay.py",
            "scripts/python/verify_alas_opsi_task_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
