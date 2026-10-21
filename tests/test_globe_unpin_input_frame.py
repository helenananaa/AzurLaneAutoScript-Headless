"""Native globe centering can outlive its screenshot before the unpin drag."""
from unittest.mock import Mock

import pytest

from alas_headless.adapter import StaleFrameError
from tests.test_combat_screenshot_observation import host


def test_unpin_reacquires_expired_entry_frame_before_existing_live_input_proof():
    backend, session, _ = host('combat', False)
    clock = session._frame_clock
    previous = clock.borrow()
    clock._monotonic_ns = lambda: previous.captured_monotonic_ns + 11_000_000_000
    receipt = object()
    def live_unpin(*, precondition_oracle):
        # The unchanged live oracle's input preflight requires this lease.
        assert clock.borrow(require_fresh=True).frame_id != previous.frame_id
        assert precondition_oracle is session.open()._require_frame_observation_oracle()
        return receipt
    session.open().operation_siren_globe_unpin = Mock(side_effect=live_unpin)
    assert session.operation_siren_globe_unpin() is receipt
    session.open().operation_siren_globe_unpin.assert_called_once()
    assert not backend.taps and not backend.swipes


def test_unpin_never_calls_input_proof_when_new_frame_is_unavailable():
    backend, session, _ = host('combat', False)
    session.refresh_frame = Mock(side_effect=StaleFrameError())
    session.open().operation_siren_globe_unpin = Mock()
    with pytest.raises(StaleFrameError):
        session.operation_siren_globe_unpin()
    session.open().operation_siren_globe_unpin.assert_not_called()
    assert not backend.taps and not backend.swipes
