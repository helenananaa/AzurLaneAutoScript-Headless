"""Regression coverage for the actual semantic input and immutable frame boundary."""

from unittest import mock

import pytest

from alas_headless.adapter import AdbRuntimeHandle, SemanticFrameReader, StaleFrameError
from alas_headless.oracle.targets import TargetsOracle
from alas_headless.semantic_oracle import AdbObserverBridge, SemanticGateClosed
from tests.test_adapter_frame import make_clock
from tests.test_adapter_session_runtime_handle import (
    AlasSemanticSession, FrameRuntimeHandle, PACKAGE, REVISION,
    expected_fingerprint,
)
from tests.test_weekly_mission_state_ports import weekly


@pytest.mark.parametrize("elapsed_ms,admitted", [(99, True), (101, False)])
def test_input_lease_includes_original_observer_age(elapsed_ms, admitted):
    handle, timer, clock = make_clock(max_age_ms=1000)
    handle.snapshot["age_ms"] = handle.buttons["age_ms"] = 900
    frame = clock.acquire()
    oracle = SemanticFrameReader(clock, clock._oracle).oracle()
    timer.value += elapsed_ms * 1_000_000
    # Passive ALAS scans preserve their one screenshot, regardless of age.
    assert oracle.enabled("login/enter")
    if admitted:
        oracle.click("login/enter")
        assert handle.taps == [(640, 360)]
    else:
        with pytest.raises(StaleFrameError):
            oracle.click("login/enter")
        assert handle.taps == []
        assert oracle.input_dispatch_count == 0
    assert frame.age_ms == 900


@pytest.mark.parametrize("include_ui", [False, True])
def test_acquisition_time_does_not_reset_endpoint_age(include_ui):
    handle, timer, clock = make_clock(max_age_ms=1000)
    handle.snapshot["age_ms"] = handle.buttons["age_ms"] = 900
    handle.ui["age_ms"] = 900
    handle.after_request = lambda: setattr(timer, "value", timer.value + 101_000_000)
    with pytest.raises(StaleFrameError):
        clock.acquire(include_ui=include_ui)
    assert clock.current_frame_id is None
    assert handle.taps == []


def adb_session():
    backend = FrameRuntimeHandle()
    bridge = AdbObserverBridge("offline-device", PACKAGE)
    bridge.pid = backend.pid
    bridge.request = backend.observer_request
    bridge.foreground_component = backend.foreground_component
    bridge.tap = backend.tap
    bridge.swipe = backend.swipe
    bridge.package_pid = mock.Mock(return_value=backend.pid)
    handle = AdbRuntimeHandle(bridge, fingerprint_sha256=expected_fingerprint())
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle,
                                  allow_mission_claim_once=True)
    adapter = session.open()
    session.refresh_frame()
    return backend, bridge, session, adapter


@pytest.mark.parametrize("current_pid", [4242, 5000, None])
@pytest.mark.parametrize("gesture", ["tap", "swipe"])
def test_actual_adb_process_is_checked_before_dispatch(current_pid, gesture):
    backend, bridge, session, adapter = adb_session()
    oracle = adapter._require_frame_observation_oracle()
    bridge.package_pid.return_value = current_pid
    operation = (lambda: oracle.click("login/enter")) if gesture == "tap" else (
        lambda: oracle._swipe(10, 20, 30, 40, 100))
    if current_pid == 4242:
        operation()
        assert oracle.input_dispatch_count == adapter.oracle.input_dispatch_count == 1
        assert session._frame_clock.current_frame_id is None
        assert len(backend.taps if gesture == "tap" else backend.swipes) == 1
    else:
        with pytest.raises(SemanticGateClosed, match="game PID changed before semantic input"):
            adapter._dispatch_mutation("mission.claim", operation)
        assert oracle.input_dispatch_count == adapter.oracle.input_dispatch_count == 0
        assert adapter._action_ledger.remaining("mission.claim") == 1
        assert backend.taps == backend.swipes == []
    bridge.package_pid.assert_called_once_with()


def test_slow_current_pid_check_cannot_extend_the_frame_input_lease():
    backend, bridge, session, adapter = adb_session()
    oracle = adapter._require_frame_observation_oracle()
    frame = session._frame_clock.borrow()

    def slow_pid_check():
        session._frame_clock._monotonic_ns = lambda: frame.captured_monotonic_ns + 11_000_000_000
        return bridge.pid

    bridge.package_pid.side_effect = slow_pid_check
    with pytest.raises(StaleFrameError):
        adapter._dispatch_mutation("mission.claim", lambda: oracle.click("login/enter"))
    assert adapter._action_ledger.remaining("mission.claim") == 1
    assert oracle.input_dispatch_count == 0
    assert backend.taps == []


def weekly_session():
    backend, _, _ = weekly()
    handle = FrameRuntimeHandle()
    handle.pid = backend.snapshot["pid"]
    handle.observer_request = backend.request
    handle.foreground_component = backend.foreground_component
    handle.tap = backend.tap
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle,
                                  observer_max_age_ms=1000, allow_mission_claim_once=True)
    adapter = session.open()
    adapter.begin_mission_reward(daily=False, weekly=True)
    frame = session.refresh_frame()
    return backend, handle, session, adapter, frame


def test_weekly_claim_final_stale_refusal_refunds_without_input():
    backend, _, session, adapter, frame = weekly_session()
    session._frame_clock._monotonic_ns = lambda: frame.captured_monotonic_ns + 1_100_000_000
    with pytest.raises(StaleFrameError):
        session.claim_weekly_mission_progress_once()
    assert backend.taps == []
    assert adapter.oracle.input_dispatch_count == 0
    assert adapter._action_ledger.remaining("mission.claim") == 1


def test_unknown_backend_result_still_consumes_grant():
    backend, _, session, adapter, _ = weekly_session()
    failure = RuntimeError("ADB outcome is unknown")
    adapter.oracle._tap_backend = mock.Mock(side_effect=failure)
    with pytest.raises(RuntimeError, match="ADB outcome is unknown"):
        session.claim_weekly_mission_progress_once()
    assert adapter.oracle.input_dispatch_count == 1
    assert adapter._action_ledger.remaining("mission.claim") == 0
    assert backend.taps == []


@pytest.mark.parametrize("bounds,point,expected", [
    ((1200, 330, 1280, 390), (1279.75, 360), (1279, 360)),
    ((600, 680, 680, 720), (640, 719.75), (640, 719)),
    ((10.1, 20.1, 11.9, 21.9), (10.2, 20.2), (11, 21)),
    ((600, 330, 680, 390), (640, 360), (640, 360)),
    ((10.1, 20.1, 10.4, 20.4), (10.2, 20.2), None),
])
def test_integer_tap_remains_inside_target_and_screen(bounds, point, expected):
    handle, _, clock = make_clock()
    button = handle.buttons["buttons"][0]
    button["adb_point"] = dict(zip(("x", "y"), point))
    button["adb_bounds"] = dict(zip(("left", "top", "right", "bottom"), bounds))
    if expected is None:
        with pytest.raises(SemanticGateClosed, match="no in-bounds integer input point"):
            clock._oracle.click("login/enter")
        assert handle.taps == []
        assert clock._oracle.input_dispatch_count == 0
    else:
        clock._oracle.click("login/enter")
        assert handle.taps == [expected]


def test_blockers_are_memoized_only_for_current_immutable_frame():
    handle, _, clock = make_clock()
    clock.acquire()
    provider = SemanticFrameReader(clock, clock._oracle)
    first = provider.oracle()
    state = first.read_state()
    original = TargetsOracle._blocking_rules
    calls = []

    def counted(oracle, current, semantic_id):
        calls.append((oracle, current, semantic_id))
        return original(oracle, current, semantic_id)

    with mock.patch.object(TargetsOracle, "_blocking_rules", counted):
        expected = first._blocking_rules(state, "login/enter")
        for _ in range(10):
            assert first._blocking_rules(state, "login/enter") is expected
        assert len(calls) == 1
        first._blocking_rules(state, "main/task")
        assert len(calls) == 2
        # A live mutable state is never retained by the frame cache.
        live_state = clock._oracle.read_state()
        first._blocking_rules(live_state, "login/enter")
        first._blocking_rules(live_state, "login/enter")
        assert len(calls) == 4
        clock._oracle._blocking_rules(live_state, "login/enter")
        clock._oracle._blocking_rules(live_state, "login/enter")
        assert len(calls) == 6
        handle.snapshot["generation"] = handle.buttons["generation"] = 11
        clock.acquire()
        second = provider.oracle()
        second._blocking_rules(second.read_state(), "login/enter")
        assert len(calls) == 7
        with pytest.raises(StaleFrameError):
            first._blocking_rules(state, "login/enter")
        assert len(calls) == 7
