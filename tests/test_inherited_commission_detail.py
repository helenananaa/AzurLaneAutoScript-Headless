from copy import deepcopy
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import make_button, make_buttons, make_snapshot, make_ui
from tests.test_commission_detail_projection_retry import detail, SIGNATURE


def host():
    backend, oracle = detail()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_commission()
    return backend, oracle, adapter


@pytest.mark.parametrize('probe', ['COMMISSION_CHECK', 'MAIN_PAGE', 'RESEARCH_CHECK', 'GAME_ROOM_CHECK', 'GOTO_MAIN_WHITE', 'RPG_HOME'])
def test_inherited_detail_reaches_only_native_unknown_page_return(probe):
    backend, oracle, adapter = host()
    assert adapter.appear(SimpleNamespace(name=probe)) is False
    assert adapter.appear(SimpleNamespace(name='GOTO_MAIN')) is True
    assert not backend.taps


@pytest.mark.parametrize('destination', ['list', 'reward'])
def test_one_return_input_requires_a_new_actionable_native_destination(destination):
    backend, oracle, adapter = host()
    def publish(*_):
        backend.snapshot = make_snapshot(generation=11)
        button = (make_button('back_btn', 'root/UICamera/Canvas/UIMain/EventUI(Clone)/blur_panel/adapt/top/back_btn')
                  if destination == 'list' else make_button('CommissionInfoUI4Mellow(Clone)',
                      'root/OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'))
        backend.buttons = make_buttons([button], generation=11)
        backend.ui = make_ui([], generation=11)
    backend.on_tap = publish
    receipt = adapter.click(SimpleNamespace(name='GOTO_MAIN'))
    assert receipt.semantic_id == 'commission/detail/back' and len(backend.taps) == 1
    target = 'commission/page/back' if destination == 'list' else 'reward/page/back'
    assert oracle.enabled(target) and oracle.read_state().generation > receipt.generation


@pytest.mark.parametrize('case', ['malformed', 'ambiguous', 'modal', 'foreground', 'stale'])
def test_unproven_detail_cannot_borrow_recovery(case):
    backend, oracle, adapter = host()
    if case == 'malformed': backend.ui['texts'][1]['text'] = 'unknown'
    elif case == 'ambiguous':
        backend.ui['texts'].append(deepcopy(backend.ui['texts'][0]))
        backend.ui['text_count'] += 1
    elif case == 'modal':
        backend.buttons['buttons'].append(make_button('confirm', 'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    else: backend.snapshot['age_ms'] = 100000
    oracle._sleep = lambda _: None
    with pytest.raises(SemanticGateClosed): adapter.click(SimpleNamespace(name='GOTO_MAIN'))
    assert not backend.taps


def test_current_native_selection_is_not_discarded_as_inherited_detail():
    backend, oracle, adapter = host()
    adapter._commission_context.selected_signature = SIGNATURE
    assert adapter._retained_commission_detail_visible(oracle) is False
    assert adapter._goto_main_target() is None and not backend.taps


def test_input_frame_change_rejects_return_before_input():
    backend, oracle, adapter = host()
    def changed():
        backend.ui['texts'][1]['text'] = 'unknown'
        return oracle
    adapter._fresh_input_oracle = changed
    oracle._sleep = lambda _: None
    with pytest.raises(SemanticGateClosed): adapter.click(SimpleNamespace(name='GOTO_MAIN'))
    assert not backend.taps


def test_uncertain_return_does_not_repeat_input():
    backend, oracle, adapter = host()
    error = SemanticGateClosed('detail return uncertain')
    def uncertain(*_): raise error
    backend.on_tap = uncertain
    with pytest.raises(SemanticGateClosed) as caught: adapter.click(SimpleNamespace(name='GOTO_MAIN'))
    assert caught.value is error and len(backend.taps) == 1


def test_unrelated_page_with_shared_back_does_not_enter_commission_parser():
    from unittest.mock import Mock
    backend, oracle, adapter = host()
    backend.buttons['buttons'] = [backend.buttons['buttons'][0]]
    backend.buttons['button_count'] = 1
    oracle.commission_detail_state = Mock(side_effect=AssertionError('foreign task parser'))
    assert adapter._retained_commission_detail_visible(oracle) is False
    oracle.commission_detail_state.assert_not_called()
    assert not backend.taps
