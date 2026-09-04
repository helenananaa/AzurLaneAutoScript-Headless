"""Mission regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticUnmapped,
    MissionClaimableDetected,
    MissionDisposition,
    SemanticGateClosed,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_generic_page_scan_recovers_exact_mission_page_after_reward(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.enabled_values["task/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("MISSION_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "task/page/back")
        self.assertEqual(oracle.click_calls, ["task/page/back"])

    def test_generic_page_scan_does_not_expose_blocked_mission_underlay(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.mission_page_state = Mock(
            side_effect=SemanticGateClosed(
                "mission page identity is not safely actionable"
            )
        )

        with self.assertRaisesRegex(AlasSemanticUnmapped, "FLEET_CHECK"):
            adapter.appear(NamedButton("FLEET_CHECK"))

    def test_goto_main_from_mission_uses_exact_task_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.enabled_values["task/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "task/page/back")
        self.assertEqual(oracle.click_calls, ["task/page/back"])

    def test_weekly_only_mission_notice_uses_exact_main_task_badge(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.main_red_dot_values["main/task"] = True
        adapter.begin_mission_reward(daily=False, weekly=True)

        self.assertTrue(adapter.appear(NamedButton("MISSION_NOTICE")))

    def test_weekly_badge_is_read_from_typed_mission_marker(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.mission_weekly_reward_available_value = True
        adapter.begin_mission_reward(daily=False, weekly=True)

        self.assertTrue(
            adapter.image_color_count(
                NamedButton("MISSION_WEEKLY_RED_DOT"),
                color=(206, 81, 66),
                threshold=221,
                count=20,
            )
        )

    def test_mission_ship_receipt_uses_exact_new_ship_continue(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.new_ship_reward_visible_value = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        self.assertTrue(adapter.appear(NamedButton("GET_SHIP")))
        receipt = adapter.click(NamedButton("GET_SHIP"))

        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(oracle.click_calls, ["reward/new-ship/continue"])

    def test_default_navbar_requires_exact_mission_entry_click(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        with self.assertRaises(SemanticGateClosed):
            adapter.image_color_count(
                NamedButton("REWARD_SIDE_NAVBAR_0_0"),
                color=(247, 255, 173),
                threshold=180,
                count=100,
            )

    def test_mission_navbar_reuses_alas_click_with_typed_image_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=True)
        adapter.click(NamedButton("MAIN_GOTO_MISSION"))

        receipt = adapter.click(NamedButton("REWARD_SIDE_NAVBAR_0_4"))

        self.assertEqual(receipt.semantic_id, "task/nav/weekly")
        self.assertEqual(oracle.click_calls, ["main/task", "task/nav/weekly"])

    def test_unknown_presence_is_false_only_on_proven_mission_surface(self):
        adapter, oracle, gate_calls = self.make_adapter()
        adapter.begin_mission_reward(daily=True, weekly=False)
        oracle.exists_values["main/task"] = True

        self.assertFalse(adapter.appear(NamedButton("UNRELATED_PAGE_CHECK")))

        oracle.exists_values.clear()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("UNRELATED_PAGE_CHECK"))
        self.assertGreaterEqual(len(gate_calls), 1)

    def test_reviewed_mission_transition_has_bounded_passive_scan_grace(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["task/page/back"] = True
        oracle.enabled_values["task/page/back"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        adapter.click(NamedButton("GOTO_MAIN"))
        oracle.exists_values.clear()
        oracle.enabled_values.clear()

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        adapter._mission_context.passive_transition_until = time.monotonic() - 1.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))

    def test_mission_entry_alias_cannot_double_click_during_transition(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["main/task"] = True
        adapter.begin_mission_reward(daily=True, weekly=False)

        adapter.click(NamedButton("MAIN_GOTO_MISSION"))
        duplicate = adapter.click(NamedButton("MAIN_GOTO_MISSION_WHITE"))

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_MISSION_WHITE")))
        self.assertEqual(oracle.click_calls, ["main/task"])
        self.assertEqual(duplicate.semantic_id, "main/task")

    def test_mission_no_claim_round_trip_enters_and_exits(self):
        adapter, oracle, gate_calls = self.make_adapter()

        receipt = adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(receipt.outcome, "nothing-claimable")
        self.assertFalse(receipt.claim_injected)
        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(
            [call[0] for call in oracle.wait_calls],
            ["task/page/back", "main/task"],
        )
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claimable_state_exits_then_fails_closed(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL

        with self.assertRaises(MissionClaimableDetected) as raised:
            adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(
            raised.exception.page.disposition,
            MissionDisposition.CLAIMABLE_ALL,
        )
        self.assertFalse(hasattr(raised.exception, "claim_receipt"))
        self.assertEqual(len(gate_calls), 1)

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_mission_dismisses_only_reviewed_overlay_close(self, _sleep):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values = {
            "main/task": False,
            "overlay/bulletin/close": False,
            "overlay/guild-message/close": True,
        }
        oracle.enable_main_after_overlay_click = True

        receipt = adapter.run_mission_reward(timeout_seconds=12)

        self.assertEqual(
            receipt.dismissed_overlays,
            ("overlay/guild-message/close",),
        )
        self.assertEqual(
            oracle.click_calls,
            ["overlay/guild-message/close", "main/task", "task/page/back"],
        )
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claim_all_closes_popup_and_proves_unfinished(self):
        adapter, oracle, gate_calls = self.make_adapter(
            allow_mission_claim_once=True
        )
        oracle.mission_dispositions = [
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.UNFINISHED,
        ]

        receipt = adapter.claim_mission_rewards_once(timeout_seconds=12)

        self.assertEqual(receipt.outcome, "claimed-all-once")
        self.assertEqual(receipt.claim_input_count, 1)
        self.assertEqual(
            oracle.click_calls,
            [
                "main/task",
                "task/claim/all",
                "reward/award-info/close",
                "task/page/back",
            ],
        )
        self.assertEqual(
            oracle.wait_any_calls[0][0],
            (
                "reward/award-info/close",
                "reward/award-info1/close",
            ),
        )
        self.assertEqual(len(gate_calls), 1)

    def test_mission_claim_refuses_row_only_before_claim_input(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ROW

        with self.assertRaises(SemanticGateClosed):
            adapter.claim_mission_rewards_once(timeout_seconds=12)

        self.assertEqual(oracle.click_calls, ["main/task", "task/page/back"])
        self.assertEqual(len(gate_calls), 1)
