"""Campaign regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    SemanticGateClosed,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import (
    CampaignGridButton,
    FakeOracle,
    NamedButton,
    make_campaign_combat_decision,
    make_campaign_combat_state,
)
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_main_battle_transition_reuses_receipt_under_exact_campaign_menu(self):
        adapter, oracle, _ = self.make_adapter()

        first = adapter.click(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
        oracle.campaign_menu_value = True
        oracle.enabled_values["main/battle"] = False
        repeated = adapter.click(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))

        self.assertIs(repeated, first)
        self.assertEqual(oracle.click_calls, ["main/battle"])

        oracle.campaign_menu_value = False
        oracle.enabled_values["main/battle"] = True
        next_entry = adapter.click(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
        self.assertEqual(next_entry.semantic_id, "main/battle")
        self.assertEqual(oracle.click_calls, ["main/battle", "main/battle"])

    def test_typed_campaign_menu_hides_unrelated_pixel_page_checks(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_campaign_menu_uses_presence_check_and_exact_navigation_targets(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))
        self.assertEqual(
            adapter.semantic_id_for("CAMPAIGN_MENU_GOTO_CAMPAIGN"),
            "campaign-menu/normal",
        )
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        self.assertEqual(oracle.click_calls, ["campaign-menu/page/back"])

    def test_campaign_menu_generic_back_uses_exact_navigation_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_menu_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        receipt = adapter.click(NamedButton("BACK_ARROW"))

        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        self.assertEqual(oracle.click_calls, ["campaign-menu/page/back"])

    def test_campaign_menu_entry_has_bounded_transition_grace(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_error = SemanticGateClosed(
            "campaign page identity is not proven"
        )

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            receipt = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_CAMPAIGN"))
            duplicate = adapter.click(NamedButton("CAMPAIGN_MENU_GOTO_CAMPAIGN"))
            self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))

        self.assertEqual(duplicate, receipt)
        self.assertEqual(oracle.click_calls, ["campaign-menu/normal"])
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=31.0):
            with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
                adapter.appear(NamedButton("CAMPAIGN_CHECK"))
        adapter.end_campaign_pre_sortie()

    def test_resumed_map_does_not_impersonate_campaign_menu(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_in_map_value = True

        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_MENU_CHECK")))

    def test_campaign_chapter_check_and_back_require_typed_page_identity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True
        oracle.enabled_values["login/enter"] = False
        oracle.enabled_values["overlay/bulletin/close"] = False
        oracle.enabled_values["campaign-menu/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertEqual(adapter.campaign_page_state().chapter_name, "第一章")
        self.assertEqual(adapter.event_points(), 17060)
        self.assertEqual(adapter.event_coin(), 70477)
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        self.assertEqual(oracle.click_calls, ["campaign-menu/page/back"])

    def test_campaign_page_state_retries_only_generation_coherence(self):
        adapter, oracle, _ = self.make_adapter()
        expected = oracle.campaign_state_value
        attempts = []

        def transient_page_state():
            attempts.append(True)
            if len(attempts) < 3:
                raise SemanticGateClosed("campaign snapshots are not coherent")
            return expected

        oracle.campaign_page_state = transient_page_state

        self.assertIs(adapter.campaign_page_state(), expected)
        self.assertEqual(len(attempts), 3)

        def identity_failure():
            raise SemanticGateClosed("campaign page identity is not proven")

        oracle.campaign_page_state = identity_failure
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            adapter.campaign_page_state()

    def test_campaign_stage_entry_is_exact_and_spends_one_independent_budget(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云下",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.campaign_stage_entry_allowed())
        self.assertTrue(adapter.appear(button))
        receipt = adapter.click(button)

        self.assertEqual(receipt.semantic_id, "campaign/stage/12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        self.assertEqual(oracle.click_calls, ["campaign/stage/12-4"])
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.click(button)
        adapter.end_campaign_pre_sortie()

    def test_campaign_context_recovers_only_exact_network_reconnect_prompt(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        oracle.enabled_values["overlay/network-reconnect/cancel"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True

        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_CAMPAIGN_RECONNECT"))

        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(
            oracle.click_calls,
            ["overlay/network-reconnect/confirm"],
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_result_ready_requires_committed_campaign_owner(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        oracle.daily_battle_result_visible = Mock(return_value=True)
        oracle.operation_siren_battle_result_visible = Mock(return_value=False)
        adapter.campaign_combat_committed = Mock(return_value=True)

        self.assertTrue(session.campaign_result_ready())
        adapter.campaign_combat_committed.return_value = False
        self.assertFalse(session.campaign_result_ready())

    def test_campaign_boss_stage_return_requires_committed_owner_and_closed_result(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.operation_siren_battle_result_visible = Mock(return_value=False)
        oracle.campaign_page_value = True
        adapter.campaign_combat_committed = Mock(return_value=True)

        self.assertTrue(session.campaign_boss_returned_to_stage())
        oracle.daily_battle_result_visible.return_value = True
        self.assertFalse(session.campaign_boss_returned_to_stage())
        oracle.daily_battle_result_visible.return_value = False
        adapter.campaign_combat_committed.return_value = False
        self.assertFalse(session.campaign_boss_returned_to_stage())

    def test_orphan_campaign_result_accepts_reviewed_map_return(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.campaign_battle_reward_visible = Mock(return_value=False)
        oracle.campaign_is_in_map = Mock(return_value=True)
        oracle.operation_siren_page_visible = Mock(return_value=False)
        oracle.daily_page_visible = Mock(return_value=False)
        oracle.main_page_visible = Mock(return_value=False)

        self.assertEqual(session.recover_orphan_combat_result(), ())

    def test_orphan_campaign_result_tolerates_exact_map_mount_gap(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.orphan_combat_result_visible = lambda: True
        session._combat_result_transition_until = 0.0
        adapter._require_frame_observation_oracle = lambda: oracle
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.campaign_battle_reward_visible = Mock(return_value=False)
        oracle.campaign_is_in_map = Mock(
            side_effect=(
                SemanticGateClosed("campaign startup surface is not reviewed"),
                True,
            )
        )
        oracle.operation_siren_page_visible = Mock(return_value=False)
        oracle.daily_page_visible = Mock(return_value=False)
        oracle.main_page_visible = Mock(return_value=False)

        with patch("alas_headless.alas_adapter.time.sleep", return_value=None):
            self.assertEqual(session.recover_orphan_combat_result(), ())

    def test_campaign_stage_probe_defers_to_exact_late_reconnect_prompt(self):
        adapter, oracle, _ = self.make_adapter()
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")

        def disconnected(_stage_code):
            raise SemanticGateClosed("campaign page identity is not proven")

        oracle.campaign_stage_actionable = disconnected
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True

        self.assertFalse(adapter.appear(button))
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_stage_entry_defaults_closed_and_rejects_identity_change(self):
        adapter, oracle, _ = self.make_adapter()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云下",
            stages=(stage,),
        )
        button = NamedButton("12-3")
        button.semantic_campaign_stage_code = "12-3"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            adapter.appear(button)
        adapter.end_campaign_pre_sortie()

    def test_campaign_startup_in_map_probe_reuses_typed_non_map_gate(self):
        adapter, _, _ = self.make_adapter()

        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.appear(NamedButton("UNREVIEWED_PAGE_CHECK")))
        adapter.end_campaign_pre_sortie()

    def test_campaign_map_proof_allows_only_passive_unknown_probes(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        oracle.campaign_in_map_value = True

        self.assertFalse(adapter.appear(NamedButton("EXERCISE_CHECK")))
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.click(NamedButton("EXERCISE_CHECK"))
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_unknown_surface_keeps_passive_probe_closed(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter._campaign_context.passive_transition_until = time.monotonic() - 1

        def unknown_surface():
            raise SemanticGateClosed("campaign startup surface is not reviewed")

        oracle.campaign_is_in_map = unknown_surface
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("EXERCISE_CHECK"))
        self.assertEqual(oracle.click_calls, [])

    def test_regular_campaign_back_uses_main_scene_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_page_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True
        adapter.begin_campaign_pre_sortie("15-1", mode="normal")

        self.assertTrue(adapter.appear(NamedButton("BACK_ARROW")))
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")
        self.assertEqual(oracle.click_calls, ["campaign-menu/page/back"])

    def test_campaign_mode_switch_reports_exact_destination_without_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.war_archives_page_visible = Mock(
            side_effect=SemanticGateClosed("archive snapshots are unrelated")
        )
        oracle.battle_pass_page_visible = Mock(
            side_effect=SemanticGateClosed("Battle Pass snapshots are unrelated")
        )
        oracle.recommendation_shop_visible = Mock(
            side_effect=SemanticGateClosed("shop snapshots are unrelated")
        )

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("SWITCH_1_HARD")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_1_NORMAL")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_2_HARD")))
        self.assertFalse(adapter.appear(NamedButton("SWITCH_2_EX")))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(oracle.click_calls, [])
        oracle.war_archives_page_visible.assert_not_called()
        oracle.battle_pass_page_visible.assert_not_called()
        oracle.recommendation_shop_visible.assert_not_called()

    def test_campaign_oil_is_typed_for_global_alas_status_probe(self):
        adapter, _, _ = self.make_adapter()
        self.assertEqual(adapter.campaign_oil(), 9504)

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertEqual(adapter.campaign_oil(), 9504)
        adapter.end_campaign_pre_sortie()

    def test_campaign_stop_condition_observations_are_stage_bound(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        adapter.begin_campaign_pre_sortie("12-4")

        achievement = adapter.campaign_map_achievement_state()
        levels = adapter.campaign_fleet_levels()

        self.assertIs(achievement, oracle.campaign_achievement_value)
        self.assertEqual(levels, (118, 109, 117, 110, 118, 107))
        adapter.end_campaign_pre_sortie()

        with self.assertRaisesRegex(SemanticGateClosed, "outside"):
            adapter.campaign_map_achievement_state()
        with self.assertRaisesRegex(SemanticGateClosed, "outside"):
            adapter.campaign_fleet_levels()

    def test_hard_campaign_9710_uses_game_managed_roles_without_adjustment_click(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_all_fleet2_standby"
        )

        self.assertEqual(
            (roles.fleet1_role, roles.fleet2_role),
            ("game-managed", "game-managed"),
        )
        self.assertFalse(any("adjustment" in call for call in oracle.click_calls))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_all_fleet2_standby",
            )
        )
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_97328_reads_duty_tab_from_fresh_immutable_frames(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=2,
            campaign_sortie_budget=1,
            frame_observation_oracle=lambda: oracle,
            input_frame_refresher=refresh,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_all_fleet2_standby"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("all", "standby"))
        self.assertIn(
            "campaign/fleet-preparation/roles/tab", oracle.click_calls
        )
        self.assertGreaterEqual(refresh.call_count, 4)
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_97328_waits_for_duty_tab_postcondition(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        original_toggle_selected = oracle.toggle_selected
        probe_count = 0

        def delayed_toggle_selected(semantic_id):
            nonlocal probe_count
            probe_count += 1
            if (
                semantic_id == "campaign/fleet-preparation/roles/tab"
                and probe_count == 2
            ):
                return False
            return original_toggle_selected(semantic_id)

        oracle.toggle_selected = delayed_toggle_selected
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=2,
            campaign_sortie_budget=1,
            frame_observation_oracle=lambda: oracle,
            input_frame_refresher=lambda: None,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_all_fleet2_standby"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("all", "standby"))
        self.assertGreaterEqual(probe_count, 3)
        self.assertEqual(
            oracle.click_calls.count("campaign/fleet-preparation/roles/tab"), 1
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_map_model_is_read_only_and_context_bound(self):
        oracle = FakeOracle()
        package_checks = []
        adapter = AlasSemanticAdapter(oracle, lambda: package_checks.append(True))
        adapter.begin_campaign_pre_sortie("12-4")

        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((5, 0), (6, 0)),
            expected_fleet_count=2,
        )

        self.assertIs(state, oracle.campaign_map_state_value)
        self.assertEqual(
            oracle.campaign_map_state_calls,
            [("12-4", 11, 8, ((5, 0), (6, 0)), 2)],
        )
        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(len(package_checks), 2)
        adapter.end_campaign_pre_sortie()

        with self.assertRaisesRegex(SemanticGateClosed, "pre-sortie flow"):
            adapter.campaign_map_state(
                columns=11,
                rows=8,
                land_cells=((5, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_map_model_keeps_unreviewed_hard_stage_isolated(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("10-4", mode="hard")

        with self.assertRaisesRegex(
            SemanticGateClosed, "reviewed shared event C/D stages"
        ):
            adapter.campaign_map_state(
                columns=9,
                rows=9,
                land_cells=((3, 0),),
                expected_fleet_count=2,
            )

        self.assertEqual(oracle.campaign_map_state_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_map_reconnect_returns_to_same_logical_map(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        self.assertTrue(adapter.recover_campaign_map_network_reconnect())
        self.assertEqual(
            oracle.click_calls, ["overlay/network-reconnect/confirm"]
        )
        self.assertIs(state, oracle.campaign_map_state_value)
        self.assertEqual(len(oracle.campaign_map_state_calls), 2)

    def test_campaign_map_reconnect_is_noop_when_prompt_is_absent(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        oracle.enabled_values["overlay/network-reconnect/confirm"] = False
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        self.assertFalse(adapter.recover_campaign_map_network_reconnect())
        self.assertEqual(oracle.click_calls, [])

    def test_campaign_result_passive_fallback_clicks_fresh_statistics_page(self):
        adapter, oracle, _ = self.make_adapter(campaign_combat_budget=1)
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(make_campaign_combat_decision(), state)
        adapter.click(CampaignGridButton((3, 5)))

        expected = oracle.click_receipt("daily/battle/result", generation=60)
        oracle.daily_battle_result_visible = Mock(return_value=True)
        oracle.click_daily_battle_result = Mock(return_value=expected)
        stale_oracle = SimpleNamespace(
            daily_battle_result_visible=Mock(return_value=False),
            operation_siren_battle_result_visible=Mock(return_value=False),
        )
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = Mock()
        session._combat_result_action_oracle = lambda _adapter: stale_oracle
        session._combat_result_observation = (
            "BATTLE_STATUS_S",
            time.monotonic(),
        )
        session._combat_last_result_receipt = None
        session._arm_combat_result_transition = Mock()

        receipt = session.click(NamedButton("BATTLE_STATUS_S"))

        self.assertEqual(receipt, expected)
        session.refresh_frame.assert_called_once_with()
        oracle.click_daily_battle_result.assert_called_once_with()
        session._arm_combat_result_transition.assert_called_once_with(adapter)
        self.assertIsNone(session._combat_result_observation)
        adapter.end_campaign_pre_sortie()

    def test_campaign_input_transition_extends_stale_presence_grace(self):
        adapter, oracle, _ = self.make_adapter()

        def stale(_semantic_id):
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = stale
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        adapter._observer_stale_since = time.monotonic() - 6

        self.assertFalse(adapter.appear(NamedButton("BATTLE_PREPARATION")))

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaisesRegex(SemanticGateClosed, "observer snapshot is stale"):
            adapter.appear(NamedButton("BATTLE_PREPARATION"))
        adapter.end_campaign_pre_sortie()
