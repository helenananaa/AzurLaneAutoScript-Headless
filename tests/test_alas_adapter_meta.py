"""Meta regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
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
