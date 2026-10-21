"""Reuse the acquired globe source, retaining live path and destination proof."""
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.test_combat_screenshot_observation import host
from tests.test_globe_stronghold_decoration import stronghold
from tests.test_globe_unpin_anchor import setup_unpin
from tests.semantic_support.observer_fixtures import make_buttons, make_ui


def globe_host(drift=False):
    backend, session, _ = host('combat', False)
    globe, _ = stronghold('updated_decoration' if drift else '')
    geometry, _ = setup_unpin()
    backend.buttons = deepcopy(globe.buttons)
    backend.ui = deepcopy(globe.ui)
    backend.ui['globe_geometry'] = deepcopy(geometry.ui['globe_geometry'])
    if drift:
        backend.ui['images'].reverse()
        backend.ui['optional_metadata'] = {'added_field': True}

    def unpin():
        backend.snapshot['generation'] = 13
        backend.buttons = make_buttons(backend.buttons['buttons'], generation=13)
        backend.ui = make_ui([], generation=13)
        backend.ui_sequence = [make_ui([], generation=12), make_ui([], generation=13)]
    backend.on_swipe = unpin
    return backend, session, session.open().oracle


@pytest.mark.parametrize('drift', [False, True])
def test_same_one_drag_and_live_proofs_with_fewer_source_requests(drift):
    results = []
    for reuse in (False, True):
        backend, session, live = globe_host(drift)
        backend.requests.clear()
        backend.foreground_requests = 0
        with patch.object(live, 'operation_siren_globe_drag_owned', return_value=True) as proof:
            if reuse:
                receipt = session.operation_siren_globe_unpin()
            else:
                session.refresh_frame()
                receipt = live.operation_siren_globe_unpin()
        proof.assert_called_once_with(receipt.start, receipt.end)
        assert receipt.post_generation == 13
        assert len(backend.swipes) == 1 and not backend.taps
        results.append((backend.swipes, len(backend.requests), backend.foreground_requests))
    assert results[0][0] == results[1][0]
    assert results[0][1] - results[1][1] == 3
    assert results[0][2] - results[1][2] == 1


def test_incomplete_source_uses_existing_read_retry_then_live_complete_state():
    backend, session, live = globe_host()
    session.refresh_frame()
    source = session.open()._require_frame_observation_oracle()
    source._operation_siren_globe_unpin_targets = Mock(side_effect=SemanticGateClosed('pin mounting'))
    with patch.object(live, 'operation_siren_globe_drag_owned', return_value=True):
        receipt = live.operation_siren_globe_unpin(precondition_oracle=source)
    assert receipt.post_generation == 13 and len(backend.swipes) == 1


def test_expired_input_lease_still_rejects_even_if_live_source_is_complete():
    backend, session, live = globe_host()
    session.refresh_frame()
    source = session.open()._require_frame_observation_oracle()
    frame = session._frame_clock.borrow()
    session._frame_clock._monotonic_ns = lambda: frame.captured_monotonic_ns + 11_000_000_000
    with patch.object(live, 'operation_siren_globe_drag_owned', return_value=True):
        with pytest.raises(StaleFrameError):
            live.operation_siren_globe_unpin(precondition_oracle=source)
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('change', ['foreground', 'loading', 'unknown-proof', 'unowned'])
def test_reused_source_does_not_replace_live_input_guards(change):
    backend, session, live = globe_host()
    def proof(*_):
        if change == 'foreground':
            backend.foreground = 'other/.Activity'
        elif change == 'loading':
            live._blocking_rules = Mock(return_value=(Mock(blocker_id='loading'),))
        elif change == 'unknown-proof':
            raise SemanticGateClosed('unknown path proof')
        return change != 'unowned'
    with patch.object(live, 'operation_siren_globe_drag_owned', side_effect=proof):
        with pytest.raises(SemanticGateClosed):
            session.operation_siren_globe_unpin()
    assert not backend.taps and not backend.swipes


def test_incomplete_live_fallback_never_dispatches_a_drag():
    backend, session, live = globe_host()
    session.refresh_frame()
    source = session.open()._require_frame_observation_oracle()
    source._operation_siren_globe_unpin_targets = Mock(side_effect=SemanticGateClosed('pin mounting'))
    backend.ui['globe_geometry']['status'] = 0
    with pytest.raises(SemanticGateClosed):
        live.operation_siren_globe_unpin(precondition_oracle=source)
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('point', [[True, 425], [float('nan'), 425], ['508', 425], [508]])
def test_frozen_coordinate_container_acceptance_still_requires_two_finite_numbers(point):
    backend, session, live = globe_host()
    for marker in backend.ui['globe_geometry']['objects']:
        marker['input_point'] = point
    with patch.object(live, 'operation_siren_globe_drag_owned') as proof:
        with pytest.raises(SemanticGateClosed, match='no unobscured typed plane target|not canonical JSON'):
            session.operation_siren_globe_unpin()
    proof.assert_not_called()
    assert not backend.taps and not backend.swipes
