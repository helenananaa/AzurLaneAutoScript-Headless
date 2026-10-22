"""Transport regression cases for the oracle."""

import unittest
import pytest
from alas_headless.semantic_oracle import AdbObserverBridge, ObserverTransportError
from tests.semantic_support.observer_fixtures import FakeBackend, PACKAGE, make_oracle
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport
from types import SimpleNamespace
from unittest import mock


@pytest.mark.parametrize('winerror', [1450, 5])
def test_host_spawn_failure_keeps_error_code_without_replaying_input(tmp_path, winerror):
    import json
    from alas_headless.runtime_trace import RuntimeTraceRecorder
    path = tmp_path / 'trace.jsonl'
    trace = RuntimeTraceRecorder(path, enabled=True)
    bridge = AdbObserverBridge('device-1', PACKAGE, trace=trace)
    failure = OSError('private diagnostic must not enter trace')
    failure.winerror = winerror
    with mock.patch('alas_headless.semantic_oracle.subprocess.run', side_effect=failure) as run:
        with pytest.raises(ObserverTransportError) as caught:
            bridge._run(('shell', 'input', 'tap', '12', '34'))
        assert caught.value.__cause__ is failure
        assert run.call_count == 1
        assert ('WinError 1450' in str(caught.value)) == (winerror == 1450)
    trace.close()
    raw = path.read_text(encoding='utf-8')
    assert 'private diagnostic' not in raw
    assert json.loads(raw)['fields']['winerror'] == winerror


@pytest.mark.parametrize('flags,methods', [(15, 15), (31, 15), (15, 31), (0x100F, 0x100F)])
def test_state_read_accepts_additive_publisher_capabilities(flags, methods):
    backend = FakeBackend([])
    backend.snapshot.update(flags=flags, ui_method_mask=methods, future_metadata='ignored')
    assert make_oracle(backend).read_state().generation == 10
    assert backend.taps == []


@pytest.mark.parametrize('field,value', [
    ('flags', 7), ('flags', 0x8000000F), ('flags', -1), ('flags', True),
    ('flags', 0x10000000F), ('ui_method_mask', 7), ('ui_method_mask', '15'),
    ('ui_stage', 99), ('ui_stage', 100.0), ('main_thread', False),
])
def test_incomplete_or_failed_publisher_still_rejects_state(field, value):
    from alas_headless.semantic_oracle import SemanticGateClosed

    backend = FakeBackend([])
    backend.snapshot[field] = value
    with pytest.raises(SemanticGateClosed, match='typed main-thread UI probe is incomplete'):
        make_oracle(backend).read_state()
    assert backend.taps == []


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_adb_utf8_output_is_independent_of_windows_locale(self):
        bridge = AdbObserverBridge('emulator-5554', PACKAGE)
        with mock.patch('alas_headless.semantic_oracle.subprocess.run',
                        return_value=SimpleNamespace(stdout='当前活动\n'.encode('utf-8'))) as run:
            self.assertEqual(bridge._run(('shell', 'dumpsys', 'activity', 'activities')), '当前活动')
        self.assertIs(run.call_args.kwargs['text'], False)

    def test_malformed_adb_output_is_a_classified_transport_failure(self):
        bridge = AdbObserverBridge('emulator-5554', PACKAGE)
        with mock.patch('alas_headless.semantic_oracle.subprocess.run',
                        return_value=SimpleNamespace(stdout=b'\x80')):
            with self.assertRaises(ObserverTransportError):
                bridge._run(('shell', 'dumpsys', 'activity', 'activities'))
    def test_observer_bridge_targets_the_pinned_adb_server(self):
        bridge = AdbObserverBridge(
            "127.0.0.1:5589",
            PACKAGE,
            adb="/runtime/platform-tools/adb",
            adb_server_port=5043,
        )
        completed = SimpleNamespace(stdout=b"device\n")
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
        completed = SimpleNamespace(stdout=b"device\n")
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
