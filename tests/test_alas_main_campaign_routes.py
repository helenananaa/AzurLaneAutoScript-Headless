import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from alas_headless.alas_campaign_route_config_contract import (
    MAIN_TASKS,
    validate_alas_main_campaign_route_config,
)
from alas_headless.alas_campaign_route_config_replay import verify_main_campaign_routes
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-alas-topdown-live")


def test_original_campaign_run_normalizes_only_its_semantic_stage_entry():
    from tests.test_alas_config_branch_compatibility import method, source
    from tests.semantic_support.adapter_fixtures import FakeOracle
    from alas_headless import AlasSemanticAdapter

    normalizer = next(node for node in ast.parse(source("module/handler/fast_forward.py")).body
                      if isinstance(node, ast.FunctionDef) and node.name == "to_map_input_name")
    scope = {"re": re}
    exec(compile(ast.Module(body=[normalizer], type_ignores=[]), "fast_forward.py", "exec"), scope)
    run = method("module/campaign/run.py", "CampaignRun", "run",
                 to_map_input_name=scope["to_map_input_name"])

    class Config:
        def __getattr__(self, name):
            return None  # Other contracts are independently covered.

    for stage in ("12-4", "campaign_12_4", "12_4", " 12 - 4 "):
        adapter = AlasSemanticAdapter(FakeOracle(), lambda: None)
        entries, native_runs = [], []

        def begin(canonical, mode):
            adapter.begin_campaign_pre_sortie(canonical, mode)
            entries.append(adapter._campaign_context.stage_code)

        semantic = SimpleNamespace(
            validate_campaign_fleet_config=Mock(), validate_campaign_hp_control_config=Mock(),
            validate_campaign_enemy_priority_config=Mock(), validate_campaign_submarine_config=Mock(),
            begin_campaign_pre_sortie=begin, end_campaign_pre_sortie=adapter.end_campaign_pre_sortie,
        )
        host = SimpleNamespace(
            config=Config(), device=SimpleNamespace(semantic_adapter=semantic),
            _validate_main_campaign_route_config=lambda name, folder, mode:
                validate_alas_main_campaign_route_config(task="Main", stage=name, event=folder, mode=mode),
            _validate_main_stop_condition_config=Mock(), _validate_event_shared_entry_config=Mock(),
            _validate_campaign_switch_config=Mock(),
            _run=lambda name, **options: native_runs.append((name, options)) or "native-result",
        )
        assert run(host, stage, total=2) == "native-result"
        assert entries == ["12-4"]
        assert native_runs == [(stage, {"folder": "campaign_main", "mode": "normal", "total": 2})]
        assert adapter._campaign_context is None


class AlasMainCampaignRouteTests(unittest.TestCase):
    def test_native_main_route_aliases_share_one_canonical_stage(self):
        for task in MAIN_TASKS:
            for stage in ("12-4", "campaign_12_4", "12_4", " 12 - 4 ", "CAMPAIGN_12_4"):
                with self.subTest(task=task, stage=stage):
                    route = validate_alas_main_campaign_route_config(
                        task=task, stage=stage, event="campaign_main", mode="normal",
                    )
                    self.assertEqual(route.stage, "12-4")
                    self.assertEqual(route.module_name, "campaign_12_4")

    def test_main_alias_admission_does_not_allow_paths_or_invalid_sections(self):
        for stage in ("campaign_12_5", "../campaign_12_4", "campaign_12-4", "12_4.extra"):
            with self.subTest(stage=stage), self.assertRaises(SemanticGateClosed):
                validate_alas_main_campaign_route_config(
                    task="Main", stage=stage, event="campaign_main", mode="normal",
                )

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
