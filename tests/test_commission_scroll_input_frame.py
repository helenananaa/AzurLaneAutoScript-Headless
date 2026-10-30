"""One fresh scrollbar/row plan, followed by live movement confirmation."""
from unittest.mock import Mock
import pytest

from alas_headless.adapter import StaleFrameError
from alas_headless.oracle.errors import SemanticTargetMissing
from tests.test_combat_screenshot_observation import host
from tests.semantic_support.observer_fixtures import set_commission_scroll_view


@pytest.mark.parametrize('direction', ['next', 'top'])
def test_expired_screenshot_is_replaced_before_planning_and_postcondition_stays_live(direction):
    backend, session, _ = host('combat', False)
    old = session._frame_clock.borrow()
    session._frame_clock._monotonic_ns = lambda: old.captured_monotonic_ns+11_000_000_000
    session.begin_commission()
    set_commission_scroll_view(backend, index=0, name='before',
        handle_top=75 if direction == 'next' else 195, generation=11)
    live = session.open().oracle
    original_state, original_rows = live.commission_scroll_state, live.commission_rows
    def after_only(call):
        assert len(backend.swipes) == 1
        return call()
    live.commission_scroll_state = lambda: after_only(original_state)
    live.commission_rows = lambda: after_only(original_rows)
    def moved():
        assert session._frame_clock.current_frame_id is None
        set_commission_scroll_view(backend, index=1, name='after',
            handle_top=135 if direction == 'next' else 75, generation=12)
    backend.on_swipe = moved
    call = session.commission_scroll_next if direction == 'next' else session.commission_scroll_to_top
    proof = call()
    assert proof.before_generation == 11 and proof.after_generation == 12
    assert proof.before_row_signatures != proof.after_row_signatures
    assert len(backend.swipes) == 1 and backend.swipes[0][-1] == 1500
    assert live.input_dispatch_count == 1


def test_failed_refresh_cannot_fall_back_to_expired_scroll_authority(monkeypatch):
    backend, session, _ = host('combat', False)
    session.begin_commission()
    monkeypatch.setattr(session.open(), '_input_frame_refresher', Mock(side_effect=StaleFrameError()))
    with pytest.raises(StaleFrameError):
        session.commission_scroll_next()
    assert not backend.swipes and not backend.taps


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('port', ['commission_scroll_state', 'commission_rows', 'commission_is_empty'])
def test_passive_scroll_observation_uses_original_screenshot_frame(drift, port):
    backend, session, _ = host('combat', False)
    set_commission_scroll_view(backend, index=0, name='original',
        handle_top=75, generation=11)
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['optional_upstream_metadata'] = 'additive'
    session.refresh_frame()
    session.begin_commission()
    # A subsequent live endpoint pair can straddle Unity generations, even
    # though the screenshot's validated scrollbar projection is still leased.
    live = session.open().oracle
    split = Mock(side_effect=AssertionError('split live list observation'))
    setattr(live, port, split)
    set_commission_scroll_view(backend, index=1, name='later',
        handle_top=195, generation=50)
    state = getattr(session, port)()
    if port == 'commission_scroll_state':
        assert state.generation == 11 and state.at_top and not state.at_bottom
    elif port == 'commission_rows':
        assert len(state) == 1 and state[0].name == 'original'
    else:
        assert state is False
    split.assert_not_called()
    assert not backend.swipes and not backend.taps


@pytest.mark.parametrize('port', ['commission_scroll_state', 'commission_rows', 'commission_is_empty'])
def test_passive_scroll_rejects_wrong_screenshot_page_without_using_live_page(port):
    backend, session, _ = host('combat', False)
    session.begin_commission()
    set_commission_scroll_view(backend, index=0, name='later',
        handle_top=75, generation=11)
    with pytest.raises(SemanticTargetMissing, match='commission/page/back'):
        getattr(session, port)()
    assert not backend.swipes and not backend.taps
