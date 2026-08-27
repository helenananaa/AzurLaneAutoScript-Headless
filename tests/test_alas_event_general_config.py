import ast
import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alas_headless.alas_event_general_config_contract import (
    TASK_BALANCER_CALLS,
    validate_alas_event_general_config,
)
from alas_headless.alas_event_general_config_replay import (
    verify_event_general_config,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


def defaults():
    return {
        "pt_limit": 0,
        "time_limit": datetime(2020, 1, 1),
        "task_balancer_enable": False,
        "task_balancer_coin_limit": 10_000,
        "task_balancer_task_call": "Main",
    }


class AlasEventGeneralConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/campaign/campaign_event.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_event_general_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 5)
        self.assertEqual(result["accepted_case_count"], 30)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_pt_formats_enable_and_task_calls_are_classified(self):
        for pt, expected in (
            (0, 0),
            (100_000, 100_000),
            ("100,000", 100_000),
            ("100。000", 100_000),
        ):
            for enabled in (False, True):
                for task in TASK_BALANCER_CALLS:
                    config = defaults()
                    config.update(
                        pt_limit=pt,
                        task_balancer_enable=enabled,
                        task_balancer_task_call=task,
                    )
                    snapshot = validate_alas_event_general_config(**config)
                    self.assertEqual(snapshot.pt_limit, expected)

    def test_invalid_values_fail_closed(self):
        for field, value in (
            ("pt_limit", -1),
            ("pt_limit", True),
            ("pt_limit", "1e5"),
            ("time_limit", "2026-08-15"),
            ("time_limit", datetime(2026, 8, 15, tzinfo=timezone.utc)),
            ("task_balancer_enable", 1),
            ("task_balancer_coin_limit", -1),
            ("task_balancer_coin_limit", True),
            ("task_balancer_task_call", "Reward"),
        ):
            config = defaults()
            config[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_event_general_config(**config)

    def test_patch_gates_every_original_decision_method(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0040-campaign-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/campaign/campaign_event.py", patch)
        self.assertEqual(patch.count("self._validate_event_general_config()"), 4)
        self.assertIn("pt = semantic_adapter.event_points()", patch)
        self.assertIn("return semantic_session.event_coin()", patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_event_general_config_contract.py",
            "python/alas_headless/alas_event_general_config_replay.py",
            "scripts/python/verify_alas_event_general_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
