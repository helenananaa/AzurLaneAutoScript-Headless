"""Opsi combat regression cases for the oracle."""

import copy
import unittest
from alas_headless.semantic_oracle import (
    OperationSirenDaemonTarget,
    SemanticGateClosed,
    SemanticOracle,
)
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_snapshot,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import OperationSirenSemanticOracleTestsSupport
from unittest import mock


class OperationSirenSemanticOracleTests(OperationSirenSemanticOracleTestsSupport, unittest.TestCase):
    def test_local_map_shell_and_current_fleet_are_typed(self):
        oracle = self._local_map_oracle("3")
        self.assertTrue(oracle.operation_siren_page_visible())
        self.assertTrue(oracle.operation_siren_local_map_visible())
        self.assertEqual(oracle.operation_siren_current_fleet(), 3)

    def test_fleet_bar_click_retries_incoherent_observer_snapshots(self):
        bar_path = (
            "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/"
            "fleet_bar"
        )
        bounds = {"left": 620.0, "top": 340.0, "right": 660.0, "bottom": 380.0}
        buttons = [
            make_button(
                "back_button",
                "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/"
                "back_button",
            ),
            make_button(
                "fleet_bar",
                bar_path,
                x=640.0,
                y=360.0,
                bounds=bounds,
            ),
        ]
        backend = FakeBackend(buttons)
        control = make_image(bar_path, "btn_switch", bounds)
        backend.snapshot_sequence = [
            make_snapshot(generation=10),
            make_snapshot(generation=10),
            make_snapshot(generation=20),
        ]
        backend.ui_sequence = [
            make_ui([], images=[control], generation=20),
            make_ui([], images=[control], generation=21),
        ]
        oracle = make_oracle(backend)

        receipt = oracle.click_operation_siren_fleet_bar()

        self.assertEqual(receipt.semantic_id, "os/map/fleet-selector/open")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_fleet_bar_click_still_fails_closed_when_snapshots_never_settle(self):
        bar_path = (
            "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/"
            "fleet_bar"
        )
        bounds = {"left": 620.0, "top": 340.0, "right": 660.0, "bottom": 380.0}
        buttons = [
            make_button(
                "back_button",
                "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/"
                "back_button",
            ),
            make_button(
                "fleet_bar",
                bar_path,
                x=640.0,
                y=360.0,
                bounds=bounds,
            ),
        ]
        backend = FakeBackend(buttons)
        control = make_image(bar_path, "btn_switch", bounds)
        backend.snapshot_sequence = [
            make_snapshot(generation=generation)
            for generation in (10, 10, 20, 30, 40, 50)
        ]
        backend.ui_sequence = [
            make_ui([], images=[control], generation=generation)
            for generation in (20, 30, 40, 50, 60)
        ]
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "not coherent"):
            oracle.click_operation_siren_fleet_bar()
        self.assertEqual(backend.taps, [])

    def test_operation_siren_page_shell_does_not_require_fleet_panel(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                )
            ]
        )

        oracle = make_oracle(backend)
        self.assertTrue(oracle.operation_siren_page_visible())
        self.assertFalse(oracle.operation_siren_local_map_visible())

    def test_current_fleet_rejects_unknown_sprite(self):
        oracle = self._local_map_oracle("fleet_unknown")
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            oracle.operation_siren_current_fleet()

    def test_selected_fleet_low_resolve_uses_exact_map_marker(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "LevelCamera/Canvas/LevelOrigin/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "LevelCamera/Canvas/LevelOrigin/top/adapt/left_stage/other/"
                    "fleet_bar/text_selected/x",
                    "4",
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "fleet_4/shadow",
                    "shadow",
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.operation_siren_current_fleet_defeated())
        backend.ui = make_ui(
            [],
            images=backend.ui["images"]
            + [
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "fleet_4/marks/damage/1",
                    "200",
                )
            ],
        )
        self.assertTrue(oracle.operation_siren_current_fleet_defeated())
        self.assertTrue(oracle.operation_siren_low_resolve_visible())

    def test_selected_fleet_low_resolve_requires_complete_map_anchor(self):
        oracle = self._local_map_oracle("2")
        state = oracle.read_ui_state()
        self.assertEqual(
            SemanticOracle._operation_siren_current_fleet_from_ui_state(state),
            2,
        )

        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/"
                    "fleet_bar/text_selected/x",
                    "2",
                )
            ],
        )
        with self.assertRaisesRegex(SemanticGateClosed, "map anchor"):
            make_oracle(backend).operation_siren_current_fleet_defeated()

    def test_radar_boss_click_accepts_exact_overlapped_shadow(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/"
                    "other/fleet_bar/text_selected/x",
                    "4",
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                    "cells/cell_8_8/attachments/enemy_9/live/char/shadow",
                    "shadow",
                    {"left": 600, "top": 310, "right": 680, "bottom": 390},
                ),
            ],
        )
        oracle = make_oracle(backend)
        oracle.operation_siren_radar_targets = mock.Mock(return_value=((0, 0),))

        receipt = oracle.click_operation_siren_radar_boss((0, 0))

        self.assertEqual(receipt.semantic_id, "os/map/boss/relative/0/0")
        self.assertEqual(backend.taps, [(640, 350)])

    def test_radar_boss_click_accepts_exact_month_boss_event_shadow(self):
        radar = (
            "OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
            "compass_panel/ring/compass/range/7032027"
        )
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/"
                    "other/fleet_bar/text_selected/x",
                    "4",
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                    "cells/fleet_4/shadow",
                    "shadow",
                    {"left": 584, "top": 319, "right": 696, "bottom": 401},
                ),
                make_image(
                    radar,
                    "boss",
                    {"left": 1132, "top": 206, "right": 1150, "bottom": 225},
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                    "cells/cell_4_6/attachments/event_7032027/char/shadow",
                    "shadow",
                    {"left": 588, "top": 187, "right": 692, "bottom": 263},
                ),
            ],
        )
        oracle = make_oracle(backend)
        oracle.operation_siren_radar_targets = mock.Mock(return_value=((0, -1),))

        receipt = oracle.click_operation_siren_radar_boss((0, -1))

        self.assertEqual(receipt.semantic_id, "os/map/boss/relative/0/-1")
        self.assertEqual(backend.taps, [(640, 225)])

    def test_radar_boss_click_rejects_ambiguous_overlapped_shadows(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/"
                    "other/fleet_bar/text_selected/x",
                    "4",
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                    "cells/cell_8_8/attachments/enemy_9/live/char/shadow",
                    "shadow",
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                    "cells/cell_9_8/attachments/enemy_10/live/char/shadow",
                    "shadow",
                ),
            ],
        )
        oracle = make_oracle(backend)
        oracle.operation_siren_radar_targets = mock.Mock(return_value=((0, 0),))

        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            oracle.click_operation_siren_radar_boss((0, 0))
        self.assertEqual(backend.taps, [])

    def test_typed_radar_port_and_relative_grid_click(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        oracle = make_oracle(backend)
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
                    "compass_panel/ring/compass/range/mark",
                    "port",
                    {"left": 1083.6, "top": 192.1, "right": 1105.067, "bottom": 214.967},
                ),
                make_image(
                    "OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
                    "compass_panel/ring/compass/range/7000040",
                    "guidepost",
                    {"left": 1159.433, "top": 207.5, "right": 1169.233, "bottom": 222.9},
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/"
                    "world_quad_8_6/walk_quad",
                    "cell_white",
                    {"left": 587.85, "top": 324.41, "right": 692.15, "bottom": 396.876},
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/"
                    "world_quad_6_5/walk_quad",
                    "cell_white",
                    {"left": 494.09, "top": 193.648, "right": 592.949, "bottom": 256.826},
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/"
                    "world_quad_8_7/walk_quad",
                    "cell_white",
                    {"left": 690.332, "top": 324.41, "right": 796.451, "bottom": 396.876},
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "cell_8_7/attachments/event_7000040/icon/model/"
                    "chongdong02(Clone)",
                    "chongdong42",
                    {"left": 700.0, "top": 300.0, "right": 790.0, "bottom": 390.0},
                ),
            ],
        )

        self.assertEqual(oracle.operation_siren_radar_targets("port"), ((-4, -2),))
        self.assertEqual(
            oracle.operation_siren_radar_targets("guidepost"), ((2, -1),)
        )
        self.assertEqual(
            oracle.operation_siren_radar_targets("question"), ((2, -1),)
        )
        receipt = oracle.click_operation_siren_relative_grid((-1, -2))
        self.assertEqual(receipt.semantic_id, "os/map/grid/relative/-1/-2")
        self.assertEqual(backend.taps, [(544, 225)])
        adjacent = oracle.click_operation_siren_relative_grid(
            (1, 0), prefer_adjacent_event=True
        )
        self.assertTrue(adjacent.path.endswith("chongdong02(Clone)"))
        self.assertEqual(backend.taps[-1], (745, 345))

    def test_daemon_target_uses_reviewed_nearest_object_and_port_fixup(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        root = (
            "root/OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
            "compass_panel/ring/compass/range/"
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    root + "1001",
                    "battle",
                    {"left": 1111.7, "top": 231.85, "right": 1121.7, "bottom": 243.55},
                ),
                make_image(
                    root + "1002",
                    "task",
                    {"left": 1170.1, "top": 231.85, "right": 1180.1, "bottom": 243.55},
                ),
                make_image(
                    root + "mark",
                    "port",
                    {"left": 1146.7, "top": 221.0, "right": 1156.7, "bottom": 231.0},
                ),
                make_image(
                    root + "1003",
                    "guidepost",
                    {"left": 1135.0, "top": 221.0, "right": 1145.0, "bottom": 231.0},
                ),
            ],
        )
        oracle = make_oracle(backend)

        target = oracle.operation_siren_nearest_daemon_target()

        self.assertEqual(target.target_kind, "enemy")
        self.assertEqual(target.source_position, (-2, 1))
        self.assertEqual(target.relative_position, (-2, 1))

    def test_daemon_target_rejects_ties_unknown_kinds_and_untyped_emp_step(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        root = (
            "root/OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
            "compass_panel/ring/compass/range/"
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    root + "1001",
                    "battle",
                    {"left": 1146.7, "top": 221.0, "right": 1156.7, "bottom": 231.0},
                ),
                make_image(
                    root + "1002",
                    "task",
                    {"left": 1135.0, "top": 232.7, "right": 1145.0, "bottom": 242.7},
                ),
            ],
        )
        oracle = make_oracle(backend)
        with self.assertRaisesRegex(SemanticGateClosed, "nearest.*ambiguous"):
            oracle.operation_siren_nearest_daemon_target()

        backend.ui["images"] = [
            make_image(
                root + "1004",
                "archive",
                {"left": 1146.7, "top": 221.0, "right": 1156.7, "bottom": 231.0},
            )
        ]
        backend.ui["image_count"] = 1
        with self.assertRaisesRegex(SemanticGateClosed, "kind is not reviewed"):
            oracle.operation_siren_nearest_daemon_target()

        backend.ui["images"] = [
            make_image(
                root + "1005",
                "battle",
                {"left": 1181.8, "top": 232.7, "right": 1191.8, "bottom": 242.7},
            )
        ]
        with self.assertRaisesRegex(SemanticGateClosed, "typed EMP"):
            oracle.operation_siren_nearest_daemon_target()

    def test_daemon_target_click_rejects_stale_identity_without_input(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        oracle = make_oracle(backend)
        expected = OperationSirenDaemonTarget(
            generation=10,
            target_kind="enemy",
            source_position=(-1, 0),
            relative_position=(-1, 0),
        )
        with mock.patch.object(
            oracle,
            "operation_siren_nearest_daemon_target",
            return_value=OperationSirenDaemonTarget(
                generation=11,
                target_kind="event",
                source_position=(-1, 0),
                relative_position=(-1, 0),
            ),
        ), self.assertRaisesRegex(SemanticGateClosed, "changed before input"):
            oracle.click_operation_siren_daemon_target(expected)
        self.assertEqual(backend.taps, [])

    def test_typed_question_radar_is_the_alas_question_wormhole_not_other_guideposts(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        root = (
            "OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
            "compass_panel/ring/compass/range/"
        )
        world = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    root + "7030051",
                    "guidepost",
                    {"left": 1136.1, "top": 207.5, "right": 1145.9, "bottom": 222.9},
                ),
                make_image(
                    root + "7030011",
                    "guidepost",
                    {"left": 1124.433, "top": 265.833, "right": 1134.233, "bottom": 281.233},
                ),
                make_image(
                    world
                    + "cell_12_5/attachments/event_7030011/icon/model/"
                    "chongdong02(Clone)",
                    "chongdong42",
                ),
                make_image(
                    world
                    + "cell_7_6/attachments/event_7030051/icon/model/"
                    "taban_jinzhi(Clone)/taban",
                    "taban01",
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.operation_siren_radar_targets("guidepost"),
            ((-1, 4), (0, -1)),
        )
        self.assertEqual(
            oracle.operation_siren_radar_targets("question"),
            ((-1, 4),),
        )
        self.assertEqual(
            oracle.operation_siren_radar_targets("switch"),
            ((0, -1),),
        )

    def test_typed_question_radar_keeps_the_upper_wormhole_not_the_right_buoy(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        root = (
            "OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
            "compass_panel/ring/compass/range/"
        )
        world = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
        )
        wormhole = make_image(
            world
            + "cell_12_4/attachments/event_7000011/icon/model/"
            "chongdong02(Clone)",
            "chongdong42",
        )
        wormhole["flags"] |= 0x10
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    root + "7000011",
                    "guidepost",
                    {
                        "left": 1135.1,
                        "top": 186.0,
                        "right": 1144.9,
                        "bottom": 195.8,
                    },
                ),
                make_image(
                    root + "7000040",
                    "guidepost",
                    {
                        "left": 1170.2,
                        "top": 221.1,
                        "right": 1180.0,
                        "bottom": 230.9,
                    },
                ),
                wormhole,
                make_image(
                    world
                    + "cell_9_6/attachments/event_7000040/icon/model/"
                    "fubiao3(Clone)",
                    "fubiao3",
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.operation_siren_radar_targets("guidepost"),
            ((0, -3), (3, 0)),
        )
        self.assertEqual(
            oracle.operation_siren_radar_targets("question"),
            ((0, -3),),
        )
        self.assertEqual(oracle.operation_siren_radar_targets("switch"), ())

    def test_typed_question_radar_falls_back_to_room_waypoints_without_a_wormhole(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        root = (
            "OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
            "compass_panel/ring/compass/range/"
        )
        world = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    root + "7030051",
                    "guidepost",
                    {"left": 1136.1, "top": 207.5, "right": 1145.9, "bottom": 222.9},
                ),
                make_image(
                    root + "7030011",
                    "guidepost",
                    {"left": 1124.433, "top": 265.833, "right": 1134.233, "bottom": 281.233},
                ),
                make_image(
                    world
                    + "cell_7_6/attachments/event_7030051/icon/model/"
                    "taban_jinzhi(Clone)/taban",
                    "taban01",
                ),
                make_image(
                    world
                    + "cell_12_5/attachments/event_7030011/icon/model/"
                    "fubiao3(Clone)",
                    "fubiao3",
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.operation_siren_radar_targets("guidepost"),
            ((-1, 4), (0, -1)),
        )
        self.assertEqual(
            oracle.operation_siren_radar_targets("question"),
            ((-1, 4), (0, -1)),
        )
        self.assertEqual(
            oracle.operation_siren_radar_targets("switch"),
            ((0, -1),),
        )

    def test_typed_boss_radar_survives_bounded_image_slice(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        oracle = make_oracle(backend)
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "LevelCamera/Canvas/LevelOrigin/top/adapt/right_stage/"
                    "compass_panel/ring/compass/range/7032007",
                    "boss",
                    {
                        "left": 1134.1,
                        "top": 208.45,
                        "right": 1145.9,
                        "bottom": 220.15,
                    },
                )
            ],
        )
        backend.ui["image_truncated"] = True

        self.assertEqual(
            oracle.operation_siren_radar_targets("boss"),
            ((0, -1),),
        )

    def test_adjacent_guidepost_uses_radar_and_selected_fleet_anchors(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/"
                    "fleet_bar/text_selected/x",
                    "3",
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "fleet_3/shadow",
                    "shadow",
                    {"left": 584.0, "top": 319.0, "right": 696.0, "bottom": 401.0},
                ),
                make_image(
                    "OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
                    "compass_panel/ring/compass/range/7000040",
                    "guidepost",
                    {"left": 1135.0, "top": 209.0, "right": 1145.0, "bottom": 219.0},
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "cell_4_16/attachments/event_7000040/char/shadow",
                    "shadow",
                    {"left": 615.0, "top": 275.0, "right": 665.0, "bottom": 305.0},
                ),
            ],
        )
        oracle = make_oracle(backend)

        for image in backend.ui["images"]:
            bounds = image["adb_bounds"]
            image["adb_point"] = {"x": (bounds["left"] + bounds["right"])/2,
                                  "y": (bounds["top"] + bounds["bottom"])/2}
        for row, y in ((5, 360), (4, 290)):
            image = make_image(
                f"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/"
                f"world_quad_{row}_16/walk_quad", "cell_white",
                {"left": 615., "right": 665., "top": y-15., "bottom": y+15.})
            image["adb_point"] = {"x": 640., "y": float(y)}
            backend.ui["images"].append(image)
        backend.ui["image_count"] = len(backend.ui["images"])

        receipt = oracle.click_operation_siren_radar_guidepost((0, -1))

        self.assertEqual(receipt.semantic_id, "os/map/guidepost/relative/0/-1")
        self.assertEqual(backend.taps, [(640, 290)])

        backend.ui["images"].append(copy.deepcopy(backend.ui["images"][3]))
        backend.ui["image_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            oracle.click_operation_siren_radar_guidepost((0, -1))

    def test_fog_guidepost_uses_unique_native_walk_cell_without_model(self):
        backend = FakeBackend([
            make_button("back_button", "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button"),
            make_button("fleet_bar", "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar"),
            make_button("gold", "OverlayCamera/Overlay/UIMain/top/adapt/top_stage/resources/WorldResPanel(Clone)/gold"),
        ])
        def projected(path, sprite, x, y):
            image = make_image(path, sprite, {"left": x-20., "right": x+20.,
                                             "top": y-15., "bottom": y+15.})
            image["adb_point"] = {"x": x, "y": y}
            return image
        root = "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
        backend.ui = make_ui([], images=[
            make_image("root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar/text_selected/x", "1"),
            projected(root+"cells/fleet_1/shadow", "shadow", 640., 360.),
            projected(root+"quads/world_quad_4_4/walk_quad", "cell_white", 640., 360.),
            projected(root+"quads/world_quad_4_5/walk_quad", "cell_white", 742.45, 360.),
            projected("OverlayCamera/Overlay/UIMain/top/adapt/right_stage/compass_panel/ring/compass/range/5403", "guidepost", 1152.667, 226.867),
        ])
        oracle = make_oracle(backend)
        receipt = oracle.click_operation_siren_radar_guidepost((1, 0))
        self.assertEqual(backend.taps, [(742, 360)])
        self.assertTrue(receipt.path.endswith("world_quad_4_5/walk_quad"))
        backend.taps.clear()
        target = backend.ui["images"][3]
        for mutation in ("duplicate", "missing-projection", "foreign-foreground", "blocker"):
            with self.subTest(mutation=mutation):
                saved = copy.deepcopy(backend.ui)
                if mutation == "duplicate":
                    backend.ui["images"].append(copy.deepcopy(target))
                    backend.ui["image_count"] += 1
                elif mutation == "missing-projection":
                    backend.ui["images"][3].pop("adb_point")
                elif mutation == "foreign-foreground":
                    oracle._foreground_component = mock.Mock(return_value="foreign/activity")
                else:
                    oracle._blocking_rules = mock.Mock(return_value=[object()])
                with self.assertRaises(SemanticGateClosed):
                    oracle.click_operation_siren_radar_guidepost((1, 0))
                self.assertEqual(backend.taps, [])
                backend.ui = saved
                oracle._foreground_component = mock.Mock(return_value=oracle.fingerprint.component)
                oracle._blocking_rules = mock.Mock(return_value=[])

    def test_obscure_exit_passage_uses_exact_tip_portal_and_radar_step(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        root = "LevelCamera/Canvas/LevelOrigin/top/"
        backend.ui = make_ui(
            [
                make_text(
                    "卡利比安海C-隐秘海域",
                    root + "adapt/top_stage/title/name",
                ),
                make_text(
                    "从塞壬特殊通行装置离开隐秘海域",
                    root + "adapt/right_stage/tip_word/Text",
                ),
            ],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/"
                    "fleet_bar/text_selected/x",
                    "1",
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "fleet_1/shadow",
                    "shadow",
                    {"left": 584.0, "top": 319.0, "right": 696.0, "bottom": 401.0},
                ),
                make_image(
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "cell_15_14/attachments/event_1000034/icon/model/"
                    "chuansong01(Clone)/Xyz/Ring01/01",
                    "chuansong01",
                ),
                make_image(
                    "LevelCamera/Canvas/LevelOrigin/top/adapt/right_stage/"
                    "compass_panel/ring/compass/range/mark",
                    "boss",
                    {"left": 1146.7, "top": 291.2, "right": 1156.7, "bottom": 301.2},
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.operation_siren_obscure_exit_passage_position(), (15, 14)
        )

        portal = backend.ui["images"][2]
        portal["adb_bounds"] = {
            "left": -20.0, "top": 1450.0, "right": 280.0, "bottom": 1750.0
        }

        def move_portal():
            portal["adb_bounds"] = {
                "left": 260.0, "top": 1210.0, "right": 560.0, "bottom": 1510.0
            }
            backend.ui["generation"] = 11
            backend.snapshot["generation"] = 11
            backend.buttons["generation"] = 11

        backend.on_swipe = move_portal
        swipe = oracle.operation_siren_obscure_exit_camera_swipe()
        self.assertEqual(swipe.semantic_id, "os/map/obscure-exit/swipe")
        self.assertEqual(backend.swipes, [(360, 500, 640, 260, 450)])

        portal["adb_bounds"] = {
            "left": 500.0, "top": 250.0, "right": 700.0, "bottom": 450.0
        }
        receipt = oracle.click_operation_siren_obscure_exit_passage()
        self.assertEqual(receipt.semantic_id, "os/map/obscure-exit/passage")
        self.assertEqual(backend.taps, [(600, 350)])

        backend.ui["texts"][1]["text"] = "离开隐秘海域"
        with self.assertRaisesRegex(SemanticGateClosed, "incomplete"):
            oracle.operation_siren_obscure_exit_passage_position()

        backend.ui["texts"][1]["text"] = "从塞壬特殊通行装置离开隐秘海域"
        backend.ui["images"].pop(2)
        backend.ui["image_count"] -= 1
        self.assertIsNone(oracle.operation_siren_obscure_exit_passage_position())

    def test_relative_grid_rejects_unknown_radar_kind_and_missing_center(self):
        oracle = self._local_map_oracle("1")
        with self.assertRaisesRegex(SemanticGateClosed, "not reviewed"):
            oracle.operation_siren_radar_targets("enemy")
        with self.assertRaisesRegex(SemanticGateClosed, "center grid"):
            oracle.click_operation_siren_relative_grid((0, 0))

    def test_fleet_lock_state_and_click_are_exact(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        oracle = make_oracle(backend)
        path = (
            "LevelCamera/Canvas/LevelOrigin/top/adapt/right_stage/btn_list/"
            "auto_switch/on"
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    path,
                    "auto_switch_on",
                    {"left": 1110, "top": 560, "right": 1170, "bottom": 620},
                )
            ],
        )

        self.assertEqual(oracle.operation_siren_fleet_lock_state(), "on")
        receipt = oracle.click_operation_siren_fleet_lock("on")
        self.assertEqual(receipt.semantic_id, "os/map/fleet-lock/on")
        self.assertEqual(backend.taps, [(1140, 590)])
        with self.assertRaisesRegex(SemanticGateClosed, "changed"):
            oracle.click_operation_siren_fleet_lock("off")

    def test_fleet_selector_open_and_exact_fourth_row_click(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        oracle = make_oracle(backend)
        root = "OverlayCamera/Overlay/UIMain/top/adapt/left_stage/mask/list/"
        rows = ["item", "item (1)", "item (2)", "item (3)"]
        backend.buttons = make_buttons(
            backend.buttons["buttons"]
            + [
                make_button(name, root + name, x=180, y=610 - index * 80)
                for index, name in enumerate(rows)
            ]
        )

        self.assertTrue(oracle.operation_siren_fleet_selector_open())
        receipt = oracle.click_operation_siren_fleet_selector(4)
        self.assertEqual(receipt.semantic_id, "os/map/fleet-selector/4")
        self.assertEqual(backend.taps, [(180, 370)])
        backend.buttons["buttons"].pop()
        backend.buttons["button_count"] -= 1
        with self.assertRaisesRegex(SemanticGateClosed, "incomplete"):
            oracle.operation_siren_fleet_selector_open()
