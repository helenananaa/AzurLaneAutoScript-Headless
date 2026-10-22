"""Image input re-reads coherent endpoints before dispatching a single tap."""
import unittest
from unittest.mock import Mock
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_ui, make_toggle,
)
from alas_headless.semantic_oracle import SemanticGateClosed


class ImageInputTransitionTests(unittest.TestCase):
    def test_toggle_pair_keeps_slow_foreground_check_before_dispatch(self):
        backend = FakeBackend([])
        backend.ui = make_ui([], toggles=[make_toggle(
            'root/LevelFleetSelectView(Clone)/mask/list/item1')])
        oracle = make_oracle(backend)
        calls = []
        def foreground():
            calls.append(True)
            if len(calls) > 1:
                backend.ui['generation'] = 13
            return oracle.fingerprint.component
        oracle._foreground_component = foreground
        receipt = oracle.click_toggle('campaign/fleet-preparation/option/1')
        self.assertEqual(receipt.generation, 10)
        self.assertEqual(len(backend.taps), 1)
        backend.ui['generation'] = 10
        backend.taps.clear()
        oracle._foreground_component = Mock(side_effect=[oracle.fingerprint.component, 'other/app'])
        with self.assertRaisesRegex(SemanticGateClosed, 'activity changed before toggle input'):
            oracle.click_toggle('campaign/fleet-preparation/option/1')
        self.assertEqual(backend.taps, [])

    def fixture(self, *, covered=False):
        page = "root/EventUI(Clone)"
        buttons = [make_button("back_btn", page + "/blur_panel/adapt/top/back_btn")]
        if covered:
            buttons.append(make_button("custom_button_1(Clone)",
                "root/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)"))
        backend = FakeBackend(buttons)
        image = make_image(page + "/blur_panel/adapt/left_length/frame/scroll_rect/"
            "tagRoot/daily_btn/selected/Image", "toggle_meiri_sel 1",
            {"left":0,"top":100,"right":100,"bottom":200})
        image.update(raycast_target=True, raycast_top=True)
        return backend, image

    def test_generation_gap_recovers_before_one_input(self):
        backend, image = self.fixture()
        backend.ui_sequence = [make_ui([], images=[image], generation=7),
            make_ui([], images=[image], generation=10)]
        receipt = make_oracle(backend).click_image("commission/nav/daily")
        self.assertEqual(receipt.generation, 10)
        self.assertEqual(backend.taps, [(50,150)])

    def test_persistent_gap_or_foreign_overlay_never_dispatches(self):
        backend, image = self.fixture()
        backend.ui = make_ui([], images=[image], generation=7)
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).click_image("commission/nav/daily")
        self.assertEqual(backend.taps, [])
        backend, image = self.fixture(covered=True)
        backend.ui = make_ui([], images=[image])
        with self.assertRaisesRegex(SemanticGateClosed, "blocked"):
            make_oracle(backend).click_image("commission/nav/daily")
        self.assertEqual(backend.taps, [])

    def test_slow_activity_read_does_not_split_the_input_pair(self):
        backend, image = self.fixture()
        backend.ui = make_ui([], images=[image])
        oracle = make_oracle(backend)
        reads = []
        def foreground():
            reads.append('activity')
            # The later activity lookup takes three publications. It belongs
            # after the coherent pair, immediately before input.
            if len(reads) > 1:
                backend.ui['generation'] = 13
            return oracle.fingerprint.component
        oracle._foreground_component = foreground
        receipt = oracle.click_image('commission/nav/daily')
        self.assertEqual(receipt.generation, 10)
        self.assertEqual(backend.taps, [(50, 150)])

    def test_activity_change_after_pair_still_rejects_input(self):
        backend, image = self.fixture()
        backend.ui = make_ui([], images=[image])
        oracle = make_oracle(backend)
        oracle._foreground_component = Mock(side_effect=[oracle.fingerprint.component, 'other/app'])
        with self.assertRaisesRegex(SemanticGateClosed, 'activity changed before image input'):
            oracle.click_image('commission/nav/daily')
        self.assertEqual(backend.taps, [])
