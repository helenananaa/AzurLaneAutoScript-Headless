"""Campaign preparation regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    SemanticGateClosed,
    SemanticOracle,
    SemanticTargetMissing,
)
from dataclasses import replace
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_completed_inherited_run_resets_observations_without_refilling_grants(self):
        oracle = FakeOracle()
        oracle.campaign_page_value = True
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        previous = adapter._campaign_context
        previous.auto_search_completion = SimpleNamespace(result_exit_receipt=object())
        adapter.prepare_campaign_run()
        self.assertIsNot(adapter._campaign_context, previous)
        self.assertIsNone(adapter._campaign_context.auto_search_completion)
        self.assertEqual(adapter._action_ledger.remaining("campaign.sortie"), 0)

    def test_manual_repeat_uses_the_completion_alas_already_observed(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None, campaign_sortie_budget=2)
        adapter.begin_campaign_pre_sortie("12-4")
        context = adapter._campaign_context
        context.sortie_receipt = adapter._dispatch_mutation(
            "campaign.sortie", lambda: oracle.click_receipt("campaign/fleet-preparation/sortie"))
        context.combat_receipt = oracle.click_receipt("campaign/grid")
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.operation_siren_battle_result_visible = Mock(return_value=False)
        oracle.campaign_page_value = True
        with self.assertRaisesRegex(SemanticGateClosed, "completion"):
            adapter.prepare_campaign_run()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.open = lambda: adapter
        self.assertTrue(session.campaign_boss_returned_to_stage())
        self.assertTrue(context.manual_completion_proven)
        adapter.prepare_campaign_run()
        self.assertFalse(adapter._campaign_context.manual_completion_proven)
        self.assertIsNone(adapter._campaign_context.sortie_receipt)
        self.assertEqual(adapter._action_ledger.remaining("campaign.sortie"), 1)

    def test_book_toggle_blocks_unchanged_state_but_allows_inverse_setting(self):
        oracle = FakeOracle()
        oracle.enabled_values["reward/campaign-total/exit"] = True
        oracle.click_campaign_2x_book = Mock(
            side_effect=lambda *args, **kwargs: oracle.click_receipt("campaign/2x-book-auto"))
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("3-1")
        adapter.click(NamedButton("BOOK_BOX_AUTO"))
        with self.assertRaisesRegex(SemanticGateClosed, "did not advance"):
            adapter.click(NamedButton("BOOK_BOX_AUTO"))
        oracle.campaign_2x_book_value = True
        adapter.click(NamedButton("BOOK_BOX_AUTO"))
        self.assertEqual(oracle.click_campaign_2x_book.call_count, 2)
        oracle.campaign_2x_book_value = False
        self.assertFalse(adapter.campaign_2x_book_selected())
        self.assertIsNone(adapter._campaign_context.book_toggle_from)

    def test_optional_preparation_popups_share_the_alas_frame(self):
        live = FakeOracle()
        live.campaign_dock_full_visible = Mock(side_effect=AssertionError("unexpected live observation"))
        live.campaign_2x_book_cancelled = Mock(side_effect=AssertionError("unexpected live observation"))
        live.campaign_2x_book_prompt_visible = Mock(side_effect=AssertionError("unexpected live observation"))
        frame = SimpleNamespace(
            campaign_dock_full_visible=Mock(return_value=False),
            campaign_2x_book_cancelled=Mock(return_value=False),
            campaign_2x_book_prompt_visible=Mock(return_value=False),
        )
        adapter = AlasSemanticAdapter(live, lambda: None, frame_observation_oracle=lambda: frame)
        adapter.begin_campaign_pre_sortie("7-2")
        self.assertFalse(adapter.campaign_dock_full_visible())
        self.assertFalse(adapter.handle_campaign_2x_book_popup())
        frame.campaign_dock_full_visible.assert_called_once_with("7-2")
        frame.campaign_2x_book_prompt_visible.assert_called_once_with()
        self.assertEqual(live.click_calls, [])

    def test_repeated_normal_sortie_reacquires_preparation_without_refilling_budget(self):
        for stage in ("7-2", "12-4"):
            oracle = FakeOracle()
            oracle.campaign_fleets.update(fleet1=2, fleet2=1, submarine=0)
            adapter = AlasSemanticAdapter(oracle, lambda: None,
                campaign_stage_entry_budget=2, campaign_sortie_budget=2,
                campaign_fleet_mutation_budget=6)
            adapter.begin_campaign_pre_sortie(stage)
            for remaining in (1, 0):
                adapter.prepare_campaign_run()
                self.assertIsNone(adapter._campaign_context.prepared_fleet_state)
                entrance = NamedButton(stage)
                entrance.semantic_campaign_stage_code = stage
                adapter.click(entrance)
                # The spent entrance stays non-actionable even if Unity has
                # not mounted preparation in the current screenshot yet.
                self.assertFalse(adapter.appear(entrance))
                adapter.click(NamedButton("MAP_PREPARATION"))
                adapter.authorize_campaign_fleet_preparation(2, 1, 0)
                adapter.confirm_campaign_fleet_selection()
                roles = adapter.ensure_campaign_auto_search_roles("fleet1_boss_fleet2_mob")
                self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("boss", "mob"))
                self.assertTrue(adapter.authorize_campaign_sortie(
                    use_auto_search=True, use_2x_book=False,
                    submarine_mode="do_not_use", fleet_order="fleet1_boss_fleet2_mob"))
                adapter.click(NamedButton("FLEET_PREPARATION"))
                adapter.confirm_campaign_auto_search_started()
                self.assertEqual(adapter._action_ledger.remaining("campaign.sortie"), remaining)
                with self.assertRaisesRegex(SemanticGateClosed, "completion"):
                    adapter.prepare_campaign_run()
                # Completion is supplied here; its live/parser validation is
                # independently covered by the original completion test below.
                adapter._campaign_context.auto_search_completion = SimpleNamespace(result_exit_receipt=object())
                oracle.campaign_page_value = True
                oracle.campaign_preparation_kind_value = None
            adapter.prepare_campaign_run()
            with self.assertRaisesRegex(SemanticGateClosed, "budget"):
                adapter.click(entrance)

    def test_campaign_check_short_circuits_restored_chapter_before_preparation(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        oracle.campaign_page_value = True
        oracle.campaign_preparation_error = AssertionError(
            "restored chapter must not probe campaign preparation"
        )

        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))

        adapter.end_campaign_pre_sortie()

    def test_campaign_stage_entry_accepts_exact_preparation_transition(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            adapter.click(button)

            def identity_failure(_stage_code):
                raise SemanticGateClosed("campaign page identity is not proven")

            oracle.campaign_stage_actionable = identity_failure
            self.assertFalse(adapter.appear(button))

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=31.0):
            self.assertFalse(adapter.appear(button))
            oracle.campaign_preparation_value = None
            self.assertFalse(adapter.appear(button))
            with self.assertRaisesRegex(SemanticGateClosed, "budget"):
                adapter.click(button)
            adapter.end_campaign_pre_sortie()
            adapter.begin_campaign_pre_sortie("12-4")
            with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
                adapter.appear(button)

        adapter.end_campaign_pre_sortie()

    def test_campaign_event_identity_is_shadowed_by_owned_preparation_overlay(self):
        for kind in ("map", "fleet"):
            with self.subTest(kind=kind):
                adapter, oracle, _ = self.make_owned_campaign_preparation(
                    "SP", fleet=kind == "fleet"
                )
                oracle.event_campaign_page_visible_value = True
                oracle.event_campaign_page_error = SemanticGateClosed(
                    "event campaign page back is not available"
                )
                context = adapter._campaign_context
                actions_before = tuple(oracle.click_calls)
                mutation_receipts_before = tuple(context.fleet_mutation_receipts)
                context_before = dict(vars(context))
                mutation_budget_before = adapter._action_ledger.remaining(
                    "campaign.fleet_mutation"
                )

                self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))

                self.assertEqual(tuple(oracle.click_calls), actions_before)
                self.assertEqual(vars(context), context_before)
                self.assertEqual(
                    tuple(context.fleet_mutation_receipts),
                    mutation_receipts_before,
                )
                self.assertEqual(
                    adapter._action_ledger.remaining(
                        "campaign.fleet_mutation"
                    ),
                    mutation_budget_before,
                )
                self.assertIsNone(context.cancel_receipt)
                self.assertNotIn("campaign-menu/page/back", oracle.click_calls)
                if kind == "map":
                    self.assertTrue(
                        adapter.appear(NamedButton("MAP_PREPARATION"))
                    )
                else:
                    self.assertTrue(
                        adapter.appear(NamedButton("FLEET_PREPARATION"))
                    )

                receipt = adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
                self.assertEqual(
                    receipt.semantic_id,
                    "campaign/{0}-preparation/cancel".format(kind),
                )
                self.assertEqual(oracle.click_calls[-1], receipt.semantic_id)
                self.assertNotIn("campaign-menu/page/back", oracle.click_calls)

                oracle.event_campaign_page_error = None
                self.assertTrue(adapter.appear(NamedButton("EVENT_CHECK")))
                adapter.end_campaign_pre_sortie()

    def test_campaign_event_preparation_shadow_preserves_strict_failures(self):
        for message in (
            "observer snapshot is stale",
            "observer endpoints are not generation-coherent",
            "campaign fleet-preparation snapshots are not coherent",
            "campaign fleet-preparation cancel is absent or ambiguous",
            "campaign fleet-preparation sortie is not proven",
            "campaign fleet-preparation stage identity changed",
            "campaign fleet-preparation root is remounted",
        ):
            with self.subTest(message=message):
                adapter, oracle, _ = self.make_owned_campaign_preparation(
                    "SP", fleet=True
                )
                oracle.campaign_preparation_error = SemanticGateClosed(message)
                actions_before = tuple(oracle.click_calls)

                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.appear(NamedButton("EVENT_CHECK"))

                self.assertEqual(tuple(oracle.click_calls), actions_before)
                self.assertEqual(
                    adapter._campaign_context.fleet_mutation_receipts, []
                )
                adapter.end_campaign_pre_sortie()

    def test_campaign_event_preparation_shadow_rejects_wrong_or_partial_overlay(self):
        for preparation, message in (
            (SimpleNamespace(kind="raid"), "overlay kind is invalid"),
            (SimpleNamespace(), "overlay kind is invalid"),
        ):
            with self.subTest(message=message):
                adapter, oracle, _ = self.make_adapter()
                adapter.begin_campaign_pre_sortie("SP")
                oracle.campaign_preparation_value = preparation
                oracle.event_campaign_page_error = SemanticGateClosed(
                    "event campaign page back is not available"
                )

                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.appear(NamedButton("EVENT_CHECK"))

                self.assertEqual(oracle.click_calls, [])
                self.assertEqual(
                    adapter._campaign_context.fleet_mutation_receipts, []
                )
                adapter.end_campaign_pre_sortie()

    def test_campaign_event_preparation_shadow_preserves_inherited_map_cancel(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("SP")
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        oracle.event_campaign_page_error = SemanticGateClosed(
            "event campaign page back is not available"
        )

        self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
        receipt = adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))

        self.assertEqual(
            receipt.semantic_id, "campaign/map-preparation/cancel"
        )
        self.assertEqual(
            oracle.click_calls, ["campaign/map-preparation/cancel"]
        )
        self.assertIsNone(adapter._campaign_context.cancel_receipt)
        adapter.end_campaign_pre_sortie()

    def test_campaign_event_preparation_shadow_requires_active_owned_context(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
        oracle.event_campaign_page_error = SemanticGateClosed(
            "event campaign page back is not available"
        )

        with self.assertRaisesRegex(SemanticGateClosed, "back is not available"):
            adapter.appear(NamedButton("EVENT_CHECK"))

        self.assertEqual(oracle.click_calls, [])

    def test_campaign_auto_search_resources_feed_original_alas_switch(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = True
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)

        for name in (
            "AUTO_SEARCH_ON",
            "AUTO_SEARCH_ON2",
            "AUTO_SEARCH_ON3",
            "AUTO_SEARCH_ON4",
        ):
            self.assertTrue(adapter.appear(NamedButton(name)))
        for name in (
            "AUTO_SEARCH_OFF",
            "AUTO_SEARCH_OFF2",
            "AUTO_SEARCH_OFF3",
            "AUTO_SEARCH_OFF4",
        ):
            self.assertFalse(adapter.appear(NamedButton(name)))

        receipt = adapter.click(NamedButton("AUTO_SEARCH_ON"))
        self.assertEqual(
            receipt.semantic_id, "campaign/map-preparation/auto-search"
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = False
        self.assertTrue(adapter.appear(NamedButton("AUTO_SEARCH_OFF")))
        with self.assertRaisesRegex(SemanticGateClosed, "single-use"):
            adapter.click(NamedButton("AUTO_SEARCH_OFF"))

        self.assertEqual(
            oracle.click_calls,
            ["campaign/stage/12-4", "campaign/map-preparation/auto-search"],
        )

    def test_campaign_auto_search_state_has_single_typed_fast_path(self):
        oracle = FakeOracle()
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(
                SimpleNamespace(
                    stage_code="12-4",
                    button=SimpleNamespace(actionable=True),
                ),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = False
        adapter.begin_campaign_pre_sortie("12-4")
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.click(entrance)

        self.assertFalse(adapter.campaign_auto_search_selected())
        adapter.end_campaign_pre_sortie()

    def test_campaign_pre_sortie_reuses_prepare_and_cancel_states(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_map_preparation_committed())
        adapter.click(entrance)
        self.assertFalse(adapter.campaign_map_preparation_committed())
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation snapshots are not coherent"
        )
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.campaign_preparation_error = None
        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION")))
        with patch.object(
            adapter, "_campaign_preparation_kind", return_value=None
        ):
            adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.campaign_map_preparation_committed())
        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaisesRegex(
            SemanticGateClosed,
            "map-preparation transition did not reach the fleet overlay",
        ):
            adapter.campaign_map_preparation_committed()
        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation controls are not proven"
        )
        self.assertFalse(adapter.appear(NamedButton("MAP_PREPARATION")))
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map preparation is transitioning away"
        )
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))
        oracle.campaign_preparation_error = None
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
        self.assertTrue(adapter.appear(NamedButton("FLEET_PREPARATION")))
        with self.assertRaisesRegex(SemanticGateClosed, "authorized budget"):
            adapter.click(NamedButton("FLEET_PREPARATION"))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign fleet preparation is transitioning away"
        )
        self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("IN_MAP")))
        oracle.campaign_preparation_error = None
        oracle.campaign_page_value = True
        self.assertTrue(adapter.appear(NamedButton("CAMPAIGN_CHECK")))
        proof = adapter.confirm_campaign_pre_sortie()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "12-4")
        self.assertEqual(proof.preparation_kind, "fleet")
        self.assertEqual(proof.entry_generation, 7)
        self.assertEqual(proof.cancel_generation, 9)
        self.assertEqual(proof.restored_generation, 12)
        self.assertEqual(
            oracle.click_calls,
            [
                "campaign/stage/12-4",
                "campaign/map-preparation/proceed",
                "campaign/fleet-preparation/cancel",
            ],
        )

    def test_campaign_stale_map_preparation_can_be_closed_before_fresh_entry(self):
        oracle = FakeOracle()
        oracle.campaign_preparation_value = SimpleNamespace(kind="map")
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION_CANCEL")))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))

        # Closing an inherited overlay must not consume the normal flow's
        # single cancel proof.  A fresh entry can still complete the original
        # ALAS preparation/cancel sequence in this same task run.
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))

        self.assertEqual(
            oracle.click_calls,
            [
                "campaign/map-preparation/cancel",
                "campaign/stage/12-4",
                "campaign/map-preparation/proceed",
                "campaign/fleet-preparation/cancel",
            ],
        )

    def test_campaign_auto_search_roles_accept_exact_zero_grant_noop(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        oracle.campaign_role_tab_selected = True
        oracle.campaign_roles = ["mob", "boss"]
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
        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))
        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.fleet_mutation"), 0
        )
        adapter.end_campaign_pre_sortie()

    def test_daemon_sortie_reuses_exact_owned_campaign_state_without_mutation(self):
        adapter, oracle, _ = self.make_adapter(
            campaign_stage_entry_budget=1,
            campaign_sortie_budget=1,
        )
        oracle.campaign_fleets["submarine"] = 0
        oracle.campaign_role_tab_selected = True
        oracle.campaign_roles = ["mob", "boss"]
        oracle.toggle_selected_values[
            "campaign/map-preparation/auto-search"
        ] = True
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="chapter 12",
            stages=(
                SimpleNamespace(
                    stage_code="12-4",
                    button=SimpleNamespace(actionable=True),
                ),
            ),
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        self.assertTrue(adapter.arm_daemon_campaign_map_preparation())
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(
            adapter.authorize_daemon_campaign_sortie(
                fleet1=1,
                fleet2=2,
                submarine=0,
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )

        context = adapter._campaign_context
        self.assertEqual(context.requested_fleets, (1, 2, 0))
        self.assertIs(context.initial_fleet_state, context.prepared_fleet_state)
        self.assertEqual(context.required_fleet_mutations, 0)
        self.assertEqual(
            (context.auto_search_role_state.fleet1_role,
             context.auto_search_role_state.fleet2_role),
            ("mob", "boss"),
        )
        self.assertEqual(
            oracle.click_calls,
            ["campaign/stage/12-4", "campaign/map-preparation/proceed"],
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_auto_search_roles_reject_nonexact_zero_grant_without_input(self):
        for tab_selected, roles, message in (
            (False, ("mob", "boss"), "selected duty tab"),
            (True, ("boss", "mob"), "exact no-op proof"),
        ):
            with self.subTest(tab_selected=tab_selected, roles=roles):
                oracle = FakeOracle()
                oracle.campaign_fleets["submarine"] = 0
                oracle.campaign_role_tab_selected = tab_selected
                oracle.campaign_roles = list(roles)
                adapter = AlasSemanticAdapter(
                    oracle,
                    lambda: None,
                    campaign_fleet_mutation_budget=0,
                )
                oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
                adapter.begin_campaign_pre_sortie("SP")
                self.seed_owned_campaign_fleet_overlay(adapter)
                adapter.authorize_campaign_fleet_preparation(1, 2, 0)
                adapter.confirm_campaign_fleet_selection()

                with self.assertRaisesRegex(SemanticGateClosed, message):
                    adapter.ensure_campaign_auto_search_roles(
                        "fleet1_mob_fleet2_boss"
                    )

                self.assertEqual(oracle.click_calls, [])
                adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_reuses_exact_alas_click_and_proves_map_root(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=2,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        receipt = adapter.click(NamedButton("FLEET_PREPARATION"))
        self.assertEqual(receipt.semantic_id, "campaign/fleet-preparation/sortie")
        self.assertTrue(adapter.campaign_sortie_committed())
        self.assertTrue(adapter.appear(NamedButton("IN_MAP")))
        proof = adapter.confirm_campaign_sortie()
        self.assertEqual(adapter._action_ledger.remaining("campaign.sortie"), 1)
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "12-4")
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertEqual(proof.oil_before_sortie, 9504)
        self.assertEqual(proof.required_oil, 97)
        self.assertGreater(proof.map_generation, proof.sortie_generation)
        self.assertEqual(
            proof.map_root_path, "LevelCamera/Canvas/UIMain/LevelGrid"
        )
        self.assertEqual(oracle.click_calls[-1], "campaign/fleet-preparation/sortie")

    def test_campaign_auto_search_proves_roles_and_passive_start(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
            input_frame_refresher=refresh,
        )
        adapter.bind_next_campaign_evidence_owner("Main")
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )
        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))

        self.assertTrue(adapter.campaign_auto_search_running())
        proof = adapter.confirm_campaign_auto_search_started()
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertIn("CombatUIStandard", proof.map_root_path)
        self.assertEqual(
            oracle.click_calls[-1], "campaign/fleet-preparation/sortie"
        )

        oracle.enabled_values["reward/campaign-total/exit"] = True
        oracle.campaign_page_value = True
        oracle.campaign_official_combat_auto_state = Mock(
            return_value=(81, True)
        )
        oracle.read_state = Mock(
            return_value=SimpleNamespace(
                generation=82,
                buttons=(
                    SimpleNamespace(
                        name="ButtonExit",
                        path=(
                            "LevelStageTotalRewardPanel(Clone)/Window/Fixed/"
                            "ButtonExit"
                        ),
                        actionable=True,
                    ),
                ),
            )
        )
        refresh_before_result = refresh.call_count

        completion = adapter.wait_campaign_auto_search_completion(
            "12-4", timeout_seconds=60
        )

        self.assertEqual(completion.result_generation, 82)
        self.assertEqual(completion.combat_auto_generation, 81)
        self.assertEqual(
            completion.result_exit_receipt.semantic_id,
            "reward/campaign-total/exit",
        )
        self.assertEqual(
            completion.result_exit_receipt.path,
            completion.result_path,
        )
        self.assertEqual(
            oracle.click_calls[-1], "reward/campaign-total/exit"
        )
        self.assertEqual(refresh.call_count, refresh_before_result + 1)
        adapter.end_campaign_pre_sortie()
        bundle = adapter.consume_campaign_auto_search_evidence(
            expected_owner="Main",
            expected_stage_code="12-4",
            expected_mode="normal",
        )
        self.assertEqual(bundle.integrity_errors, ())
        self.assertIs(bundle.sortie_proof, proof)
        self.assertIs(bundle.completion_proof, completion)
        self.assertIsNone(
            adapter.consume_campaign_auto_search_evidence(
                expected_owner="Main",
                expected_stage_code="12-4",
                expected_mode="normal",
            )
        )
        stale_receipt = replace(
            completion.result_exit_receipt,
            generation=completion.result_generation - 1,
        )
        stale_completion = replace(
            completion,
            result_exit_receipt=stale_receipt,
        )
        adapter._campaign_evidence_bundle = replace(
            bundle,
            transaction_id=bundle.transaction_id + 1,
            completion_proof=stale_completion,
        )
        stale = adapter.consume_campaign_auto_search_evidence(
            expected_owner="Main",
            expected_stage_code="12-4",
            expected_mode="normal",
        )
        self.assertIn(
            "campaign_evidence.exit_receipt_stale",
            stale.integrity_errors,
        )
        bool_completion = replace(completion, combat_auto_generation=True)
        adapter._campaign_evidence_bundle = replace(
            bundle,
            transaction_id=bundle.transaction_id + 2,
            completion_proof=bool_completion,
        )
        malformed = adapter.consume_campaign_auto_search_evidence(
            expected_owner="Main",
            expected_stage_code="12-4",
            expected_mode="normal",
        )
        self.assertIn(
            "campaign_evidence.completion_generation_malformed",
            malformed.integrity_errors,
        )
        adapter._campaign_evidence_bundle = replace(
            bundle,
            transaction_id=bundle.transaction_id + 3,
        )
        valid_again = adapter.consume_campaign_auto_search_evidence(
            expected_owner="Main",
            expected_stage_code="12-4",
            expected_mode="normal",
        )
        self.assertEqual(valid_again.integrity_errors, ())

    def test_campaign_auto_search_retained_preparation_only_refreshes_frame(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
            input_frame_refresher=refresh,
        )
        entrance = NamedButton("sp")
        entrance.semantic_campaign_stage_code = "sp"
        adapter.begin_campaign_pre_sortie("SP")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()
        adapter.ensure_campaign_auto_search_roles("fleet1_mob_fleet2_boss")
        adapter.authorize_campaign_sortie(
            use_auto_search=True,
            use_2x_book=False,
            submarine_mode="do_not_use",
            fleet_order="fleet1_mob_fleet2_boss",
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))
        clicks_after_sortie = tuple(oracle.click_calls)
        refreshes_after_sortie = refresh.call_count
        retained_generation = adapter._campaign_context.sortie_receipt.generation + 1
        oracle.campaign_preparation_value = SimpleNamespace(
            kind="fleet",
            stage_code="sp",
            generation=retained_generation,
        )
        active_ui = SimpleNamespace(
            generation=retained_generation,
            texts=(),
            images=(),
        )
        real_oracle = object.__new__(SemanticOracle)
        real_oracle.read_ui_state = Mock(side_effect=lambda: active_ui)
        oracle.campaign_auto_search_active_state = lambda: (
            SemanticOracle.campaign_auto_search_active_state(real_oracle)
        )

        self.assertFalse(adapter.campaign_auto_search_running())
        self.assertFalse(adapter.campaign_auto_search_running())

        self.assertEqual(tuple(oracle.click_calls), clicks_after_sortie)
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 2)

        active_ui.texts = (
            SimpleNamespace(
                path=(
                    "root/UICamera/Canvas/UIMain/CombatUIStandard(Clone)/"
                    "AutoBtn/Text"
                ),
                active_in_hierarchy=True,
                active_and_enabled=True,
            ),
            SimpleNamespace(
                path=(
                    "root/UICamera/Canvas/UIMain/NewBattleResultEmptyUI(Clone)/"
                    "Main/Text"
                ),
                active_in_hierarchy=True,
                active_and_enabled=True,
            ),
        )
        with self.assertRaisesRegex(
            SemanticGateClosed, "official auto-search surface is ambiguous"
        ):
            adapter.campaign_auto_search_running()
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 2)

        active_ui.texts = ()
        oracle.campaign_preparation_error = SemanticGateClosed(
            "observer state is stale"
        )
        with self.assertRaisesRegex(SemanticGateClosed, "stale"):
            adapter.campaign_auto_search_running()
        oracle.campaign_preparation_error = None
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 2)

        oracle.campaign_preparation_value.stage_code = "a1"
        with self.assertRaisesRegex(
            SemanticTargetMissing, "official auto-search surface is absent"
        ):
            adapter.campaign_auto_search_running()
        oracle.campaign_preparation_value.stage_code = "sp"
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 2)

        sortie_receipt = adapter._campaign_context.sortie_receipt
        adapter._campaign_context.sortie_receipt = replace(
            sortie_receipt, generation=True
        )
        with self.assertRaisesRegex(
            SemanticTargetMissing, "official auto-search surface is absent"
        ):
            adapter.campaign_auto_search_running()
        adapter._campaign_context.sortie_receipt = sortie_receipt
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 2)

        oracle.campaign_preparation_value.generation = retained_generation + 1
        self.assertFalse(adapter.campaign_auto_search_running())
        oracle.campaign_preparation_value.generation = retained_generation
        with self.assertRaisesRegex(SemanticGateClosed, "moved backwards"):
            adapter.campaign_auto_search_running()
        oracle.campaign_preparation_value.generation = retained_generation + 1
        for _ in range(6):
            self.assertFalse(adapter.campaign_auto_search_running())
        with self.assertRaisesRegex(SemanticGateClosed, "did not advance"):
            adapter.campaign_auto_search_running()
        self.assertEqual(tuple(oracle.click_calls), clicks_after_sortie)
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 9)

    def test_campaign_auto_search_empty_post_sortie_load_has_bounded_grace(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
            input_frame_refresher=refresh,
        )
        entrance = NamedButton("sp")
        entrance.semantic_campaign_stage_code = "sp"
        adapter.begin_campaign_pre_sortie("SP")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()
        adapter.ensure_campaign_auto_search_roles("fleet1_mob_fleet2_boss")
        adapter.authorize_campaign_sortie(
            use_auto_search=True,
            use_2x_book=False,
            submarine_mode="do_not_use",
            fleet_order="fleet1_mob_fleet2_boss",
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))
        clicks_after_sortie = tuple(oracle.click_calls)
        refreshes_after_sortie = refresh.call_count
        oracle.campaign_preparation_value = None
        oracle.campaign_auto_search_active_state = Mock(
            side_effect=SemanticTargetMissing(
                "campaign official auto-search surface is absent"
            )
        )

        adapter._campaign_context.passive_transition_until = time.monotonic() + 1.0
        self.assertFalse(adapter.campaign_auto_search_running())
        self.assertEqual(tuple(oracle.click_calls), clicks_after_sortie)
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 1)

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1.0
        with self.assertRaisesRegex(
            SemanticTargetMissing, "official auto-search surface is absent"
        ):
            adapter.campaign_auto_search_running()
        self.assertEqual(tuple(oracle.click_calls), clicks_after_sortie)
        self.assertEqual(refresh.call_count, refreshes_after_sortie + 1)

    def test_campaign_auto_search_rejects_nonunique_total_result_target(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("sp")
        entrance.semantic_campaign_stage_code = "sp"
        adapter.begin_campaign_pre_sortie("SP")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()
        adapter.ensure_campaign_auto_search_roles("fleet1_mob_fleet2_boss")
        adapter.authorize_campaign_sortie(
            use_auto_search=True,
            use_2x_book=False,
            submarine_mode="do_not_use",
            fleet_order="fleet1_mob_fleet2_boss",
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))
        start = adapter.confirm_campaign_auto_search_started()
        result_path = (
            "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"
        )
        target = SimpleNamespace(
            name="ButtonExit",
            path=result_path,
            actionable=True,
        )
        oracle.enabled_values["reward/campaign-total/exit"] = True
        oracle.campaign_official_combat_auto_state = Mock(
            return_value=(start.map_generation + 1, True)
        )
        oracle.read_state = Mock(
            return_value=SimpleNamespace(
                generation=start.map_generation + 2,
                buttons=(target, target),
            )
        )

        with self.assertRaisesRegex(SemanticGateClosed, "result target is ambiguous"):
            adapter.wait_campaign_auto_search_completion(
                "sp", timeout_seconds=60
            )
        self.assertNotEqual(
            oracle.click_calls[-1], "reward/campaign-total/exit"
        )

    def test_campaign_auto_search_accepts_reversed_mob_boss_roles(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_boss_fleet2_mob"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("boss", "mob"))
        self.assertEqual(
            oracle.click_calls[-2:],
            [
                "campaign/fleet-preparation/roles/fleet1/boss",
                "campaign/fleet-preparation/roles/fleet2/mob",
            ],
        )

    def test_event_campaign_auto_search_uses_same_typed_role_contract(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("a1")
        entrance.semantic_campaign_stage_code = "a1"
        adapter.begin_campaign_pre_sortie("A1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )

    def test_event_hard_shared_entrance_does_not_hide_map_preparation(self):
        oracle = FakeOracle()
        oracle.event_campaign_page_visible_value = True
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
        adapter.click(entrance)

        def preparation_state(stage_code):
            if stage_code == "c1":
                raise SemanticGateClosed("campaign preparation stage identity changed")
            self.assertEqual(stage_code, "a1")
            return SimpleNamespace(kind="map")

        oracle.campaign_preparation_state = Mock(side_effect=preparation_state)

        self.assertTrue(adapter.appear(NamedButton("MAP_PREPARATION")))

    def test_inherited_event_auto_search_closes_exact_total_reward(self):
        oracle = FakeOracle()
        oracle.exists_values["reward/campaign-total/exit"] = True
        oracle.enabled_values["reward/campaign-total/exit"] = True
        oracle.campaign_page_value = True
        oracle.campaign_in_map_value = True
        oracle.campaign_official_combat_auto_state = Mock(
            return_value=(19, True)
        )
        refresh = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            input_frame_refresher=refresh,
        )
        adapter.begin_campaign_pre_sortie("A1")

        self.assertTrue(adapter.campaign_inherited_auto_search_visible())
        proof = adapter.recover_inherited_campaign_auto_search(
            "a1",
            "fleet1_mob_fleet2_boss",
            timeout_seconds=60,
        )

        self.assertEqual(proof.stage_code, "a1")
        self.assertEqual((proof.fleet1_role, proof.fleet2_role), ("mob", "boss"))
        self.assertEqual(oracle.click_calls[-1], "reward/campaign-total/exit")
        refresh.assert_called_once_with()

    def test_campaign_sortie_preconditions_fail_before_input(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "auto search"):
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()
