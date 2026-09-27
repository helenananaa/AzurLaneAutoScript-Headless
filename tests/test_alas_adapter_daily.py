"""Daily regression cases for the adapter."""

import time
import unittest
from contextlib import nullcontext
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_session_reward_dispatch_preserves_daily_quick_owner(self):
        for quick, campaign in ((True, False), (False, False), (True, True)):
            with self.subTest(quick=quick, campaign=campaign):
                adapter, oracle, _ = self.make_adapter()
                adapter._daily_kind = "fierce_assault"
                adapter._daily_stage = 1
                if quick:
                    adapter._daily_pending_receipt = oracle.click_receipt(
                        "daily/execute/fierce_assault/stage/1/quick/all", generation=6
                    )
                if campaign:
                    adapter.begin_campaign_pre_sortie("11-4", mode="hard")
                oracle.enabled_values["reward/award-info/close"] = True
                oracle.campaign_battle_reward_visible = lambda: True
                adapter.prepared_input_frame = lambda provider: nullcontext()
                session = AlasSemanticSession.__new__(AlasSemanticSession)
                session.adapter = adapter
                session.open = lambda: adapter
                session.refresh_frame = Mock()
                session._combat_result_action_oracle = lambda owner: oracle
                session._arm_combat_result_transition = Mock()

                session.click(NamedButton("GET_ITEMS_1"))

                self.assertEqual(adapter._daily_quick_reward_closed, quick and not campaign)
                self.assertEqual(oracle.click_calls, ["reward/award-info/close"])
                self.assertEqual(session.refresh_frame.call_count, int(quick and not campaign))
                self.assertEqual(session._arm_combat_result_transition.call_count,
                                 int(not quick or campaign))

    def test_current_raid_result_returns_to_raid_not_daily_page(self):
        adapter, oracle, _ = self.make_adapter(campaign_sortie_budget=1)
        self.assertFalse(adapter.current_raid_result_active())
        adapter.click_raid_precombat_start("raid_20260827")
        self.assertTrue(adapter.current_raid_result_active())
        self.assertFalse(adapter.daily_execution_active())
        oracle.raid_page_visible_value = True
        oracle.raid_page_visible_errors = [
            SemanticGateClosed("current Raid stage sprite does not cover its button")
        ]

        with patch("alas_headless.alas_adapter.time.sleep") as sleep:
            receipts = adapter.complete_daily_battle_result(timeout_seconds=0.1)

        self.assertEqual(receipts, ())
        self.assertIsNone(adapter._current_raid_result_event)
        self.assertFalse(adapter.current_raid_result_active())
        self.assertFalse(oracle.daily_page_visible_value)
        sleep.assert_called_once_with(0.25)

    def test_campaign_startup_leaves_daily_page_through_exact_typed_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.daily_page_visible_value = True

        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(receipt.semantic_id, "daily/page/back")
        self.assertEqual(oracle.click_calls, ["daily/page/back"])

    def test_daily_page_makes_mail_escape_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.daily_page_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("GOTO_MAIN_WHITE")))
        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))

    def test_daily_check_distinguishes_overview_from_stage_detail(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.daily_page_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("DAILY_CHECK")))

        oracle.daily_detail_visible_value = True
        self.assertFalse(adapter.appear(NamedButton("DAILY_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DAILY_ENTER_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("BACK_ARROW")))

    def test_daily_expanded_stage_exposes_exact_run_choices(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._daily_kind = "fierce_assault"
        adapter._daily_stage = 1
        oracle.daily_page_visible_value = True
        oracle.daily_detail_visible_value = True
        oracle.daily_selected_stage_visible_value = True
        oracle.daily_run_choices = {"normal", "skip"}

        self.assertFalse(adapter.appear(NamedButton("DAILY_ENTER_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("DAILY_NORMAL_RUN")))
        self.assertTrue(adapter.appear(NamedButton("DAILY_SKIP")))

    def test_daily_stage_transition_makes_in_map_probe_a_passive_miss(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._daily_transition_until = time.monotonic() + 1.0
        oracle.campaign_page_error = SemanticGateClosed("not a campaign page")

        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))

    def test_quick_completion_requires_own_receipt_zero_count_and_closed_award(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.daily_page_visible_value = True
        oracle.daily_remaining_for_kind = lambda kind: 0
        adapter._daily_kind = "tactical_training"
        adapter._daily_stage = 1
        self.assertFalse(adapter.daily_quick_complete())

        adapter._daily_pending_receipt = oracle.click_receipt(
            "daily/execute/tactical_training/stage/1/quick/all", generation=10
        )
        oracle.enabled_values["reward/award-info/close"] = True
        self.assertFalse(adapter.daily_quick_complete())
        oracle.enabled_values["reward/award-info/close"] = False
        self.assertFalse(adapter.daily_quick_complete())
        adapter._daily_quick_reward_closed = True
        oracle.daily_remaining_for_kind = lambda kind: 1
        self.assertFalse(adapter.daily_quick_complete())
        oracle.daily_remaining_for_kind = lambda kind: 0
        oracle.state_generation = 10
        self.assertFalse(adapter.daily_quick_complete())
        oracle.state_generation = 11
        self.assertTrue(adapter.daily_quick_complete())

    def test_quick_award_close_is_correlated_with_pending_dispatch(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._daily_kind = "fierce_assault"
        adapter._daily_stage = 1
        adapter._daily_pending_receipt = oracle.click_receipt(
            "daily/execute/fierce_assault/stage/1/quick/all", generation=6
        )
        oracle.enabled_values["reward/award-info/close"] = True
        adapter._click_daily("GET_ITEMS_1")
        self.assertTrue(adapter._daily_quick_reward_closed)
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_spent_quick_card_is_not_reselected_while_reward_is_pending(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._daily_kind = "fierce_assault"
        adapter._daily_stage = 1
        adapter._daily_pending_receipt = oracle.click_receipt(
            "daily/execute/fierce_assault/stage/1/quick/all", generation=7
        )
        oracle.state_generation = 8
        oracle.daily_page_visible_value = True
        oracle.daily_detail_visible_value = True
        oracle.daily_remaining_for_kind = lambda kind: 0
        self.assertTrue(adapter.daily_quick_consumed())
        self.assertFalse(adapter.appear(NamedButton("DAILY_ENTER_CHECK")))
        oracle.daily_remaining_for_kind = lambda kind: 1
        self.assertTrue(adapter.appear(NamedButton("DAILY_ENTER_CHECK")))

    def test_daily_result_owner_is_disabled_during_campaign_combat(self):
        adapter, _, _ = self.make_adapter()
        adapter._daily_kind = "tactical"
        self.assertTrue(adapter.daily_execution_active())

        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        self.assertFalse(adapter.daily_execution_active())
        adapter.end_campaign_pre_sortie()
