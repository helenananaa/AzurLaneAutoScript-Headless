"""Native research cancellation keeps selected identity and exact modal proof."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)


PROMPT = '确定终止研发吗？将不返还材料'


def popup(text=PROMPT):
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    backend = FakeBackend([
        make_button('custom_button_1(Clone)', root + 'button_container/custom_button_1(Clone)'),
        make_button('custom_button_2(Clone)', root + 'button_container/custom_button_2(Clone)'),
    ])
    backend.ui = make_ui([
        make_text(text, root + 'msg_panel/content'),
        make_text('取消', root + 'button_container/custom_button_2(Clone)/pic'),
        make_text('确定', root + 'button_container/custom_button_1(Clone)/pic'),
    ])
    return backend, make_oracle(backend)


def test_stop_modal_is_exact_and_does_not_alias_start_or_queue():
    backend, oracle = popup()
    assert oracle.enabled('research/stop/confirm')
    assert not oracle.enabled('research/queue/confirm')
    assert not oracle.enabled('research/start/confirm')
    assert oracle.click('research/stop/cancel').semantic_id == 'research/stop/cancel'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['wrong-text', 'wrong-label', 'duplicate', 'covered', 'stale'])
def test_unproven_stop_modal_rejects_input(case):
    backend, oracle = popup('是否购买物资？' if case == 'wrong-text' else PROMPT)
    if case == 'wrong-label':
        backend.ui['texts'][2]['text'] = '购买'
    elif case == 'duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count'] += 1
    elif case == 'covered':
        backend.buttons['buttons'][0]['raycast_top'] = False
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    with pytest.raises(SemanticGateClosed):
        oracle.click('research/stop/confirm')
    assert not backend.taps


def adapter():
    oracle = FakeOracle()
    oracle.research_detail_identity = lambda: ('E-315-MI', 9)
    a = AlasSemanticAdapter(oracle, lambda: None)
    a.begin_research()
    a._research_context.selected_code = 'E-315-MI'
    a._research_context.selected_series = 9
    return a, oracle


def test_native_stop_and_confirmation_are_once_only_with_a_postcondition():
    a, oracle = adapter()
    stop = a.click('RESEARCH_STOP')
    assert a.click('RESEARCH_STOP') is stop
    oracle.research_detail_state = Mock(return_value=SimpleNamespace(
        code='E-315-MI', series=9, is_running=False))
    oracle.read_state = lambda: SimpleNamespace(generation=999)
    oracle._retry_transition_read = lambda read, **kwargs: read()
    receipt = a.click('POPUP_CONFIRM_RESEARCH_CANCEL')
    assert a.click('POPUP_CONFIRM_RESEARCH_CANCEL') is receipt
    assert oracle.click_calls == ['research/detail/stop', 'research/stop/confirm']
    oracle.research_detail_state.assert_called_once()


@pytest.mark.parametrize('case', ['no-selection', 'changed-code', 'changed-series'])
def test_stop_requires_the_original_selected_project(case):
    a, oracle = adapter()
    if case == 'no-selection':
        a._research_context.selected_code = None
    else:
        oracle.research_detail_identity = lambda: (
            'D-315-MI' if case == 'changed-code' else 'E-315-MI',
            8 if case == 'changed-series' else 9)
    with pytest.raises(SemanticGateClosed):
        a.click('RESEARCH_STOP')
    assert not oracle.click_calls


def test_confirmation_cannot_stop_a_project_without_native_stop_intent():
    a, oracle = adapter()
    with pytest.raises(SemanticGateClosed):
        a.click('POPUP_CONFIRM_RESEARCH_CANCEL')
    assert not oracle.click_calls


@pytest.mark.parametrize('case', ['running', 'same-generation', 'changed-identity'])
def test_stop_confirmation_requires_an_advancing_selected_postcondition(case):
    a, oracle = adapter()
    a.click('RESEARCH_STOP')
    oracle.research_detail_state = lambda: SimpleNamespace(
        code='D-315-MI' if case == 'changed-identity' else 'E-315-MI',
        series=9, is_running=case == 'running')
    oracle.read_state = lambda: SimpleNamespace(
        generation=0 if case == 'same-generation' else 999)
    oracle._retry_transition_read = lambda read, **kwargs: read()
    with pytest.raises(SemanticGateClosed):
        a.click('POPUP_CONFIRM_RESEARCH_CANCEL')
    assert oracle.click_calls == ['research/detail/stop', 'research/stop/confirm']
