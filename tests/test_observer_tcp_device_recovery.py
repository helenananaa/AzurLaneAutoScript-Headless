"""An absent configured TCP device may reconnect only before a read retry."""
import subprocess
from unittest.mock import Mock, patch

import pytest

from alas_headless.oracle.errors import ObserverTransportError
from tests.test_observer_forward_recovery import bridge_with_error, refused


def missing(serial):
    error = ObserverTransportError('ADB command failed')
    error.__cause__ = subprocess.CalledProcessError(
        1, ['adb', '-s', serial, 'shell', 'pidof', 'com.bilibili.azurlane'],
        stderr=("adb.exe: device '"+serial+"' not found\n").encode())
    return error


def rig(serial='127.0.0.1:44123'):
    bridge = bridge_with_error(refused())
    bridge.serial = serial
    return bridge


@pytest.mark.parametrize('serial,listing', [
    ('127.0.0.1:44123', 'List of devices attached\nother-usb device product:phone\n'),
    ('android-device.local:44123', '* daemon started successfully\nList of devices attached\nother-usb future-state future:metadata\n'),
    ('[::1]:44123', 'List of devices attached\n'),
])
def test_proven_missing_configured_tcp_device_reconnects_one_read(serial, listing):
    bridge = rig(serial)
    bridge._run = Mock(side_effect=['', missing(serial), listing, 'connected', '1957', '34567'])
    replacement = Mock()
    replacement.request.return_value = {'status':'ok', 'generation':77}
    with patch('alas_headless.oracle.transport.TcpObserverTransport', return_value=replacement):
        assert bridge.request('GET /v1/state\n')['generation'] == 77
    commands = [call.args[0] for call in bridge._run.call_args_list]
    assert commands.count(('connect', serial)) == 1
    assert not any('kill-server' in cmd or 'start-server' in cmd for cmd in commands)
    assert commands[-2:] == [('shell', 'pidof', bridge.package),
                             ('forward', 'tcp:0', 'localabstract:alas.g3.1957')]
    replacement.request.assert_called_once_with('GET /v1/state\n')


@pytest.mark.parametrize('state', ['device', 'offline', 'unauthorized', 'future-state'])
def test_listed_target_is_never_reconnected_even_if_pidof_reports_missing(state):
    bridge = rig()
    bridge._run = Mock(side_effect=['', missing(bridge.serial),
        'List of devices attached\n'+bridge.serial+' '+state+'\n'])
    with pytest.raises(ObserverTransportError):
        bridge.request('GET /v1/state\n')
    assert not any(call.args[0][0] == 'connect' for call in bridge._run.call_args_list)


@pytest.mark.parametrize('serial', ['usb-device', 'emulator-5556', 'localhost:0', 'localhost:65536'])
def test_non_tcp_or_invalid_port_is_not_converted_to_a_network_target(serial):
    bridge = rig(serial)
    bridge._run = Mock(side_effect=['', missing(serial)])
    with pytest.raises(ObserverTransportError):
        bridge.request('GET /v1/state\n')
    assert not any(call.args[0][0] == 'connect' for call in bridge._run.call_args_list)


def test_missing_device_table_header_does_not_prove_target_absence():
    bridge = rig()
    bridge._run = Mock(side_effect=['', missing(bridge.serial), 'diagnostic output only'])
    with pytest.raises(ObserverTransportError):
        bridge.request('GET /v1/state\n')
    assert not any(call.args[0][0] == 'connect' for call in bridge._run.call_args_list)


def test_another_devices_error_does_not_authorize_this_target_reconnect():
    bridge = rig()
    bridge._run = Mock(side_effect=['', missing('another-device:1234')])
    with pytest.raises(ObserverTransportError):
        bridge.request('GET /v1/state\n')
    assert not any(call.args[0][0] == 'connect' for call in bridge._run.call_args_list)


def test_reconnect_never_rebinds_to_a_changed_game_pid():
    bridge = rig()
    bridge._run = Mock(side_effect=['', missing(bridge.serial),
        'List of devices attached\n', 'connected', '2000'])
    with patch('alas_headless.oracle.transport.TcpObserverTransport') as replacement:
        with pytest.raises(ObserverTransportError, match='PID changed'):
            bridge.request('GET /v1/state\n')
    replacement.assert_not_called()
    assert bridge.pid == 1957 and bridge.port == 23456


def test_failed_reconnect_does_not_loop_or_resend_the_read():
    bridge = rig()
    bridge._run = Mock(side_effect=['', missing(bridge.serial),
        'List of devices attached\n', 'failed to connect', missing(bridge.serial)])
    with pytest.raises(ObserverTransportError):
        bridge.request('GET /v1/state\n')
    assert sum(call.args[0][0] == 'connect' for call in bridge._run.call_args_list) == 1
    bridge.transport.request.assert_called_once()
