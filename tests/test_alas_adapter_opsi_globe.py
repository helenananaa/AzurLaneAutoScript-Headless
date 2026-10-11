"""Opsi globe regression cases for the adapter."""

import unittest
import time
from alas_headless import SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_committed_zone_entry_keeps_optional_reward_probe_passive_during_mount(self):
        adapter, oracle, _ = self.make_adapter()
        receipt = oracle.click_receipt('os/globe/zone-enter')
        oracle.click_operation_siren_globe_zone_enter = Mock(return_value=receipt)
        self.assertFalse(adapter._operation_siren_allows_passive_probe())
        self.assertEqual(adapter.click_operation_siren_globe_zone_enter('东南洋脊A'), receipt)
        self.assertFalse(adapter.appear(NamedButton('GET_ITEMS_1')))
        self.assertTrue(adapter._operation_siren_allows_passive_probe())
        oracle.operation_siren_state = Mock(return_value=SimpleNamespace())
        self.assertTrue(adapter.operation_siren_map_visible())
        self.assertEqual(adapter._operation_siren_entry_transition_until, 0)
        oracle.click_operation_siren_globe_zone_enter.assert_called_once_with('东南洋脊A')

    def test_failed_zone_input_does_not_own_mount_or_authorize_unknown_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.click_operation_siren_globe_zone_enter = Mock(side_effect=SemanticGateClosed('pinned zone changed'))
        with self.assertRaisesRegex(SemanticGateClosed, 'pinned zone changed'):
            adapter.click_operation_siren_globe_zone_enter('东南洋脊A')
        self.assertFalse(adapter._operation_siren_allows_passive_probe())
        self.assertEqual(adapter._operation_siren_entry_transition_until, 0)

    def test_repeated_exit_confirmation_acknowledges_fresh_globe_without_second_input(self):
        adapter, oracle, _ = self.make_adapter()
        prior = oracle.click_receipt('os/exit/confirm')
        adapter._operation_siren_exit_receipt = prior
        adapter._operation_siren_entry_transition_until = time.monotonic() + 30
        oracle.main_page_visible = Mock(return_value=False)
        oracle.campaign_menu_is_entry = Mock(return_value=False)
        oracle.operation_siren_globe_visible = Mock(return_value=True)
        oracle.read_state = Mock(return_value=SimpleNamespace(generation=prior.generation + 1))
        self.assertEqual(adapter.click(NamedButton('POPUP_CONFIRM')), prior)
        self.assertEqual(oracle.click_calls, [])
        self.assertIsNone(adapter._operation_siren_exit_receipt)

    def test_native_globe_loop_can_handle_exit_prompt_before_covered_map_entry(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_state = Mock(return_value=SimpleNamespace())
        oracle.exists_values['os/map/globe'] = True
        oracle.enabled_values['os/map/globe'] = True
        self.assertTrue(adapter.appear(NamedButton('MAP_GOTO_GLOBE')))
        oracle.observation_prompt_kind_value = 'opsi-exit'
        oracle.operation_siren_exit_prompt_visible = Mock(return_value=True)
        self.assertFalse(adapter.appear(NamedButton('MAP_GOTO_GLOBE')))
        self.assertFalse(adapter.appear(NamedButton('MAP_GOTO_GLOBE_FOG')))
        self.assertTrue(adapter.appear(NamedButton('POPUP_CONFIRM')))
        oracle.observation_prompt_kind_value = None
        oracle.operation_siren_exit_prompt_visible.return_value = False
        self.assertTrue(adapter.appear(NamedButton('MAP_GOTO_GLOBE')))

    def test_operation_siren_globe_navigation_owns_loading_gap(self):
        adapter, oracle, _ = self.make_adapter()
        receipt = oracle.click_receipt("os/map/globe")
        oracle.click_operation_siren_globe = Mock(return_value=receipt)

        self.assertEqual(adapter.click(NamedButton("MAP_GOTO_GLOBE")), receipt)
        self.assertFalse(adapter.appear(NamedButton("GET_MISSION")))

        oracle.operation_siren_globe_visible = Mock(return_value=True)
        self.assertTrue(adapter.operation_siren_globe_visible())
        self.assertEqual(adapter._operation_siren_entry_transition_until, 0.0)

    def test_operation_siren_globe_return_commit_is_idempotent(self):
        adapter, oracle, _ = self.make_adapter()
        receipt = oracle.click_receipt("os/globe/map")
        oracle.click_operation_siren_globe_map = Mock(return_value=receipt)

        first = adapter.click(NamedButton("GLOBE_GOTO_MAP"))
        self.assertFalse(adapter.appear(NamedButton("GLOBE_GOTO_MAP")))
        duplicate = adapter.click(NamedButton("GLOBE_GOTO_MAP"))

        self.assertEqual(first, receipt)
        self.assertEqual(duplicate, receipt)
        oracle.click_operation_siren_globe_map.assert_called_once_with()

    def test_operation_siren_globe_swipe_accepts_unobstructed_map_strip(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_globe_state = Mock(
            return_value=SimpleNamespace(zone_name="NA海域西南C")
        )
        oracle.operation_siren_globe_visible = Mock(return_value=True)

        oracle._require_operation_siren_globe_visible = Mock(return_value=True)
        oracle._retry_transition_read = lambda reader: reader()
        intent = adapter.begin_operation_siren_globe_swipe_vector(
            (100, -100),
            box=(600, 220, 980, 620),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="GLOBE_SWIPE_100_-100",
            distance_check=True,
        )

        self.assertEqual(intent.box, (600, 220, 980, 620))
        self.assertEqual(gate_calls, [True])
        adapter.end_operation_siren_globe_swipe_vector(intent)
