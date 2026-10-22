"""Legacy observer framing failures get one plain-read retry, never action replay."""
import json
import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from alas_headless.oracle.transport import TcpObserverTransport
from alas_headless.oracle.errors import ObserverResponseTimeout, SemanticSnapshotStale


def connection(value):
    client = MagicMock()
    client.__enter__.return_value = client
    client.recv.return_value = json.dumps(value).encode() + b'\n'
    return client


@pytest.mark.parametrize('endpoint', ['snapshot', 'buttons', 'ui', 'state'])
def test_valid_plain_read_reconnects_once_after_explicit_bad_request(endpoint):
    line = f'GET /v1/{endpoint}\n'
    first, second = connection({'status': 'bad-request'}), connection({'status': 'ok', 'generation': 7})
    with patch('alas_headless.oracle.transport.socket.create_connection', side_effect=[first, second]) as connect:
        assert TcpObserverTransport('localhost', 1234).request(line)['generation'] == 7
        assert connect.call_count == 2
    first.sendall.assert_called_once_with(line.encode())
    second.sendall.assert_called_once_with(line.encode())


def test_permanent_bad_request_remains_a_failure_after_one_retry():
    with patch('alas_headless.oracle.transport.socket.create_connection',
               side_effect=[connection({'status': 'bad-request'}), connection({'status': 'bad-request'})]) as connect:
        assert TcpObserverTransport('localhost', 1234).request('GET /v1/state\n')['status'] == 'bad-request'
        assert connect.call_count == 2


@pytest.mark.parametrize('line', ['GET /v1/globe-projection 1 2\n',
                                'GET /v1/os-map-drag 1 2 3 4\n', 'GET /v1/globe-port-input 6\n'])
def test_parameterized_requests_are_not_replayed(line):
    with patch('alas_headless.oracle.transport.socket.create_connection',
               return_value=connection({'status': 'bad-request'})) as connect:
        assert TcpObserverTransport('localhost', 1234).request(line)['status'] == 'bad-request'
        connect.assert_called_once()


def test_other_rejections_are_not_retried():
    with patch('alas_headless.oracle.transport.socket.create_connection',
               return_value=connection({'status': 'forbidden'})) as connect:
        assert TcpObserverTransport('localhost', 1234).request('GET /v1/state\n')['status'] == 'forbidden'
        connect.assert_called_once()


def test_real_socket_plain_read_recovers_on_a_new_connection():
    received, failures = [], []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(2)
        listener.settimeout(3)
        def server():
            try:
                for status in ('bad-request', 'ok'):
                    client, _ = listener.accept()
                    with client:
                        client.settimeout(3)
                        request = b''
                        while not request.endswith(b'\n'):
                            chunk = client.recv(3)
                            if not chunk: break
                            request += chunk
                        received.append(request)
                        client.sendall(json.dumps({'status': status}).encode()+b'\n')
            except BaseException as exc:
                failures.append(exc)
        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        assert TcpObserverTransport('127.0.0.1', listener.getsockname()[1]).request('GET /v1/state\n')['status'] == 'ok'
        thread.join(3)
        assert not thread.is_alive() and not failures
    assert received == [b'GET /v1/state\n'] * 2


@pytest.mark.parametrize('endpoint', ['snapshot', 'buttons', 'ui', 'state'])
def test_plain_read_reconnects_once_after_response_timeout(endpoint):
    first = connection({})
    first.recv.side_effect = TimeoutError('delayed read')
    second = connection({'status': 'ok', 'generation': 8})
    with patch('alas_headless.oracle.transport.socket.create_connection', side_effect=[first, second]) as connect:
        assert TcpObserverTransport('localhost', 1234).request(f'GET /v1/{endpoint}\n')['generation'] == 8
        assert connect.call_count == 2


def test_two_timeouts_remain_bounded_and_raise_original_classification():
    first, second = connection({}), connection({})
    first.recv.side_effect = second.recv.side_effect = TimeoutError('delayed read')
    with patch('alas_headless.oracle.transport.socket.create_connection', side_effect=[first, second]) as connect:
        with pytest.raises(ObserverResponseTimeout):
            TcpObserverTransport('localhost', 1234).request('GET /v1/state\n')
        assert connect.call_count == 2


@pytest.mark.parametrize('line', ['GET /v1/globe-projection 1 2\n',
                                'GET /v1/os-map-drag 1 2 3 4\n', 'GET /v1/globe-port-input 6\n'])
def test_parameterized_timeout_is_not_replayed(line):
    client = connection({})
    client.recv.side_effect = TimeoutError('delayed query')
    with patch('alas_headless.oracle.transport.socket.create_connection', return_value=client) as connect:
        with pytest.raises(ObserverResponseTimeout):
            TcpObserverTransport('localhost', 1234).request(line)
        connect.assert_called_once()


def test_retried_state_still_rejects_stale_snapshot_before_input():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle
    backend = FakeBackend([])
    backend.snapshot['age_ms'] = 10001
    stale = backend.request('GET /v1/state\n')
    first = connection({})
    first.recv.side_effect = TimeoutError('delayed read')
    oracle = make_oracle(backend)
    oracle._request = TcpObserverTransport('localhost', 1234).request
    with patch('alas_headless.oracle.transport.socket.create_connection', side_effect=[first, connection(stale)]):
        with pytest.raises(SemanticSnapshotStale):
            oracle.read_state()
    assert not backend.taps


def test_real_socket_discards_partial_timeout_response_before_reconnect():
    received, failures = [], []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(2)
        listener.settimeout(3)
        def server():
            try:
                for index in range(2):
                    client, _ = listener.accept()
                    with client:
                        client.settimeout(3)
                        request = b''
                        while not request.endswith(b'\n'):
                            request += client.recv(128)
                        received.append(request)
                        if index == 0:
                            client.sendall(b'{"status":')
                            assert client.recv(1) == b''  # Timed-out client closes.
                        else:
                            client.sendall(b'{"status":"ok","generation":9}\n')
            except BaseException as exc:
                failures.append(exc)
        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        assert TcpObserverTransport('127.0.0.1', listener.getsockname()[1], timeout_seconds=.2).request('GET /v1/state\n')['generation'] == 9
        thread.join(3)
        assert not thread.is_alive() and not failures
    assert received == [b'GET /v1/state\n'] * 2
