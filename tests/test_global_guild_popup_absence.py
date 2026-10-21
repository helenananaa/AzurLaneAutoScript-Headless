"""A global popup's absence does not require a Mission flow owner."""
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_commission_inheriting_guild_can_probe_absent_global_notice(drift):
    backend, oracle, adapter = host(drift, 'commission-inherited-guild-r274.json')
    # Offline stable replay at the paired UI publication; preserve the raw
    # original clocks in the retained fixture rather than editing evidence.
    backend.snapshot['generation'] = backend.buttons['generation'] = backend.ui['generation']
    adapter.begin_commission()
    adapter._commission_context.passive_transition_until = 0
    assert not oracle.observation_target_present('overlay/guild-message/close')
    assert adapter.appear('GUILD_POPUP_CONFIRM') is False
    assert adapter.appear('GUILD_POPUP_CANCEL') is False
    assert not backend.taps


@pytest.mark.parametrize('failure', ['foreign', 'truncated'])
def test_global_absence_does_not_hide_invalid_observation(failure):
    backend, oracle, adapter = host(fixture='commission-inherited-guild-r274.json')
    if failure == 'foreign':
        backend.foreground = 'unrelated/.Activity'
    else:
        backend.buttons['truncated'] = True
    adapter.begin_commission()
    with pytest.raises(SemanticGateClosed):
        adapter.appear('GUILD_POPUP_CONFIRM')
    assert not backend.taps
