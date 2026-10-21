"""A departing sidebar under Loading cannot abort native reward reception."""
import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['REWARD_2', 'REWARD_2_WHITE'])
def test_actual_departing_reward_yields_to_next_native_screenshot(name, drift):
    backend, oracle, _ = host(drift, 'tactical-reward-loading-r656.json')
    adapter = AlasSemanticAdapter(oracle, lambda: None, allow_tactical_rewards=True)
    adapter.begin_tactical()
    assert adapter.appear(name) is False
    assert not backend.taps and oracle.input_dispatch_count == 0
    assert adapter._action_ledger.remaining('tactical.reward') == 1
    # Passive absence does not make the covered source actionable.
    with pytest.raises(SemanticGateClosed):
        oracle.click('reward/tactical/finish')
    assert not backend.taps


@pytest.mark.parametrize('damage', ['foreign-modal', 'foreign-package', 'truncated'])
def test_loading_absence_does_not_hide_invalid_or_unknown_state(damage):
    backend, oracle, _ = host(fixture='tactical-reward-loading-r656.json')
    if damage == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif damage == 'foreign-package':
        backend.foreground = 'other/.Activity'
    else:
        backend.buttons['truncated'] = True
    adapter = AlasSemanticAdapter(oracle, lambda: None, allow_tactical_rewards=True)
    adapter.begin_tactical()
    with pytest.raises(SemanticGateClosed):
        adapter.appear('REWARD_2')
    assert not backend.taps and oracle.input_dispatch_count == 0
