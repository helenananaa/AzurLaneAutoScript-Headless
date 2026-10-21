"""A plain observation can reconnect once after an established stream abort."""
from unittest.mock import patch

import pytest

from alas_headless.oracle.errors import ObserverTransportError, SemanticSnapshotStale
from alas_headless.oracle.transport import TcpObserverTransport
from tests.test_observer_plain_read_retry import connection


@pytest.mark.parametrize('endpoint', ['state', 'snapshot', 'buttons', 'ui'])
def test_interrupted_plain_read_discards_partial_response_and_reconnects(endpoint):
    first = connection({})
    first.recv.side_effect = [b'{"partial":', ConnectionAbortedError(10053, 'host aborted established stream')]
    second = connection({'status': 'ok', 'generation': 12})
    with patch('alas_headless.oracle.transport.socket.create_connection', side_effect=[first, second]) as connect:
        assert TcpObserverTransport('localhost', 1234).request(f'GET /v1/{endpoint}\n')['generation'] == 12
        assert connect.call_count == 2


@pytest.mark.parametrize('error', [ConnectionResetError, BrokenPipeError])
def test_reset_and_send_interruption_share_the_same_single_read_retry(error):
    first = connection({})
    first.sendall.side_effect = error('established stream interrupted')
    with patch('alas_headless.oracle.transport.socket.create_connection',
               side_effect=[first, connection({'status': 'ok'})]) as connect:
        assert TcpObserverTransport('localhost', 1234).request('GET /v1/state\n')['status'] == 'ok'
        assert connect.call_count == 2


def test_second_interruption_is_not_retried_again():
    first, second = connection({}), connection({})
    first.recv.side_effect = second.recv.side_effect = ConnectionAbortedError('interrupted')
    with patch('alas_headless.oracle.transport.socket.create_connection', side_effect=[first, second]) as connect:
        with pytest.raises(ObserverTransportError):
            TcpObserverTransport('localhost', 1234).request('GET /v1/state\n')
        assert connect.call_count == 2


@pytest.mark.parametrize('line', ['GET /v1/globe-projection 1 2\n', 'GET /v1/os-map-drag 1 2 3 4\n'])
def test_parameterized_request_interruption_is_never_replayed(line):
    client = connection({})
    client.recv.side_effect = ConnectionAbortedError('interrupted')
    with patch('alas_headless.oracle.transport.socket.create_connection', return_value=client) as connect:
        with pytest.raises(ObserverTransportError):
            TcpObserverTransport('localhost', 1234).request(line)
        connect.assert_called_once()


def test_connection_failure_is_not_an_established_stream_interruption():
    with patch('alas_headless.oracle.transport.socket.create_connection',
               side_effect=ConnectionAbortedError('not connected')) as connect:
        with pytest.raises(ObserverTransportError):
            TcpObserverTransport('localhost', 1234).request('GET /v1/state\n')
        connect.assert_called_once()


def test_reconnected_observation_still_refuses_stale_data_before_input():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle
    backend = FakeBackend([])
    backend.snapshot['age_ms'] = 10001
    first = connection({})
    first.recv.side_effect = ConnectionAbortedError('interrupted')
    oracle = make_oracle(backend)
    oracle._request = TcpObserverTransport('localhost', 1234).request
    with patch('alas_headless.oracle.transport.socket.create_connection',
               side_effect=[first, connection(backend.request('GET /v1/state\n'))]):
        with pytest.raises(SemanticSnapshotStale):
            oracle.read_state()
    assert not backend.taps
