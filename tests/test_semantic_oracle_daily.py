"""Daily regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import Point, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_buttons,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_result_absence_ignores_unrelated_partial_dock_toggles(self):
        backend = FakeBackend([])
        backend.ui = make_ui([])
        backend.ui['toggle_truncated'] = True
        oracle = make_oracle(backend)
        self.assertFalse(oracle.daily_battle_result_visible())
        self.assertFalse(oracle.enabled('overlay/login-data-expired/confirm'))
        with self.assertRaisesRegex(SemanticGateClosed, 'toggle snapshot'):
            _ = oracle.read_ui_state().toggles
        backend.ui['text_truncated'] = True
        with self.assertRaisesRegex(SemanticGateClosed, 'text snapshot'):
            oracle.daily_battle_result_visible()
        self.assertEqual(backend.taps, [])

    def test_daily_battle_result_rejects_ambiguous_or_obscured_target(self):
        path = (
            "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
            "NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn"
        )
        backend = FakeBackend(
            [make_button("confirmBtn", path), make_button("confirmBtn", path)]
        )
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            oracle.click_daily_battle_result()
        self.assertEqual(backend.taps, [])

        backend.buttons = make_buttons(
            [make_button("confirmBtn", path, raycast_top=False)]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click_daily_battle_result()
        self.assertEqual(backend.taps, [])

    def test_daily_stage_receipt_uses_the_same_actionable_frame(self):
        root = (
            "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/desc_panel/main_mask/"
            "main/scrollview/content/stagetpl(Clone)/info"
        )
        button = make_button(
            "info",
            root,
            779.0,
            133.0,
            bounds={"left": 381.0, "top": 133.0, "right": 1187.0, "bottom": 280.0},
        )
        backend = FakeBackend([])
        backend.buttons_sequence = [
            make_buttons([button], generation=31),
            make_buttons([], generation=99),
        ]

        receipt = make_oracle(backend).click_daily_stage(1)

        self.assertEqual(receipt.generation, 31)
        self.assertEqual(len(backend.buttons_sequence), 1)
        self.assertEqual(backend.taps, [(779, 133)])

    def test_selected_daily_stage_is_proved_and_clicked_from_one_frame(self):
        row = (
            "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/desc_panel/main_mask/"
            "main/scrollview/content/stagetpl(Clone)/info"
        )
        selected = "OverlayCamera/Overlay/UIMain/selected/stagetpl/info"
        bounds = {"left": 381.0, "top": 133.0, "right": 1187.0, "bottom": 280.0}
        backend = FakeBackend(
            [
                make_button("info", row, 779.0, 200.0, bounds=bounds),
                make_button("info", selected, 779.0, 200.0, bounds=bounds),
            ]
        )

        receipt = make_oracle(backend).click_daily_selected_stage(1)

        self.assertEqual(receipt.semantic_id, "daily/stage/1/selected")
        self.assertEqual(backend.requests.count("GET /v1/state\n"), 1)
        self.assertEqual(backend.taps, [(779, 200)])

    def test_daily_stage_requires_a_topmost_event_point(self):
        root = (
            "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/desc_panel/main_mask/"
            "main/scrollview/content/stagetpl(Clone)/info"
        )
        backend = FakeBackend(
            [
                make_button(
                    "info",
                    root,
                    779.0,
                    133.0,
                    bounds={
                        "left": 381.0,
                        "top": 133.0,
                        "right": 1187.0,
                        "bottom": 280.0,
                    },
                    raycast_top=True,
                ),
                make_button(
                    "info",
                    root,
                    779.0,
                    293.0,
                    bounds={
                        "left": 381.0,
                        "top": 293.0,
                        "right": 1187.0,
                        "bottom": 440.0,
                    },
                    raycast_top=False,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.daily_stage_available(1))
        self.assertFalse(oracle.daily_stage_available(2))
        receipt = oracle.click_daily_stage(1)

        self.assertEqual(receipt.semantic_id, "daily/stage/1")
        self.assertEqual(receipt.point, Point(779.0, 133.0))
        self.assertEqual(backend.taps, [(779, 133)])

    def test_daily_current_kind_uses_centered_card_title_sprite(self):
        root = "UICamera/Canvas/UIMain/DailyLevelUI(Clone)"
        card = root + "/list_panel/list/601"
        backend = FakeBackend(
            [
                make_button("back_button", root + "/blur_panel/adapt/top/back_button"),
                make_button(
                    "601",
                    card,
                    x=636.0,
                    y=384.0,
                    bounds={"left": 515.0, "top": 102.0, "right": 758.0, "bottom": 666.0},
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [], images=[make_image(card + "/icon/card/title", "zhanshuzuanyan_zi")]
        )

        self.assertEqual(make_oracle(backend).daily_current_kind(), "tactical_training")

    def test_daily_expanded_stage_uses_exact_normal_and_bulk_skip_buttons(self):
        root = "OverlayCamera/Overlay/UIMain/selected/stagetpl/quickly/bg/"
        backend = FakeBackend(
            [
                make_button("challenge", root + "challenge", 484.0, 322.0),
                make_button("once", root + "once", 900.0, 322.0),
                make_button("mult", root + "mult", 1078.0, 322.0),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.daily_run_choice_visible("normal"))
        self.assertTrue(oracle.daily_run_choice_visible("skip"))
        normal = oracle.click_daily_run_choice("normal")
        skip = oracle.click_daily_run_choice("skip")

        self.assertEqual(normal.path, root + "challenge")
        self.assertEqual(skip.path, root + "mult")
        self.assertEqual(backend.taps, [(484, 322), (1078, 322)])

    def test_daily_precombat_reads_and_moves_typed_fleet_on_ui_origin(self):
        root = "UICamera/Canvas/UIOrigin/PreCombatUI(Clone)"
        backend = FakeBackend(
            [
                make_button("start", root + "/adapt/right/start", raycast_top=None),
                make_button("nextPage", root + "/adapt/middle/nextPage", x=915.0, y=340.0, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [make_text("1", root + "/adapt/middle/fleet_info/fleet_number")]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.daily_precombat_visible())
        self.assertEqual(oracle.daily_fleet_index(), 1)
        receipt = oracle.click_daily_fleet("next")
        self.assertEqual(receipt.semantic_id, "daily/fleet/next")
        self.assertEqual(backend.taps, [(915, 340)])
