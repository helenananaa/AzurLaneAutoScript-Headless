"""Typed edge samples propose placement; a fresh complete proof grants it."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.test_semantic_oracle_opsi_port_geometry import fixture
from tests.test_globe_swipe_box_compatibility import arm

BOX = (600, 220, 980, 620)
CASES = json.loads((Path(__file__).parent / 'fixtures/globe-drag-background-edge-r746.json').read_text(encoding='utf8'))


def proof(start, end, missing=()):
    root = 'WorldMap3D/entity/Plane'
    return {'status': 1, 'handler_instance_id': 55, 'handler_path': root,
            'endpoints': [*start, *end],
            'samples': [{'x': start[0]+(end[0]-start[0])*i/32,
                         'y': start[1]+(end[1]-start[1])*i/32,
                         'owned': i not in missing,
                         'top_path': root if i not in missing else 'UICamera/Canvas/UIMain/WorldUI(Clone)/main/bg'}
                        for i in range(33)]}


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('fresh_owned', [False, True])
def test_retained_background_tail_only_proposes_same_vector_then_requires_new_proof(case, fresh_owned):
    backend, oracle = fixture()
    start, end = tuple(case['requested_endpoints'][:2]), tuple(case['requested_endpoints'][2:])
    def read(a, b):
        if (a, b) == (start, end):
            return deepcopy(case['proof'])
        return proof(a, b, () if fresh_owned else (32,))
    oracle._settled_globe_drag_proof = Mock(side_effect=read)
    result = oracle.operation_siren_globe_drag_candidate(start, end, box=BOX)
    assert oracle._settled_globe_drag_proof.call_count == 2
    a, b = oracle._settled_globe_drag_proof.call_args.args
    assert tuple(y-x for x, y in zip(a, b)) == tuple(y-x for x, y in zip(start, end))
    assert (a, b) != (start, end)
    assert all(BOX[0] <= p[0] <= BOX[2] and BOX[1] <= p[1] <= BOX[3] for p in (a, b))
    assert result == ((a, b) if fresh_owned else None)
    assert backend.taps == backend.swipes == []


@pytest.mark.parametrize('missing', [tuple(range(33)), (10,), (0, 32)])
def test_no_translation_for_absent_or_split_owned_edge(missing):
    backend, oracle = fixture()
    start, end = (841, 476), (766, 401)
    oracle._settled_globe_drag_proof = Mock(return_value=proof(start, end, missing))
    assert oracle.operation_siren_globe_drag_candidate(start, end, box=BOX) is None
    assert oracle._settled_globe_drag_proof.call_count == 1
    assert not backend.swipes


def test_translated_path_cannot_leave_original_alas_box():
    _, oracle = fixture()
    start, end = (979, 476), (904, 401)
    oracle._settled_globe_drag_proof = Mock(return_value=proof(start, end, range(24, 33)))
    assert oracle.operation_siren_globe_drag_candidate(start, end, box=BOX) is None
    assert oracle._settled_globe_drag_proof.call_count == 1


def test_owned_suffix_preserves_reverse_vector_and_reproves_new_path():
    _, oracle = fixture()
    start, end = (766, 401), (841, 476)
    oracle._settled_globe_drag_proof = Mock(side_effect=[proof(start, end, range(9)), proof((787,422), (862,497))])
    assert oracle.operation_siren_globe_drag_candidate(start, end, box=BOX) == ((787,422), (862,497))
    assert oracle._settled_globe_drag_proof.call_args.args == ((787,422), (862,497))


@pytest.mark.parametrize('armed', [False, True])
def test_candidate_port_requires_matching_current_globe_intent(armed):
    backend, oracle = fixture()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    oracle.operation_siren_globe_drag_candidate = Mock()
    if armed:
        arm(adapter, BOX)
    with pytest.raises(SemanticGateClosed, match='matching ALAS swipe intent'):
        adapter.operation_siren_globe_drag_candidate((841,476), (766,401), box=(610,220,980,620))
    oracle.operation_siren_globe_drag_candidate.assert_not_called()
    assert not backend.swipes


@pytest.mark.parametrize('fresh_foreign', [False, True])
def test_real_request_pipeline_reproves_translated_and_dispatched_integer_path(fresh_foreign):
    backend, oracle = fixture()
    oracle._sleep = lambda _: None
    start, end = (841,476), (766,401)
    requests = []
    original_request = oracle._request
    def request(line):
        if line.startswith('GET /v1/globe-map-drag '):
            points = tuple(map(int, line.split()[2:]))
            requests.append(points)
            data = deepcopy(CASES[1]['proof']) if points == (*start,*end) else proof(points[:2], points[2:])
            if fresh_foreign and len(requests) == 2:
                data['handler_path'] = 'Other/Plane'
            for value in (backend.snapshot, backend.buttons, backend.ui):
                value['generation'] += 1
            backend.ui['operation_siren_globe_drag'] = data
            return {'status':'ok', 'scope':'read-only-globe-map-drag'}
        return original_request(line)
    oracle._request = request
    if fresh_foreign:
        with pytest.raises(SemanticGateClosed, match='handler'):
            oracle.operation_siren_globe_drag_candidate(start, end, box=BOX)
        assert len(requests) == 2
        assert backend.swipes == []
    else:
        candidate = oracle.operation_siren_globe_drag_candidate(start, end, box=BOX)
        assert candidate == ((862,497), (787,422))
        def moved():
            for value in (backend.snapshot, backend.buttons, backend.ui):
                value['generation'] += 1
        backend.on_swipe = moved
        receipt = oracle.operation_siren_globe_swipe(*candidate, 300)
        assert requests == [(*start,*end), (862,497,787,422), (862,497,787,422)]
        assert backend.swipes == [(862,497,787,422,2000)]
        assert receipt.post_generation > receipt.pre_generation
