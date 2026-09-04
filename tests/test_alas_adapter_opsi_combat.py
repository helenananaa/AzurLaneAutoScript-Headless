"""Opsi combat regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_operation_siren_fleet_hp_retries_transient_missing_portraits(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_page_visible_value = True
        oracle.operation_siren_state = lambda: SimpleNamespace()
        calls = []

        def fleet_hp():
            calls.append(None)
            if len(calls) == 1:
                raise SemanticGateClosed(
                    "Operation Siren fleet portraits are absent or incomplete"
                )
            return (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)

        oracle.operation_siren_fleet_hp = fleet_hp

        self.assertEqual(
            adapter.campaign_fleet_hp(),
            (1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        )
        self.assertEqual(len(calls), 2)

    def test_operation_siren_fleet_hp_uses_local_shell_when_summary_is_incomplete(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_page_visible_value = True
        oracle.operation_siren_state = Mock(
            side_effect=SemanticGateClosed("operation siren fleet summary is malformed")
        )
        oracle.operation_siren_fleet_hp = lambda: (0.9, 0.8, 0.7, 0.6, 0.5, 0.4)

        self.assertEqual(
            adapter.campaign_fleet_hp(),
            (0.9, 0.8, 0.7, 0.6, 0.5, 0.4),
        )
        oracle.operation_siren_state.assert_not_called()

    def test_operation_siren_boss_combat_requires_exact_target_and_owns_result(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=())

        with self.assertRaisesRegex(
            SemanticGateClosed, "requires an exact boss target"
        ):
            adapter.begin_operation_siren_boss_combat()
        self.assertFalse(adapter.operation_siren_combat_committed())

        oracle.operation_siren_radar_targets.return_value = ((0, -2),)
        adapter.begin_operation_siren_boss_combat()

        self.assertTrue(adapter.operation_siren_combat_committed())
        self.assertEqual(gate_calls, [True, True])
        oracle.operation_siren_radar_targets.assert_called_with("boss")

    def test_operation_siren_combat_owner_releases_only_on_unobstructed_map(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.daily_battle_result_visible = Mock(return_value=True)
        oracle.award_info_page_visible = Mock(return_value=False)
        oracle.operation_siren_local_map_visible = Mock(return_value=True)

        self.assertFalse(adapter.complete_operation_siren_combat_if_map_restored())
        self.assertTrue(adapter.operation_siren_combat_committed())

        oracle.daily_battle_result_visible.return_value = False
        oracle.award_info_page_visible.return_value = True
        self.assertFalse(adapter.complete_operation_siren_combat_if_map_restored())
        self.assertTrue(adapter.operation_siren_combat_committed())

        oracle.award_info_page_visible.return_value = False
        self.assertTrue(adapter.complete_operation_siren_combat_if_map_restored())
        self.assertFalse(adapter.operation_siren_combat_committed())

    def test_operation_siren_combat_observer_gap_keeps_loading_and_execution(self):
        adapter, oracle, _ = self.make_adapter()
        adapter._operation_siren_combat_active = True
        oracle.operation_siren_local_map_visible = Mock(return_value=False)
        oracle.enabled_values["reward/award-info/close"] = False
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        def incomplete():
            raise SemanticGateClosed(
                "combat fixture endpoint completeness changed"
            )

        session._live_combat_visible = incomplete

        self.assertTrue(session.combat_is_loading())
        self.assertTrue(session.combat_is_executing())
        self.assertFalse(session.appear(NamedButton("BATTLE_PREPARATION")))

        adapter._operation_siren_combat_active = False
        self.assertFalse(session.combat_is_loading())
        self.assertFalse(session.combat_is_executing())
        self.assertFalse(
            session._operation_siren_combat_observer_gap(
                SemanticGateClosed(
                    "combat fixture endpoint completeness changed"
                )
            )
        )

    def test_operation_siren_low_resolve_cancel_remembers_defeated_fleet(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        receipt = oracle.click_receipt("os/combat/low-resolve/cancel")
        oracle.click_operation_siren_low_resolve_cancel = Mock(
            return_value=receipt
        )
        oracle.operation_siren_current_fleet_defeated = Mock(
            side_effect=AssertionError("remembered fleet must not be re-probed")
        )

        self.assertEqual(
            adapter.click_operation_siren_low_resolve_cancel(), receipt
        )
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())
        oracle.click_operation_siren_low_resolve_cancel.assert_called_once_with()
