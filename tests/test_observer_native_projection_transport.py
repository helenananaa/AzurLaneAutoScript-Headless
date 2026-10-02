import json
from unittest.mock import MagicMock, patch

import pytest

from alas_headless.oracle.transport import TcpObserverTransport
from alas_headless.oracle.errors import ObserverTransportError


@pytest.mark.parametrize('line', ['GET /v1/globe-projection 268 421\n',
    'GET /v1/globe-projection -2.68e2 +.421E3\n', 'GET /v1/state\n', 'GET /v1/os-map-drag 500 500 500 300\n', 'GET /v1/globe-map-drag 361 537 661 554\n'])
def test_transport_sends_complete_read_request(line):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.recv.return_value = json.dumps({'status': 'ok'}).encode() + b'\n'
    with patch('alas_headless.oracle.transport.socket.create_connection', return_value=connection):
        assert TcpObserverTransport('localhost', 1234).request(line)['status'] == 'ok'
    connection.sendall.assert_called_once_with(line.encode('ascii'))


@pytest.mark.parametrize('line', ['GET /v1/globe-projection nan 421\n',
    'GET /v1/globe-projection inf 421\n', 'GET /v1/globe-projection 1e999 421\n',
    'GET /v1/globe-projection 268 421 trailing\n', 'GET /v1/globe-projection 268 421\nGET /v1/state\n',
    'GET /v1/globe-projection 268 421', 'POST /v1/globe-projection 268 421\n', 'GET /v1/os-map-drag nan 1 2 3\n',
    'GET /v1/os-map-drag 1 2 3 4 trailing\n', 'GET /v1/os-map-drag 1 2 3 4\nGET /v1/state\n', 'GET /v1/globe-map-drag nan 1 2 3\n',
    'GET /v1/globe-map-drag 1 2 3 4\nGET /v1/state\n'])
def test_transport_refuses_malformed_request_before_socket(line):
    with patch('alas_headless.oracle.transport.socket.create_connection') as connect:
        with pytest.raises(ObserverTransportError, match='unsupported'):
            TcpObserverTransport('localhost', 1234).request(line)
        connect.assert_not_called()
