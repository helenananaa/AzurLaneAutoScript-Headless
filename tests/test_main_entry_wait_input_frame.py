"""A main-page mount wait must reacquire its expired input frame."""
import pytest
from alas_headless import SemanticGateClosed
from tests.test_frame_post_input_foreground import session_for_meta


@pytest.mark.parametrize('foreign', [False, True])
def test_main_entry_after_mount_wait_reacquires_and_checks_real_foreground(monkeypatch, foreign):
    backend, session, _ = session_for_meta('main-tech-after-wait-r256.json')
    adapter = session.open()
    path = adapter.oracle._unique(adapter.oracle.read_state(), 'main/tech').path
    button = next(b for b in backend.buttons['buttons'] if b['path'] == path)
    button['raycast_top'] = False
    old = session._frame_clock.borrow()
    waits = []
    def finish_mount(_):
        waits.append(True)
        assert not backend.taps
        session._frame_clock._monotonic_ns = lambda: old.captured_monotonic_ns+11_000_000_000
        button['raycast_top'] = True
        for p in (backend.snapshot, backend.buttons, backend.ui):
            p['generation'] += 1
        if foreign:
            backend.foreground = 'unrelated/.Activity'
    monkeypatch.setattr('alas_headless.adapter.semantic.dispatch_actions.time.sleep', finish_mount)
    if foreign:
        with pytest.raises(SemanticGateClosed):
            adapter._click_main_ready('main/tech')
        assert not backend.taps
    else:
        receipt = adapter._click_main_ready('main/tech')
        assert receipt.semantic_id == 'main/tech'
        assert receipt.generation > old.generation
        assert len(backend.taps) == 1
    assert waits
