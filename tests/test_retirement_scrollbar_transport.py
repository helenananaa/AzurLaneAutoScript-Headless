"""New read-only query uses the existing finite two-coordinate grammar, no retry."""
import json
from unittest.mock import MagicMock,patch
import pytest
from alas_headless.oracle.transport import TcpObserverTransport
from alas_headless.oracle.errors import ObserverTransportError,ObserverResponseTimeout

@pytest.mark.parametrize('line',['GET /v1/retirement-scrollbar-input 1093.333 276.437\n',
    'GET /v1/retirement-scrollbar-input +1.093e3 .276e3\n'])
def test_new_query_is_sent_once_and_bad_request_is_not_replayed(line):
    client=MagicMock();client.__enter__.return_value=client
    client.recv.return_value=json.dumps({'status':'bad-request'}).encode()+b'\n'
    with patch('alas_headless.oracle.transport.socket.create_connection',return_value=client)as connect:
        assert TcpObserverTransport('localhost',1).request(line)['status']=='bad-request'
        connect.assert_called_once()
    client.sendall.assert_called_once_with(line.encode())

@pytest.mark.parametrize('line',['GET /v1/retirement-scrollbar-input nan 2\n',
    'GET /v1/retirement-scrollbar-input 1e999 2\n',
    'GET /v1/retirement-scrollbar-input 1 2 extra\n',
    'GET /v1/retirement-scrollbar-input 1 2\nGET /v1/state\n',
    'POST /v1/retirement-scrollbar-input 1 2\n'])
def test_malformed_new_query_is_refused_before_socket(line):
    with patch('alas_headless.oracle.transport.socket.create_connection')as connect:
        with pytest.raises(ObserverTransportError,match='unsupported'):
            TcpObserverTransport('localhost',1).request(line)
        connect.assert_not_called()

def test_parameterized_timeout_is_not_replayed():
    client=MagicMock();client.__enter__.return_value=client;client.recv.side_effect=TimeoutError('controlled')
    with patch('alas_headless.oracle.transport.socket.create_connection',return_value=client)as connect:
        with pytest.raises(ObserverResponseTimeout):
            TcpObserverTransport('localhost',1).request('GET /v1/retirement-scrollbar-input 1 2\n')
        connect.assert_called_once()
