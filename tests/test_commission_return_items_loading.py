"""Known loading over the departing reward sidebar is a passive native wait."""
import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP'])
@pytest.mark.parametrize('drift', [False, True])
def test_actual_failed_return_frame_yields_unowned_reward_probes_without_input(name, drift):
    backend, oracle, adapter = host(drift, 'commission-return-items-r499.json')
    assert adapter._mission_context is None and adapter._commission_context is None
    assert adapter.appear(name) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(name)
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('damage', ['foreign-modal', 'foreign-package', 'truncated', 'stale'])
def test_loading_wait_does_not_hide_unreviewed_or_invalid_state(damage):
    backend, oracle, adapter = host(fixture='commission-return-items-r499.json')
    if damage == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif damage == 'foreign-package':
        backend.foreground = 'other/.Activity'
    elif damage == 'truncated':
        backend.buttons['truncated'] = True
    else:
        backend.snapshot['age_ms'] = 10001
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        # Test admission directly; appear() retains its existing input-free
        # stale-frame grace for the next original ALAS screenshot.
        adapter._appear_once('GET_ITEMS_1')
    assert not backend.taps and not backend.swipes
