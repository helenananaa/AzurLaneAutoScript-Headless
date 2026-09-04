"""Transport regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.semantic_support.observer_fixtures import FakeBackend, PACKAGE, make_oracle
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport
from types import SimpleNamespace
from unittest import mock


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_observer_bridge_targets_the_pinned_adb_server(self):
        bridge = AdbObserverBridge(
            "127.0.0.1:5589",
            PACKAGE,
            adb="/runtime/platform-tools/adb",
            adb_server_port=5043,
        )
        completed = SimpleNamespace(stdout="device\n")
        with mock.patch(
            "alas_headless.semantic_oracle.subprocess.run",
            return_value=completed,
        ) as run:
            self.assertEqual(bridge._run(("get-state",)), "device")
        self.assertEqual(
            run.call_args.args[0],
            [
                "/runtime/platform-tools/adb",
                "-P",
                "5043",
                "-s",
                "127.0.0.1:5589",
                "get-state",
            ],
        )

    def test_observer_bridge_uses_only_its_configured_adb_server(self):
        completed = SimpleNamespace(stdout="device\n")
        with mock.patch(
            "alas_headless.semantic_oracle.subprocess.run",
            return_value=completed,
        ) as run:
            bridge = AdbObserverBridge(
                "device-1",
                PACKAGE,
                adb="owned-adb",
                adb_server_port=5044,
            )
            self.assertEqual(bridge._run(("get-state",)), "device")

        self.assertEqual(
            run.call_args.args[0],
            [
                "owned-adb",
                "-P",
                "5044",
                "-s",
                "device-1",
                "get-state",
            ],
        )
        with self.assertRaisesRegex(ValueError, "ADB server port"):
            AdbObserverBridge("device-1", PACKAGE, adb_server_port=65536)

    def test_read_state_uses_atomic_endpoint_and_falls_back_for_old_observer(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)
        oracle.read_state()
        self.assertEqual(backend.requests, ["GET /v1/state\n"])

        legacy = FakeBackend([])
        legacy.support_state = False
        make_oracle(legacy).read_state()
        self.assertEqual(
            legacy.requests,
            ["GET /v1/state\n", "GET /v1/snapshot\n", "GET /v1/buttons\n"],
        )
