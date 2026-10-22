"""One unpin gesture retains its existing bounded read-only postcondition wait."""
from unittest.mock import patch

import pytest

from alas_headless import SemanticGateClosed
from tests.test_globe_unpin_anchor import setup_unpin
from tests.semantic_support.observer_fixtures import make_ui


@pytest.mark.parametrize('drift', [False, True])
def test_transient_globe_visibility_does_not_abort_or_repeat_accepted_drag(drift):
    backend, oracle = setup_unpin()
    oracle._sleep = lambda _: None
    on_swipe = backend.on_swipe

    def unpin():
        on_swipe()
        # Independent subsequent publications after one short visibility gap.
        backend.ui_sequence = [make_ui([], generation=n) for n in (12, 13, 14, 15)]
        if drift:
            for ui in backend.ui_sequence:
                ui['optional_metadata'] = {'additive_field': True}
    backend.on_swipe = unpin
    with patch.object(oracle, 'operation_siren_globe_state'), patch.object(
            oracle, 'operation_siren_globe_drag_owned', return_value=True), patch.object(
            oracle, 'operation_siren_globe_visible', side_effect=[False, True]) as visible:
        receipt = oracle.operation_siren_globe_unpin()
    assert receipt.post_generation == 15
    assert visible.call_count == 2
    assert len(backend.swipes) == 1
    assert backend.swipes[0][-1] == 2000
    assert not backend.taps


def test_persistent_missing_globe_still_refuses_without_another_drag():
    backend, oracle = setup_unpin()
    oracle._sleep = lambda _: None
    with patch.object(oracle, 'operation_siren_globe_state'), patch.object(
            oracle, 'operation_siren_globe_drag_owned', return_value=True), patch.object(
            oracle, 'operation_siren_globe_visible', return_value=False):
        with pytest.raises(SemanticGateClosed):
            oracle.operation_siren_globe_unpin()
    assert len(backend.swipes) == 1
    assert not backend.taps


def test_returning_pin_during_visibility_gap_is_not_unpin_success():
    backend, oracle = setup_unpin()
    oracle._sleep = lambda _: None
    pin = backend.ui['images'][0]
    on_swipe = backend.on_swipe

    def selected_again():
        on_swipe()
        backend.ui = make_ui([], images=[pin], generation=15)
        backend.ui_sequence = [make_ui([], generation=12), make_ui([], generation=13), backend.ui]
    backend.on_swipe = selected_again
    with patch.object(oracle, 'operation_siren_globe_state'), patch.object(
            oracle, 'operation_siren_globe_drag_owned', return_value=True), patch.object(
            oracle, 'operation_siren_globe_visible', return_value=False):
        with pytest.raises(SemanticGateClosed):
            oracle.operation_siren_globe_unpin()
    assert len(backend.swipes) == 1
    assert not backend.taps


@pytest.mark.parametrize('change', ['foreign-package', 'truncated'])
def test_invalid_post_observation_after_gap_still_fails_closed(change):
    backend, oracle = setup_unpin()
    oracle._sleep = lambda _: None
    on_swipe = backend.on_swipe

    def unpin():
        on_swipe()
        bad = make_ui([], generation=14)
        if change == 'foreign-package':
            bad['package'] = 'other.package'
        else:
            bad['image_truncated'] = True
        backend.ui_sequence = [make_ui([], generation=12), make_ui([], generation=13), bad]
    backend.on_swipe = unpin
    with patch.object(oracle, 'operation_siren_globe_state'), patch.object(
            oracle, 'operation_siren_globe_drag_owned', return_value=True), patch.object(
            oracle, 'operation_siren_globe_visible', return_value=False):
        with pytest.raises(SemanticGateClosed):
            oracle.operation_siren_globe_unpin()
    assert len(backend.swipes) == 1
    assert not backend.taps
