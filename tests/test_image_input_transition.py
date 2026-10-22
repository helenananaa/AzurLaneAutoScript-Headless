"""Image input re-reads coherent endpoints before dispatching a single tap."""
import unittest
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_ui,
)
from alas_headless.semantic_oracle import SemanticGateClosed


class ImageInputTransitionTests(unittest.TestCase):
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
