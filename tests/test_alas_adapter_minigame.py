"""Minigame ticket-contract regression cases for the adapter."""

import unittest
from unittest.mock import Mock

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from alas_headless.oracle.surfaces import ObservationSurface


class TicketOracle:
    def __init__(self, selected, owned):
        self.value = (selected, owned)

    def new_year_challenge_ticket_count(self):
        return self.value


class AlasSemanticAdapterMinigameTests(unittest.TestCase):
    def test_startup_discovers_inherited_build_queue_before_transition_grace(self):
        oracle = FakeOracle()
        oracle.build_queue_visible_value = True
        oracle.exists_values['build/page/back'] = True
        oracle.enabled_values['build/page/back'] = True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        self.assertTrue(adapter.appear(NamedButton('BUILD_CHECK')))
        self.assertTrue(adapter.appear(NamedButton('GOTO_MAIN')))
        self.assertFalse(adapter.appear(NamedButton('UNREVIEWED_PIXEL_PAGE')))
        self.assertEqual(oracle.click_calls, [])

    def test_startup_does_not_invent_a_build_page_or_covered_return(self):
        oracle = FakeOracle()
        oracle.build_queue_visible_value = False
        oracle.exists_values['build/page/back'] = True
        oracle.enabled_values['build/page/back'] = False
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        self.assertFalse(adapter.appear(NamedButton('BUILD_CHECK')))
        self.assertFalse(adapter.appear(NamedButton('GOTO_MAIN')))
        self.assertEqual(oracle.click_calls, [])

    def test_live_menu_arrival_reuses_entry_receipt(self):
        oracle = FakeOracle()
        # Preserve the abstract destination-handoff model. Typed pending Main
        # source matching is covered by test_live_menu_navigation_handoff.
        oracle._matches = lambda state, target: ()
        oracle.exists_values['main/live'] = True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()

        first = adapter.click(NamedButton("MAIN_GOTO_DORMMENU"))
        oracle.exists_values["dorm-menu/academy"] = True
        oracle.enabled_values["dorm-menu/academy"] = True
        oracle.state_generation = first.generation + 1
        second = adapter.click(NamedButton("MAIN_GOTO_DORMMENU"))

        self.assertEqual(second, first)
        self.assertEqual(oracle.click_calls, ["main/live"])

    def test_ticket_confirmation_repeated_scan_uses_closed_prompt_receipt(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.minigame_ticket_prompt_visible = lambda: True

        first = adapter.click(NamedButton("POPUP_CONFIRM"))
        oracle.minigame_ticket_prompt_visible = lambda: False
        oracle.state_generation = first.generation + 1
        second = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(second, first)
        self.assertEqual(oracle.click_calls, ["minigame/tickets/confirm"])

    def test_live_menu_animation_waits_without_second_toggle(self):
        oracle = FakeOracle()
        oracle._matches = lambda state, target: ()
        oracle.exists_values['main/live'] = True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        first = adapter.click(NamedButton('MAIN_GOTO_DORMMENU'))
        oracle.exists_values['dorm-menu/academy'] = True
        oracle.state_generation = first.generation + 1
        original_enabled = oracle.enabled
        reads = iter((False, True))
        oracle.enabled = lambda target: next(reads) if target == 'dorm-menu/academy' else original_enabled(target)
        self.assertEqual(adapter.click(NamedButton('MAIN_GOTO_DORMMENU')), first)
        self.assertEqual(oracle.click_calls, ['main/live'])

    def test_live_menu_blocked_by_new_message_does_not_toggle_again(self):
        oracle = FakeOracle()
        oracle._matches = lambda state, target: ()
        oracle.exists_values['main/live'] = True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        adapter.click(NamedButton('MAIN_GOTO_DORMMENU'))
        oracle.exists_values['dorm-menu/academy'] = True
        oracle.enabled_values['dorm-menu/academy'] = False
        oracle.observation_surfaces.add(ObservationSurface.MESSAGE_BOX)
        with self.assertRaisesRegex(SemanticGateClosed, 'did not become actionable'):
            adapter.click(NamedButton('MAIN_GOTO_DORMMENU'))
        self.assertEqual(oracle.click_calls, ['main/live'])

    def test_game_room_list_treats_unrelated_reward_probe_as_absent(self):
        oracle = FakeOracle()
        oracle.game_room_list_visible = lambda: True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()

        self.assertFalse(adapter.appear(NamedButton("GET_MISSION")))
        self.assertFalse(adapter.appear(NamedButton("GET_SHIP")))

    def test_native_popup_scan_uses_immutable_game_room_owner(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        frame = FakeOracle()
        frame.game_room_page_visible = lambda: True
        adapter._frame_or_live_observation_oracle = lambda: frame
        oracle.game_room_page_visible = Mock(side_effect=SemanticGateClosed('live transition'))
        self.assertFalse(adapter.appear(NamedButton('GET_MISSION')))
        oracle.game_room_page_visible.assert_not_called()

    def test_original_unknown_page_recovery_reaches_fushun_back(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.exists_values['minigame/new-year/back'] = True
        oracle.new_year_challenge_prepare_visible = lambda: True
        oracle.new_year_challenge_home_visible = lambda: True
        oracle.click_new_year_challenge_prepare_control = lambda control: oracle.click_receipt('minigame/new-year/' + control)
        self.assertTrue(adapter.appear(NamedButton('GOTO_MAIN')))
        oracle.game_room_page_visible = lambda: True
        receipt = adapter.click(NamedButton('GOTO_MAIN'))
        self.assertEqual(receipt.semantic_id, 'minigame/new-year/back')

    def test_original_back_closes_list_instead_of_clicking_covered_list_entry(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.new_year_challenge_result = lambda: None
        oracle.new_year_challenge_home_visible = lambda: False
        oracle.new_year_challenge_ticket_count = Mock(side_effect=SemanticGateClosed('Fushun absent'))
        states = iter((True, False))
        oracle.game_room_list_visible = lambda: next(states)
        oracle.game_room_page_visible = lambda: True
        self.assertEqual(adapter.click(NamedButton('BACK')).semantic_id, 'game-room/back')
        self.assertEqual(oracle.click_calls, ['game-room/back'])

    def test_opsi_exit_prompt_during_minigame_navigation_uses_its_own_handler(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.minigame_ticket_prompt_visible = lambda: False
        oracle.observation_prompt_kind_value = 'opsi-exit'
        oracle.operation_siren_exit_prompt_visible = lambda: True
        receipt = adapter.click(NamedButton('POPUP_CONFIRM'))
        self.assertEqual(receipt.semantic_id, 'os/exit/confirm')
        self.assertEqual(oracle.click_calls, ['os/exit/confirm'])
        self.assertIsNone(adapter._minigame_context.ticket_confirm_receipt)

    def test_closed_ticket_receipt_does_not_swallow_new_opsi_exit_prompt(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.minigame_ticket_prompt_visible = lambda: True
        first = adapter.click(NamedButton('POPUP_CONFIRM'))
        oracle.minigame_ticket_prompt_visible = lambda: False
        oracle.observation_prompt_kind_value = 'opsi-exit'
        oracle.operation_siren_exit_prompt_visible = lambda: True
        oracle.state_generation = first.generation + 1
        receipt = adapter.click(NamedButton('POPUP_CONFIRM'))
        self.assertEqual(receipt.semantic_id, 'os/exit/confirm')
        self.assertEqual(oracle.click_calls, ['minigame/tickets/confirm', 'os/exit/confirm'])

    def test_repeated_exit_confirmation_waits_for_native_destination_without_input(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.minigame_ticket_prompt_visible = lambda: False
        oracle.observation_prompt_kind_value = 'opsi-exit'
        oracle.operation_siren_exit_prompt_visible = lambda: True
        first = adapter.click(NamedButton('POPUP_CONFIRM_UI_ADDITIONAL'))
        oracle.observation_prompt_kind_value = None
        oracle.operation_siren_exit_prompt_visible = lambda: False
        oracle.state_generation = first.generation + 1
        oracle.campaign_menu_is_entry = lambda: True
        second = adapter.click(NamedButton('POPUP_CONFIRM_UI_ADDITIONAL'))
        self.assertEqual(first, second)
        self.assertEqual(oracle.click_calls, ['os/exit/confirm'])
        self.assertIsNone(adapter._operation_siren_exit_receipt)

    def test_exit_receipt_does_not_swallow_new_ticket_prompt(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.minigame_ticket_prompt_visible = lambda: False
        oracle.observation_prompt_kind_value = 'opsi-exit'
        oracle.operation_siren_exit_prompt_visible = lambda: True
        adapter.click(NamedButton('POPUP_CONFIRM'))
        oracle.observation_prompt_kind_value = None
        oracle.operation_siren_exit_prompt_visible = lambda: False
        oracle.minigame_ticket_prompt_visible = lambda: True
        receipt = adapter.click(NamedButton('POPUP_CONFIRM'))
        self.assertEqual(receipt.semantic_id, 'minigame/tickets/confirm')
        self.assertEqual(oracle.click_calls, ['os/exit/confirm', 'minigame/tickets/confirm'])

    def test_exit_receipt_does_not_swallow_unknown_message(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_minigame()
        oracle.minigame_ticket_prompt_visible = lambda: False
        oracle.observation_prompt_kind_value = 'opsi-exit'
        oracle.operation_siren_exit_prompt_visible = lambda: True
        first = adapter.click(NamedButton('POPUP_CONFIRM'))
        oracle.observation_prompt_kind_value = None
        oracle.operation_siren_exit_prompt_visible = lambda: False
        oracle.state_generation = first.generation + 1
        oracle.campaign_menu_is_entry = lambda: True
        oracle.observation_surfaces.add(ObservationSurface.MESSAGE_BOX)
        oracle.click = Mock(side_effect=SemanticGateClosed('unknown prompt'))
        with self.assertRaisesRegex(SemanticGateClosed, 'unknown prompt'):
            adapter.click(NamedButton('POPUP_CONFIRM'))
        self.assertEqual(adapter._operation_siren_exit_receipt, first)

    def make_adapter(self, selected=1, owned=20):
        oracle = TicketOracle(selected, owned)
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            minigame_play_budget=1,
        )
        adapter.begin_minigame()
        adapter._minigame_context.coins_owned = owned
        return adapter, oracle

    def test_default_ticket_uses_selected_and_owned_counter_contract(self):
        adapter, _ = self.make_adapter(selected=1, owned=7)

        self.assertEqual(adapter.minigame_prepare_default_ticket(), 1)
        self.assertEqual(adapter._minigame_context.selected_tickets, 1)

    def test_native_five_ticket_selection_binds_inventory(self):
        adapter, oracle = self.make_adapter(selected=5, owned=36)
        self.assertEqual(adapter.minigame_prepare_selected_tickets(), 5)
        self.assertEqual(adapter._minigame_context.selected_tickets, 5)
        oracle.value = (5, 35)
        with self.assertRaisesRegex(SemanticGateClosed, 'does not match inventory'):
            adapter.minigame_prepare_selected_tickets()

    def test_native_selection_can_be_observed_after_play_grant_is_spent(self):
        adapter, _ = self.make_adapter(selected=5, owned=36)
        adapter._action_ledger.dispatch('minigame.play', lambda: None)
        self.assertEqual(adapter.minigame_prepare_selected_tickets(), 5)
        self.assertEqual(adapter._action_ledger.remaining('minigame.play'), 0)

    def test_default_ticket_rejects_more_than_one_selected_ticket(self):
        adapter, _ = self.make_adapter(selected=2, owned=20)

        with self.assertRaisesRegex(SemanticGateClosed, "inconsistent"):
            adapter.minigame_prepare_default_ticket()

    def test_zero_default_selection_returns_native_no_play_decision(self):
        adapter, _ = self.make_adapter(selected=0, owned=40)
        self.assertEqual(adapter.minigame_prepare_default_ticket(), 0)
        self.assertEqual(adapter._minigame_context.selected_tickets, 0)

    def test_default_ticket_rejects_counter_inventory_mismatch(self):
        adapter, oracle = self.make_adapter(selected=1, owned=20)
        oracle.value = (1, 19)

        with self.assertRaisesRegex(SemanticGateClosed, "inconsistent"):
            adapter.minigame_prepare_default_ticket()


if __name__ == "__main__":
    unittest.main()
