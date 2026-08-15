import unittest
from unittest import mock

from alas_headless.adapter import (
    AdbRuntimeHandle,
    RuntimeHandlePort,
    semantic_runtime_fingerprint_sha256,
)
from alas_headless.semantic_oracle import (
    AdbObserverBridge,
    ObserverTransportError,
)


SHA_LOWER = "a" * 64


class FakeTransport:
    def __init__(self, response=None):
        self.response = response if response is not None else {"status": "ok"}
        self.requests = []

    def request(self, request_line):
        self.requests.append(request_line)
        return self.response


class AdbRuntimeHandleTests(unittest.TestCase):
    def make_bridge(self):
        return AdbObserverBridge("device-1", "com.example.game")

    def make_handle(self):
        bridge = self.make_bridge()
        bridge.pid = 4242
        return bridge, AdbRuntimeHandle(
            bridge,
            fingerprint_sha256=SHA_LOWER,
        )

    def test_wraps_exact_bridge_and_satisfies_runtime_protocol(self):
        bridge, handle = self.make_handle()

        self.assertIsInstance(handle, RuntimeHandlePort)
        self.assertEqual(handle.fingerprint_sha256, SHA_LOWER)
        self.assertEqual(handle.pid, 4242)
        self.assertEqual(bridge.serial, "device-1")
        self.assertEqual(bridge.package, "com.example.game")

    def test_constructor_rejects_non_bridge_and_noncanonical_fingerprint(self):
        with self.assertRaisesRegex(TypeError, "AdbObserverBridge"):
            AdbRuntimeHandle(object(), fingerprint_sha256=SHA_LOWER)

        bridge = self.make_bridge()
        for value in (None, "", "a" * 63, "A" * 64, "g" * 64):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    AdbRuntimeHandle(bridge, fingerprint_sha256=value)

    def test_pid_requires_an_exact_positive_attached_process(self):
        bridge = self.make_bridge()
        handle = AdbRuntimeHandle(bridge, fingerprint_sha256=SHA_LOWER)

        for value in (None, True, 0, -1, "4242"):
            with self.subTest(value=value):
                bridge.pid = value
                with self.assertRaisesRegex(
                    ObserverTransportError,
                    "no attached game PID",
                ):
                    _ = handle.pid

    def test_observer_request_delegates_without_copying_the_response(self):
        bridge, handle = self.make_handle()
        response = {"status": "ok", "generation": 17}
        transport = FakeTransport(response)
        bridge.transport = transport

        actual = handle.observer_request("GET /v1/state\n")

        self.assertIs(actual, response)
        self.assertEqual(transport.requests, ["GET /v1/state\n"])

    def test_closed_bridge_fails_without_open_or_reconnect_attempt(self):
        bridge, handle = self.make_handle()
        with mock.patch.object(
            bridge,
            "_run",
            side_effect=AssertionError("unexpected ADB command"),
        ):
            with self.assertRaisesRegex(ObserverTransportError, "not open"):
                handle.observer_request("GET /v1/state\n")

        self.assertIsNone(bridge.transport)
        self.assertIsNone(bridge.port)

    def test_foreground_tap_and_swipe_preserve_exact_bridge_calls(self):
        bridge, handle = self.make_handle()
        with mock.patch.object(
            bridge,
            "_run",
            side_effect=(
                "topResumedActivity: ActivityRecord u0 com.example.game/.Main",
                "",
                "",
            ),
        ) as run:
            self.assertEqual(
                handle.foreground_component(),
                "com.example.game/.Main",
            )
            handle.tap(12, 34)
            handle.swipe(1, 2, 3, 4, 500)

        self.assertEqual(
            run.call_args_list,
            [
                mock.call(
                    ("shell", "dumpsys", "activity", "activities"),
                    timeout_seconds=30.0,
                ),
                mock.call(("shell", "input", "tap", "12", "34")),
                mock.call(
                    (
                        "shell",
                        "input",
                        "swipe",
                        "1",
                        "2",
                        "3",
                        "4",
                        "500",
                    )
                ),
            ],
        )
        self.assertEqual(
            [
                bridge._classify_adb_operation(call.args[0])
                for call in run.call_args_list
            ],
            ["foreground-activity", "input-tap", "input-swipe"],
        )

    def test_bridge_errors_propagate_without_translation(self):
        bridge, handle = self.make_handle()
        failure = ObserverTransportError("ADB command failed")
        with mock.patch.object(bridge, "tap", side_effect=failure):
            with self.assertRaises(ObserverTransportError) as caught:
                handle.tap(1, 2)
        self.assertIs(caught.exception, failure)

    def test_handle_exposes_no_backend_or_bridge_lifecycle_operations(self):
        _, handle = self.make_handle()

        for name in (
            "bridge",
            "open",
            "close",
            "provision",
            "start",
            "stop",
            "reconnect",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(handle, name))

    def test_runtime_identity_depends_on_abi_not_game_version_or_hash(self):
        common = {
            "package": "com.example.game",
            "component": "com.example.game/.Main",
            "driver_revision": "b" * 40,
        }

        x86_64 = semantic_runtime_fingerprint_sha256(
            **common,
            required_primary_abi="x86_64",
        )
        arm64 = semantic_runtime_fingerprint_sha256(
            **common,
            required_primary_abi="arm64-v8a",
        )

        self.assertRegex(x86_64, r"^[0-9a-f]{64}$")
        self.assertNotEqual(x86_64, arm64)
        with self.assertRaisesRegex(ValueError, "primary ABI"):
            semantic_runtime_fingerprint_sha256(
                **common,
                required_primary_abi="",
            )


if __name__ == "__main__":
    unittest.main()
