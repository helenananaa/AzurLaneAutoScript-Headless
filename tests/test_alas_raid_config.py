import ast
import itertools
import unittest
from pathlib import Path

from alas_headless.alas_raid_config_contract import (
    RAID_DAILY_STAGES,
    validate_alas_raid_daily_stage_filter,
    validate_alas_raid_mode,
    validate_alas_raid_use_ticket,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_raid_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")
RAID_REMAIN_PATCH = ROOT / "integration/alas/series/0450-raid-daily-remain-port.patch"
CURRENT_RAID_PATCH = ROOT / "integration/alas/series/0480-current-raid-runtime.patch"


class AlasRaidConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/raid/raid.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 70)
        self.assertEqual(result["invalid_case_count"], 21)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertEqual(result["ticket_final_input_boundaries"], 2)
        self.assertFalse(result["android_input_injected"])

    def test_all_declared_stage_filter_permutations_are_admitted(self):
        for size in range(1, 5):
            for tokens in itertools.permutations(sorted(RAID_DAILY_STAGES), size):
                value = " > ".join(tokens)
                with self.subTest(value=value):
                    self.assertEqual(validate_alas_raid_daily_stage_filter(value), value)

    def test_invalid_settings_fail_closed(self):
        for function, value in (
            (validate_alas_raid_mode, "HARD"),
            (validate_alas_raid_mode, True),
            (validate_alas_raid_use_ticket, 0),
            (validate_alas_raid_use_ticket, "false"),
            (validate_alas_raid_daily_stage_filter, "hard > hard"),
            (validate_alas_raid_daily_stage_filter, "hard > unknown"),
            (validate_alas_raid_daily_stage_filter, None),
        ):
            with self.subTest(function=function.__name__, value=value), self.assertRaises(SemanticGateClosed):
                function(value)

    def test_patch_gates_before_ticket_or_daily_ui(self):
        patch = ROOT.joinpath("integration/alas/0001-semantic-oracle-hooks.patch").read_text(
            encoding="utf-8"
        )
        self.assertEqual(patch.count("validate_alas_raid_use_ticket("), 2)
        self.assertLess(
            patch.index("validate_alas_raid_daily_stage_filter("),
            patch.index("reward_config = validate_alas_reward_config("),
        )
        self.assertLess(patch.rindex("validate_alas_raid_use_ticket("), patch.index("if self.appear(TICKET_USE_CONFIRM"))

    def test_daily_remain_patch_preserves_pixel_mode_and_uses_semantic_port(self):
        patch = RAID_REMAIN_PATCH.read_text(encoding="utf-8")
        self.assertIn("semantic_adapter.raid_remain(", patch)
        self.assertIn("event=self.config.Campaign_Event", patch)
        self.assertIn("mode=mode", patch)
        self.assertIn("+                ocr = raid_ocr(", patch)
        self.assertIn("+                result = ocr.ocr(self.device.image)", patch)
        self.assertIn(
            "if semantic_adapter is None and self.appear_then_click(RAID_REWARDS",
            patch,
        )
        self.assertLess(
            patch.index("if semantic_adapter is not None:"),
            patch.index("+                ocr = raid_ocr("),
        )

    def test_current_raid_patch_is_scoped_and_single_dispatch(self):
        patch = CURRENT_RAID_PATCH.read_text(encoding="utf-8")

        self.assertIn("raid == 'raid_20260827'", patch)
        self.assertIn("else raid_entrance(raid=raid, mode=mode)", patch)
        self.assertEqual(patch.count("+                        semantic_adapter.click_raid_stage("), 1)
        self.assertEqual(
            patch.count("+                            semantic_adapter.click_raid_fleet_start("),
            1,
        )
        self.assertIn("semantic_phase = 'battle-loading'", patch)
        self.assertLess(
            patch.index("+                if semantic_phase == 'battle-loading':"),
            patch.index("+                    if semantic_adapter.combat_is_loading():"),
        )
        self.assertLess(
            patch.index("+                    if semantic_adapter.combat_is_loading():"),
            patch.index("+                elif semantic_phase == 'raid-page':"),
        )
        self.assertEqual(
            patch.count("+                                semantic_adapter.click_raid_fleet_recommend("),
            1,
        )
        self.assertEqual(
            patch.count("+                            semantic_adapter.click_raid_precombat_notice(event=raid)"),
            1,
        )
        self.assertEqual(
            patch.count("+                        semantic_adapter.click_raid_precombat_start(event=raid)"),
            1,
        )
        self.assertIn("return to the exact Raid page and retry", patch)
        self.assertIn("def _ensure_raid_page(self, name):", patch)
        self.assertIn("semantic_adapter.enter_raid_page(event=name)", patch)
        self.assertIn("self.ui_ensure(page_main)", patch)
        self.assertEqual(patch.count("+                self._ensure_raid_page(name)"), 1)
        self.assertEqual(patch.count("+        self._ensure_raid_page(name)"), 1)
        self.assertEqual(patch.count("+            self._ensure_raid_page(name)"), 1)
        self.assertNotIn("advanced", patch)
        self.assertNotIn("+                self.device.click(", patch)

    def test_current_raid_config_is_cn_only_and_keeps_pinned_baseline(self):
        patch = CURRENT_RAID_PATCH.read_text(encoding="utf-8")

        self.assertEqual(patch.count('+          "raid_20260827"'), 6)
        self.assertEqual(patch.count('           "raid_20260212"'), 6)
        self.assertNotIn('-          "raid_20260827"', patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_raid_config_contract.py",
            "python/alas_headless/alas_raid_config_replay.py",
            "scripts/python/verify_alas_raid_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
