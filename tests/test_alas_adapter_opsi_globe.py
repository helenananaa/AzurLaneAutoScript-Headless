"""Opsi globe regression cases for the adapter."""

import unittest
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
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
