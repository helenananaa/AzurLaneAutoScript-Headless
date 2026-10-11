"""Mail regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import Point
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_text,
    make_toggle,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_empty_probe_yields_during_known_manager_mount_without_granting_input(self):
        from unittest.mock import Mock
        from alas_headless.semantic_oracle import SemanticGateClosed
        page = make_button('back_btn', 'root/MailUI(Clone)/adapt/CommonTitleAndBack/back_btn', raycast_top=False)
        # The real manager can cover MailUI before its controls are ready.
        manager = make_button('btn_get', 'root/MailMgrMsgboxUI(Clone)/window/button_container/btn_get')
        manager['interactable'] = False
        backend = FakeBackend([page, manager])
        oracle = make_oracle(backend)
        oracle.read_text_state = Mock(side_effect=AssertionError('covered counter must not be read'))
        self.assertFalse(oracle.mail_is_empty())
        oracle.read_text_state.assert_not_called()
        self.assertFalse(oracle.enabled('mail/manage/claim'))
        with self.assertRaises(SemanticGateClosed):
            oracle.click('mail/manage/claim')
        self.assertEqual(backend.taps, [])

    def test_empty_probe_yields_to_manager_in_same_snapshot(self):
        from alas_headless.semantic_oracle import SemanticGateClosed
        from unittest.mock import Mock
        page = make_button('back_btn', 'root/MailUI(Clone)/adapt/CommonTitleAndBack/back_btn', 51, 49, raycast_top=False)
        manager = make_button('btnBack', 'root/MailMgrMsgboxUI(Clone)/window/top/btnBack', 908, 153)
        backend = FakeBackend([page, manager])
        oracle = make_oracle(backend)
        oracle.read_text_state = Mock(side_effect=AssertionError('covered counter must not be read'))
        self.assertFalse(oracle.mail_is_empty())
        oracle.read_text_state.assert_not_called()
        self.assertEqual(backend.taps, [])

        from tests.semantic_support.observer_fixtures import make_buttons
        # A foreign overlay and an ambiguous manager cannot prove this miss.
        for buttons in ([page, manager, manager],
                        [page, manager, make_button('confirm', 'root/Msgbox(Clone)/window/btn_confirm', 640, 400)]):
            backend.buttons = make_buttons(buttons)
            with self.assertRaises(SemanticGateClosed):
                oracle.mail_is_empty()
        self.assertEqual(backend.taps, [])

    def test_duplicate_mail_toggle_paths_are_disambiguated_by_child_sprite(self):
        path = (
            "root/MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/"
            "content/toggle_tpl(Clone)"
        )
        gold_bounds = {"left": 558, "top": 390, "right": 639, "bottom": 431}
        oil_bounds = {"left": 678, "top": 390, "right": 759, "bottom": 431}
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(path, x=598, y=410, bounds=gold_bounds),
                make_toggle(path, x=718, y=410, bounds=oil_bounds),
            ],
            images=[
                make_image(
                    path + "/Image",
                    "gold",
                    {"left": 599, "top": 394, "right": 632, "bottom": 427},
                ),
                make_image(
                    path + "/Image",
                    "oil",
                    {"left": 719, "top": 394, "right": 752, "bottom": 427},
                ),
            ],
        )
        oracle = make_oracle(backend)

        receipt = oracle.click_toggle("mail/manage/oil")

        self.assertEqual(receipt.point, Point(718, 410))
        self.assertEqual(backend.taps, [(718, 410)])

    def test_mail_empty_uses_explicit_typed_counter(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/MailUI(Clone)/adapt/CommonTitleAndBack/back_btn",
                    51,
                    49,
                )
            ]
        )
        counter_path = (
            "root/MailUI(Clone)/adapt/main/content/left/left_content/top/count"
        )
        backend.ui = make_ui(
            [make_text("<color=#fff>0</color>/<color=#222>100</color>", counter_path)]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.mail_count(), (0, 100))
        self.assertTrue(oracle.mail_is_empty())

        backend.ui = make_ui([make_text("59/100", counter_path)])
        self.assertFalse(oracle.mail_is_empty())
