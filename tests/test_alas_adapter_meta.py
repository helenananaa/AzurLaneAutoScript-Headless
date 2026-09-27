"""Meta regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_meta_character_entry_ack_requires_newer_proven_page(self):
        for newer, visible in ((True, True), (False, True), (True, False)):
            adapter, oracle, _ = self.make_adapter()
            previous = SimpleNamespace(generation=10)
            adapter._meta_character_entry_receipt = previous
            oracle.meta_character_page_visible = Mock(return_value=False)
            oracle.meta_character_menu_visible = Mock(return_value=visible)
            oracle.read_state = Mock(return_value=SimpleNamespace(generation=11 if newer else 10))
            oracle.click = Mock(side_effect=SemanticGateClosed('entry absent'))
            if newer and visible:
                self.assertIs(adapter.click(NamedButton('RESHMENU_GOTO_META')), previous)
                oracle.click.assert_not_called()
            else:
                with self.assertRaises(SemanticGateClosed):
                    adapter.click(NamedButton('RESHMENU_GOTO_META'))
            adapter.reset_task_state()
            self.assertIsNone(adapter._meta_character_entry_receipt)

    def test_meta_current_entry_reuses_only_proven_newer_page(self):
        adapter, oracle, _ = self.make_adapter()
        previous = SimpleNamespace(generation=10)
        adapter._meta_current_entry_receipt = previous
        oracle.observation_target_present = Mock(return_value=False)
        oracle.meta_current_empty_points = Mock(return_value=(0, 200))
        oracle.read_state = Mock(return_value=SimpleNamespace(generation=11))
        oracle.click_meta_card = Mock(side_effect=SemanticGateClosed('no landing'))
        self.assertIs(adapter.click(NamedButton('META_MAIN_BEACON_ENTRANCE')), previous)
        oracle.click_meta_card.assert_not_called()
        oracle.read_state.return_value.generation = 10
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton('META_MAIN_BEACON_ENTRANCE'))
        adapter.reset_task_state()
        self.assertIsNone(adapter._meta_current_entry_receipt)

    def test_worldboss_landing_does_not_impersonate_sync_page(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values['meta/current/open'] = True
        oracle.meta_page_visible_value = True
        for name in ('FLEET_CHECK', 'META_CHECK', 'SHIPYARD_CHECK'):
            self.assertFalse(adapter.appear(NamedButton(name)))
        self.assertTrue(adapter.appear(NamedButton('GOTO_MAIN')))
        adapter.begin_meta_assist()
        self.assertTrue(adapter.appear(NamedButton('GOTO_MAIN')))
        adapter.end_meta_assist()
        oracle.exists_values['meta/current/open'] = False
        oracle.main_page_visible_value = True
        for name in ('GOTO_MAIN_WHITE', 'RPG_HOME'):
            self.assertFalse(adapter.appear(NamedButton(name)))

    def test_meta_entry_acknowledges_only_newer_proven_destination(self):
        for newer, valid in ((True, True), (False, True), (True, False)):
            with self.subTest(newer=newer, valid=valid):
                adapter, oracle, _ = self.make_adapter()
                previous = SimpleNamespace(generation=10)
                adapter._meta_entry_receipt = previous
                oracle.meta_entrance_available = Mock(return_value=False)
                oracle.meta_entrance_state = Mock(
                    return_value=object(), side_effect=None if valid else SemanticGateClosed('unknown page'))
                oracle.read_state = Mock(return_value=SimpleNamespace(generation=11 if newer else 10))
                oracle.click_meta_entrance = Mock(side_effect=SemanticGateClosed('entry absent'))
                if newer and valid:
                    self.assertIs(adapter.click(NamedButton('META_ENTRANCE')), previous)
                    oracle.click_meta_entrance.assert_not_called()
                else:
                    with self.assertRaises(SemanticGateClosed):
                        adapter.click(NamedButton('META_ENTRANCE'))
                adapter.reset_task_state()
                self.assertIsNone(adapter._meta_entry_receipt)

    def test_meta_landing_alias_uses_typed_entrance_state(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meta_entrance_state = Mock(return_value=SimpleNamespace())

        self.assertTrue(adapter.appear(NamedButton("ASH_SHOWDOWN")))
        self.assertEqual(adapter.semantic_id_for("ASH_SHOWDOWN"), "meta/page/back")

        oracle.meta_page_visible_value = True
        adapter.click(NamedButton("GOTO_MAIN"))
        self.assertEqual(oracle.click_calls, ["meta/home"])

    def test_meta_empty_beacon_page_maps_list_and_create_controls(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meta_current_empty_points = Mock(return_value=(200, 200))
        oracle.click_meta_current_create = Mock(
            return_value=oracle.click_receipt("meta/current/create")
        )

        self.assertTrue(adapter.appear(NamedButton("BEACON_LIST")))
        self.assertTrue(adapter.appear(NamedButton("META_BEGIN_ENTRANCE")))
        receipt = adapter.click(NamedButton("META_BEGIN_ENTRANCE"))

        self.assertEqual(receipt.semantic_id, "meta/current/create")
        oracle.click_meta_current_create.assert_called_once_with()

    def test_meta_assist_candidate_port_preserves_typed_expectations_through_session(self):
        adapter, oracle, gate_calls = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_tactical_input_frame = Mock()

        state = session.meta_assist_state()
        receipt = session.click_meta_assist_next_candidate(
            expected_index=state.selected_candidate_index,
            expected_level=state.selected_level,
        )

        self.assertEqual(state, oracle.meta_assist_state_value)
        self.assertEqual(receipt.semantic_id, "meta/assist/candidate/3")
        self.assertEqual(oracle.click_calls, ["meta/assist/candidate/3"])
        self.assertEqual(gate_calls, [True, True])
        session.refresh_tactical_input_frame.assert_called_once_with()

    def test_meta_beacon_owner_keeps_generic_reward_probe_passive(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["reward/award-info/close"] = False
        oracle.enabled_values["reward/award-info1/close"] = False
        adapter.begin_meta_beacon()

        self.assertTrue(adapter._operation_siren_allows_passive_probe())
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_1")))

        adapter.end_meta_beacon()
        self.assertFalse(adapter._meta_beacon_active)

    def test_meta_precombat_refuses_an_empty_saved_fleet(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meta_precombat_fleet_ready_value = False

        with self.assertRaisesRegex(SemanticGateClosed, "non-empty"):
            adapter.click_meta_precombat_start()

        self.assertEqual(oracle.click_calls, [])

    def test_meta_task_owner_survives_adapter_replacement(self):
        first, _, _ = self.make_adapter()
        replacement, replacement_oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = first
        session._meta_beacon_active = False
        session.open = lambda: session.adapter
        session.refresh_tactical_input_frame = lambda: None

        session.begin_meta_beacon()
        session.adapter = replacement
        receipt = session.click_daily_precombat_start()

        self.assertTrue(session.meta_beacon_active())
        self.assertTrue(replacement.meta_beacon_active())
        self.assertEqual(receipt.semantic_id, "daily/precombat/start")
        self.assertEqual(replacement_oracle.click_calls, ["daily/precombat/start"])
