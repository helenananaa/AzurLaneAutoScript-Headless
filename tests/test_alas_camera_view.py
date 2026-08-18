import unittest
from dataclasses import replace
from types import SimpleNamespace

from alas_headless import (
    Bounds,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapState,
    Point,
    SemanticGateClosed,
    build_alas_campaign_camera_view,
    install_alas_campaign_camera_view,
)
from alas_headless.alas_viewport_continuation import (
    _natural_goto_camera_vector,
)


def make_state(*, generation=10, dx=0.0, dy=0.0, deform=False, columns=5):
    cells = []
    for row in range(1, 6):
        for column in range(1, columns + 1):
            x = 100.0 * (column - 0.5) + 100.0 + dx
            y = 80.0 * (row - 0.5) + 100.0 + dy
            if deform and row == 2 and column == 4:
                x += 30.0
                y -= 25.0
            cells.append(
                CampaignMapCellState(
                    row=row,
                    column=column,
                    node=chr(ord("A") + column - 1) + str(row),
                    button_path=(
                        "root/quads/chapter_cell_quad_{0}_{1}".format(
                            row, column
                        )
                    ),
                    point=Point(x, y),
                    bounds=Bounds(x - 40, y - 30, x + 40, y + 30),
                )
            )
    return CampaignMapState(
        generation=generation,
        stage_code="12-4",
        rows=5,
        columns=columns,
        cells=tuple(cells),
        land_nodes=("A1",),
        fleets=(),
        enemies=(),
        pickups=(),
        displayed_fleet_index=1,
        current_fleet_marker="fleet",
        current_fleet_roster_sprites=("ship",),
    )


def make_single_row_state(*, generation=10, dx=0.0):
    state = make_state(generation=generation, columns=7)
    cells = tuple(
        replace(cell, row=1, node=cell.node[0] + "1")
        for cell in state.cells
        if cell.row == 1
    )
    if dx:
        cells = tuple(
            replace(
                cell,
                point=Point(cell.point.x + dx, cell.point.y),
                bounds=Bounds(
                    cell.bounds.left + dx,
                    cell.bounds.top,
                    cell.bounds.right + dx,
                    cell.bounds.bottom,
                ),
            )
            for cell in cells
        )
    return replace(state, stage_code="1-1", rows=1, cells=cells, land_nodes=())


class AlasCampaignCameraViewTests(unittest.TestCase):
    def test_builds_single_row_camera_from_typed_centers_and_bounds(self):
        view = build_alas_campaign_camera_view(
            make_single_row_state(),
            screen_center=(350.0, 140.0),
            target_node="C1",
        )
        observation = view.semantic_observation

        self.assertEqual(observation.camera_location, (2, 0))
        self.assertAlmostEqual(observation.center_offset[0], 0.5)
        self.assertAlmostEqual(observation.center_offset[1], 0.5)
        self.assertEqual(tuple(view.swipe_base), (100.0, 60.0))
        self.assertLess(observation.projective_maximum_residual, 1e-8)

    def test_builds_exact_internal_camera_view_and_target_grid(self):
        state = make_state()
        view = build_alas_campaign_camera_view(
            state,
            screen_center=(350.0, 300.0),
            target_node="C3",
        )
        observation = view.semantic_observation

        self.assertEqual(observation.camera_location, (2, 2))
        self.assertEqual(observation.camera_node, "C3")
        self.assertAlmostEqual(observation.center_offset[0], 0.5)
        self.assertAlmostEqual(observation.center_offset[1], 0.5)
        self.assertEqual(observation.target_local_location, (2, 2))
        self.assertEqual(view[(2, 2)].semantic_path, observation.target_path)
        self.assertEqual(tuple(view.swipe_base), (100.0, 80.0))
        self.assertLess(observation.projective_maximum_residual, 1e-8)

    def test_grid_exposes_conservative_native_merge_fields(self):
        view = build_alas_campaign_camera_view(
            make_single_row_state(),
            screen_center=(350.0, 140.0),
        )
        grid = view[(0, 0)]

        self.assertFalse(grid.is_submarine)
        self.assertFalse(grid.is_caught_by_siren)
        self.assertFalse(grid.is_carrier)
        self.assertFalse(grid.is_missile_attack)
        self.assertFalse(grid.is_ammo)
        self.assertEqual(grid.enemy_scale, 0)
        self.assertIsNone(grid.enemy_genre)
        self.assertEqual(grid.str, "--")

    def test_predict_swipe_uses_observed_camera_delta(self):
        before = build_alas_campaign_camera_view(
            make_state(generation=10),
            screen_center=(350.0, 300.0),
        )
        # Moving rendered cells left by one column and down by one row moves
        # the camera coordinate right one and up one.
        after = build_alas_campaign_camera_view(
            make_state(generation=12, dx=-100.0, dy=80.0),
            screen_center=(350.0, 300.0),
        )

        self.assertEqual(before.predict_swipe(after), (1, -1))

    def test_predict_swipe_accepts_edge_clamped_maximum_delta(self):
        before = build_alas_campaign_camera_view(
            make_state(generation=10, columns=6), screen_center=(150.0, 300.0)
        )
        after = build_alas_campaign_camera_view(
            make_state(generation=12, dx=-500.0, columns=6),
            screen_center=(150.0, 300.0),
        )

        self.assertEqual(before.predict_swipe(after), (5, 0))

    def test_predict_swipe_allows_only_exact_additive_boss_transition(self):
        before_state = make_state(generation=10)
        before = build_alas_campaign_camera_view(
            before_state, screen_center=(350.0, 300.0)
        )
        boss = CampaignMapEnemyState(
            row=1,
            column=5,
            node="E1",
            object_id=1001,
            sprite="bossicon",
            scale=0,
            genre="Boss",
            level=2,
            fighting=False,
        )
        after_state = replace(
            make_state(generation=12, dx=-100.0), enemies=(boss,)
        )
        after = build_alas_campaign_camera_view(
            after_state, screen_center=(350.0, 300.0)
        )

        self.assertEqual(before.predict_swipe(after), (1, 0))

        mob = replace(boss, genre="Enemy", sprite="enemyicon")
        changed = build_alas_campaign_camera_view(
            replace(after_state, enemies=(mob,)), screen_center=(350.0, 300.0)
        )
        with self.assertRaisesRegex(SemanticGateClosed, "changed map"):
            before.predict_swipe(changed)

    def test_rejects_incoherent_projection_and_unqualified_edge(self):
        with self.assertRaisesRegex(SemanticGateClosed, "incoherent"):
            build_alas_campaign_camera_view(
                make_state(deform=True),
                screen_center=(350.0, 300.0),
            )
        with self.assertRaisesRegex(SemanticGateClosed, "edge"):
            build_alas_campaign_camera_view(
                make_state(),
                screen_center=(160.0, 10.0),
            )

    def test_install_replaces_only_campaign_view_input(self):
        campaign = SimpleNamespace(
            config=SimpleNamespace(SCREEN_CENTER=(350.0, 300.0))
        )
        state = make_state()

        observation = install_alas_campaign_camera_view(
            campaign, state, target_node="C3"
        )

        self.assertIs(campaign.view.semantic_state, state)
        self.assertIs(campaign.semantic_camera_view_observation, observation)
        self.assertEqual(observation.target_node, "C3")

    def test_predict_swipe_rejects_logical_map_drift(self):
        before = build_alas_campaign_camera_view(
            make_state(generation=10), screen_center=(350.0, 300.0)
        )
        changed = replace(
            make_state(generation=12, dx=-100.0), stage_code="12-3"
        )
        after = build_alas_campaign_camera_view(
            changed, screen_center=(350.0, 300.0)
        )

        with self.assertRaisesRegex(SemanticGateClosed, "changed map"):
            before.predict_swipe(after)

    def test_natural_goto_camera_vector_matches_walk_sight(self):
        sight = (-3, -1, 3, 2)

        self.assertEqual(
            _natural_goto_camera_vector((5, 2), (5, 5), sight),
            (0, 1),
        )
        self.assertEqual(
            _natural_goto_camera_vector((5, 3), (5, 5), sight),
            (0, 0),
        )
        self.assertEqual(
            _natural_goto_camera_vector((1, 4), (5, 3), sight),
            (1, -1),
        )

    def test_natural_goto_camera_vector_rejects_malformed_sight(self):
        with self.assertRaisesRegex(SemanticGateClosed, "malformed"):
            _natural_goto_camera_vector((5, 2), (5, 5), (1, -1, 3, 2))


if __name__ == "__main__":
    unittest.main()
