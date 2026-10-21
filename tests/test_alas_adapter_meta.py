"""Meta regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_own_meta_passive_result_mount_does_not_grant_input(self):
        path = ('OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/'
                'NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn')
        message = ('combat action control is not exact top-raycast actionable: '
                   + path + ', raycast_top=False')
        for owned, count in ((True, 1), (False, 1), (True, 2)):
            adapter, oracle, _ = self.make_adapter()
            if owned:
                adapter.begin_meta_beacon()
            result = SimpleNamespace(path=path, active_in_hierarchy=True,
                                     active_and_enabled=True, raycast_top=False,
                                     actionable=False, point=object(),
                                     bounds=SimpleNamespace(contains=lambda p: True))
            oracle.read_state = Mock(return_value=SimpleNamespace(buttons=[result] * count))
            session = AlasSemanticSession.__new__(AlasSemanticSession)
            session.open = lambda: adapter
            session._live_combat_snapshot = Mock(return_value=object())
            session._live_combat_manifest = Mock(return_value=object())
            with patch('alas_headless.adapter.semantic.session_combat.alas_combat_visible_resource_names',
                       side_effect=SemanticGateClosed(message)):
                if owned and count == 1:
                    self.assertEqual(session._live_combat_visible(), ())
                else:
                    with self.assertRaisesRegex(SemanticGateClosed, 'top-raycast'):
                        session._live_combat_visible()
            self.assertEqual(oracle.click_calls, [])

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

    def test_meta_sync_menu_is_a_valid_original_meta_page(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meta_character_page_visible = Mock(return_value=False)
        oracle.meta_character_menu_visible = Mock(return_value=True)

        self.assertTrue(adapter.appear(NamedButton('META_CHECK')))
        self.assertTrue(adapter.appear(NamedButton('META_MENU_CHECK')))
        oracle.meta_character_menu_visible = Mock(return_value=False)
        self.assertFalse(adapter.appear(NamedButton('META_CHECK')))

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

    def test_meta_assist_reuses_precombat_back_only_after_list_mounts(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_meta_assist()
        oracle.daily_precombat_visible_value = True
        oracle.click_meta_assist_precombat_back = Mock(side_effect=oracle.click_daily_precombat_back)
        first = adapter.click(NamedButton('BACK_ARROW'))
        self.assertEqual(first.semantic_id, 'daily/precombat/back')

        oracle.daily_precombat_visible_value = False
        oracle.state_generation = first.generation + 1
        repeated = adapter.click(NamedButton('BACK_ARROW'))
        self.assertIs(repeated, first)
        self.assertEqual(oracle.click_calls, ['daily/precombat/back'])

        oracle.state_generation = first.generation
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton('BACK_ARROW'))
        adapter.end_meta_assist()

    def test_meta_assist_entry_reuses_receipt_only_on_new_precombat(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_meta_assist()
        oracle.click_meta_assist_start = Mock(
            return_value=oracle.click_receipt('meta/assist/start')
        )
        first = adapter.click(NamedButton('ASH_START'))
        oracle.daily_precombat_visible_value = True
        oracle.state_generation = first.generation + 1
        repeated = adapter.click(NamedButton('ASH_START'))
        self.assertIs(repeated, first)
        oracle.click_meta_assist_start.assert_called_once_with()

        oracle.state_generation = first.generation
        adapter.click(NamedButton('ASH_START'))
        self.assertEqual(oracle.click_meta_assist_start.call_count, 2)
        adapter.end_meta_assist()

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

    def test_own_meta_orphan_result_accepts_reviewed_meta_return(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_meta_beacon()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        for name in ('daily_battle_result_visible', 'campaign_battle_reward_visible',
                     'operation_siren_page_visible', 'daily_page_visible',
                     'main_page_visible', 'event_campaign_page_visible',
                     'campaign_is_in_map'):
            setattr(oracle, name, Mock(return_value=False))
        oracle.meta_page_visible = Mock(return_value=True)
        self.assertEqual(session.recover_orphan_combat_result(), ())
        adapter.end_meta_beacon()
        # Recovery also serves unrelated tasks inheriting a complete META
        # page. Its typed identity owns this return, not the departed task.
        self.assertEqual(session.recover_orphan_combat_result(), ())
        oracle.meta_page_visible.return_value = False
        with self.assertRaisesRegex(SemanticGateClosed, 'did not return'):
            session.recover_orphan_combat_result(timeout_seconds=.001)

    def test_assist_orphan_result_uses_complete_meta_page_proof_once(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_meta_assist()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        for name in ('daily_battle_result_visible', 'campaign_battle_reward_visible',
                     'operation_siren_page_visible', 'daily_page_visible',
                     'main_page_visible', 'event_campaign_page_visible'):
            setattr(oracle, name, Mock(return_value=False))
        oracle.meta_assist_state = Mock(return_value=object())
        oracle.meta_page_visible = Mock(side_effect=lambda: bool(oracle.meta_assist_state()))
        self.assertEqual(session.recover_orphan_combat_result(), ())
        oracle.meta_assist_state.assert_called_once()
        oracle.meta_assist_state.side_effect = SemanticGateClosed('unknown assist state')
        with self.assertRaisesRegex(SemanticGateClosed, 'unknown assist'):
            session.recover_orphan_combat_result()
        self.assertEqual(oracle.click_calls, [])

    def test_own_meta_start_ack_requires_newer_proven_transition(self):
        for newer, transitioned in ((True, True), (False, True), (True, False)):
            with self.subTest(newer=newer, transitioned=transitioned):
                adapter, oracle, _ = self.make_adapter()
                adapter.begin_meta_beacon()
                first = adapter.click_meta_precombat_start()
                oracle.state_generation = first.generation + int(newer)
                oracle.meta_precombat_fleet_ready_value = False
                oracle.daily_combat_visible = Mock(return_value=transitioned)
                oracle.daily_battle_result_visible = Mock(return_value=False)
                oracle.meta_assist_sortie_prompt_visible = Mock(return_value=False)
                if newer and transitioned:
                    self.assertIs(adapter.click_meta_precombat_start(), first)
                else:
                    adapter._meta_precombat_start_until = 5.0
                    with patch('alas_headless.adapter.semantic.meta.time.monotonic',
                               side_effect=[0, 6]):
                        with self.assertRaisesRegex(SemanticGateClosed, 'reviewed transition'):
                            adapter.click_meta_precombat_start()
                self.assertEqual(oracle.click_calls, ['daily/precombat/start'])
                adapter.end_meta_beacon()
                self.assertIsNone(adapter._meta_precombat_start_receipt)

    def test_own_meta_start_ack_tolerates_loading_but_not_foreign_popup(self):
        for blocker in ('loading', 'network-down'):
            adapter, oracle, _ = self.make_adapter()
            adapter.begin_meta_beacon()
            first = adapter.click_meta_precombat_start()
            oracle.state_generation = first.generation + 1
            oracle.meta_precombat_fleet_ready_value = False
            for name in ('daily_combat_visible', 'daily_battle_result_visible',
                         'meta_assist_sortie_prompt_visible'):
                setattr(oracle, name, Mock(return_value=False))
            oracle._blocking_rules = Mock(return_value=[SimpleNamespace(blocker_id=blocker)])
            if blocker == 'loading':
                self.assertIs(adapter.click_meta_precombat_start(), first)
            else:
                adapter._meta_precombat_start_until = 5.0
                with patch('alas_headless.adapter.semantic.meta.time.monotonic',
                           side_effect=[0, 6]):
                    with self.assertRaisesRegex(SemanticGateClosed, 'reviewed transition'):
                        adapter.click_meta_precombat_start()
            self.assertEqual(oracle.click_calls, ['daily/precombat/start'])

    def test_own_meta_start_wait_uses_existing_twenty_second_lease(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_meta_beacon()
        first = adapter.click_meta_precombat_start()
        adapter._meta_precombat_start_until = 20.0
        oracle.state_generation = first.generation + 1
        oracle.meta_precombat_fleet_ready_value = False
        oracle.daily_combat_visible = Mock(side_effect=[False, True])
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.meta_assist_sortie_prompt_visible = Mock(return_value=False)
        with patch('alas_headless.adapter.semantic.meta.time.monotonic', side_effect=[0, 6]), \
                patch('alas_headless.adapter.semantic.meta.time.sleep'):
            self.assertIs(adapter.click_meta_precombat_start(), first)
        self.assertEqual(oracle.click_calls, ['daily/precombat/start'])

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

    def test_own_meta_result_uses_reviewed_typed_stack(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_meta_beacon()
        adapter._operation_siren_combat_active = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.open = lambda: adapter
        session.refresh_tactical_input_frame = Mock()
        session._combat_result_transition_until = 0.0
        expected = oracle.click_receipt('daily/battle/result')
        oracle.click_daily_battle_result = Mock(return_value=expected)
        self.assertIs(session._live_combat_click('BATTLE_STATUS_S'), expected)
        session.refresh_tactical_input_frame.assert_called_once_with()
        self.assertIs(session._combat_last_result_receipt, expected)
        oracle.click_daily_battle_result.side_effect = SemanticGateClosed('ambiguous result')
        with self.assertRaisesRegex(SemanticGateClosed, 'ambiguous'):
            session._live_combat_click('BATTLE_STATUS_S')
        adapter.end_meta_beacon()
        session._runtime_handle = None
        with self.assertRaisesRegex(SemanticGateClosed, 'runtime handle'):
            session._live_combat_click('BATTLE_STATUS_S')
        self.assertEqual(oracle.click_daily_battle_result.call_count, 2)

    def test_own_meta_result_return_requires_reviewed_page(self):
        for visible in (True, False):
            adapter, oracle, _ = self.make_adapter()
            adapter.begin_meta_beacon()
            adapter._operation_siren_combat_active = True
            oracle.read_state = Mock(return_value=SimpleNamespace(buttons=[]))
            oracle.meta_page_visible = Mock(return_value=visible)
            adapter.appear = Mock(return_value=False)
            session = AlasSemanticSession.__new__(AlasSemanticSession)
            session.open = lambda: adapter
            session.refresh_frame = Mock()
            if visible:
                self.assertFalse(session._meta_assist_result_return_observation('BATTLE_PREPARATION'))
                self.assertFalse(adapter._operation_siren_combat_active)
            else:
                with self.assertRaisesRegex(SemanticGateClosed, 'not reviewed'):
                    session._meta_assist_result_return_observation('BATTLE_PREPARATION')
                self.assertTrue(adapter._operation_siren_combat_active)
            self.assertEqual(oracle.click_calls, [])
