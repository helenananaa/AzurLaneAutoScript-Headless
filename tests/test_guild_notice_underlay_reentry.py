"""An accepted global notice close need not return specifically to Main."""
from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_retained_archives_underlay_after_accepted_close_has_no_second_input(drift):
    backend, oracle, adapter = host(drift, 'guild-notice-archives-return-r157.json')
    state = oracle.read_state()
    assert state.generation == 1572
    assert any('ActivityRemasterUI(Clone)' in b.path for b in state.buttons)
    assert not oracle.main_page_visible()
    adapter._guild_message_close_receipt = SimpleNamespace(generation=state.generation - 1)
    assert adapter.click('GUILD_POPUP_CANCEL') is None
    assert not backend.taps


@pytest.mark.parametrize('failure', ['no_receipt', 'same_generation', 'foreign', 'truncated'])
def test_unproven_notice_disappearance_still_fails_closed(failure):
    backend, oracle, adapter = host(False, 'guild-notice-archives-return-r157.json')
    adapter._guild_message_close_receipt = SimpleNamespace(generation=1571)
    if failure == 'no_receipt':
        adapter._guild_message_close_receipt = None
    elif failure == 'same_generation':
        adapter._guild_message_close_receipt.generation = 1572
    elif failure == 'foreign':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.buttons['truncated'] = True
    with pytest.raises(SemanticGateClosed):
        adapter.click('GUILD_POPUP_CANCEL')
    assert not backend.taps
