import ast
import unittest
from pathlib import Path

from alas_headless.alas_event_shared_entry_contract import (
    EVENT_COMMANDS,
    EVENT_SHARED_GROUPS,
    validate_alas_event_shared_entry_config,
)
from alas_headless.alas_event_shared_entry_replay import verify_event_shared_entry
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasEventSharedEntryTests(unittest.TestCase):
    def test_seven_panels_share_one_base_surface(self):
        if not PINNED_UPSTREAM.joinpath("alas.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_event_shared_entry(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["tasks"], list(EVENT_COMMANDS))
        self.assertEqual(result["shared_group_count"], len(EVENT_SHARED_GROUPS))
        self.assertEqual(result["shared_field_count"], 54)
        self.assertEqual(result["panel_field_instance_count"], 386)
        self.assertEqual(result["accepted_entry_rows"], 81)
        self.assertEqual(result["rejected_entry_rows"], 80)
        self.assertEqual(result["event_inventory"]["script_count"], 13)
        self.assertEqual(set(result["dispatches"]), set(EVENT_COMMANDS))
        self.assertTrue(
            all(
                value["config_identity_preserved"]
                and value["device_identity_preserved"]
                for value in result["dispatches"].values()
            )
        )
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_contract_preserves_non_event_campaign_consumers(self):
        self.assertIsNone(
            validate_alas_event_shared_entry_config(
                task="Main", stage="12-4", event="campaign_main", mode="normal"
            )
        )

    def test_wrong_family_and_unsafe_folder_fail_closed(self):
        defaults = dict(
            task="EventA",
            stage="dynamic",
            event="event_20260813_cn",
            mode="normal",
        )
        for field, value in (
            ("stage", "B1"),
            ("event", "../event_20260813_cn"),
            ("event", "campaign_main"),
            ("mode", "hard"),
            ("task", None),
        ):
            values = dict(defaults)
            values[field] = value
            with self.subTest(field=field), self.assertRaises(SemanticGateClosed):
                validate_alas_event_shared_entry_config(**values)

    def test_runtime_member_guards_every_entry_before_stateful_boundaries(self):
        member = ROOT.joinpath(
            "integration/alas/series/0420-event-shared-entry-runtime.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("module/campaign/run.py", member)
        self.assertIn("module/event/campaign_abcd.py", member)
        self.assertIn("module/event/campaign_sp.py", member)
        self.assertLess(
            member.index("self._validate_event_shared_entry_config(name, folder, mode)"),
            member.index("self._validate_campaign_switch_config()"),
        )
        self.assertLess(
            member.index("validate_alas_event_shared_entry_config", member.index("campaign_abcd.py")),
            member.index("stage_filter = validate_alas_event_daily_stage_filter", member.index("campaign_abcd.py")),
        )
        self.assertLess(
            member.index("validate_alas_event_shared_entry_config", member.index("campaign_sp.py")),
            member.index("os.path.exists", member.index("campaign_sp.py")),
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_event_shared_entry_contract.py",
            "python/alas_headless/alas_event_shared_entry_replay.py",
            "scripts/python/verify_alas_event_shared_entry.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
