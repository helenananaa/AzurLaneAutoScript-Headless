"""A late Loading raycast retries only the unsubmitted native camera proof."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.oracle.contracts import Point
from alas_headless.oracle.errors import SemanticGateClosed, SemanticInputBlocked
from tests.test_opsi_native_map_swipe import START, END, proof, reader, map_state
from tests.test_semantic_oracle_opsi_map_geometry import setup_map

LOADING = 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'


def covered():
    result = proof()
    for sample in result['samples']:
        sample.update(owned=False, top_path=LOADING)
    return result


@pytest.mark.parametrize('child', [False, True])
@pytest.mark.parametrize('partial', [False, True])
def test_exact_loading_is_classified_without_accepting_the_covered_proof(child, partial):
    result = proof()
    for sample in result['samples'][8:16] if partial else result['samples']:
        sample.update(owned=False, top_path=LOADING+('/bg' if child else ''))
    backend, oracle = reader(result)
    with pytest.raises(SemanticInputBlocked) as error:
        oracle.operation_siren_map_drag_proof(START, END)
    assert error.value.blockers == ('loading',)
    assert backend.swipes == [] and backend.taps == []


@pytest.mark.parametrize('fault', ['foreign', 'near-name', 'point', 'unclassified', 'owned'])
def test_loading_cannot_hide_other_unsafe_samples(fault):
    result = covered()
    sample = result['samples'][12]
    if fault == 'foreign': sample['top_path'] = 'OtherPopup/Window'
    elif fault == 'near-name': sample['top_path'] = LOADING+'Other/bg'
    elif fault == 'point': sample['x'] += 1
    elif fault == 'unclassified': sample['owned'] = None
    elif fault == 'owned': sample['owned'] = True
    backend, oracle = reader(result)
    with pytest.raises(SemanticGateClosed) as error:
        oracle.operation_siren_map_drag_proof(START, END)
    assert not isinstance(error.value, SemanticInputBlocked)
    assert backend.swipes == [] and backend.taps == []


@pytest.mark.parametrize('outcome', ['clear', 'persistent', 'map-changed', 'foreign'])
def test_late_loading_reenters_existing_wait_and_reproves_before_one_input(outcome):
    backend, oracle = setup_map()
    state = map_state(oracle)
    after = replace(state, generation=100, cells=tuple(
        replace(c, point=Point(c.point.x,c.point.y-200)) for c in state.cells))
    changed = replace(state, fleet_cells=((1,'A2'),))
    oracle.operation_siren_map_geometry = Mock(side_effect=[
        state, changed if outcome == 'map-changed' else state]+[after]*12)
    error = SemanticInputBlocked('os/map/camera-swipe', 2, ('loading',))
    oracle.operation_siren_map_drag_proof = Mock(side_effect=error if outcome == 'persistent'
        else [error, (state.generation+1,proof())])
    if outcome == 'persistent': oracle.operation_siren_map_geometry = Mock(return_value=state)
    oracle._blocking_rules = Mock(side_effect=[(),(SimpleNamespace(blocker_id='popup'),)]
        if outcome == 'foreign' else lambda *a: ())
    oracle._sleep = lambda _: None
    oracle._foreground_component = lambda: oracle.fingerprint.component
    if outcome == 'clear':
        result = oracle.operation_siren_map_swipe(state, START, END, 300)
        assert result.post_generation == 100
        assert oracle.operation_siren_map_drag_proof.call_count == 2
        assert backend.swipes == [(500,500,500,300,300)]
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.operation_siren_map_swipe(state, START, END, 300)
        assert backend.swipes == []
