import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('blocked', [None, 'raycast', 'loading'])
def test_exact_guild_notice_close_can_leave_reward_sidebar_mounted(blocked):
    close = make_button('close', 'OverlayCamera/Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/close',
                        raycast_top=blocked != 'raycast')
    buttons = [close, make_button('frame', 'UICamera/Canvas/UIOrigin/CommissionInfoUI4Mellow(Clone)/frame')]
    if blocked == 'loading':
        buttons.append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    backend = FakeBackend(buttons)
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    adapter.begin_tactical()
    assert adapter.appear('GUILD_POPUP_CANCEL') is (blocked is None)
    if blocked is None:
        assert adapter.click('GUILD_POPUP_CANCEL').semantic_id == 'overlay/guild-message/close'
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            adapter.click('GUILD_POPUP_CANCEL')
        assert backend.taps == []
