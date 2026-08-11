import copy
import unittest
from unittest import mock

from alas_headless import (
    AlasSemanticSession,
    PINNED_CN_GAME_FINGERPRINT,
    SemanticGateClosed,
)
from alas_headless.adapter import (
    AdbRuntimeHandle,
    StaleFrameError,
    semantic_runtime_fingerprint_sha256,
)
from alas_headless.semantic_oracle import ObserverTransportError


REVISION = "be80ce591a481c12d60c50d6040d40c035b40a2b"
PACKAGE = "com.bilibili.azurlane"
COMPONENT = "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"


def expected_fingerprint():
    return semantic_runtime_fingerprint_sha256(
        package=PACKAGE,
        component=COMPONENT,
        driver_revision=REVISION,
        game_fingerprint=PINNED_CN_GAME_FINGERPRINT,
    )


class FakeRuntimeHandle:
    def __init__(self, fingerprint_sha256=None):
        self.fingerprint_sha256 = (
            expected_fingerprint()
            if fingerprint_sha256 is None
            else fingerprint_sha256
        )
        self.pid = 4242
        self.requests = []
        self.foreground_calls = 0
        self.taps = []
        self.swipes = []

    def observer_request(self, request_line):
        self.requests.append(request_line)
        return {"status": "unused-in-open"}

    def foreground_component(self):
        self.foreground_calls += 1
        return COMPONENT

    def tap(self, x, y):
        self.taps.append((x, y))

    def swipe(self, x1, y1, x2, y2, duration_ms):
        self.swipes.append((x1, y1, x2, y2, duration_ms))


class FrameRuntimeHandle(FakeRuntimeHandle):
    def __init__(self):
        super().__init__()
        self.generation = 10

    def observer_request(self, request_line):
        self.requests.append(request_line)
        identity = {
            "protocol_schema": "alas-headless.observer/v1",
            "status": "ok",
            "package": PACKAGE,
            "pid": self.pid,
            "peer_uid": 2000,
            "driver_revision": REVISION,
            "generation": self.generation,
            "age_ms": 20,
        }
        if request_line == "GET /v1/state\n":
            snapshot = dict(
                identity,
                snapshot_schema=1,
                main_thread=True,
                flags=15,
                ui_stage=100,
                ui_method_mask=15,
                width=1280,
                height=720,
                scene_handle=-76,
            )
            records = [
                {
                    "name": "LoginUI2(Clone)",
                    "path": "UICamera/Canvas/UIMain/LoginUI2(Clone)",
                    "active_in_hierarchy": True,
                    "active_and_enabled": True,
                    "interactable": True,
                    "raycast_top": True,
                    "adb_point": {"x": 640.0, "y": 360.0},
                    "adb_bounds": {
                        "left": 600.0,
                        "top": 330.0,
                        "right": 680.0,
                        "bottom": 390.0,
                    },
                }
            ]
            button_state = dict(
                identity,
                semantic_schema="alas-headless.buttons/v1",
                schema=1,
                button_count=1,
                truncated=False,
                error_count=0,
                buttons=records,
            )
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": copy.deepcopy(snapshot),
                "buttons": copy.deepcopy(button_state),
            }
        if request_line == "GET /v1/ui\n":
            return dict(
                identity,
                semantic_schema="alas-headless.ui/v1",
                schema=1,
                method_mask=15,
                toggle_count=0,
                text_count=0,
                image_count=0,
                toggle_truncated=False,
                text_truncated=False,
                image_truncated=False,
                error_count=0,
                skipped_count=0,
                toggles=[],
                texts=[],
                images=[],
            )
        raise AssertionError("unexpected observer request: {0}".format(request_line))


class SessionRuntimeHandleTests(unittest.TestCase):
    def test_login_reads_require_refresh_and_reuse_one_frame_acquisition(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()

        with self.assertRaises(StaleFrameError):
            adapter.appear("LOGIN_CHECK")
        self.assertEqual(handle.requests, [])

        first = session.refresh_frame()
        self.assertTrue(adapter.appear("LOGIN_CHECK"))
        self.assertTrue(adapter.match_template_color("LOGIN_CHECK"))
        self.assertFalse(adapter.appear("LOGIN_ANNOUNCE"))
        self.assertEqual(
            handle.requests,
            ["GET /v1/state\n", "GET /v1/ui\n"],
        )
        self.assertIs(session._frame_clock.borrow(), first)

        handle.generation = 11
        second = session.refresh_frame()
        self.assertEqual(second.generation, 11)
        self.assertNotEqual(second.frame_id, first.frame_id)
        self.assertEqual(len(handle.requests), 4)

    def test_session_close_clears_current_frame(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        session.refresh_frame()
        frame_clock = session._frame_clock
        session.close()

        self.assertIsNone(session._frame_clock)
        with self.assertRaises(StaleFrameError):
            frame_clock.borrow()

    def test_live_input_invalidates_frame_before_runtime_tap(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()
        frame = session.refresh_frame()

        receipt = adapter.click("LOGIN_CHECK")

        self.assertEqual(receipt.semantic_id, "login/enter")
        self.assertEqual(handle.taps, [(640, 360)])
        self.assertEqual(
            handle.requests,
            ["GET /v1/state\n", "GET /v1/ui\n"],
        )
        with self.assertRaises(StaleFrameError):
            session._frame_clock.borrow()
        with self.assertRaises(StaleFrameError):
            session.refresh_frame()
        handle.generation = frame.generation + 1
        self.assertEqual(session.refresh_frame().generation, 11)

    def test_live_input_rechecks_frame_age_before_runtime_tap(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()
        frame = session.refresh_frame()
        frame_clock = session._frame_clock
        clock_reads = iter(
            (
                frame.captured_monotonic_ns,
                frame.captured_monotonic_ns,
                frame.captured_monotonic_ns
                + int((frame_clock._maximum_age_ms + 1) * 1_000_000),
            )
        )
        frame_clock._monotonic_ns = lambda: next(clock_reads)

        with self.assertRaises(StaleFrameError):
            adapter.click("LOGIN_CHECK")

        self.assertEqual(handle.taps, [])
        self.assertIsNone(frame_clock.current_frame_id)

    def test_deliberate_refresh_records_the_frame_transition(self):
        handle = FrameRuntimeHandle()
        trace = mock.Mock()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
            trace=trace,
        )

        first = session.refresh_frame()
        handle.generation = 11
        second = session.refresh_frame()

        frame_events = [
            call
            for call in trace.emit.call_args_list
            if call.args and call.args[0] == "semantic.frame.refresh"
        ]
        self.assertEqual(len(frame_events), 2)
        self.assertEqual(
            frame_events[0].kwargs["fields"],
            {
                "previous_frame_id": None,
                "frame_id": first.frame_id,
                "generation": 10,
            },
        )
        self.assertEqual(
            frame_events[1].kwargs["fields"],
            {
                "previous_frame_id": first.frame_id,
                "frame_id": second.frame_id,
                "generation": 11,
            },
        )

    def test_explicit_handle_path_wires_only_the_protocol(self):
        handle = FakeRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )

        adapter = session.open()

        self.assertIs(session.runtime_handle, handle)
        self.assertFalse(hasattr(session, "bridge"))
        self.assertIs(adapter.oracle._request.__self__, handle)
        self.assertIs(adapter.oracle._foreground_component.__self__, handle)
        self.assertTrue(callable(adapter.oracle._tap))
        self.assertTrue(callable(adapter.oracle._swipe))
        self.assertEqual(adapter.oracle.fingerprint.expected_pid, 4242)
        self.assertEqual(handle.requests, [])

    def test_fake_handle_path_never_invokes_subprocess(self):
        handle = FakeRuntimeHandle()
        with mock.patch("alas_headless.semantic_oracle.subprocess.run") as run:
            session = AlasSemanticSession(
                driver_revision=REVISION,
                runtime_handle=handle,
            )
            first = session.open()
            self.assertIs(session.open(), first)
            session.close()

        run.assert_not_called()
        self.assertIsNone(session.adapter)
        self.assertIs(session.runtime_handle, handle)

    def test_explicit_handle_rejects_conflicting_adb_arguments(self):
        handle = FakeRuntimeHandle()
        conflicts = (
            {"serial": "device-1"},
            {"adb": "custom-adb"},
            {"adb_command_timeout_seconds": 11},
        )
        for values in conflicts:
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, "conflicts with ADB"):
                    AlasSemanticSession(
                        driver_revision=REVISION,
                        runtime_handle=handle,
                        **values,
                    )

    def test_handle_fingerprint_mismatch_fails_before_observer_or_input(self):
        handle = FakeRuntimeHandle("b" * 64)
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )

        with self.assertRaisesRegex(
            SemanticGateClosed,
            "runtime handle fingerprint changed",
        ):
            session.open()

        self.assertIsNone(session.adapter)
        self.assertEqual(handle.requests, [])
        self.assertEqual(handle.foreground_calls, 0)
        self.assertEqual(handle.taps, [])
        self.assertEqual(handle.swipes, [])

    def test_explicit_handle_pid_change_fails_closed_after_open(self):
        handle = FakeRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        handle.pid = 4243

        with self.assertRaisesRegex(SemanticGateClosed, "PID changed"):
            adapter._package_gate()

    def test_legacy_environment_path_builds_one_adb_wrapper_lazily(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": REVISION,
        }
        with mock.patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("device-1")
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge
        self.assertIsNone(session.runtime_handle)

        def mark_open():
            bridge.pid = 4242
            return bridge

        with mock.patch.object(
            bridge,
            "open",
            side_effect=mark_open,
        ) as open_bridge, mock.patch.object(
            bridge,
            "require_package_fingerprint",
            return_value=PINNED_CN_GAME_FINGERPRINT,
        ) as require_package:
            first = session.open()
            self.assertIs(session.open(), first)

        self.assertIsInstance(session.runtime_handle, AdbRuntimeHandle)
        open_bridge.assert_called_once_with()
        require_package.assert_called_once_with(PINNED_CN_GAME_FINGERPRINT)

    def test_legacy_partial_open_closes_forwarding_and_clears_state(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge

        def fail_after_forward():
            bridge.pid = 4242
            bridge.port = 17001
            raise ObserverTransportError("scripted partial open")

        with mock.patch.object(
            bridge,
            "open",
            side_effect=fail_after_forward,
        ), mock.patch.object(bridge, "_run", return_value="") as run:
            with self.assertRaisesRegex(ObserverTransportError, "partial open"):
                session.open()

        run.assert_called_once_with(("forward", "--remove", "tcp:17001"))
        self.assertIsNone(bridge.port)
        self.assertIsNone(bridge.transport)
        self.assertIsNone(session.runtime_handle)
        self.assertIsNone(session.adapter)


if __name__ == "__main__":
    unittest.main()
