"""Campaign map regression cases for the oracle."""

import dataclasses
import unittest
from alas_headless.semantic_oracle import Point, SemanticGateClosed, SemanticOracle
from tests.semantic_support.campaign_fixtures import make_campaign_map_backend
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_snapshot,
    make_toggle,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_campaign_official_combat_auto_state_requires_exact_checked_toggle(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/AutoBtn",
                    checked=True,
                )
            ],
            generation=37,
        )

        self.assertEqual(
            make_oracle(backend).campaign_official_combat_auto_state(),
            (37, True),
        )

    def test_campaign_official_combat_auto_state_rejects_ambiguous_toggle(self):
        backend = FakeBackend([])
        suffix = "CombatUIStandard(Clone)/AutoBtn"
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle("UICamera/A/" + suffix, checked=True),
                make_toggle("UICamera/B/" + suffix, checked=True),
            ],
        )

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            make_oracle(backend).campaign_official_combat_auto_state()

    def test_campaign_precombat_back_requires_exact_image_contract(self):
        root = "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)"
        path = root + "/adapt/top/back_btn"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    path,
                    x=58,
                    y=54,
                    bounds={"left": 0, "top": 0, "right": 115, "bottom": 111},
                    raycast_top=True,
                )
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(path, "icon_bg_front_1920"),
                make_image(path + "/mask", "icon_bg_mask_1920"),
                make_image(path + "/mask/Image", "back_btn"),
            ],
        )

        receipt = make_oracle(backend).click_campaign_precombat_back()

        self.assertEqual(receipt.semantic_id, "campaign/precombat/back")
        self.assertEqual(backend.taps, [(58, 54)])
        backend.buttons["buttons"][0]["raycast_top"] = None
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).click_campaign_precombat_back()
        self.assertEqual(backend.taps, [(58, 54)])

    def test_campaign_map_cell_viewport_target_allows_bounded_easing_only(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        target = next(
            button
            for button in backend.buttons["buttons"]
            if button["path"].endswith("chapter_cell_quad_1_1")
        )
        backend.snapshot = make_snapshot(generation=12)
        backend.buttons["generation"] = 12
        target["raycast_top"] = False
        target["adb_point"]["y"] += 0.9
        target["adb_bounds"]["top"] += 0.9
        target["adb_bounds"]["bottom"] += 0.9
        backend.buttons["buttons"].append(
            make_button("loading", "root/UIOverlay/Loading(Clone)/mask")
        )
        backend.buttons["button_count"] += 1

        observed = oracle.campaign_map_cell_viewport_target(state, "A1")
        self.assertEqual(observed.path, state.cells[0].button_path)

        target["adb_bounds"]["bottom"] += 4.2
        with self.assertRaisesRegex(SemanticGateClosed, "geometry"):
            oracle.campaign_map_cell_viewport_target(state, "A1")

    def test_campaign_map_viewport_swipe_proves_same_map_coherent_shift(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, covered=False)

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(backend.swipes, [(500, 400, 700, 400, 375)])
        self.assertEqual(proof.semantic_id, "campaign/map/viewport/A1")
        self.assertEqual(proof.median_cell_delta, (200.0, 0.0))
        self.assertEqual(proof.coherent_cell_count, 5)
        self.assertEqual(proof.target_before_point, Point(100.0, 100.0))
        self.assertEqual(proof.target_after_point, Point(300.0, 100.0))
        self.assertGreater(proof.post_generation, proof.input_generation)

    def test_campaign_map_viewport_accepts_edge_noop_for_exposed_target(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(
            backend, covered=False, no_move=True
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.median_cell_delta, (0.0, 0.0))
        self.assertEqual(proof.target_before_point, proof.target_after_point)

    def test_campaign_map_viewport_accepts_edge_noop_at_current_fleet(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        next(
            button
            for button in backend.buttons["buttons"]
            if button["path"].endswith("chapter_cell_quad_2_1")
        )["raycast_top"] = False
        self._arm_campaign_viewport_backend(
            backend, covered=True, no_move=True
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A2",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.median_cell_delta, (0.0, 0.0))
        self.assertEqual(proof.target_before_point, proof.target_after_point)

    def test_campaign_map_viewport_allows_exact_additive_boss_appearance(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        state = dataclasses.replace(state, enemies=())
        self._arm_campaign_viewport_backend(
            backend,
            covered=False,
            boss_appears=True,
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.semantic_id, "campaign/map/viewport/A1")

    def test_campaign_map_viewport_allows_additive_wave_only_when_authorized(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        state = dataclasses.replace(state, enemies=())
        self._arm_campaign_viewport_backend(backend, covered=False)

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
            allow_enemy_additions=True,
        )

        self.assertEqual(proof.semantic_id, "campaign/map/viewport/A1")

    def test_campaign_map_viewport_allows_wave_auto_focus_on_other_axis(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        state = dataclasses.replace(state, enemies=())
        self._arm_campaign_viewport_backend(
            backend,
            covered=False,
            orthogonal=True,
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
            allow_enemy_additions=True,
        )

        self.assertEqual(proof.median_cell_delta, (0.0, 200.0))

    def test_campaign_map_viewport_allows_opposed_axis_during_boss_auto_focus(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        state = dataclasses.replace(state, enemies=())
        self._arm_campaign_viewport_backend(
            backend,
            covered=False,
            boss_appears=True,
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(700, 400),
            end=(500, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.median_cell_delta, (200.0, 0.0))

    def test_campaign_map_viewport_rejects_orthogonal_displacement(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, covered=False)

        with self.assertRaisesRegex(SemanticGateClosed, "gesture axis"):
            oracle.campaign_map_viewport_swipe(
                state,
                "A1",
                self._campaign_viewport_intent(),
                start=(500, 300),
                end=(500, 500),
                duration_ms=375,
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_map_viewport_swipe_consumes_input_but_rejects_incoherence(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, incoherent=True)

        with self.assertRaisesRegex(SemanticGateClosed, "projective"):
            oracle.campaign_map_viewport_swipe(
                state,
                "A1",
                self._campaign_viewport_intent(),
                start=(500, 400),
                end=(700, 400),
                duration_ms=375,
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

        self.assertEqual(backend.swipes, [(500, 400, 700, 400, 375)])

    def test_campaign_map_viewport_accepts_coherent_nonuniform_projection(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, covered=False, nonuniform=True)

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.coherent_cell_count, 5)
        self.assertLess(proof.maximum_delta_residual, 1e-6)

    def test_campaign_map_viewport_affine_model_accepts_one_row_translation(self):
        before = tuple(Point(float(x), 300.0) for x in range(100, 800, 100))
        after = tuple(Point(point.x - 392.0, point.y + 45.0) for point in before)

        residuals, rms = SemanticOracle._campaign_projective_residuals(
            before,
            after,
        )

        self.assertLess(max(residuals), 1e-6)
        self.assertLess(rms, 1e-6)
