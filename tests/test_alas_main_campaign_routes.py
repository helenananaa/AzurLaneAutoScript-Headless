import ast
import unittest
from pathlib import Path

from alas_headless.alas_campaign_route_config_contract import (
    MAIN_TASKS,
    validate_alas_main_campaign_route_config,
)
from alas_headless.alas_campaign_route_config_replay import verify_main_campaign_routes
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


class AlasMainCampaignRouteTests(unittest.TestCase):
    def test_all_pinned_routes_replay_for_three_tasks(self):
        if not LIVE_ALAS.joinpath("module/campaign/run.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_main_campaign_routes(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["task_count"], 3)
        self.assertEqual(result["stage_count"], 64)
        self.assertEqual(result["accepted_route_count"], 192)
        self.assertEqual(result["invalid_case_count"], 8)
        self.assertEqual(set(result["routes"]), set(MAIN_TASKS))
        for route in result["routes"].values():
            self.assertEqual(route["first_stage"], "1-1")
            self.assertEqual(route["last_stage"], "16-4")
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_runtime_guard_precedes_all_campaign_input(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0050-combat-flow-ports.patch"
        ).read_text(encoding="utf-8")
        method = patch.index("def _validate_main_campaign_route_config")
        route_guard = patch.index(
            "self._validate_main_campaign_route_config(name, folder, mode)", method
        )
        switch_guard = patch.index("self._validate_campaign_switch_config()", route_guard)
        semantic_scope = patch.index(
            "semantic_adapter.begin_campaign_pre_sortie(name, mode=mode)", switch_guard
        )
        self.assertLess(method, route_guard)
        self.assertLess(route_guard, switch_guard)
        self.assertLess(switch_guard, semantic_scope)
        for field in ("Scheduler_Command", "stage=name", "event=folder", "mode=mode"):
            self.assertIn(field, patch[method:route_guard])

    def test_invalid_main_routes_fail_closed(self):
        for values in (
            dict(task="Main", stage="-1-1", event="campaign_main", mode="normal"),
            dict(task="Main2", stage="12-4", event="event_x", mode="normal"),
            dict(task="Main3", stage="12-4", event="campaign_main", mode="hard"),
        ):
            with self.subTest(values=values), self.assertRaises(SemanticGateClosed):
                validate_alas_main_campaign_route_config(**values)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_campaign_route_config_contract.py",
            "python/alas_headless/alas_campaign_route_config_replay.py",
            "scripts/python/verify_alas_main_campaign_routes.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
