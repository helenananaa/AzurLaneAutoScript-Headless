"""Slow live META readiness cannot dispatch against its expired entry lease."""
from unittest.mock import patch

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.errors import ExpiredFrameError
from tests.test_opsi_repair_input_frame import host


def setup():
    backend, session = host('meta-precombat-expired-r813.json')
    session.begin_meta_beacon()
    clock = session._frame_clock
    tick = [clock._monotonic_ns()]
    clock._monotonic_ns = lambda: tick[0]
    live = session.open().oracle
    original = live.meta_precombat_fleet_ready

    def slow_fleet():
        ready = original()
        tick[0] += 11_000_000_000
        return ready

    live.meta_precombat_fleet_ready = slow_fleet
    return backend, session, live


def test_original_live_entry_lease_expires_before_backend():
    backend, session, live = setup()
    # Reproduce the old adapter's complete sequence without the new final frame.
    session.refresh_tactical_input_frame()
    assert live.meta_precombat_fleet_ready()
    with pytest.raises(ExpiredFrameError):
        live.click_daily_precombat_start()
    assert not backend.taps


def test_original_two_live_geometry_reads_then_fresh_frame_dispatch_exactly_once():
    backend, session, live = setup()
    read = live.read_state
    reads = []

    def record(*args, **kwargs):
        result = read(*args, **kwargs)
        reads.append(result.generation)
        return result

    live.read_state = record
    receipt = session.click_daily_precombat_start()
    assert receipt.semantic_id == 'daily/precombat/start'
    assert len(backend.taps) == 1
    assert len(reads) >= 4  # Entry capture, fleet, stable live pair, closing capture.
    assert session.open()._meta_precombat_start_receipt is receipt


@pytest.mark.parametrize('case', ['foreign', 'loading', 'moved', 'empty-fleet', 'ambiguous'])
def test_final_frame_rechecks_changed_page_fleet_target_and_identity(case):
    backend, session, live = setup()
    adapter = session.open()
    acquire = adapter._fresh_input_oracle

    def changed_frame():
        if case == 'foreign':
            backend.foreground = 'other.package/.Activity'
        elif case == 'loading':
            from tests.semantic_support.observer_fixtures import make_button
            backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
            backend.buttons['button_count'] += 1
        elif case in ('moved', 'ambiguous'):
            import copy
            button = next(b for b in backend.buttons['buttons'] if b['path'].endswith('PreCombatUI(Clone)/adapt/right/start'))
            if case == 'moved':
                button['adb_point']['x'] += 10
            else:
                backend.buttons['buttons'].append(copy.deepcopy(button))
                backend.buttons['button_count'] += 1
        else:
            text = next(t for t in backend.ui['texts'] if t['path'].endswith('/gear_score/main/Text'))
            text['text'] = '0'
        return acquire()

    adapter._fresh_input_oracle = changed_frame
    with patch('alas_headless.adapter.frame.time.sleep', lambda _: None):
        with pytest.raises(SemanticGateClosed):
            session.click_daily_precombat_start()
    assert not backend.taps
    assert adapter._meta_precombat_start_receipt is None


def test_new_frame_expiring_during_final_proof_still_refuses_without_retry():
    backend, session, _ = setup()
    adapter = session.open()
    acquire = adapter._fresh_input_oracle
    calls = []

    def expires_after_proof():
        reader = acquire()
        fleet_ready = reader.meta_precombat_fleet_ready

        def delayed_fleet():
            ready = fleet_ready()
            clock = session._frame_clock
            captured = clock._current.captured_monotonic_ns
            clock._monotonic_ns = lambda: captured + 11_000_000_000
            return ready

        reader.meta_precombat_fleet_ready = delayed_fleet
        calls.append(1)
        return reader

    adapter._fresh_input_oracle = expires_after_proof
    with pytest.raises(ExpiredFrameError):
        session.click_daily_precombat_start()
    assert calls == [1]
    assert not backend.taps


def test_postdispatch_foreground_failure_never_resubmits_start():
    backend, session, _ = setup()
    backend.on_tap = lambda: setattr(backend, 'foreground', 'other.package/.Activity')
    with pytest.raises(SemanticGateClosed):
        session.click_daily_precombat_start()
    assert len(backend.taps) == 1
