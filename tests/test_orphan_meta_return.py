"""Orphan recovery accepts a proven META destination without a prior owner."""
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_frame_post_input_foreground import session_for_meta


@pytest.mark.parametrize('drift', [False, True])
def test_actual_assist_return_ends_recovery_without_meta_task_ownership(monkeypatch, drift):
    backend, session, frame = session_for_meta('orphan-meta-assist-return-r375.json')
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['optional_upstream_field'] = 1
    assert not session.open().meta_beacon_active()
    assert not session.open()._meta_assist_active
    assert frame.meta_page_visible()
    frame.meta_assist_state()  # Complete actual selected beacon and attempts.
    # The result had just disappeared before this retained return frame.
    session.orphan_combat_result_visible = Mock(return_value=True)
    sleep = Mock(side_effect=AssertionError('stable typed return must not wait'))
    monkeypatch.setattr('alas_headless.adapter.semantic.session_combat.time.sleep', sleep)
    assert session.recover_orphan_combat_result() == ()
    assert not backend.taps
    assert not session.open()._meta_assist_active


def test_foreign_package_does_not_complete_orphan_recovery(monkeypatch):
    backend, session, _ = session_for_meta('orphan-meta-assist-return-r375.json')
    session.orphan_combat_result_visible = Mock(return_value=True)
    backend.foreground = 'unrelated.package/.Activity'
    session._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 0
    with pytest.raises(SemanticGateClosed):
        session.recover_orphan_combat_result()
    assert not backend.taps
