"""Lost shared-ADB forwarding recovers observations without replaying input."""

from unittest.mock import Mock, patch

import pytest

from alas_headless.oracle.errors import ObserverResponseTimeout, ObserverTransportError
from alas_headless.oracle.transport import AdbObserverBridge, TcpObserverTransport


def refused():
    error = ObserverTransportError('observer socket request failed')
    error.__cause__ = ConnectionRefusedError('listener removed')
    return error


def bridge_with_error(error):
    bridge = AdbObserverBridge('exact-device', 'com.bilibili.azurlane')
    bridge.pid, bridge.port = 1957, 23456
    bridge.transport = TcpObserverTransport('127.0.0.1', bridge.port, timeout_seconds=7)
    bridge.transport.request = Mock(side_effect=error)
    return bridge


@pytest.mark.parametrize('endpoint', ['state', 'snapshot', 'buttons', 'ui'])
def test_removed_forward_recovers_one_read_on_the_same_game_pid(endpoint):
    bridge = bridge_with_error(refused())
    old_transport = bridge.transport
    bridge._run = Mock(side_effect=['other-device tcp:1234 tcp:7912', '1957', '34567'])
    replacement = Mock()
    replacement.request.return_value = {'status': 'ok', 'generation': 77}
    line = 'GET /v1/' + endpoint + '\n'
    with patch('alas_headless.oracle.transport.TcpObserverTransport', return_value=replacement) as factory:
        assert bridge.request(line)['generation'] == 77
    assert bridge._run.call_args_list[0].args[0] == ('forward', '--list')
    assert bridge._run.call_args_list[1].args[0] == ('shell', 'pidof', bridge.package)
    assert bridge._run.call_args_list[2].args[0] == ('forward', 'tcp:0', 'localabstract:alas.g3.1957')
    old_transport.request.assert_called_once_with(line)
    replacement.request.assert_called_once_with(line)
    assert factory.call_args.kwargs['timeout_seconds'] == 7
    assert bridge.pid == 1957 and bridge.port == 34567


@pytest.mark.parametrize('line', [
    'GET /v1/globe-port-input 1\n',
    'GET /v1/os-map-drag 1 2 3 4\n',
    'GET /v1/globe-map-drag 1 2 3 4\n',
])
def test_native_input_is_never_replayed(line):
    bridge = bridge_with_error(refused())
    bridge._run = Mock()
    with pytest.raises(ObserverTransportError):
        bridge.request(line)
    bridge.transport.request.assert_called_once_with(line)
    bridge._run.assert_not_called()


@pytest.mark.parametrize('error', [
    ObserverResponseTimeout('response timed out'),
    ObserverTransportError('observer returned invalid JSON'),
])
def test_uncertain_or_malformed_response_is_not_retried(error):
    bridge = bridge_with_error(error)
    bridge._run = Mock()
    with pytest.raises(ObserverTransportError):
        bridge.request('GET /v1/state\n')
    bridge._run.assert_not_called()


@pytest.mark.parametrize('listing', [
    'exact-device tcp:23456 localabstract:alas.g3.1957',
    'other-device tcp:23456 tcp:1234',
])
def test_present_or_reassigned_listener_is_not_overwritten(listing):
    bridge = bridge_with_error(refused())
    bridge._run = Mock(return_value=listing)
    with pytest.raises(ObserverTransportError):
        bridge.request('GET /v1/state\n')
    assert bridge._run.call_count == 1


def test_changed_pid_stops_recovery_without_rebinding():
    bridge = bridge_with_error(refused())
    bridge._run = Mock(side_effect=['', '2000'])
    with pytest.raises(ObserverTransportError, match='PID changed'):
        bridge.request('GET /v1/state\n')
    assert bridge._run.call_count == 2
    assert bridge.pid == 1957 and bridge.port == 23456


def test_failed_replacement_read_does_not_loop():
    bridge = bridge_with_error(refused())
    bridge._run = Mock(side_effect=['', '1957', '34567'])
    replacement = Mock()
    replacement.request.side_effect = refused()
    with patch('alas_headless.oracle.transport.TcpObserverTransport', return_value=replacement):
        with pytest.raises(ObserverTransportError):
            bridge.request('GET /v1/state\n')
    assert bridge._run.call_count == 3
    replacement.request.assert_called_once()
