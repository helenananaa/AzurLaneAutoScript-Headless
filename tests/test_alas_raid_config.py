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
RAID_CONFIG_PATCH = ROOT / "integration/alas/series/0170-raid-config-contract.patch"
RAID_DAILY_CONFIG_PATCH = ROOT / "integration/alas/series/0010-mission-mail-flow-ports.patch"
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
        patch = RAID_CONFIG_PATCH.read_text(encoding="utf-8")
        daily_patch = RAID_DAILY_CONFIG_PATCH.read_text(encoding="utf-8")
        current_patch = CURRENT_RAID_PATCH.read_text(encoding="utf-8")

        self.assertEqual(patch.count("validate_alas_raid_use_ticket("), 2)
        self.assertLess(
            daily_patch.index("validate_alas_raid_daily_stage_filter("),
            daily_patch.index("reward_config = validate_alas_reward_config("),
        )
        self.assertLess(patch.rindex("validate_alas_raid_use_ticket("), patch.index("if self.appear(TICKET_USE_CONFIRM"))
        self.assertIn(
            "+        semantic_use_ticket = (",
            current_patch,
        )
        self.assertIn(
            "+            validate_alas_raid_use_ticket(self.config.Raid_UseTicket)",
            current_patch,
        )

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
            patch.count("semantic_adapter.click_raid_precombat_start(event=raid)"),
            1,
        )
        self.assertIn("return to the exact Raid page and retry", patch)
        self.assertIn("def _ensure_raid_page(self, name):", patch)
        self.assertIn("semantic_adapter.enter_raid_page(event=name)", patch)
        self.assertIn("self.ui_ensure(page_main)", patch)
        self.assertEqual(patch.count("+                self._ensure_raid_page(name)"), 1)
        self.assertEqual(patch.count("+        self._ensure_raid_page(name)"), 1)
        self.assertEqual(patch.count("+            self._ensure_raid_page(name)"), 1)
        self.assertNotIn(
            "+                if self.run_limit and self.config.StopCondition_RunCount <= 0:",
            patch,
        )
        self.assertNotIn("advanced", patch)
        self.assertNotIn("+                self.device.click(", patch)
        self.assertIn("or semantic_adapter.current_raid_result_active()", patch)
        self.assertIn("semantic_adapter.complete_daily_battle_result()", patch)
        self.assertNotIn("if semantic_current_raid and use_ticket:", patch)
        self.assertIn(
            "semantic_adapter.raid_multiple_sortie_state(",
            patch,
        )
        self.assertIn("multiple_state.ticket_owned > 0", patch)
        self.assertIn("multiple_state.zero_ticket_disabled", patch)
        self.assertIn("semantic_phase = 'multiple-sortie-closed'", patch)
        self.assertIn(
            "Current Raid positive ticket selection is not ", patch
        )
        self.assertLess(
            patch.index("semantic_adapter.click_raid_precombat_multiple(event=raid)"),
            patch.index("semantic_phase = 'multiple-sortie'", patch.index("semantic_adapter.click_raid_precombat_multiple(event=raid)")),
        )
        positive_guard = patch.index("+                        if multiple_state.ticket_owned > 0:")
        positive_close = patch.index(
            "+                            semantic_adapter.click_raid_multiple_sortie_back(",
            positive_guard,
        )
        positive_error = patch.index(
            "+                            raise ScriptError(",
            positive_close,
        )
        self.assertLess(positive_guard, positive_close)
        self.assertLess(positive_close, positive_error)
        zero_guard = patch.index("+                        if not (", positive_error)
        zero_close = patch.index(
            "+                        semantic_adapter.click_raid_multiple_sortie_back(event=raid)",
            zero_guard,
        )
        zero_closed_phase = patch.index(
            "+                        semantic_phase = 'multiple-sortie-closed'",
            zero_close,
        )
        zero_reentry_guard = patch.index(
            "+                            and semantic_phase != 'multiple-sortie-closed'",
            zero_closed_phase,
        )
        ordinary_start = patch.index(
            "+                            semantic_adapter.click_raid_precombat_start(event=raid)",
            zero_reentry_guard,
        )
        self.assertLess(zero_guard, zero_close)
        self.assertLess(zero_close, zero_closed_phase)
        self.assertLess(zero_closed_phase, zero_reentry_guard)
        self.assertLess(zero_reentry_guard, ordinary_start)

    def test_current_raid_config_is_cn_only_and_keeps_pinned_baseline(self):
        patch = CURRENT_RAID_PATCH.read_text(encoding="utf-8")

        self.assertEqual(patch.count('+          "raid_20260827"'), 6)
        self.assertEqual(patch.count('-          "raid_20260212"'), 6)
        self.assertEqual(patch.count('+          "raid_20260212",'), 4)
        self.assertNotIn('-          "raid_20260827"', patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_raid_config_contract.py",
            "python/alas_headless/alas_raid_config_replay.py",
            "scripts/python/verify_alas_raid_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))

    def test_current_raid_runner_bounds_multi_battle_daily_validation(self):
        source = ROOT.joinpath(
            "scripts/python/run_alas_raid_live_validation.py"
        ).read_text(encoding="utf-8")
        self.assertIn('daily_mode.add_argument(\n        "--daily-battles"', source)
        self.assertIn('daily_mode.add_argument(\n        "--daily-empty-stage"', source)
        self.assertIn('daily_mode.add_argument(\n        "--daily-reward-ex"', source)
        self.assertIn('"--use-ticket"', source)
        self.assertIn('"UseTicket": args.use_ticket', source)
        self.assertIn("Raid_UseTicket=args.use_ticket", source)
        self.assertIn("--use-ticket is only valid for the standalone Raid task", source)
        self.assertIn('ui_recovery_steps.append("multiple_sortie_back")', source)
        self.assertIn('"--daily-stage-filter"', source)
        self.assertIn(
            'task["RaidDaily"].update({"StageFilter": configured_stage_filter})',
            source,
        )
        self.assertIn("RaidDaily_StageFilter=configured_stage_filter", source)
        self.assertIn("str(24 * (daily_battle_count or 1))", source)
        self.assertIn(
            'before["remaining"] - after["remaining"] == expected_battles',
            source,
        )
        self.assertIn('if daily_task\n                else after["remaining"]', source)
        self.assertIn("multiple_sortie_entry_receipts", source)
        self.assertIn("multiple_sortie_states", source)
        self.assertIn("multiple_sortie_back_receipts", source)
        self.assertIn('multiple_sortie_states[0]["ticket_owned"] == 0', source)
        self.assertIn('multiple_sortie_states[0]["zero_ticket_disabled"] is True', source)
        self.assertIn('and after["remaining"] == 0', source)
        self.assertIn('before["remaining"] != daily_battle_count', source)
        self.assertIn("len(sortie_receipts) == expected_battles", source)
        self.assertIn("if configured_task == task_name", source)
        self.assertIn('scheduler["Enable"] = False', source)
        self.assertIn("datetime.now() + timedelta(hours=1)", source)
        self.assertIn('scheduler["NextRun"] = isolated_next_run', source)
        self.assertIn("if next_task.command != task_name:", source)
        override_block = source.split("overrides = dict(", 1)[1].split(")", 1)[0]
        self.assertNotIn("StopCondition_RunCount", override_block)
        self.assertIn(
            '"configured_run_count": instance.config.StopCondition_RunCount', source
        )
        self.assertIn('"RunCount": 0 if daily_task else 1', source)
        self.assertIn('"1" if daily_reward_ex else "0"', source)
        self.assertIn('if capability == "mission.claim":', source)
        self.assertIn("claim_count = len(mission_claim_dispatches)", source)
        self.assertIn("fresh_claim_path = bool(", source)
        self.assertIn("resumed_claim_path = bool(", source)
        self.assertIn('ui_recovery_steps.append("mission_page_back")', source)
        self.assertIn('== 1 - claim_count', source)
        self.assertIn('and ex_battles in (1, 2, 3)', source)
        self.assertIn('after["sortie_grant"] == 3 - ex_battles', source)
        self.assertIn("if oracle.daily_combat_visible():", source)
        self.assertIn("interrupted_combat.combat_execute(", source)
        self.assertIn('ui_recovery_steps.append("active_combat_execute")', source)
        self.assertIn("session.recover_orphan_combat_result(", source)
        self.assertIn("current Raid result recovery did not stabilize", source)
        self.assertIn(
            'str(exc) != "current Raid button and UI snapshots are incoherent"',
            source,
        )
        self.assertIn(
            "current Raid validation requires a stable main or Raid page",
            source,
        )
        self.assertIn("page_deadline = time.monotonic() + 10.0", source)


if __name__ == "__main__":
    unittest.main()
