"""Unrelated multi-choice modals must not become a network reconnect target."""
import copy

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)


@pytest.mark.parametrize('drift', [False, True])
def test_real_equipment_full_is_absent_from_network_alias_without_input(drift):
    backend, oracle, _ = host(drift, 'research-equipment-full-20261027.json')
    assert oracle.read_state().generation == 4098
    for target in ('overlay/network-reconnect/confirm', 'overlay/network-reconnect/cancel'):
        assert oracle.enabled(target) is False
        assert oracle.exists(target) is False
        with pytest.raises(SemanticGateClosed):
            oracle.click(target)
    assert not backend.taps


@pytest.mark.parametrize('code', ['NetworkDown', 'HostNotFound', 'ConnectionReset'])
@pytest.mark.parametrize('duplicate', [False, True])
def test_real_network_prompt_keeps_unique_target_and_input_boundary(code, duplicate):
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    buttons = [make_button('custom_button_1(Clone)', root+'button_container/custom_button_1(Clone)'),
               make_button('custom_button_2(Clone)', root+'button_container/custom_button_2(Clone)')]
    if duplicate:
        buttons.append(copy.deepcopy(buttons[0]))
    backend = FakeBackend(buttons)
    backend.ui = make_ui([
        make_text('服务器连接失败，是否重新连接？\n['+code+']', root+'msg_panel/content'),
        make_text('确 定', root+'button_container/custom_button_1(Clone)/pic'),
        make_text('取 消', root+'button_container/custom_button_2(Clone)/pic'),
    ])
    oracle = make_oracle(backend)
    if duplicate:
        with pytest.raises(SemanticGateClosed, match='ambiguous'):
            oracle.enabled('overlay/network-reconnect/confirm')
        with pytest.raises(SemanticGateClosed):
            oracle.click('overlay/network-reconnect/confirm')
        assert not backend.taps
    else:
        assert oracle.enabled('overlay/network-reconnect/confirm')
        assert oracle.enabled('overlay/network-reconnect/cancel')
        assert not backend.taps


@pytest.mark.parametrize('damage', ['foreign', 'truncated', 'stale'])
def test_non_network_modal_does_not_hide_invalid_runtime(damage):
    backend, oracle, _ = host(fixture='research-equipment-full-20261027.json')
    if damage == 'foreign':
        backend.snapshot['package'] = 'unrelated.package'
    elif damage == 'truncated':
        backend.buttons['truncated'] = True
    else:
        backend.snapshot['age_ms'] = 10001
    with pytest.raises(SemanticGateClosed):
        oracle.enabled('overlay/network-reconnect/confirm')
    assert not backend.taps
