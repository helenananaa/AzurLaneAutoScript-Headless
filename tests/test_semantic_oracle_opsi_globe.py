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
    def test_globe_unpin_drags_exact_selected_zone_point(self):
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

        def unpin():
            backend.buttons = make_buttons(
                backend.buttons["buttons"], generation=12
            )
            backend.ui = make_ui([], images=[], generation=12)

        backend.on_swipe = unpin
        oracle = make_oracle(backend)
        with mock.patch.object(oracle, "operation_siren_globe_state"):
            receipt = oracle.operation_siren_globe_unpin()

        self.assertEqual(receipt.semantic_id, "os/globe/zone/unpin")
        self.assertEqual(backend.swipes, [(508, 426, 476, 402, 150)])

    def test_globe_unpin_has_a_four_gesture_fail_closed_bound(self):
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
        oracle = make_oracle(backend)
        with mock.patch.object(oracle, "operation_siren_globe_state"):
            with self.assertRaisesRegex(SemanticGateClosed, "unpin was not proven"):
                oracle.operation_siren_globe_unpin()

        self.assertEqual(len(backend.swipes), 4)
        self.assertEqual(backend.requests.count("GET /v1/ui\n"), 69)

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
        receipt = oracle.click_operation_siren_globe_zone(
            "圣彼得堡", (944.0, 363.0)
        )

        self.assertEqual(receipt.semantic_id, "os/globe/zone/select-mismatch")
        self.assertEqual(receipt.generation, 12)
        self.assertEqual(backend.taps, [(944, 363)])
        self.assertEqual(backend.requests.count("GET /v1/state\n"), 2)
        self.assertEqual(backend.requests.count("GET /v1/ui\n"), 4)
        self.assertEqual(backend.foreground_requests, 4)

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

        with self.assertRaisesRegex(
            SemanticGateClosed, "zone selection was not proven"
        ):
            oracle.click_operation_siren_globe_zone(
                "西大陆架D", (647.0, 355.0)
            )

        self.assertEqual(backend.taps, [(647, 355)])
        self.assertEqual(backend.requests.count("GET /v1/ui\n"), 25)

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
