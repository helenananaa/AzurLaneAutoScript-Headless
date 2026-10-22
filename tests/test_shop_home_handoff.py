"""One accepted shop Home returns control to native ui_goto during its fade."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_text, make_toggle, make_ui, make_oracle,
)


def shop_return(drift=False):
    root = 'OverlayCamera/Overlay/UIMain/'
    backend = FakeBackend([make_button('homeBtn', root+'buttonList/top/homeBtn', 1140, 42, raycast_top=None),
                           make_button('closeBtn', root+'buttonList/top/closeBtn')])
    backend.ui = make_ui([make_text('商店', root+'buttonList/top/title/Text')],
        toggles=[make_toggle(root+'buttonList/shop1List/giftPackShop/shop1Tg', checked=False)])
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['optional_metadata'] = {'upstream': 'new'}
    live = make_oracle(backend)
    adapter = AlasSemanticAdapter(live, lambda: None)
    adapter._frame_observation_oracle = lambda: live
    def fresh():
        return _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
            live._tap, live.fingerprint, frame_guard=lambda: None,
            input_dispatch_counter=lambda: live.input_dispatch_count)
    adapter._fresh_input_oracle = Mock(side_effect=fresh)
    live.click_recommendation_shop_home = Mock(side_effect=AssertionError('split live input proof'))
    def departed():
        backend.buttons['buttons'] = [make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')]
        backend.buttons['button_count'] = 1
        backend.ui = make_ui([], generation=backend.snapshot['generation']+1)
        backend.snapshot['generation'] += 1
        backend.buttons['generation'] = backend.snapshot['generation']
    backend.on_tap = departed
    return backend, live, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_shop_home_uses_one_fresh_proof_then_yields_loading_without_duplicate_input(drift):
    backend, live, adapter = shop_return(drift)
    receipt = adapter._click_main('GOTO_MAIN', None)
    assert receipt.semantic_id == 'shop/home'
    assert len(backend.taps) == live.input_dispatch_count == 1
    adapter._goto_main_target = Mock(side_effect=AssertionError('old source edge redispatched'))
    assert adapter._click_main('GOTO_MAIN', None) is receipt
    assert len(backend.taps) == live.input_dispatch_count == 1
    adapter._fresh_input_oracle.assert_called_once()
    live.click_recommendation_shop_home.assert_not_called()


def test_a_real_reentry_after_another_input_can_leave_shop_again_inside_the_window():
    backend, live, adapter = shop_return()
    buttons, ui = deepcopy(backend.buttons), deepcopy(backend.ui)
    first = adapter._click_main('GOTO_MAIN', None)
    _, count, deadline = adapter._shop_home_handoff
    adapter._shop_home_handoff = (first, count-1, deadline)
    backend.snapshot['generation'] += 1
    for source in (buttons, ui):
        source['generation'] = backend.snapshot['generation']
    backend.buttons, backend.ui = buttons, ui
    second = adapter._click_main('GOTO_MAIN', None)
    assert second.semantic_id == 'shop/home' and second.generation > first.generation
    assert len(backend.taps) == live.input_dispatch_count == 2


@pytest.mark.parametrize('case', ['expired', 'intervening_input', 'foreign_prompt', 'foreign_pid'])
def test_unproven_shop_return_does_not_become_a_blanket_no_input_acknowledgement(case):
    backend, live, adapter = shop_return()
    adapter._click_main('GOTO_MAIN', None)
    previous, count, deadline = adapter._shop_home_handoff
    if case == 'expired':
        adapter._shop_home_handoff = (previous, count, 0)
    elif case == 'intervening_input':
        adapter._shop_home_handoff = (previous, count-1, deadline)
    elif case == 'foreign_prompt':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    else:
        backend.snapshot['pid'] += 1
    adapter._goto_main_target = Mock(side_effect=SemanticGateClosed('native edge requires re-entry'))
    with pytest.raises(SemanticGateClosed):
        adapter._click_main('GOTO_MAIN', None)
    assert len(backend.taps) == live.input_dispatch_count == 1
