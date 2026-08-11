import unittest
from unittest import mock

from alas_headless import (
    AlasSemanticSession,
    PINNED_CN_GAME_FINGERPRINT,
    SemanticGateClosed,
)
from alas_headless.adapter import (
    AdbRuntimeHandle,
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


class SessionRuntimeHandleTests(unittest.TestCase):
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
        self.assertIs(adapter.oracle._tap.__self__, handle)
        self.assertIs(adapter.oracle._swipe.__self__, handle)
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
