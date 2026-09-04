"""Exercise regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_exercise_page_and_remaining_require_exact_surface(self):
        page = "root/UICamera/Canvas/UIMain/MilitaryExerciseUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "backBtn", page + "blur_panel/adapt/top/backBtn", raycast_top=None
                ),
                *[
                    make_button(
                        "rivaltpl_{0}".format(index),
                        page + "center/rival_list/rivaltpl_{0}".format(index),
                        raycast_top=None,
                    )
                    for index in range(1, 5)
                ],
            ]
        )
        backend.ui = make_ui([make_text("8/10", page + "center/season_info/count")])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.exercise_page_visible())
        self.assertEqual(oracle.exercise_remaining(), 8)

        backend.ui["texts"][0]["text"] = "剩余八次"
        self.assertFalse(oracle.exercise_page_visible())
        with self.assertRaisesRegex(SemanticGateClosed, "malformed"):
            oracle.exercise_remaining()

    def test_exercise_typed_period_power_and_partial_fleet_levels(self):
        page = "root/UICamera/Canvas/UIMain/MilitaryExerciseUI(Clone)/"
        buttons = [
            make_button("backBtn", page + "blur_panel/adapt/top/backBtn", raycast_top=None),
            *[
                make_button(
                    "rivaltpl_{0}".format(index),
                    page + "center/rival_list/rivaltpl_{0}".format(index),
                    raycast_top=None,
                )
                for index in range(1, 5)
            ],
        ]
        texts = [
            make_text("6/10", page + "center/season_info/count"),
            make_text("3", page + "center/season_info/left_time_container/day"),
            make_text("10:58:27", page + "center/season_info/left_time_container/time"),
        ]
        for index, (main, vanguard) in enumerate(
            ((8669, 8484), (8627, 9217), (7661, 6204), (5306, 5166)), start=1
        ):
            prefix = (
                page + "center/rival_list/rivaltpl_{0}/comprehensive_panel/"
                "comprehensive/"
            ).format(index)
            texts.extend((
                make_text(str(main), prefix + "main_fleet/value"),
                make_text(str(vanguard), prefix + "vanguard_fleet/value"),
            ))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts)
        oracle = make_oracle(backend)

        self.assertEqual(oracle.exercise_period_remaining_text(), "3d10:58:27")
        self.assertEqual(oracle.exercise_opponent_power(4), (5306, 5166))

        detail = "root/OverlayCamera/Overlay/UIMain/RivalInfoUI(Clone)/"
        backend.buttons = make_buttons([
            make_button("bg", detail + "bg", raycast_top=None),
            make_button("start_btn", detail + "ships_container/start_btn", raycast_top=None),
        ])
        backend.ui = make_ui([
            make_text("garbled-title", detail + "info/title_miex"),
            make_text(
                "110", detail + "ships_container/ships/main/ShipCardTpl(Clone)/"
                "content/dockyard/lv/Text",
                bounds={"left": 130, "top": 259, "right": 188, "bottom": 280},
            ),
            make_text(
                "125", detail + "ships_container/ships/vanguard/ShipCardTpl(Clone)/"
                "content/dockyard/lv/Text",
                bounds={"left": 832, "top": 259, "right": 890, "bottom": 280},
            ),
        ])
        self.assertTrue(oracle.exercise_opponent_detail_visible())
        self.assertEqual(oracle.exercise_opponent_levels(), (110, 0, 0, 125, 0, 0))

    def test_exercise_pause_leave_and_quit_confirmation_are_exact(self):
        pause = make_button(
            "PauseBtn",
            "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn",
            raycast_top=None,
        )
        leave_backend = FakeBackend([
            pause,
            make_button(
                "leave",
                "root/OverlayCamera/Overlay/UIMain/Msgbox/window/"
                "button_container/leave",
                raycast_top=None,
            ),
        ])
        leave_oracle = make_oracle(leave_backend)
        self.assertTrue(leave_oracle.exercise_combat_pause_menu_visible())
        leave_receipt = leave_oracle.click_exercise_combat_leave()
        self.assertEqual(leave_receipt.semantic_id, "exercise/combat/leave")
        self.assertEqual(len(leave_backend.taps), 1)

        confirm_backend = FakeBackend([
            pause,
            make_button(
                "custom_button_3(Clone)",
                "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
                "button_container/custom_button_3(Clone)",
                raycast_top=None,
            ),
            make_button(
                "custom_button_1(Clone)",
                "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
                "button_container/custom_button_1(Clone)",
                raycast_top=True,
            ),
        ])
        confirm_backend.ui = make_ui([
            make_text(
                "confirm quit",
                "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
                "msg_panel/content",
            )
        ])
        confirm_oracle = make_oracle(confirm_backend)
        self.assertTrue(confirm_oracle.exercise_combat_quit_confirm_visible())
        confirm_receipt = confirm_oracle.click_exercise_combat_quit_confirm()
        self.assertEqual(
            confirm_receipt.semantic_id, "exercise/combat/quit-confirm"
        )
        self.assertEqual(len(confirm_backend.taps), 1)
