"""Event regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    Bounds,
    Point,
    SemanticGateClosed,
    SemanticTargetMissing,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_event_story_input_owns_only_a_bounded_passive_transition(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_story_dialogue_visible_value = True

        receipt = adapter.click_event_story_option(0)
        oracle.event_story_dialogue_visible_value = False

        self.assertEqual(receipt.semantic_id, "story/option/0")
        self.assertEqual(oracle.click_calls, ["story/option/0"])
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("UNREVIEWED_PAGE_CHECK")))

        adapter._event_story_transition_until = time.monotonic() - 1.0
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("UNREVIEWED_PAGE_CHECK"))

    def test_generic_page_scan_recovers_month_sign_through_event_list_page(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])

    def test_orphan_event_result_accepts_reviewed_event_page_return(self):
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
        oracle.event_campaign_page_visible_value = True
        oracle.operation_siren_page_visible = Mock(return_value=False)
        oracle.daily_page_visible = Mock(return_value=False)
        oracle.main_page_visible = Mock(return_value=False)

        self.assertEqual(session.recover_orphan_combat_result(), ())

    def test_campaign_event_list_back_uses_exact_typed_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("BACK_ARROW")))
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])

    def test_war_archives_campaign_back_uses_main_scene_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.war_archives_campaign_visible_value = True
        oracle.enabled_values["campaign-menu/page/back"] = True

        adapter.begin_campaign_pre_sortie("A1")
        self.assertTrue(adapter.appear(NamedButton("BACK_ARROW")))
        receipt = adapter.click(NamedButton("BACK_ARROW"))
        adapter.end_campaign_pre_sortie()

        self.assertEqual(receipt.semantic_id, "campaign-menu/page/back")

    def test_campaign_event_identity_is_hidden_after_back_commit(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        receipt = adapter.click(NamedButton("BACK_ARROW"))

        self.assertIs(adapter._campaign_context.event_page_back_receipt, receipt)
        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])
        adapter.end_campaign_pre_sortie()

    def test_campaign_event_identity_uses_complete_selector_not_event_list_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True
        oracle.enabled_values["event-list/page/back"] = False
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")

        self.assertTrue(adapter.appear(NamedButton("EVENT_CHECK")))
        self.assertNotIn("event-list/page/back", oracle.enabled_calls)

        oracle.event_campaign_page_error = SemanticTargetMissing(
            "event campaign page is absent"
        )
        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))

        oracle.event_campaign_page_error = SemanticGateClosed(
            "event campaign snapshots are not coherent"
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not coherent"):
            adapter.appear(NamedButton("EVENT_CHECK"))
        adapter.end_campaign_pre_sortie()

    def test_event_check_is_observation_only_and_cannot_dispatch_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")

        self.assertTrue(adapter.appear(NamedButton("EVENT_CHECK")))
        with self.assertRaisesRegex(AlasSemanticUnmapped, "EVENT_CHECK"):
            adapter.click(NamedButton("EVENT_CHECK"))

        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_event_identity_without_overlay_uses_existing_page_contract(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("SP")
        oracle.campaign_preparation_value = None
        oracle.event_campaign_page_error = SemanticTargetMissing(
            "event campaign page is absent"
        )
        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))

        oracle.event_campaign_page_error = SemanticGateClosed(
            "event campaign page root is ambiguous"
        )
        with self.assertRaisesRegex(SemanticGateClosed, "root is ambiguous"):
            adapter.appear(NamedButton("EVENT_CHECK"))

        oracle.event_campaign_page_error = None
        oracle.event_campaign_page_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("EVENT_CHECK")))
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_event_identity_propagates_duplicate_canonical_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True
        oracle.event_campaign_page_error = SemanticGateClosed(
            "event campaign page back identity is absent or ambiguous"
        )
        adapter.begin_campaign_pre_sortie("A1")

        with self.assertRaisesRegex(SemanticGateClosed, "back identity"):
            adapter.appear(NamedButton("EVENT_CHECK"))

        adapter.end_campaign_pre_sortie()

    def test_campaign_event_identity_propagates_remounted_back_ambiguity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True
        oracle.event_campaign_page_error = SemanticGateClosed(
            "event campaign page back identity is absent or ambiguous"
        )
        adapter.begin_campaign_pre_sortie("SP")

        with self.assertRaisesRegex(SemanticGateClosed, "back identity"):
            adapter.appear(NamedButton("EVENT_CHECK"))

        adapter.end_campaign_pre_sortie()

    def test_campaign_event_identity_is_shared_without_inferring_task_stage(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.event_campaign_page_visible_value = True

        for task, stage in (
            ("Event", "A1"),
            ("Event2", "B1"),
            ("EventA", "A2"),
            ("EventB", "B2"),
            ("EventC", "C1"),
            ("EventD", "D1"),
            ("EventSp", "SP"),
        ):
            with self.subTest(task=task):
                adapter.begin_campaign_pre_sortie(stage)
                self.assertTrue(adapter.appear(NamedButton("EVENT_CHECK")))
                self.assertEqual(adapter.campaign_pre_sortie_stage_code(), stage.lower())
                adapter.end_campaign_pre_sortie()

        self.assertEqual(oracle.click_calls, [])

    def test_event_list_and_normal_campaign_identities_remain_independent(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True

        adapter.begin_campaign_pre_sortie("A1")
        self.assertTrue(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        adapter.end_campaign_pre_sortie()

        oracle.exists_values["event-list/page/back"] = False
        oracle.enabled_values["event-list/page/back"] = False
        oracle.campaign_page_value = True
        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        adapter.end_campaign_pre_sortie()

    def test_event_sp_hard_surface_accepts_exact_game_managed_zero_grant_noop(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=0,
            campaign_sortie_budget=1,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("SP")
        self.seed_owned_campaign_fleet_overlay(adapter)
        adapter._campaign_context.oil_before_sortie = oracle.campaign_oil_value
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.confirm_campaign_fleet_selection()
        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )

        self.assertEqual(
            (roles.fleet1_role, roles.fleet2_role),
            ("game-managed", "game-managed"),
        )
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.fleet_mutation"), 0
        )
        adapter.end_campaign_pre_sortie()

    def test_event_sp_hard_surface_inspection_does_not_reassign_wrong_roles(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        oracle.campaign_roles = ["boss", "mob"]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=0,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("SP")
        self.seed_owned_campaign_fleet_overlay(adapter)
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "exact no-op proof"):
            adapter.ensure_campaign_auto_search_roles(
                "fleet1_mob_fleet2_boss"
            )

        self.assertEqual(
            oracle.click_calls,
            ["campaign/fleet-preparation/roles/tab"],
        )
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.fleet_mutation"), 0
        )
        adapter.end_campaign_pre_sortie()

    def test_event_hard_stage_uses_reviewed_shared_normal_entrance(self):
        oracle = FakeOracle()
        oracle.campaign_state_value.stages = (
            SimpleNamespace(
                stage_code="a1",
                button=SimpleNamespace(actionable=True),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("c1")
        entrance.semantic_campaign_stage_code = "a1"
        adapter.begin_campaign_pre_sortie("C1")

        self.assertTrue(adapter.appear(entrance))
        receipt = adapter.click(entrance)

        self.assertEqual(receipt.semantic_id, "campaign/stage/a1")
        self.assertEqual(oracle.click_calls[-1], "campaign/stage/a1")

    def test_event_hard_page_prefers_open_target_nodes_over_shared_normal_nodes(self):
        oracle = FakeOracle()
        oracle.campaign_page_value = True
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="a/c",
            stages=(
                SimpleNamespace(stage_code="a2"),
                SimpleNamespace(stage_code="a3"),
                SimpleNamespace(stage_code="c1"),
            ),
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("C1")

        state = adapter.campaign_page_state()

        self.assertEqual(state.chapter_name, "c")
        self.assertEqual([stage.stage_code for stage in state.stages], ["c1"])

    def test_event_hard_page_uses_only_same_index_shared_normal_alias(self):
        for requested, stages, expected_chapter, expected_stage in (
            ("C2", ("a2", "a3", "c1"), "a", "a2"),
            ("C3", ("a2", "a3", "c1"), "a", "a3"),
            ("D2", ("b2", "b3", "d1"), "b", "b2"),
            ("D3", ("b2", "b3", "d1"), "b", "b3"),
        ):
            with self.subTest(requested=requested):
                oracle = FakeOracle()
                oracle.campaign_page_value = True
                oracle.campaign_state_value = SimpleNamespace(
                    generation=12,
                    chapter_name="shared",
                    stages=tuple(
                        SimpleNamespace(stage_code=stage) for stage in stages
                    ),
                )
                adapter = AlasSemanticAdapter(oracle, lambda: None)
                adapter.begin_campaign_pre_sortie(requested)

                state = adapter.campaign_page_state()

                self.assertEqual(state.chapter_name, expected_chapter)
                self.assertEqual(
                    [stage.stage_code for stage in state.stages], [expected_stage]
                )

    def test_event_hard_page_prefers_exact_index_over_shared_alias(self):
        oracle = FakeOracle()
        oracle.campaign_page_value = True
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="a/c",
            stages=(
                SimpleNamespace(stage_code="a2"),
                SimpleNamespace(stage_code="c2"),
            ),
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("C2")

        state = adapter.campaign_page_state()

        self.assertEqual(state.chapter_name, "c")
        self.assertEqual([stage.stage_code for stage in state.stages], ["c2"])

    def test_event_sp_stage_code_is_canonical_without_numeric_suffix(self):
        adapter = AlasSemanticAdapter(FakeOracle(), lambda: None)

        adapter.begin_campaign_pre_sortie("SP")

        self.assertEqual(adapter.campaign_pre_sortie_stage_code(), "sp")

    def test_event_sp_uses_exact_interactable_auto_toggle_as_clear_proof(self):
        oracle = FakeOracle()
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        oracle.campaign_map_clear_percentage = Mock(
            side_effect=SemanticGateClosed(
                "campaign achievement progress is absent or ambiguous"
            )
        )
        oracle.toggle_state = Mock(
            return_value=SimpleNamespace(
                active_in_hierarchy=True,
                active_and_enabled=True,
                interactable=True,
                point=Point(50, 50),
                bounds=Bounds(0, 0, 100, 100),
            )
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("SP")

        self.assertEqual(adapter.campaign_map_clear_percentage(), 1.0)

    def test_event_hard_stage_normalizes_mode_and_clears_selected_submarine(self):
        oracle = FakeOracle()
        fleet_state = Mock(wraps=oracle.campaign_fleet_selection_state)
        oracle.campaign_fleet_selection_state = fleet_state
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 1
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = True
        oracle.campaign_role_tab_selected = True
        oracle.campaign_roles = ["mob", "boss"]
        oracle.campaign_state_value.stages = (
            SimpleNamespace(
                stage_code="a1",
                button=SimpleNamespace(actionable=True),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("c1")
        entrance.semantic_campaign_stage_code = "a1"
        adapter.begin_campaign_pre_sortie("C1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))

        self.assertEqual(adapter._campaign_context.mode, "hard")
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.prepare_campaign_hard_fleets()
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        prepared = adapter.confirm_campaign_fleet_selection()
        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )

        self.assertEqual(
            tuple(row.selected_fleet or 0 for row in prepared.rows),
            (1, 2, 0),
        )
        self.assertEqual(
            tuple(
                receipt.semantic_id
                for receipt in adapter._campaign_context.fleet_mutation_receipts
            ),
            ("campaign/fleet-preparation/submarine/1/clear",),
        )
        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))
        self.assertTrue(fleet_state.call_args_list)
        self.assertTrue(
            all(call.args[0] == "c1" for call in fleet_state.call_args_list)
        )

    def test_campaign_map_model_is_shared_by_reviewed_event_hard_stages(self):
        for stage_code in ("C1", "D3"):
            with self.subTest(stage_code=stage_code):
                oracle = FakeOracle()
                adapter = AlasSemanticAdapter(oracle, lambda: None)
                adapter.begin_campaign_pre_sortie(stage_code)

                state = adapter.campaign_map_state(
                    columns=9,
                    rows=9,
                    land_cells=((3, 0),),
                    expected_fleet_count=2,
                )

                self.assertIs(state, oracle.campaign_map_state_value)
                self.assertEqual(
                    oracle.campaign_map_state_calls,
                    [(stage_code.lower(), 9, 9, ((3, 0),), 2)],
                )
                adapter.end_campaign_pre_sortie()
