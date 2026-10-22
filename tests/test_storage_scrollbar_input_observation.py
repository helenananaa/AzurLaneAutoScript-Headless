"""The optional routing query proves the actual drag receiver without input."""
from copy import deepcopy
import pytest
from alas_headless import SemanticGateClosed
from tests.test_storage_scrollbar_observation import storage


def routing(backend, **changes):
    bar = backend.ui['storage_scroll']['scrollbar']
    value = dict(schema='alas-headless.storage-scrollbar-input/v1', status=1,
                 point=[1260, 125], enabled=True, interactable=True, owned=True,
                 handler_instance_id=1, top_path=bar['controls'][0]['path'] + '/Handle/Image')
    value.update(changes)
    return value


def queried(backend, oracle, raw, *, advance=True):
    original = backend.request
    def request(line):
        if line.startswith('GET /v1/storage-scrollbar-input '):
            backend.requests.append(line)
            if advance:
                for packet in (backend.snapshot, backend.buttons, backend.ui): packet['generation'] += 1
            backend.ui['storage_scroll']['scrollbar']['input'] = raw
            return dict(status='ok', scope='read-only-storage-scrollbar-input')
        return original(line)
    oracle._request = request


@pytest.mark.parametrize('adapt', [False, True])
@pytest.mark.parametrize('owned', [False, True])
def test_actual_routing_is_additive_read_only_and_reports_obscured_start(adapt, owned):
    backend, oracle = storage(adapt)
    raw = routing(backend, owned=owned)
    if not owned: raw.update(handler_instance_id=91, top_path='Overlay/Msgbox/confirm')
    raw['future_metadata'] = 'compatible'
    queried(backend, oracle, raw)
    proof = oracle.storage_scrollbar_input_proof([1260, 125])
    assert proof.owned is owned and proof.generation == 11
    assert not backend.taps and not backend.swipes
    assert backend.requests.count('GET /v1/storage-scrollbar-input 1260.000 125.000\n') == 1


@pytest.mark.parametrize('case', ['other-handler', 'other-owner', 'disabled', 'uninteractable',
                                 'malformed-point', 'bool-id', 'unavailable', 'wrong-schema',
                                 'old-point', 'old-generation'])
def test_missing_or_inconsistent_routing_does_not_become_input_authority(case):
    backend, oracle = storage()
    raw = routing(backend)
    if case == 'other-handler': raw['handler_instance_id'] = 91
    elif case == 'other-owner': raw['top_path'] = 'other/Scrollbar/Handle'
    elif case == 'disabled': raw['enabled'] = False
    elif case == 'uninteractable': raw['interactable'] = False
    elif case == 'malformed-point': raw['point'][0] = float('nan')
    elif case == 'bool-id': raw['handler_instance_id'] = True
    elif case == 'unavailable': raw['status'] = 2
    elif case == 'wrong-schema': raw['schema'] = 'future-incompatible'
    elif case == 'old-point': raw['point'][1] += 10
    queried(backend, oracle, raw, advance=case != 'old-generation')
    with pytest.raises(SemanticGateClosed): oracle.storage_scrollbar_input_proof([1260, 125])
    assert not backend.taps and not backend.swipes


def test_unpublished_query_waits_for_next_native_frame_without_input():
    backend, oracle = storage()
    raw = routing(backend)
    queried(backend, oracle, raw)
    original = oracle.read_ui_state
    calls = 0
    def ui(**kw):
        nonlocal calls
        calls += 1
        result = original(**kw)
        if calls == 2:
            from dataclasses import replace
            snapshot = deepcopy(result.snapshot)
            snapshot['storage_scroll']['scrollbar']['input'] = dict(
                schema='alas-headless.storage-scrollbar-input/v1', status=0)
            return replace(result, snapshot=snapshot)
        return result
    oracle.read_ui_state = ui
    assert oracle.storage_scrollbar_input_proof([1260, 125]).owned
    assert calls == 3
    assert not backend.taps and not backend.swipes
