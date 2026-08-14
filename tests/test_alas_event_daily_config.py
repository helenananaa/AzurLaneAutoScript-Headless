import ast
import unittest
from pathlib import Path

from alas_headless.alas_event_daily_config_contract import (
    validate_alas_event_daily_last_stage,
    validate_alas_event_daily_stage_filter,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_event_daily_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasEventDailyConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/event/campaign_abcd.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 2)
        self.assertEqual(result["panel_count"], 4)
        self.assertEqual(result["accepted_case_count"], 76)
        self.assertEqual(result["invalid_case_count"], 48)
        self.assertEqual(
            result["original_decisions"]["cases"]["resume"]["runs"],
            ["a3"],
        )
        self.assertEqual(
            result["original_decisions"]["cases"]["locked_stage"]["outcome"],
            "human_takeover",
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_all_panel_filters_and_unicode_separator_are_normalized(self):
        for command in ("EventA", "EventB", "EventC", "EventD"):
            prefix = command[-1]
            self.assertEqual(
                validate_alas_event_daily_stage_filter(
                    f" {prefix}3 ＞ {prefix}1 ", task_command=command
                ),
                f"{prefix}3 > {prefix}1",
            )

    def test_last_stage_zero_and_current_panel_values_are_normalized(self):
        self.assertEqual(
            validate_alas_event_daily_last_stage(0, task_command="EventA"), 0
        )
        self.assertEqual(
            validate_alas_event_daily_last_stage(" a2 ", task_command="EventA"),
            "a2",
        )

    def test_cross_panel_partial_duplicate_and_invalid_values_fail_closed(self):
        for field, value in (
            ("filter", "B1 > B2"),
            ("filter", "A1junk"),
            ("filter", "A1 > A1"),
            ("filter", "A1 >> A2"),
            ("filter", ""),
            ("filter", None),
            ("last", "B1"),
            ("last", "A4"),
            ("last", "0"),
            ("last", 1),
            ("last", None),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                if field == "filter":
                    validate_alas_event_daily_stage_filter(
                        value, task_command="EventA"
                    )
                else:
                    validate_alas_event_daily_last_stage(
                        value, task_command="EventA"
                    )

    def test_patch_preserves_original_run_and_gates_both_fields(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0040-campaign-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("class CampaignABCD(EventBase):", patch)
        self.assertIn("validate_alas_event_daily_stage_filter", patch)
        self.assertIn("validate_alas_event_daily_last_stage", patch)
        self.assertIn("STAGE_FILTER.load(stage_filter)", patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_event_daily_config_contract.py",
            "python/alas_headless/alas_event_daily_config_replay.py",
            "scripts/python/verify_alas_event_daily_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
