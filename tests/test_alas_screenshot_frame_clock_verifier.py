import unittest

from scripts.python.verify_alas_screenshot_frame_clock import (
    ScreenshotFrameClockVerificationError,
    assert_normal_screenshot_source_preserved,
    load_patched_screenshot_classes,
)


PRISTINE_SCREENSHOT = '''class Screenshot:
    def screenshot(self):
        self._screenshot_interval.wait()
        self._screenshot_interval.reset()

        for _ in range(2):
            self.image = self.native_capture()
            break

        return self.image
'''

PATCHED_SCREENSHOT = '''class Screenshot:
    def screenshot(self):
        self._screenshot_interval.wait()
        self._screenshot_interval.reset()

        semantic_session = getattr(self, 'semantic_adapter', None)
        if semantic_session is not None:
            frame = semantic_session.refresh_frame()
            self.image = semantic_session.pixel_guard(frame)
            return self.image

        for _ in range(2):
            self.image = self.native_capture()
            break

        return self.image
'''

DEVICE_SOURCE = '''class Device(Screenshot):
    def handle_night_commission(self):
        return False

    def screenshot(self):
        self.stuck_record_check()
        try:
            super().screenshot()
        except RequestHumanTakeover:
            raise
        if self.handle_night_commission():
            super().screenshot()
        return self.image
'''


class ScreenshotFrameClockVerifierTests(unittest.TestCase):
    def test_guard_is_the_only_change_to_normal_screenshot_source(self):
        assert_normal_screenshot_source_preserved(
            PRISTINE_SCREENSHOT,
            PATCHED_SCREENSHOT,
        )
        with self.assertRaisesRegex(
            ScreenshotFrameClockVerificationError,
            "normal ALAS screenshot source changed",
        ):
            assert_normal_screenshot_source_preserved(
                PRISTINE_SCREENSHOT.replace("break", "continue"),
                PATCHED_SCREENSHOT,
            )

    def test_compiled_patched_methods_keep_timer_and_device_call_order(self):
        _, device_class = load_patched_screenshot_classes(
            PATCHED_SCREENSHOT,
            DEVICE_SOURCE,
        )
        events = []

        class Timer:
            def wait(self):
                events.append("wait")

            def reset(self):
                events.append("reset")

        class Session:
            def refresh_frame(self):
                events.append("refresh")
                return "frame-1"

            def pixel_guard(self, frame):
                events.append("guard")
                return "guarded-" + frame

        device = device_class()
        device._screenshot_interval = Timer()
        device.semantic_adapter = Session()
        device.stuck_record_check = lambda: events.append("stuck")
        device.handle_night_commission = lambda: events.append("night") or False

        self.assertEqual(device.screenshot(), "guarded-frame-1")
        self.assertEqual(
            events,
            ["stuck", "wait", "reset", "refresh", "guard", "night"],
        )


if __name__ == "__main__":
    unittest.main()
