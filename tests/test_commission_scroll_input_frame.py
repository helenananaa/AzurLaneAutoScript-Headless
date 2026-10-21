"""One fresh scrollbar/row plan, followed by live movement confirmation."""
from unittest.mock import Mock
import pytest

from alas_headless.adapter import StaleFrameError
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
