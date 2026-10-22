"""An expiring global notice returns to native ALAS without an extra input."""
from unittest.mock import patch
import pytest
from alas_headless import SemanticGateClosed
from tests.test_frame_post_input_foreground import session_for_meta
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('disappears', [False, True])
@pytest.mark.parametrize('drift', [False, True])
def test_notice_close_reuses_one_fresh_frame_or_yields_if_it_expired(disappears, drift):
    backend, oracle, adapter = host(drift, 'guild-notice-expired-main-r386.json')
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    path = 'OverlayCamera/Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/close'
    backend.buttons['buttons'].append(make_button('close', path))
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] = generation
    with patch('tests.test_frame_post_input_foreground.host', return_value=(backend, oracle, adapter)):
        _, session, _ = session_for_meta()
    refresh = session.refresh_frame
    def advance():
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] += 1
        if disappears:
            backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['path'] != path]
            backend.buttons['button_count'] = len(backend.buttons['buttons'])
        return refresh()
    with patch.object(session, 'refresh_frame', side_effect=advance) as acquire:
        receipt = session.click('GUILD_POPUP_CANCEL')
    assert acquire.call_count == 1
    assert len(backend.taps) == (0 if disappears else 1)
    if disappears:
        assert receipt is None
        # Direct input without the preceding positive observation stays closed.
        with pytest.raises(SemanticGateClosed, match='close is absent'):
            session.open().click('GUILD_POPUP_CANCEL')
    else:
        assert receipt.semantic_id == 'overlay/guild-message/close'
