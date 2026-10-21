"""A slow result observation must not dispatch against an expired screenshot."""
import json
from pathlib import Path
import pytest
from alas_headless.adapter import StaleFrameError

from tests.test_frame_post_input_foreground import session_for_meta


@pytest.mark.parametrize('drift', [False, True])
def test_result_drain_refreshes_and_binds_each_action_to_its_current_frame(monkeypatch, drift):
    backend, session, _ = session_for_meta('exercise-completed-orphan-r244.json')
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['optional_metadata'] = {'upstream_addition': True}
    old = session._frame_clock.borrow()
    session._frame_clock._monotonic_ns = lambda: old.captured_monotonic_ns+11_000_000_000
    generation = max(part['generation'] for part in
                     (backend.snapshot, backend.buttons, backend.ui))+1
    pid, revision = backend.snapshot['pid'], backend.snapshot['driver_revision']
    destination = json.loads((Path(__file__).parent/'fixtures/exercise-retained-r185.json').read_text(encoding='utf8'))
    def entered_overview():
        # Offline advancing-runtime simulation only. Retained source fixtures
        # keep their original identities and generations on disk.
        backend.snapshot, backend.buttons, backend.ui = (
            destination['snapshot'], destination['buttons'], destination['ui'])
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'], part['pid'], part['driver_revision'] = generation, pid, revision
    backend.on_tap = entered_overview
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', lambda _: None)
    receipts = session.complete_exercise_battle_result()
    assert len(receipts) == 1
    assert receipts[0].semantic_id == 'daily/battle/result'
    assert len(backend.taps) == 1
    assert session.open().oracle.input_dispatch_count == 1
    assert session._frame_clock.borrow(require_fresh=True).generation == generation


def test_result_drain_without_a_new_frame_never_dispatches(monkeypatch):
    backend, session, _ = session_for_meta('exercise-completed-orphan-r244.json')
    def unavailable():
        raise StaleFrameError()
    monkeypatch.setattr(session, 'refresh_frame', unavailable)
    with pytest.raises(StaleFrameError):
        session.complete_exercise_battle_result()
    assert not backend.taps
    assert session.open().oracle.input_dispatch_count == 0
