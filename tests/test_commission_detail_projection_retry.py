from copy import deepcopy
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_text, make_ui, make_oracle


SIGNATURE = (1, '日常资源开发III', 15, 3600, 'pending', 'faxiankuangmai')


def detail():
    root = 'root/Overlay/UIMain/blur_panel/'
    base = root + 'scrollItem/'
    panel = base + 'maskDetail/detailPanel/'
    buttons = [make_button('back_btn', root + 'adapt/top/back_btn'),
               make_button('btn_recommend', panel + 'btn_recommend', 935, 363),
               make_button('btn', panel + 'btn', 1092, 363)]
    buttons.extend(make_button('emptytpl', panel + f'frame/ship_contain_{side}/ship_{slot}/emptytpl')
                   for side in ('left', 'right') for slot in range(1, 4))
    backend = FakeBackend(buttons)
    backend.ui = make_ui([make_text('日常资源开发III', base + 'labelName$'),
                         make_text('15', base + 'level/labelLv$'),
                         make_text('01:00:00', base + 'labelTime$/Text'),
                         make_text('0', panel + 'consume/Text')])
    return backend, make_oracle(backend)


def test_complete_detail_reacquisition_preserves_identity_before_one_recommend_input():
    backend, oracle = detail()
    backend.ui['generation'] = 13
    sleeps = []
    def publish(_):
        assert not backend.taps
        sleeps.append(True)
        backend.snapshot['generation'] = backend.buttons['generation'] = backend.ui['generation'] = 20
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['compatible_addition'] = True
    oracle._sleep = publish
    receipt = oracle.click_commission_recommend(SIGNATURE)
    assert receipt.generation == 20 and backend.taps == [(935, 363)] and len(sleeps) == 1


@pytest.mark.parametrize('case', ['persistent', 'stale', 'foreign', 'foreground', 'ambiguous', 'identity-changed', 'unassigned-start'])
def test_invalid_detail_does_not_recommend_or_start(case):
    backend, oracle = detail()
    if case == 'persistent': backend.ui['generation'] = 13
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    elif case == 'foreign': backend.snapshot['package'] = 'other.package'
    elif case == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    elif case == 'ambiguous':
        backend.ui['texts'].append(deepcopy(backend.ui['texts'][0]))
        backend.ui['text_count'] += 1
    elif case == 'identity-changed': backend.ui['texts'][0]['text'] = '另一委托'
    oracle._sleep = lambda _: None
    with pytest.raises(SemanticGateClosed):
        if case == 'unassigned-start': oracle.click_commission_start(SIGNATURE)
        else: oracle.click_commission_recommend(SIGNATURE)
    assert not backend.taps


def test_detail_public_read_retains_one_existing_four_attempt_budget():
    backend, oracle = detail()
    backend.ui['generation'] = 13
    oracle._commission_detail_state_once = Mock(wraps=oracle._commission_detail_state_once)
    def still_split(_):
        backend.snapshot['generation'] += 4
        backend.buttons['generation'] += 4
        backend.ui['generation'] += 4
    oracle._sleep = still_split
    with pytest.raises(SemanticGateClosed, match='not coherent'): oracle.commission_detail_state()
    assert oracle._commission_detail_state_once.call_count == 4 and not backend.taps


def test_immutable_detail_does_not_poll_the_same_split_pair():
    backend, live = detail()
    backend.ui['generation'] = 13
    sleeps = []
    fixed = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        backend.tap, live.fingerprint, sleep=lambda _: sleeps.append(True), frame_guard=lambda: None)
    with pytest.raises(SemanticGateClosed, match='not coherent'): fixed.commission_detail_state()
    assert not backend.taps and not sleeps


def test_uncertain_recommend_input_is_not_repeated():
    backend, oracle = detail()
    error = SemanticGateClosed('recommend outcome uncertain')
    def uncertain(*_): raise error
    backend.on_tap = uncertain
    with pytest.raises(SemanticGateClosed) as caught: oracle.click_commission_recommend(SIGNATURE)
    assert caught.value is error and len(backend.taps) == 1
