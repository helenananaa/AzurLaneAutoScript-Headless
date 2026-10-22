"""Native-prepared globe leases expire without permitting a stale dispatch."""
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import SemanticFrameClock, StaleFrameError
from alas_headless.adapter.errors import ExpiredFrameError
from alas_headless.oracle.errors import SemanticTargetNotActionable
from tests.test_adapter_frame import FakeRuntimeHandle, MutableClock
from tests.test_globe_swipe_box_compatibility import START, END, arm, dispatch
from tests.test_semantic_oracle_opsi_port_geometry import fixture


def host():
    backend, oracle = fixture()
    oracle._sleep = lambda _: None
    handle = FakeRuntimeHandle()
    handle.pid = backend.snapshot['pid']
    handle.snapshot, handle.buttons, handle.ui = backend.snapshot, backend.buttons, backend.ui
    timer = MutableClock()
    clock = SemanticFrameClock(handle, oracle, monotonic_ns=timer)
    clock.acquire()

    def refresh():
        for value in (backend.snapshot, backend.buttons, backend.ui):
            value['generation'] += 1
        return clock.acquire()

    def preflight():
        current = clock.borrow(require_fresh=True)
        clock.invalidate(current.frame_id)

    oracle._input_preflight = preflight
    oracle.operation_siren_globe_drag_owned = Mock(return_value=True)
    backend.on_swipe = lambda: backend.buttons.__setitem__('generation', backend.buttons['generation'] + 1)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._input_frame_refresher = Mock(side_effect=refresh)
    adapter._frame_observation_oracle = lambda: oracle
    arm(adapter, (600, 220, 980, 620))
    return backend, oracle, adapter, clock, timer


def test_native_prepared_fresh_frame_needs_no_duplicate_acquisition():
    backend, oracle, adapter, clock, timer = host()
    receipt = dispatch(adapter)
    adapter._input_frame_refresher.assert_not_called()
    oracle.operation_siren_globe_drag_owned.assert_called_once_with(START, END)
    assert backend.swipes == [(*START, *END, 2000)]
    assert receipt.post_generation > receipt.pre_generation
    assert clock.current_frame_id is None


def test_frame_expiring_during_globe_proof_is_local_preinput_refusal():
    backend, oracle, adapter, clock, timer = host()
    def slow_proof(*_):
        timer.value += 11_000_000_000
        return True
    oracle.operation_siren_globe_drag_owned.side_effect = slow_proof
    with pytest.raises(SemanticTargetNotActionable) as failure:
        dispatch(adapter)
    assert failure.value.semantic_id == 'os/globe/swipe'
    assert isinstance(failure.value.__cause__, StaleFrameError)
    assert oracle.input_dispatch_count == 0
    assert backend.swipes == []
    assert clock.current_frame_id is None


@pytest.mark.parametrize('error', [StaleFrameError(), SemanticGateClosed('foreign process')])
def test_unknown_frame_or_identity_errors_keep_their_original_failure(error):
    backend, oracle, adapter, _, _ = host()
    oracle._input_preflight = Mock(side_effect=error)
    with pytest.raises(type(error)) as failure:
        dispatch(adapter)
    assert failure.value is error
    assert backend.swipes == []


@pytest.mark.parametrize('error', [StaleFrameError(), ExpiredFrameError(51035)])
def test_backend_uncertainty_after_dispatch_is_never_reclassified_or_retried(error):
    backend, oracle, adapter, _, _ = host()
    oracle._swipe_backend = Mock(side_effect=error)
    with pytest.raises(StaleFrameError) as failure:
        dispatch(adapter)
    assert failure.value is error
    assert oracle.input_dispatch_count == 1
    oracle._swipe_backend.assert_called_once()


def test_retained_expiry_age_is_classified_without_weakening_clock_limit():
    handle = FakeRuntimeHandle()
    from tests.test_adapter_frame import make_clock
    handle.snapshot['generation'] = handle.buttons['generation'] = handle.ui['generation'] = 51035
    handle.snapshot['age_ms'] = handle.buttons['age_ms'] = handle.ui['age_ms'] = 5985
    _, timer, clock = make_clock(handle, max_age_ms=10000)
    clock.acquire()
    timer.value += 4_063_000_000
    with pytest.raises(StaleFrameError) as failure:
        clock.borrow(require_fresh=True)
    assert getattr(failure.value, 'generation', None) == 51035
    assert clock.current_frame_id is None
