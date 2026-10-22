"""Another native task can discover Home on a complete inherited META detail."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from alas_headless.semantic_oracle import SemanticOracle
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
def test_inherited_current_beacon_is_known_without_requiring_a_meta_task_owner(drift):
    backend, _, adapter = host(drift, fixture='meta-created-detail-r127.json')
    assert not adapter.meta_beacon_active()
    for name in ('FLEET_CHECK', 'META_CHECK', 'MAIN_GOTO_CAMPAIGN', 'GOTO_MAIN_WHITE', 'RPG_HOME'):
        assert adapter.appear(name) is False
    assert adapter.appear('GOTO_MAIN')
    receipt = adapter.click('GOTO_MAIN')
    assert receipt.semantic_id == 'meta/home'
    assert len(backend.taps) == 1


def test_inherited_meta_home_uses_one_fresh_immutable_input_reader():
    backend, live, adapter = host(fixture='meta-created-detail-r127.json')
    live.click_meta_home = Mock(side_effect=AssertionError('split live input proof'))
    fresh = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        live._tap, live.fingerprint, frame_guard=lambda: None,
        input_dispatch_counter=lambda: live.input_dispatch_count)
    adapter._fresh_input_oracle = Mock(return_value=fresh)
    assert adapter.click('GOTO_MAIN').semantic_id == 'meta/home'
    assert len(backend.taps) == 1
    adapter._fresh_input_oracle.assert_called_once()
    live.click_meta_home.assert_not_called()


def test_meta_return_does_not_issue_unrelated_live_dorm_probe_requests():
    backend, live, adapter = host(fixture='meta-created-detail-r127.json')
    frame = SemanticOracle(backend.request, backend.foreground_component, backend.tap, live.fingerprint)
    adapter._frame_observation_oracle = lambda: frame
    original = live.observation_target_present
    def target_present(target):
        if target in ('dorm/feed/shop/cancel', 'dorm/feed/close'):
            raise AssertionError('unrelated live Dorm request')
        return original(target)
    live.observation_target_present = target_present
    assert adapter._click_priority('GOTO_MAIN') is UNHANDLED
    assert not backend.taps


@pytest.mark.parametrize('case', ['foreign_prompt', 'duplicate_home', 'foreign_pid', 'incomplete_detail'])
def test_inherited_meta_page_does_not_authorize_unknown_or_ambiguous_input(case):
    backend, oracle, adapter = host(fixture='meta-created-detail-r127.json')
    if case == 'foreign_prompt':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'duplicate_home':
        path = oracle._unique(oracle.read_state(), 'meta/home').path
        backend.buttons['buttons'].append(deepcopy(next(b for b in backend.buttons['buttons'] if b['path'] == path)))
        backend.buttons['button_count'] += 1
    elif case == 'foreign_pid':
        backend.snapshot['pid'] += 1
    else:
        backend.ui['texts'] = [t for t in backend.ui['texts'] if not t['path'].endswith('/hp/Text')]
        backend.ui['text_count'] = len(backend.ui['texts'])
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click('GOTO_MAIN')
    assert not backend.taps
