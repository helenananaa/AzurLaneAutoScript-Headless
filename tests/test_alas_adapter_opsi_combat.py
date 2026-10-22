"""Opsi combat regression cases for the adapter."""

import unittest
import copy
from alas_headless import AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_original_os_failure_handler_consumes_c_and_d_statistics(self):
        from tests.test_alas_config_branch_compatibility import method
        resources = dict(EXP_INFO_C=NamedButton('EXP_INFO_C'),
                         EXP_INFO_D=NamedButton('EXP_INFO_D'))
        original = method('module/os_combat/combat.py', 'Combat',
                          'handle_auto_search_exp_info', **resources)
        for grade in ('C', 'D'):
            adapter, oracle, _ = self.make_adapter()
            oracle.operation_siren_battle_statistics_grade = Mock(return_value=grade)
            oracle.operation_siren_battle_statistics_visible = Mock(return_value=True)
            oracle.operation_siren_battle_result_visible = Mock(return_value=False)
            adapter._operation_siren_auto_search_active = True
            session = AlasSemanticSession('emulator-test', '506b76f698b5089aaa29c4e7908b48edb8532a44')
            session.adapter = adapter
            session.open = lambda: adapter
            session._combat_result_action_oracle = lambda _: oracle
            oracle.click_daily_battle_result = Mock(return_value=SimpleNamespace(generation=11))
            def appear_then_click(button):
                if not session.appear(button):
                    return False
                session.click(button)
                return True
            host = SimpleNamespace(appear_then_click=appear_then_click,
                                   device=SimpleNamespace(sleep=Mock()))
            self.assertTrue(original(host))
            oracle.click_daily_battle_result.assert_called_once()

    def test_auto_search_statistics_uses_native_grade_and_rechecks_before_input(self):
        adapter, oracle, _ = self.make_adapter()
        frame = copy.copy(oracle)
        frame.operation_siren_battle_result_visible = Mock(return_value=False)
        frame.operation_siren_battle_statistics_grade = Mock(return_value='D')
        frame.operation_siren_battle_statistics_visible = Mock(return_value=True)
        frame.click_daily_battle_result = Mock(return_value=SimpleNamespace(generation=11))
        adapter._frame_or_live_observation_oracle = lambda: frame
        adapter._operation_siren_auto_search_active = True
        session = AlasSemanticSession('emulator-test', '506b76f698b5089aaa29c4e7908b48edb8532a44')
        session.adapter = adapter
        session.open = lambda: adapter
        session._combat_result_action_oracle = lambda _: frame
        self.assertTrue(session.appear(NamedButton('EXP_INFO_D')))
        self.assertFalse(session.appear(NamedButton('EXP_INFO_B')))
        self.assertFalse(session.appear(NamedButton('PAUSE')))
        session.click(NamedButton('EXP_INFO_D'))
        frame.click_daily_battle_result.assert_called_once()
        frame.operation_siren_battle_statistics_grade.return_value = 'C'
        with self.assertRaisesRegex(SemanticGateClosed, 'grade changed'):
            session.click(NamedButton('EXP_INFO_D'))
        frame.click_daily_battle_result.assert_called_once()
        adapter._operation_siren_startup_search_provisional = True
        frame.operation_siren_battle_statistics_grade.reset_mock()
        session.appear(NamedButton('EXP_INFO_D'))
        frame.operation_siren_battle_statistics_grade.assert_not_called()

    def test_unrelated_probe_on_statistics_does_not_require_a_grade_or_grant_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_battle_result_visible = Mock(return_value=False)
        oracle.operation_siren_battle_statistics_visible = Mock(return_value=True)
        oracle.operation_siren_battle_statistics_grade = Mock(side_effect=SemanticGateClosed('grade inconsistent'))
        adapter._operation_siren_auto_search_active = True
        session = AlasSemanticSession('emulator-test', '506b76f698b5089aaa29c4e7908b48edb8532a44')
        session.adapter = adapter
        session.open = lambda: adapter
        session._combat_result_action_oracle = lambda _: oracle
        for name in ('AUTO_SEARCH_REWARD', 'PAUSE', 'IN_MAP'):
            self.assertFalse(session.appear(NamedButton(name)))
        oracle.operation_siren_battle_statistics_grade.assert_not_called()
        with self.assertRaisesRegex(SemanticGateClosed, 'inconsistent'):
            session.appear(NamedButton('EXP_INFO_D'))
        with self.assertRaisesRegex(SemanticGateClosed, 'inconsistent'):
            session.click(NamedButton('EXP_INFO_D'))
        self.assertEqual(oracle.click_calls, [])

    def test_auto_search_grade_uses_one_screenshot_while_live_result_unmounts(self):
        adapter, oracle, _ = self.make_adapter()
        frame = copy.copy(oracle)
        frame.operation_siren_battle_result_visible = Mock(return_value=True)
        frame.operation_siren_battle_result_grade = Mock(return_value='DEFEAT')
        oracle.operation_siren_battle_result_visible = Mock(side_effect=AssertionError('split live observation'))
        oracle.operation_siren_battle_result_grade = Mock(side_effect=SemanticGateClosed('result unmounted'))
        adapter._frame_or_live_observation_oracle = lambda: frame
        adapter._operation_siren_auto_search_active = True
        session = AlasSemanticSession('emulator-test', '506b76f698b5089aaa29c4e7908b48edb8532a44')
        session.adapter = adapter
        session.open = lambda: adapter
        self.assertTrue(session.appear(NamedButton('BATTLE_STATUS_D')))
        oracle.operation_siren_battle_result_visible.assert_not_called()
        oracle.operation_siren_battle_result_grade.assert_not_called()

    def test_original_auto_search_defeat_uses_exact_result_without_manual_boss_owner(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_battle_result_visible = Mock(return_value=True)
        oracle.operation_siren_battle_result_grade = Mock(return_value='DEFEAT')
        session = AlasSemanticSession('emulator-test', '506b76f698b5089aaa29c4e7908b48edb8532a44')
        session.adapter = adapter
        session.open = lambda: adapter
        session._live_combat_visible = lambda: ()
        session.refresh_frame = Mock()
        self.assertFalse(adapter.operation_siren_combat_committed())
        adapter._operation_siren_auto_search_active = True
        adapter._operation_siren_startup_search_provisional = False
        self.assertTrue(session.appear(NamedButton('BATTLE_STATUS_D')))
        self.assertFalse(session.appear(NamedButton('BATTLE_STATUS_C')))
        self.assertFalse(session.appear(NamedButton('BATTLE_STATUS_S')))
        adapter._operation_siren_startup_search_provisional = True
        self.assertFalse(session.appear(NamedButton('BATTLE_STATUS_D')))
        adapter._operation_siren_startup_search_provisional = False
        adapter._operation_siren_auto_search_active = False
        with self.assertRaises(AlasSemanticUnmapped):
            session.appear(NamedButton('BATTLE_STATUS_D'))
        adapter._operation_siren_auto_search_active = True
        oracle.operation_siren_battle_result_grade.side_effect = SemanticGateClosed('ambiguous grade')
        with self.assertRaisesRegex(SemanticGateClosed, 'ambiguous grade'):
            session.appear(NamedButton('BATTLE_STATUS_D'))

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
