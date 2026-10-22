"""Opsi globe regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import OperationSirenSemanticOracleTestsSupport
from unittest import mock


class OperationSirenSemanticOracleTests(OperationSirenSemanticOracleTestsSupport, unittest.TestCase):
    def test_globe_entry_returns_to_native_loop_when_meow_confirmation_mounts(self):
        path = 'LevelCamera/Canvas/LevelOrigin/top/adapt/right_stage/btn_list/dock/transport_button'
        backend = FakeBackend([make_button('transport_button', path, raycast_top=None)])
        oracle = make_oracle(backend)
        oracle.operation_siren_state = mock.Mock()
        root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window'
        def mount_prompt(*_):
            backend.snapshot['generation'] = 11
            backend.buttons = make_buttons([
                make_button('custom_button_1(Clone)', root + '/button_container/custom_button_1(Clone)'),
                make_button('custom_button_2(Clone)', root + '/button_container/custom_button_2(Clone)'),
            ], generation=11)
            backend.ui = make_ui([make_text(
                '正在进行搜寻作业的指挥喵将被强制召回！\n是否结束搜寻并离开当前海域？',
                root + '/msg_panel/content')], generation=11)
        backend.on_tap = mount_prompt
        receipt = oracle.click_operation_siren_globe()
        self.assertEqual(receipt.semantic_id, 'os/map/globe')
        self.assertEqual(len(backend.taps), 1)
        self.assertTrue(oracle.operation_siren_exit_prompt_visible())

    def test_globe_unpin_drags_one_unobscured_typed_plane_point(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/"
                    "top_chapter/back_button",
                )
            ]
        )
        pin = make_image(
            "root/OverlayCamera/Overlay/UIMain/top/SVFloatPanel(Clone)/point",
            "click_point_safe",
            {"left": 470, "top": 396, "right": 546, "bottom": 455},
        )
        backend.ui = make_ui([], images=[pin], generation=10)
        backend.ui['globe_geometry'] = dict(status=1, truncated=False, error_count=0,
            camera_path='WorldMap3D/Main Camera', objects=[dict(name='port',
            truncated=False, plane_hit=True, ui_clear=True, ui_top_path='WorldMap3D/entity/Plane',
            plane_instance_id=55, input_point=[508, 426])])

        def unpin():
            backend.buttons = make_buttons(
                backend.buttons["buttons"], generation=13
            )
            backend.ui = make_ui([], images=[], generation=13)
            backend.ui_sequence = [make_ui([], generation=12), make_ui([], generation=13)]

        backend.on_swipe = unpin
        oracle = make_oracle(backend)
        with mock.patch.object(oracle, "operation_siren_globe_state"), mock.patch.object(oracle, "operation_siren_globe_drag_owned", return_value=True):
            receipt = oracle.operation_siren_globe_unpin()

        self.assertEqual(receipt.semantic_id, "os/globe/zone/unpin")
        self.assertEqual(backend.swipes, [(558, 376, 608, 326, 2000)])

    def test_globe_unpin_stops_after_one_unproven_drag(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/"
                    "top_chapter/back_button",
                )
            ]
        )
        pin = make_image(
            "root/OverlayCamera/Overlay/UIMain/top/SVFloatPanel(Clone)/point",
            "click_point_safe",
            {"left": 470, "top": 396, "right": 546, "bottom": 455},
        )
        backend.ui = make_ui([], images=[pin], generation=10)
        backend.ui['globe_geometry'] = dict(status=1, truncated=False, error_count=0,
            camera_path='WorldMap3D/Main Camera', objects=[dict(name='port',
            truncated=False, plane_hit=True, ui_clear=True, ui_top_path='WorldMap3D/entity/Plane',
            plane_instance_id=55, input_point=[508, 426])])
        oracle = make_oracle(backend)
        with mock.patch.object(oracle, "operation_siren_globe_state"), mock.patch.object(oracle, "operation_siren_globe_drag_owned", return_value=True):
            with self.assertRaisesRegex(SemanticGateClosed, "unpin was not proven"):
                oracle.operation_siren_globe_unpin()

        self.assertEqual(len(backend.swipes), 1)
        self.assertEqual(backend.requests.count("GET /v1/ui\n"), 17)

    def test_globe_zone_click_proves_lightweight_typed_mismatch(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/"
                    "top_chapter/back_button",
                )
            ]
        )
        title_path = (
            "root/OverlayCamera/Overlay/UIMain/top/SVFloatPanel(Clone)/point/"
            "line/bg/title/name/subText"
        )
        backend.ui = make_ui(
            [make_text("利维浦-安全海域", title_path)], generation=10
        )

        def select_other_zone():
            backend.ui_sequence = [make_ui(
                [make_text("东大陆架D-普通海域", title_path)], generation=generation
            ) for generation in (11, 11, 12)]

        backend.on_tap = select_other_zone
        oracle = make_oracle(backend)
        with self.assertRaisesRegex(SemanticGateClosed, "projected zone probes are unsupported"):
            oracle.click_operation_siren_globe_zone("port", (944.0, 363.0))
        self.assertEqual(backend.taps, [])

    def test_globe_zone_empty_probe_has_bounded_publication_wait(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/"
                    "top_chapter/back_button",
                )
            ]
        )
        backend.ui = make_ui([], generation=10)
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "projected zone probes are unsupported"):
            oracle.click_operation_siren_globe_zone("zone", (647.0, 355.0))
        self.assertEqual(backend.taps, [])

    def test_mission_overview_is_actionable_without_a_selected_zone_panel(self):
        globe_back = make_button(
            "back_button",
            "root/OverlayCamera/Overlay/UIMain/top/adapt/"
            "top_chapter/back_button",
            raycast_top=None,
        )
        overview = make_button(
            "btn_daily",
            "root/OverlayCamera/Overlay/UIMain/top/adapt/"
            "bottom_chapter/button/btn_daily",
            x=1073,
            y=675,
            raycast_top=None,
        )
        backend = FakeBackend([globe_back, overview])
        backend.ui = make_ui([], generation=10)
        oracle = make_oracle(backend)

        receipt = oracle.click_operation_siren_mission_overview()

        self.assertEqual(receipt.semantic_id, "os/globe/mission-overview")
        self.assertEqual(backend.taps, [(1073, 675)])

        backend.buttons = make_buttons([overview])
        with self.assertRaisesRegex(
            SemanticGateClosed, "operation siren globe is not visible"
        ):
            oracle.click_operation_siren_mission_overview()

    def test_special_zone_post_search_loot_back_is_exact(self):
        root = "root/OverlayCamera/Overlay/UIMain/"
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    root + "top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    root + "top/adapt/left_stage/other/fleet_bar",
                ),
                make_button(
                    "back_button",
                    root + "blur_panel/adapt/top/title/back_button",
                    x=59,
                    y=53,
                ),
                make_button(
                    "item_tpl(Clone)",
                    root
                    + "blur_panel/adapt/shop/frame/scrollview/view/"
                    "item_tpl(Clone)",
                    x=430,
                    y=230,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "加勒比海C-隐秘海域",
                    "root/LevelCamera/Canvas/LevelOrigin/top/adapt/"
                    "top_stage/title/name",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.operation_siren_post_search_loot_visible())
        receipt = oracle.click_operation_siren_post_search_loot_back()
        self.assertEqual(receipt.semantic_id, "os/auto-search/loot/back")
        self.assertEqual(backend.taps, [(59, 53)])

        backend.buttons["buttons"].pop()
        backend.buttons["button_count"] -= 1
        self.assertFalse(oracle.operation_siren_post_search_loot_visible())
