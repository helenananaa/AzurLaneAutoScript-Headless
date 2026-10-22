import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import AdbObserverBridge, ObserverTransportError
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, COMPONENT, PACKAGE


def daemon_error():
    return subprocess.CalledProcessError(1, ['adb'], stderr=b'* daemon still not running\nadb.exe: cannot connect to daemon at tcp:5037')


def response(component=COMPONENT):
    return SimpleNamespace(stdout=('topResumedActivity: ActivityRecord{abc u0 '+component+' t7}').encode('utf-8'))


@pytest.mark.parametrize('error', [daemon_error(), subprocess.TimeoutExpired(['adb'], 30)])
def test_retry_only_read_query_on_same_configured_server_and_device(monkeypatch, error):
    run = Mock(side_effect=[error, response()])
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', run)
    monkeypatch.setattr('alas_headless.oracle.transport.time.sleep', Mock())
    bridge = AdbObserverBridge('emulator-5564', PACKAGE, adb_server_port=5037)
    assert bridge.foreground_component() == COMPONENT
    assert run.call_count == 2
    for call in run.call_args_list:
        assert call.args[0] == ['adb','-P','5037','-s','emulator-5564','shell','dumpsys','activity','activities']
        assert call.kwargs['timeout'] == 30


def test_second_query_failure_propagates_without_cached_foreground(monkeypatch):
    run = Mock(side_effect=daemon_error())
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', run)
    monkeypatch.setattr('alas_headless.oracle.transport.time.sleep', Mock())
    with pytest.raises(ObserverTransportError):
        AdbObserverBridge('emulator-5564', PACKAGE).foreground_component()
    assert run.call_count == 2


@pytest.mark.parametrize('error', [
    subprocess.CalledProcessError(1, ['adb'], stderr=b'device offline'),
    FileNotFoundError('adb missing'),
    UnicodeDecodeError('utf-8', b'\x80', 0, 1, 'invalid'),
])
def test_unclassified_failure_is_not_retried_or_hidden(monkeypatch, error):
    run = Mock(side_effect=error)
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', run)
    with pytest.raises(ObserverTransportError):
        AdbObserverBridge('emulator-5564', PACKAGE).foreground_component()
    run.assert_called_once()


def test_recovered_query_with_foreign_activity_still_closes_observation_and_input(monkeypatch):
    run = Mock(side_effect=[daemon_error(), response('other.package/other.Activity')])
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', run)
    monkeypatch.setattr('alas_headless.oracle.transport.time.sleep', Mock())
    bridge = AdbObserverBridge('emulator-5564', PACKAGE)
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    oracle._foreground_component = bridge.foreground_component
    with pytest.raises(SemanticGateClosed, match='not top-resumed'):
        oracle.read_state()
    assert backend.taps == []


def test_input_outcome_is_never_replayed_when_daemon_fails(monkeypatch):
    run = Mock(side_effect=daemon_error())
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', run)
    with pytest.raises(ObserverTransportError):
        AdbObserverBridge('emulator-5564', PACKAGE).tap(640, 360)
    run.assert_called_once()
