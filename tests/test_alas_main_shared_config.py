import ast
import unittest
from pathlib import Path

from alas_headless.alas_main_shared_config_contract import (
    MAIN_SHARED_GROUPS,
    STOP_CONDITION_MAP_ACHIEVEMENTS,
    validate_alas_main_stop_condition_config,
)
from alas_headless.alas_main_shared_config_replay import verify_main_shared_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")


class AlasMainSharedConfigTests(unittest.TestCase):
    def test_three_panels_are_exact_shared_instances(self):
        if not PINNED_UPSTREAM.joinpath("alas.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_main_shared_config(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["tasks"], ["Main", "Main2", "Main3"])
        self.assertEqual(result["group_count"], len(MAIN_SHARED_GROUPS))
        self.assertEqual(result["field_count"], 54)
        self.assertEqual(result["panel_field_instance_count"], 162)
        self.assertEqual(
            result["intentional_template_differences"], ["Scheduler.Command"]
        )
        self.assertEqual(result["stop_condition_accepted_rows"], 60)
        self.assertEqual(result["stop_condition_rejected_rows"], 45)
        self.assertEqual(set(result["dispatches"]), {"Main", "Main2", "Main3"})
        self.assertTrue(
            all(
                dispatch["config_identity_preserved"]
                and dispatch["device_identity_preserved"]
                for dispatch in result["dispatches"].values()
            )
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_runtime_member_guards_all_six_fields_before_navigation(self):
        member = ROOT.joinpath(
            "integration/alas/series/0410-main-shared-config-runtime.patch"
        ).read_text(encoding="utf-8")
        for field in (
            "OilLimit",
            "RunCount",
            "MapAchievement",
            "StageIncrease",
            "GetNewShip",
            "ReachLevel",
        ):
            self.assertIn("self.config.StopCondition_" + field, member)
        route = member.index("self._validate_main_campaign_route_config")
        stop = member.index("self._validate_main_stop_condition_config()")
        switches = member.index("self._validate_campaign_switch_config()")
        semantic_scope = member.index("semantic_adapter = getattr")
        self.assertLess(route, stop)
        self.assertLess(stop, switches)
        self.assertLess(switches, semantic_scope)

    def test_stop_condition_contract_rejects_wrong_types(self):
        defaults = dict(
            task="Main",
            oil_limit=1000,
            run_count=0,
            map_achievement=STOP_CONDITION_MAP_ACHIEVEMENTS[0],
            stage_increase=False,
            get_new_ship=False,
            reach_level=0,
        )
        for field, value in (
            ("oil_limit", True),
            ("run_count", -1),
            ("map_achievement", "unknown"),
            ("stage_increase", 0),
            ("get_new_ship", None),
            ("reach_level", "125"),
        ):
            values = dict(defaults)
            values[field] = value
            with self.subTest(field=field), self.assertRaises(SemanticGateClosed):
                validate_alas_main_stop_condition_config(**values)

    def test_non_main_campaign_family_is_unchanged(self):
        self.assertIsNone(
            validate_alas_main_stop_condition_config(
                task="Event",
                oil_limit=-1,
                run_count=-1,
                map_achievement="event-owned",
                stage_increase=0,
                get_new_ship=0,
                reach_level=-1,
            )
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_main_shared_config_contract.py",
            "python/alas_headless/alas_main_shared_config_replay.py",
            "scripts/python/verify_alas_main_shared_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
