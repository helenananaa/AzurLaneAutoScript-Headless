"""Campaign map regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasCampaignDecisionPreview,
    AlasSemanticAdapter,
    AlasSemanticSession,
    Bounds,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapState,
    Point,
    SemanticGateClosed,
)
from dataclasses import replace
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import (
    CampaignGridButton,
    FakeOracle,
    NamedButton,
    make_campaign_combat_decision,
    make_campaign_combat_state,
)
from unittest.mock import Mock


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_repair_panel_after_combat_uses_campaign_observation(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("10-2")
        adapter.campaign_combat_committed = lambda: True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._live_combat_visible = lambda: self.fail(
            "repair panel must not be hidden by the combat resource set")
        for visible in (True, False):
            adapter.campaign_repair_appear = Mock(return_value=visible)
            for name in ("EMERGENCY_REPAIR_AVAILABLE", "EMERGENCY_REPAIR_CONFIRM"):
                self.assertEqual(session.appear(NamedButton(name)), visible)
                adapter.campaign_repair_appear.assert_called_with(name)
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        self.assertFalse(session.appear(NamedButton("EMERGENCY_REPAIR_CONFIRM")))

    def test_repair_confirmation_action_after_combat_uses_owned_campaign_port(self):
        adapter, _, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("10-2")
        adapter.campaign_combat_committed = lambda: True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._live_combat_click = lambda *_: self.fail("repair is not a generic combat action")
        adapter.click = Mock(return_value="owned-repair-receipt")
        for name in ("EMERGENCY_REPAIR_AVAILABLE", "EMERGENCY_REPAIR_CONFIRM"):
            button = NamedButton(name)
            self.assertEqual(session.click(button), "owned-repair-receipt")
            adapter.click.assert_called_with(button)

    def test_campaign_combat_prioritizes_exact_network_reconnect_popup(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        oracle.enabled_values["overlay/network-reconnect/cancel"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._live_combat_visible = lambda: self.fail(
            "covered combat hierarchy must not be classified"
        )

        self.assertFalse(session.appear(NamedButton("BATTLE_PREPARATION")))
        self.assertTrue(session.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(session.appear(NamedButton("POPUP_CONFIRM")))
        receipt = session.click(NamedButton("POPUP_CONFIRM_COMBAT_STATUS"))

        self.assertEqual(
            receipt.semantic_id, "overlay/network-reconnect/confirm"
        )
        self.assertEqual(
            oracle.click_calls, ["overlay/network-reconnect/confirm"]
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_execute_suffix_prioritizes_exact_network_popup(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        oracle.enabled_values["overlay/network-reconnect/cancel"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._live_combat_visible = lambda: self.fail(
            "covered combat hierarchy must not be classified"
        )

        self.assertTrue(session.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(session.appear(NamedButton("POPUP_CONFIRM")))
        receipt = session.click(NamedButton("POPUP_CONFIRM_COMBAT_EXECUTE"))

        self.assertEqual(
            receipt.semantic_id, "overlay/network-reconnect/confirm"
        )
        self.assertEqual(
            oracle.click_calls, ["overlay/network-reconnect/confirm"]
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_session_delegates_restored_chapter_check(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.campaign_combat_committed = lambda: True
        oracle.campaign_page_value = True
        oracle.campaign_preparation_error = AssertionError(
            "restored chapter must not enter combat or preparation probing"
        )
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session._live_combat_visible = lambda: self.fail(
            "restored chapter must not be classified as combat"
        )

        self.assertTrue(session.appear(NamedButton("CAMPAIGN_CHECK")))

        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_session_tolerates_stale_snapshot_only_in_transition(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.campaign_combat_committed = lambda: True
        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None

        def stale():
            raise SemanticGateClosed("observer snapshot is stale")

        session._live_combat_visible = stale

        self.assertFalse(session.appear(NamedButton("BATTLE_PREPARATION")))

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        self.assertFalse(
            session._campaign_combat_transition_error(
                SemanticGateClosed("observer snapshot is stale")
            )
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_map_mount_gap_is_bounded(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.campaign_combat_committed = lambda: True
        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter

        def mounting():
            raise SemanticGateClosed("campaign startup surface is not reviewed")

        oracle.campaign_is_in_map = mounting
        self.assertIsNone(session.campaign_is_in_map_after_combat())

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaisesRegex(SemanticGateClosed, "startup surface"):
            session.campaign_is_in_map_after_combat()
        adapter.end_campaign_pre_sortie()

    def test_campaign_committed_map_departure_counts_as_combat_loading(self):
        adapter, oracle, _ = self.make_adapter()
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        oracle.daily_battle_result_visible = Mock(return_value=False)
        oracle.daily_combat_visible = Mock(return_value=False)
        oracle.campaign_is_in_map = Mock(return_value=False)
        adapter.campaign_combat_committed = Mock(return_value=True)

        self.assertTrue(session.combat_is_loading())

    def test_campaign_ambush_spends_one_campaign_grid_click_lease(self):
        oracle = FakeOracle()
        oracle.campaign_ambush_visible = lambda *, evade: True
        oracle.click_campaign_ambush = lambda *, evade: oracle.click_receipt(
            "campaign/ambush/evade" if evade else "campaign/ambush/fight"
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")

        self.assertTrue(adapter.handle_campaign_ambush(evade=True))
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.grid_click"), 0
        )
        with self.assertRaisesRegex(SemanticGateClosed, "postcondition"):
            adapter.handle_campaign_ambush(evade=False)
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_defaults_closed_after_alas_decision(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        self.assertIsNone(admission)
        self.assertEqual(oracle.click_calls, [])
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.click(CampaignGridButton((3, 5)))
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_binds_alas_grid_click_and_proves_post_state(self):
        oracle = FakeOracle()
        before = make_campaign_combat_state()
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        self.assertIsNotNone(admission)
        receipt = adapter.click(CampaignGridButton((3, 5)))
        self.assertEqual(receipt.semantic_id, "campaign/map/grid/D6")
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(SemanticGateClosed, "proven post-state"):
            adapter.click(CampaignGridButton((3, 5)))

        oracle.campaign_map_state_value = make_campaign_combat_state(
            generation=55, after=True
        )
        acknowledgement = adapter.click(CampaignGridButton((3, 5)))
        self.assertIs(acknowledgement, receipt)
        proof = adapter.confirm_campaign_combat(battle_count_after=1)
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.target_node, "D6")
        self.assertEqual(proof.enemy_object_id, 104)
        self.assertEqual((proof.ammo_before, proof.ammo_after), (5, 4))
        self.assertEqual((proof.battle_count_before, proof.battle_count_after), (0, 1))
        # ALAS's post-combat arrival acknowledgement is semantic-only; the
        # original target tap remains the sole physical mutation.
        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])

    def test_campaign_combat_budget_can_advance_to_the_next_alas_battle(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        self.assertIsNotNone(
            adapter.authorize_campaign_combat(
                make_campaign_combat_decision(), state
            )
        )
        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = make_campaign_combat_state(
            generation=55, after=True
        )

        proof = adapter.complete_campaign_combat_round(battle_count_after=1)

        self.assertIsNotNone(proof)
        self.assertFalse(adapter.campaign_combat_committed())
        self.assertEqual(adapter._action_ledger.remaining("campaign.grid_click"), 1)
        adapter.end_campaign_pre_sortie()

    def test_campaign_post_combat_refocus_consumes_bounded_cross_axis_swipes(self):
        oracle = FakeOracle()
        before = make_campaign_combat_state()
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = make_campaign_combat_state(
            generation=55, after=True
        )
        adapter.campaign_camera_state()
        self.assertTrue(adapter.campaign_post_combat_arrived((3, 5)))
        with self.assertRaisesRegex(SemanticGateClosed, "destination changed"):
            adapter.campaign_post_combat_arrived((4, 5))

        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.375,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        cross_axis_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 200.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-2",
            distance_check=True,
        )
        cross_axis_proof = adapter.swipe(
            (500, 400),
            (500, 600),
            duration=0.375,
            name="MAP_SWIPE_0_-2",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(cross_axis_intent)

        self.assertEqual(proof.target_node, "D6")
        self.assertEqual(cross_axis_proof.grid_vector, (0, -2))
        self.assertEqual(len(adapter._campaign_context.post_combat_viewport_proofs), 2)
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.viewport_swipe"), 0
        )
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(AlasSemanticActionDeferred, "campaign.viewport_swipe"):
            adapter.begin_campaign_map_swipe_vector(
                (200.0, 0.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_executes_alas_waypoint_then_enemy_input(self):
        oracle = FakeOracle()
        base = make_campaign_combat_state()
        nodes = ("D6", "C6", "C5", "C4", "C3", "D3")
        cells = tuple(
            replace(
                base.cells[0],
                row=int(node[1:]),
                column=ord(node[0]) - ord("A") + 1,
                node=node,
                button_path="root/DragLayer/plane/quads/" + node,
                point=Point(100 + index * 80, 200 + index * 20),
                bounds=Bounds(
                    70 + index * 80,
                    170 + index * 20,
                    130 + index * 80,
                    230 + index * 20,
                ),
            )
            for index, node in enumerate(nodes)
        )
        before = replace(
            base,
            cells=cells,
            fleets=(replace(base.fleets[0], node="D6"),),
            enemies=(replace(base.enemies[0], node="D3", fighting=False),),
        )
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        decision = replace(
            make_campaign_combat_decision(),
            origin_node="D6",
            target_node="D3",
            cost=5,
            route_nodes=nodes,
            goto_nodes=("C6", "D3"),
        )
        admission = adapter.authorize_campaign_combat(decision, state)

        self.assertEqual(admission.input_nodes, ("C6", "D3"))
        self.assertEqual(adapter.campaign_camera_target_node(), "C6")
        first = adapter.click(CampaignGridButton((2, 5)))
        self.assertEqual(first.semantic_id, "campaign/map/grid/C6")
        self.assertEqual(oracle.campaign_map_cell_click_calls, [("C6", False)])
        self.assertFalse(adapter.campaign_combat_committed())
        self.assertEqual(adapter.campaign_camera_target_node(), "D3")

        oracle.campaign_map_state_value = replace(
            before,
            generation=54,
            fleets=(replace(before.fleets[0], node="C5"),),
        )
        intermediate_state = adapter.campaign_camera_state()
        self.assertEqual(intermediate_state.fleets[0].node, "C5")

        oracle.campaign_map_state_value = replace(
            before,
            generation=55,
            fleets=(replace(before.fleets[0], node="C6"),),
        )
        waypoint_state = adapter.campaign_camera_state()
        self.assertEqual(waypoint_state.fleets[0].node, "C6")
        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.375,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)
        camera_state = adapter.campaign_camera_state()
        self.assertEqual(camera_state.fleets[0].node, "C6")
        recheck = adapter.recheck_campaign_combat_target_after_camera_view(
            camera_state
        )
        self.assertEqual(recheck.target_node, "D3")
        second = adapter.click(CampaignGridButton((3, 2)))
        self.assertEqual(second.semantic_id, "campaign/map/grid/D3")
        self.assertEqual(
            oracle.campaign_map_cell_click_calls,
            [("C6", False), ("D3", True)],
        )
        self.assertTrue(adapter.campaign_combat_committed())

        oracle.campaign_map_state_value = replace(
            before,
            generation=60,
            fleets=(replace(before.fleets[0], node="D3", ammo=4),),
            enemies=(),
        )
        post_camera = adapter.campaign_camera_state()
        self.assertEqual(post_camera.fleets[0].node, "D3")
        proof = adapter.confirm_campaign_combat(battle_count_after=1)
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.target_node, "D3")
        self.assertEqual(
            oracle.click_calls,
            ["campaign/map/grid/C6", "campaign/map/grid/D3"],
        )

    def test_campaign_combat_route_ignores_only_fleet_enumeration_order(self):
        oracle = FakeOracle()
        base = make_campaign_combat_state()
        nodes = ("D6", "C6", "C5", "C4", "C3", "D3")
        cells = tuple(
            replace(
                base.cells[0],
                row=int(node[1:]),
                column=ord(node[0]) - ord("A") + 1,
                node=node,
                button_path="root/DragLayer/plane/quads/" + node,
            )
            for node in nodes
        )
        selected = replace(base.fleets[0], node="D6")
        support = replace(
            base.fleets[0],
            marker="cell_fleet_support",
            node="A1",
        )
        before = replace(
            base,
            cells=cells,
            fleets=(selected, support),
            enemies=(replace(base.enemies[0], node="D3", fighting=False),),
        )
        oracle.campaign_map_state_value = before
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=2,
        )
        decision = replace(
            make_campaign_combat_decision(),
            origin_node="D6",
            target_node="D3",
            cost=5,
            route_nodes=nodes,
            goto_nodes=("C6", "D3"),
        )
        adapter.authorize_campaign_combat(decision, state)
        adapter.click(CampaignGridButton((2, 5)))

        oracle.campaign_map_state_value = replace(
            before,
            generation=55,
            fleets=(support, replace(selected, node="C6")),
        )

        camera_state = adapter.campaign_camera_state()
        self.assertEqual(
            next(
                fleet.node
                for fleet in camera_state.fleets
                if fleet.marker == selected.marker
            ),
            "C6",
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_admits_alas_boss_over_a_long_orthogonal_route(self):
        oracle = FakeOracle()
        base = make_campaign_combat_state()
        nodes = ("D6", "E6", "F6", "G6", "H6")
        cells = tuple(
            replace(
                base.cells[0],
                column=index + 4,
                node=node,
                button_path="root/DragLayer/plane/quads/" + node,
            )
            for index, node in enumerate(nodes)
        )
        state = replace(
            base,
            cells=cells,
            enemies=(
                replace(
                    base.enemies[0],
                    column=8,
                    node="H6",
                    genre="Boss",
                    fighting=False,
                ),
            ),
        )
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        decision = replace(
            make_campaign_combat_decision(),
            target_node="H6",
            expected="combat_boss",
            cost=4,
            route_nodes=nodes,
            goto_nodes=("H6",),
        )

        admission = adapter.authorize_campaign_combat(decision, current)

        self.assertIsNotNone(admission)
        self.assertEqual(admission.target_node, "H6")
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_is_one_use_and_updates_exact_grid_geometry(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        admission = adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        self.assertIsNotNone(admission)

        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.157,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        self.assertTrue(adapter.campaign_map_viewport_swipe_committed())
        self.assertEqual(proof.target_before_point, Point(640, 360))
        self.assertEqual(proof.target_after_point, Point(840, 360))
        camera_state = adapter.campaign_camera_state()
        recheck = adapter.recheck_campaign_combat_target_after_camera_view(
            camera_state
        )
        self.assertEqual(recheck.target_node, "D6")
        self.assertEqual(recheck.camera_state_generation, 53)
        with self.assertRaisesRegex(SemanticGateClosed, "token changed"):
            adapter.recheck_campaign_combat_target_after_camera_view(
                replace(camera_state, generation=54)
            )
        receipt = adapter.click(CampaignGridButton((3, 5)))
        self.assertEqual(receipt.point, Point(840, 360))
        self.assertTrue(adapter.campaign_combat_committed())
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.begin_campaign_map_swipe_vector(
                (200.0, 0.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_accepts_large_uniform_input_frame_shift(self):
        oracle = FakeOracle()
        initial = make_campaign_combat_state()
        oracle.campaign_map_state_value = initial

        def refresh_frame():
            oracle.campaign_map_state_value = replace(
                initial,
                generation=initial.generation + 1,
                cells=tuple(
                    replace(
                        cell,
                        point=Point(cell.point.x - 400, cell.point.y + 45),
                        bounds=Bounds(
                            cell.bounds.left - 400,
                            cell.bounds.top + 45,
                            cell.bounds.right - 400,
                            cell.bounds.bottom + 45,
                        ),
                    )
                    for cell in initial.cells
                ),
            )

        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            input_frame_refresher=refresh_frame,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(make_campaign_combat_decision(), state)
        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )

        proof = adapter.swipe(
            (500, 400),
            (700, 400),
            duration=0.157,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )

        self.assertEqual(proof.end, (700, 400))
        self.assertEqual(len(oracle.campaign_map_swipe_calls), 1)
        adapter.end_campaign_map_swipe_vector(intent)
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_rejects_nonuniform_input_frame_shift(self):
        oracle = FakeOracle()
        initial = make_campaign_combat_state()
        initial = replace(
            initial,
            cells=initial.cells
            + (
                replace(
                    initial.cells[0],
                    column=5,
                    node="E6",
                    button_path=(
                        "root/DragLayer/plane/quads/chapter_cell_quad_6_5"
                    ),
                    point=Point(720, 360),
                    bounds=Bounds(680, 320, 760, 400),
                ),
            ),
        )
        oracle.campaign_map_state_value = initial

        def refresh_frame():
            shifted = []
            for index, cell in enumerate(initial.cells):
                dx = -400 if index else -390
                shifted.append(
                    replace(
                        cell,
                        point=Point(cell.point.x + dx, cell.point.y + 45),
                        bounds=Bounds(
                            cell.bounds.left + dx,
                            cell.bounds.top + 45,
                            cell.bounds.right + dx,
                            cell.bounds.bottom + 45,
                        ),
                    )
                )
            oracle.campaign_map_state_value = replace(
                initial,
                generation=initial.generation + 1,
                cells=tuple(shifted),
            )

        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            input_frame_refresher=refresh_frame,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(make_campaign_combat_decision(), state)
        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=((900, 500, 950, 550),),
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "not a uniform shift"):
            adapter.swipe(
                (500, 400),
                (700, 400),
                duration=0.157,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )

        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_map_swipe_vector(intent)
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_rebases_exact_partial_hard_route(self):
        oracle = FakeOracle()
        cells = tuple(
            CampaignMapCellState(
                row=6,
                column=column,
                node=node,
                button_path=(
                    "root/DragLayer/plane/quads/chapter_cell_quad_6_" + str(column)
                ),
                point=Point(400 + column * 80, 360),
                bounds=Bounds(360 + column * 80, 320, 440 + column * 80, 400),
            )
            for column, node in ((3, "C6"), (4, "D6"), (5, "E6"))
        )
        enemy = CampaignMapEnemyState(
            row=6,
            column=5,
            node="E6",
            object_id=104,
            sprite="zl2",
            scale=2,
            genre="Main",
            level=114,
            fighting=False,
        )
        initial = CampaignMapState(
            generation=51,
            stage_code="12-4",
            rows=8,
            columns=11,
            cells=cells,
            land_nodes=("A1",),
            fleets=(CampaignMapFleetState("cell_fleet", "C6", 5, 5),),
            enemies=(enemy,),
            pickups=(),
            displayed_fleet_index=1,
            current_fleet_marker="cell_fleet",
            current_fleet_roster_sprites=("ship",),
        )
        decision = AlasCampaignDecisionPreview(
            generation=51,
            stage_code="12-4",
            battle_count=0,
            branch_name="battle_0",
            fleet_index=1,
            fleet_marker="cell_fleet",
            origin_node="C6",
            target_node="E6",
            target_kind="enemy",
            expected="combat",
            cost=2,
            weight=50.0,
            route_nodes=("C6", "D6", "E6"),
            goto_nodes=("E6",),
            step_optimize=False,
            turning_optimize=True,
        )
        oracle.campaign_map_state_value = initial
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
            campaign_viewport_swipe_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(decision, state)
        adapter.click(CampaignGridButton((4, 5)))
        oracle.campaign_map_state_value = replace(
            initial,
            generation=53,
            fleets=(CampaignMapFleetState("cell_fleet", "D6", 5, 5),),
        )
        adapter.campaign_camera_state()

        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )

        self.assertEqual(adapter._campaign_context.combat_admission.origin_node, "D6")
        self.assertEqual(
            adapter._campaign_context.combat_admission.route_nodes,
            ("D6", "E6"),
        )
        self.assertIsNone(adapter._campaign_context.combat_receipt)
        adapter.end_campaign_map_swipe_vector(intent)
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_rejects_timing_between_direct_and_adb(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        intent = adapter.begin_campaign_map_swipe_vector(
            (200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_-2_0",
            distance_check=True,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "duration changed"):
            adapter.swipe(
                (500, 400),
                (700, 400),
                duration=0.225,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )

        adapter.end_campaign_map_swipe_vector(intent)
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_defaults_closed_and_raw_swipe_stays_rejected(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        oracle.campaign_map_target_raycast_top = False
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        with self.assertRaisesRegex(AlasSemanticActionDeferred, "campaign.viewport_swipe"):
            adapter.authorize_campaign_combat(
                make_campaign_combat_decision(), state
            )
        with self.assertRaisesRegex(SemanticGateClosed, "raw ALAS input"):
            adapter.swipe(
                (500, 400),
                (700, 400),
                duration=0.375,
                name="MAP_SWIPE_-2_0",
                distance_check=True,
            )
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_accepts_alas_whitelist_fallback_only_in_padded_domain(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )

        intent = adapter.begin_campaign_map_swipe_vector(
            (14.0, -201.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=((900, 600, 1000, 650),),
            blacklist_area=None,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )
        proof = adapter.swipe(
            (772, 482),
            (786, 281),
            duration=0.3375,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)

        self.assertEqual(proof.end, (786, 281))
        self.assertEqual(len(oracle.campaign_map_swipe_calls), 1)
        adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_accepts_native_collapsed_padded_axis(self):
        # The first vector/endpoints are the actual 2026-10-28 MAP_SWIPE_2_3
        # failure. Native random_normal_distribution_int(a, b) returns b for
        # the inverted Y interval [174, 165], then point_limit clamps the box.
        for vector, name, start, end in (
            ((-296, -448), "MAP_SWIPE_2_3", (467, 613), (171, 165)),
            ((-296.4, -449.4), "MAP_SWIPE_2_3", (467, 614), (171, 165)),
            ((296, 448), "MAP_SWIPE_-2_-3", (467, 165), (763, 613)),
            ((-1036, 0), "MAP_SWIPE_4_0", (1160, 400), (124, 400)),
            ((1036, 0), "MAP_SWIPE_-4_0", (124, 400), (1160, 400)),
        ):
            with self.subTest(vector=vector):
                oracle = FakeOracle()
                oracle.campaign_map_state_value = make_campaign_combat_state()
                adapter = AlasSemanticAdapter(
                    oracle, lambda: None,
                    campaign_combat_budget=1, campaign_viewport_swipe_budget=1,
                )
                adapter.begin_campaign_pre_sortie("12-4")
                state = adapter.campaign_map_state(
                    columns=11, rows=8, land_cells=((0, 0),), expected_fleet_count=1,
                )
                adapter.authorize_campaign_combat(make_campaign_combat_decision(), state)
                intent = adapter.begin_campaign_map_swipe_vector(
                    vector, box=(123, 159, 1175, 628), random_range=(0, 0, 0, 0),
                    padding=15, duration=(0.1, 0.2), whitelist_area=None,
                    blacklist_area=None, name=name, distance_check=True,
                )
                # Even on a collapsed axis the adjacent, non-native endpoint
                # is rejected with the same delta and both endpoints in-box.
                axis = 1 if vector[1] else 0
                offset = 1 if vector[axis] < 0 else -1
                wrong_start, wrong_end = list(start), list(end)
                wrong_start[axis] += offset
                wrong_end[axis] += offset
                with self.assertRaisesRegex(SemanticGateClosed, "selection domain"):
                    adapter.swipe(
                        wrong_start, wrong_end, duration=0.3375,
                        name=name, distance_check=True,
                    )
                self.assertEqual(oracle.campaign_map_swipe_calls, [])
                proof = adapter.swipe(
                    start, end, duration=0.3375, name=name, distance_check=True,
                )
                self.assertEqual(proof.end, end)
                self.assertEqual(len(oracle.campaign_map_swipe_calls), 1)
                adapter.end_campaign_map_swipe_vector(intent)
                adapter.end_campaign_pre_sortie()

    def test_campaign_viewport_swipe_rejects_endpoint_outside_alas_padded_domain(self):
        oracle = FakeOracle()
        oracle.campaign_map_state_value = make_campaign_combat_state()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
            campaign_viewport_swipe_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        state = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), state
        )
        intent = adapter.begin_campaign_map_swipe_vector(
            (14.0, -201.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_2",
            distance_check=True,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "selection domain"):
            adapter.swipe(
                (126, 482),
                (140, 281),
                duration=0.3375,
                name="MAP_SWIPE_0_2",
                distance_check=True,
            )
        adapter.end_campaign_map_swipe_vector(intent)
        self.assertEqual(oracle.campaign_map_swipe_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_camera_positioning_is_separate_one_use_empty_cell_contract(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        empty = CampaignMapCellState(
            row=3,
            column=6,
            node="F3",
            button_path="root/DragLayer/plane/quads/chapter_cell_quad_3_6",
            point=Point(640, 80),
            bounds=Bounds(600, 40, 680, 120),
        )
        state = replace(state, cells=state.cells + (empty,))
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_camera_positioning_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )

        admission = adapter.authorize_campaign_camera_positioning(
            "F3", current
        )
        self.assertEqual(admission.target_node, "F3")
        intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 200.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        proof = adapter.swipe(
            (500, 300),
            (500, 500),
            duration=0.35,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(intent)
        positioned_state = adapter.campaign_camera_state()
        completed = adapter.complete_campaign_camera_positioning(
            positioned_state
        )

        self.assertEqual(proof.target_node, "F3")
        self.assertEqual(completed, (proof,))
        self.assertTrue(adapter.campaign_camera_positioning_committed())
        self.assertIs(adapter.campaign_camera_positioning_proof(), proof)
        with self.assertRaisesRegex(SemanticGateClosed, "not proven"):
            adapter.campaign_map_viewport_swipe_proof()
        with self.assertRaisesRegex(SemanticGateClosed, "not available"):
            adapter.authorize_campaign_camera_positioning("F3", current)
        adapter.end_campaign_pre_sortie()

    def test_campaign_camera_positioning_rejects_enemy_or_default_zero_budget(self):
        state = make_campaign_combat_state()
        for budget, error, message in (
            (0, AlasSemanticActionDeferred, "campaign.camera_positioning"),
            (1, SemanticGateClosed, "empty sea cell"),
        ):
            oracle = FakeOracle()
            oracle.campaign_map_state_value = state
            adapter = AlasSemanticAdapter(
                oracle,
                lambda: None,
                campaign_camera_positioning_budget=budget,
            )
            adapter.begin_campaign_pre_sortie("12-4")
            current = adapter.campaign_map_state(
                columns=11,
                rows=8,
                land_cells=((0, 0),),
                expected_fleet_count=1,
            )
            with self.subTest(budget=budget):
                with self.assertRaisesRegex(error, message):
                    adapter.authorize_campaign_camera_positioning(
                        "D6", current
                    )
            adapter.end_campaign_pre_sortie()

    def test_campaign_camera_positioning_allows_two_original_focus_corrections_then_closes(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        empty = CampaignMapCellState(
            row=3,
            column=6,
            node="F3",
            button_path="root/DragLayer/plane/quads/chapter_cell_quad_3_6",
            point=Point(640, 80),
            bounds=Bounds(600, 40, 680, 120),
        )
        oracle.campaign_map_state_value = replace(
            state, cells=state.cells + (empty,)
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_camera_positioning_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_camera_positioning("F3", current)

        first_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 260.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        first = adapter.swipe(
            (500, 250),
            (500, 510),
            duration=0.35,
            name="MAP_SWIPE_0_-3",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(first_intent)
        second_intent = adapter.begin_campaign_map_swipe_vector(
            (0.0, 80.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration=(0.1, 0.2),
            whitelist_area=None,
            blacklist_area=None,
            name="MAP_SWIPE_0_-1",
            distance_check=True,
        )
        second = adapter.swipe(
            (500, 370),
            (500, 450),
            duration=0.35,
            name="MAP_SWIPE_0_-1",
            distance_check=True,
        )
        adapter.end_campaign_map_swipe_vector(second_intent)
        positioned_state = adapter.campaign_camera_state()

        completed = adapter.complete_campaign_camera_positioning(
            positioned_state
        )

        self.assertEqual(completed, (first, second))
        self.assertEqual(
            adapter.campaign_camera_positioning_proofs(),
            (first, second),
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not authorized"):
            adapter.begin_campaign_map_swipe_vector(
                (0.0, 80.0),
                box=(123, 159, 1175, 628),
                random_range=(0, 0, 0, 0),
                padding=15,
                duration=(0.1, 0.2),
                whitelist_area=None,
                blacklist_area=None,
                name="MAP_SWIPE_0_-1",
                distance_check=True,
            )
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_rejects_route_drift_before_input(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        decision = replace(
            make_campaign_combat_decision(),
            cost=1,
            route_nodes=("D6", "D5"),
        )

        with self.assertRaisesRegex(SemanticGateClosed, "exact orthogonal route"):
            adapter.authorize_campaign_combat(decision, current)

        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_rejects_failed_postcondition_without_replay(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), current
        )
        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = replace(state, generation=55)

        with self.assertRaisesRegex(SemanticGateClosed, "enemy still exists"):
            adapter.confirm_campaign_combat(battle_count_after=1)

        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_anomalous_receipt_cannot_replay_input(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=1,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(
            make_campaign_combat_decision(), current
        )
        exact_click = oracle.click_campaign_map_cell

        def anomalous_click(
            map_state, node, *, allow_expected_enemy_coverage=False
        ):
            return replace(
                exact_click(
                    map_state,
                    node,
                    allow_expected_enemy_coverage=allow_expected_enemy_coverage,
                ),
                path="wrong/path",
            )

        oracle.click_campaign_map_cell = anomalous_click
        with self.assertRaisesRegex(SemanticGateClosed, "receipt changed"):
            adapter.click(CampaignGridButton((3, 5)))
        with self.assertRaisesRegex(SemanticGateClosed, "remaining budget"):
            adapter.click(CampaignGridButton((3, 5)))

        self.assertEqual(oracle.click_calls, ["campaign/map/grid/D6"])
        adapter.end_campaign_pre_sortie()

    def test_campaign_combat_allows_one_exact_no_progress_input_retry(self):
        oracle = FakeOracle()
        state = make_campaign_combat_state()
        oracle.campaign_map_state_value = state
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_combat_budget=2,
        )
        adapter.begin_campaign_pre_sortie("12-4")
        current = adapter.campaign_map_state(
            columns=11,
            rows=8,
            land_cells=((0, 0),),
            expected_fleet_count=1,
        )
        adapter.authorize_campaign_combat(make_campaign_combat_decision(), current)

        adapter.click(CampaignGridButton((3, 5)))
        oracle.campaign_map_state_value = replace(state, generation=53)
        adapter.click(CampaignGridButton((3, 5)))

        self.assertEqual(
            oracle.click_calls,
            ["campaign/map/grid/D6", "campaign/map/grid/D6"],
        )
        self.assertEqual(adapter._campaign_context.combat_input_retry_count, 1)
        with self.assertRaisesRegex(SemanticGateClosed, "proven post-state"):
            adapter.click(CampaignGridButton((3, 5)))
        adapter.end_campaign_pre_sortie()

    def test_low_resolve_cancel_remembers_hud_fleet_not_stale_combat_snapshot(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=((0, -1),))
        oracle.operation_siren_current_fleet = Mock(return_value=2)
        adapter.begin_operation_siren_boss_combat()
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        receipt = oracle.click_receipt("os/combat/low-resolve/cancel")
        oracle.click_operation_siren_low_resolve_cancel = Mock(
            return_value=receipt
        )

        self.assertEqual(
            adapter.click_operation_siren_low_resolve_cancel(), receipt
        )
        self.assertTrue(adapter.operation_siren_fleet_already_defeated(4))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(2))
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())
