"""Opsi regression cases for the adapter."""

import time
import unittest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_operation_siren_order_owns_its_confirmation_popup(self):
        adapter, oracle, _ = self.make_adapter()

        order = adapter.click(NamedButton("ORDER_SCAN"))
        self.assertEqual(order.semantic_id, "os/order/scan")
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        confirmation = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(confirmation.semantic_id, "os/order/confirm")
        self.assertIsNone(adapter._operation_siren_pending_order)
        self.assertEqual(
            oracle.click_calls,
            ["os/order/scan", "os/order/confirm"],
        )

    def test_operation_siren_order_accepts_alas_scoped_confirmation_name(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        session.click(NamedButton("ORDER_SUBMARINE"))
        confirm = NamedButton("POPUP_CONFIRM_ORDER_SUBMARINE")
        self.assertTrue(adapter.appear(confirm))
        confirmation = session.click(confirm)

        self.assertEqual(confirmation.semantic_id, "os/order/confirm")
        self.assertIsNone(adapter._operation_siren_pending_order)
        self.assertEqual(
            oracle.click_calls,
            ["os/order/submarine", "os/order/confirm"],
        )

    def test_operation_siren_order_retries_only_endpoint_coherence(self):
        adapter, oracle, _ = self.make_adapter()
        receipt = oracle.click_receipt("os/order/submarine")
        oracle.click_operation_siren_order = Mock(
            side_effect=[
                SemanticGateClosed(
                    "operation siren order snapshots are not coherent"
                ),
                receipt,
            ]
        )

        with patch("alas_headless.alas_adapter.time.sleep") as sleep:
            returned = adapter.click(NamedButton("ORDER_SUBMARINE"))

        self.assertEqual(returned, receipt)
        self.assertEqual(adapter._operation_siren_pending_order, "submarine")
        self.assertEqual(oracle.click_operation_siren_order.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_operation_siren_map_exit_owns_exact_exit_confirmation(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_exit_prompt_visible = lambda: True

        self.assertTrue(adapter.operation_siren_map_exit_prompt_visible())
        receipt = adapter.click_operation_siren_map_exit_confirm()

        self.assertEqual(receipt.semantic_id, "os/exit/confirm")
        self.assertEqual(oracle.click_calls, ["os/exit/confirm"])
        self.assertGreater(adapter._operation_siren_entry_transition_until, 0.0)

        oracle.operation_siren_exit_prompt_visible = lambda: False
        self.assertIsNone(
            adapter.try_click_operation_siren_map_exit_confirm()
        )
        with self.assertRaisesRegex(
            SemanticGateClosed,
            "operation siren exit prompt is absent",
        ):
            adapter.click_operation_siren_map_exit_confirm()

    def test_in_map_is_positive_on_exact_operation_siren_local_map(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_local_map_visible_value = True

        self.assertTrue(adapter.appear(NamedButton("IN_MAP")))

        oracle.operation_siren_local_map_visible_value = False
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))

    def test_operation_siren_entry_transition_makes_page_probes_passive(self):
        adapter, oracle, gate_calls = self.make_adapter()
        adapter._operation_siren_entry_transition_until = time.monotonic() + 1.0

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertEqual(gate_calls, [])

        adapter._operation_siren_entry_transition_until = 0.0
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 1.0
        )
        self.assertFalse(adapter.appear(NamedButton("RETIRE_APPEAR_1")))
        self.assertEqual(gate_calls, [])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_mission_entry_requires_exact_actionable_map(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_mission_list_visible = Mock(return_value=False)
        oracle.operation_siren_state = Mock(
            return_value=SimpleNamespace(zone_name="Gibraltar")
        )
        oracle.enabled_values["os/map/mission-list"] = True

        self.assertTrue(adapter.operation_siren_mission_entry_available())
        oracle.operation_siren_state.assert_called_once_with()
        self.assertIn("os/map/mission-list", oracle.enabled_calls)
        self.assertEqual(gate_calls, [True])
        self.assertEqual(oracle.click_calls, [])

        oracle.operation_siren_state.side_effect = SemanticGateClosed(
            "Operation Siren page identity is not proven"
        )
        with self.assertRaises(SemanticGateClosed):
            adapter.operation_siren_mission_entry_available()

    def test_operation_siren_mission_entry_is_hidden_by_open_list(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_mission_list_visible = Mock(return_value=True)
        oracle.operation_siren_state = Mock()
        oracle.enabled_values["os/map/mission-list"] = True

        self.assertFalse(adapter.operation_siren_mission_entry_available())
        oracle.operation_siren_state.assert_not_called()
        self.assertNotIn("os/map/mission-list", oracle.enabled_calls)
        self.assertEqual(gate_calls, [True])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_startup_recovery_owns_reward_and_clears_on_map(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }

        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        self.assertFalse(adapter.appear(NamedButton("IN_RETIREMENT_CHECK")))
        self.assertTrue(adapter._operation_siren_auto_search_active)
        self.assertGreater(
            adapter._operation_siren_entry_transition_until,
            time.monotonic(),
        )

        oracle.operation_siren_local_map_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("OS_CHECK")))
        self.assertEqual(adapter._operation_siren_entry_transition_until, 0.0)
        oracle.operation_siren_auto_search_state = Mock(return_value="off")
        self.assertEqual(adapter.operation_siren_auto_search_state(), "off")
        self.assertFalse(adapter.operation_siren_auto_search_completed_empty())
        self.assertEqual(gate_calls, [True, True, True, True])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_reward_popup_closes_without_mission_owner(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_operation_siren_page_remount_keeps_exact_reward_owner(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        oracle.operation_siren_local_map_visible_value = True

        adapter.begin_operation_siren_page_remount(timeout_seconds=60.0)
        self.assertTrue(adapter.appear(NamedButton("OS_CHECK")))
        self.assertGreater(
            adapter._operation_siren_page_remount_until,
            time.monotonic(),
        )
        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))
        adapter.end_operation_siren_page_remount()

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(adapter._operation_siren_page_remount_until, 0.0)

    def test_operation_siren_page_remount_timeout_is_bounded(self):
        adapter, _, _ = self.make_adapter()

        for value in (True, 0, -1, 601, float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    adapter.begin_operation_siren_page_remount(value)

    def test_operation_siren_startup_recovery_recognizes_campaign_menu(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.campaign_menu_value = True

        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertEqual(gate_calls, [True])
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_startup_recovery_keeps_global_guild_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/guild-message/close"] = True
        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)

        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CONFIRM")))
        self.assertTrue(adapter.appear(NamedButton("GUILD_POPUP_CANCEL")))
        receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(oracle.click_calls, ["overlay/guild-message/close"])

    def test_operation_siren_campaign_entry_commit_is_idempotent(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_os_entrance_available = Mock(return_value=True)
        receipt = oracle.click_receipt("campaign-menu/os")
        oracle.click_campaign_os_entrance = Mock(return_value=receipt)

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_GOTO_OS")))
        first = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_OS"))
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_MENU_GOTO_OS")))
        duplicate = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_OS"))

        self.assertEqual(first, receipt)
        self.assertEqual(duplicate, receipt)
        oracle.click_campaign_os_entrance.assert_called_once_with()

    def test_operation_siren_startup_recovery_timeout_is_bounded(self):
        adapter, _, _ = self.make_adapter()

        for value in (True, 0, -1, 601, float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    adapter.begin_operation_siren_startup_recovery(value)

    def test_operation_siren_map_rejects_passive_pixel_probes_before_build_scan(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_local_map_visible_value = True
        oracle.build_queue_timers = Mock(
            side_effect=AssertionError("construction probe must not run")
        )

        self.assertFalse(adapter.appear(NamedButton("WITHDRAW")))
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertEqual(gate_calls, [])

    def test_operation_siren_auto_search_commit_owns_loading_transition(self):
        adapter, oracle, gate_calls = self.make_adapter()
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 30.0
        )
        oracle.operation_siren_auto_search_state = Mock(
            side_effect=AssertionError("loading surface must not be queried")
        )

        self.assertEqual(adapter.operation_siren_auto_search_state(), "on")
        self.assertTrue(adapter.operation_siren_auto_search_transition_active())
        self.assertEqual(gate_calls, [True, True])

    def test_operation_siren_auto_search_records_natural_empty_completion(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_auto_search_active = True
        adapter._operation_siren_auto_search_transition_until = 0.0
        oracle.operation_siren_auto_search_state = Mock(return_value="off")

        self.assertEqual(adapter.operation_siren_auto_search_state(), "off")
        self.assertTrue(adapter.operation_siren_auto_search_completed_empty())

        oracle.enabled_values["os/map/auto-search/off"] = True
        adapter.click(NamedButton("AUTO_SEARCH_OS_MAP_OPTION_OFF"))
        self.assertFalse(adapter.operation_siren_auto_search_completed_empty())

        adapter._operation_siren_auto_search_active = False
        adapter.mark_operation_siren_auto_search_completed_empty()
        self.assertTrue(adapter.operation_siren_auto_search_completed_empty())

    def test_operation_siren_original_loop_can_close_settled_off_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_auto_search_active = True
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 30.0
        )
        oracle.operation_siren_auto_search_state = Mock(return_value="off")

        adapter.mark_operation_siren_auto_search_completed_empty()

        self.assertTrue(adapter.operation_siren_auto_search_completed_empty())
        self.assertFalse(adapter.operation_siren_auto_search_transition_active())
        self.assertFalse(adapter._operation_siren_auto_search_active)

        adapter._operation_siren_auto_search_active = True
        oracle.operation_siren_auto_search_state.return_value = "on"
        with self.assertRaisesRegex(
            SemanticGateClosed, "transition is active"
        ):
            adapter.mark_operation_siren_auto_search_completed_empty()

    def test_operation_siren_interrupt_advances_exact_pause_leave_confirm_steps(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter

        oracle.exercise_combat_quit_confirm_visible = Mock(return_value=False)
        oracle.exercise_combat_pause_menu_visible = Mock(return_value=False)
        oracle.combat_pause_visible = Mock(return_value=True)
        oracle.click_combat_pause = Mock()
        self.assertTrue(session.handle_operation_siren_combat_interrupt())
        oracle.click_combat_pause.assert_called_once_with()

        oracle.combat_pause_visible.return_value = False
        oracle.exercise_combat_pause_menu_visible.return_value = True
        oracle.click_exercise_combat_leave = Mock()
        self.assertTrue(session.handle_operation_siren_combat_interrupt())
        oracle.click_exercise_combat_leave.assert_called_once_with()

        oracle.exercise_combat_pause_menu_visible.return_value = False
        oracle.exercise_combat_quit_confirm_visible.return_value = True
        oracle.click_exercise_combat_quit_confirm = Mock()
        self.assertTrue(session.handle_operation_siren_combat_interrupt())
        oracle.click_exercise_combat_quit_confirm.assert_called_once_with()

    def test_operation_siren_defeat_grade_is_not_s_rank(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.operation_siren_battle_result_visible = Mock(return_value=True)
        oracle.operation_siren_battle_result_grade = Mock(return_value="DEFEAT")
        receipt = oracle.click_receipt("operation-siren/battle/result")
        oracle.click_daily_battle_result = Mock(return_value=receipt)

        self.assertEqual(adapter.operation_siren_battle_result_grade(), "DEFEAT")
        self.assertEqual(adapter.click_operation_siren_battle_result(), receipt)
        oracle.click_daily_battle_result.assert_called_once_with()

        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._combat_result_observation = None
        session._combat_last_result_receipt = None
        session._arm_combat_result_transition = Mock()
        session._combat_result_action_oracle = lambda _adapter: oracle
        session._frame_clock = None

        self.assertTrue(session.appear(NamedButton("BATTLE_STATUS_D")))
        self.assertFalse(session.appear(NamedButton("BATTLE_STATUS_S")))
        self.assertEqual(
            session.click(NamedButton("BATTLE_STATUS_D")), receipt
        )

    def test_operation_siren_reward_close_requires_owner_and_exact_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.award_info_page_visible = Mock(return_value=True)
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }

        with self.assertRaisesRegex(SemanticGateClosed, "owner is absent"):
            adapter.click_operation_siren_reward_close()

        adapter._operation_siren_combat_active = True
        receipt = adapter.click_operation_siren_reward_close()

        self.assertEqual(receipt.semantic_id, "os/combat/reward/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_operation_siren_reward_close_rejects_ambiguous_targets(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.award_info_page_visible = Mock(return_value=True)
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": True,
        }

        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            adapter.click_operation_siren_reward_close()
        self.assertEqual(oracle.click_calls, [])

    def test_operation_siren_startup_owns_passive_activity_handoff(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        adapter.begin_operation_siren_startup_recovery(timeout_seconds=60.0)
        self.assertFalse(adapter.appear(NamedButton("SP_CHECK")))

        adapter._operation_siren_auto_search_active = False
        adapter._operation_siren_entry_transition_until = 0.0
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
            adapter.appear(NamedButton("SP_CHECK"))
