"""Native globe path reads share foreground checks at the group's two ends."""
from copy import deepcopy

import pytest

from alas_headless import SemanticGateClosed
from tests.test_semantic_oracle_opsi_port_geometry import fixture
from tests.test_opsi_native_globe_drag import START, END, proof


def native_path_reader(*, pending=0, foreign_during_query=False):
    backend, oracle = fixture()
    request = oracle._request
    original = deepcopy(backend.ui)
    issued = False
    polls = 0

    def query(line):
        nonlocal issued, polls
        if line.startswith('GET /v1/globe-map-drag '):
            issued = True
            if foreign_during_query:
                backend.foreground = 'other/.Activity'
            backend.requests.append(line)
            return {'status': 'ok', 'scope': 'read-only-globe-map-drag'}
        if line == 'GET /v1/ui\n' and issued:
            polls += 1
            if polls > pending:
                backend.ui = deepcopy(original)
                backend.ui['generation'] = 11
                backend.ui['operation_siren_globe_drag'] = proof()
        return request(line)
    oracle._request = query
    return backend, oracle


@pytest.mark.parametrize('pending', [0, 3])
def test_readonly_path_checks_both_group_ends_including_pending_publications(pending):
    backend, oracle = native_path_reader(pending=pending)
    generation, result = oracle.operation_siren_globe_drag_proof(START, END)
    assert generation == 11 and all(row['owned'] for row in result['samples'])
    assert backend.foreground_requests == 2
    assert backend.requests.count('GET /v1/ui\n') == pending + 2
    assert not backend.taps and not backend.swipes


def test_foreign_foreground_at_start_prevents_native_query():
    backend, oracle = native_path_reader()
    backend.foreground = 'other/.Activity'
    with pytest.raises(SemanticGateClosed):
        oracle.operation_siren_globe_drag_proof(START, END)
    assert not any('globe-map-drag' in request for request in backend.requests)
    assert not backend.taps and not backend.swipes


def test_foreground_changed_during_query_rejects_even_a_fully_owned_path():
    backend, oracle = native_path_reader(foreign_during_query=True)
    with pytest.raises(SemanticGateClosed, match='activity changed during globe drag proof'):
        oracle.operation_siren_globe_drag_proof(START, END)
    assert backend.foreground_requests == 2
    assert not backend.taps and not backend.swipes
