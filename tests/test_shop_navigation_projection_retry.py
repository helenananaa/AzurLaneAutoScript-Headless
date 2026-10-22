from copy import deepcopy
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import make_text, make_toggle
from tests.test_shop_page_projection_retry import shop


def navigation():
    backend, oracle = shop()
    path = 'OverlayCamera/Overlay/UIMain/ShopSupplyShopUI(Clone)/buttonList/shop1List/supplyShop/shop2List/monthShop'
    backend.ui['texts'].append(make_text('月度商店', path + '/name'))
    backend.ui['text_count'] += 1
    backend.ui['toggles'] = [make_toggle(path, x=93, y=497)]
    backend.ui['toggle_count'] = 1
    return backend, oracle


def test_split_navigation_reacquires_the_whole_pair_before_one_input():
    backend, oracle = navigation()
    backend.ui['generation'] = 13
    sleeps = []
    def publish(_):
        assert not backend.taps
        sleeps.append(True)
        backend.snapshot['generation'] = backend.buttons['generation'] = backend.ui['generation'] = 20
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['compatible_addition'] = True
        backend.ui['toggles'][0]['adb_point']['x'] = 96
    oracle._sleep = publish
    receipt = oracle.click_shop_nav('月度商店')
    assert receipt.generation == 20 and backend.taps == [(96, 497)] and len(sleeps) == 1


@pytest.mark.parametrize('case', ['persistent', 'stale', 'foreign', 'foreground', 'duplicate', 'missing', 'wrong-page', 'obscured'])
def test_navigation_keeps_invalid_input_closed(case):
    backend, oracle = navigation()
    if case == 'persistent': backend.ui['generation'] = 13
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    elif case == 'foreign': backend.snapshot['package'] = 'other.package'
    elif case == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    elif case == 'duplicate':
        backend.ui['toggles'].append(deepcopy(backend.ui['toggles'][0]))
        backend.ui['toggle_count'] += 1
    elif case == 'missing':
        backend.ui['toggles'] = []
        backend.ui['toggle_count'] = 0
    elif case == 'wrong-page': backend.ui['texts'][0]['text'] = '其他页面'
    else: backend.ui['toggles'][0]['raycast_top'] = False
    oracle._sleep = lambda _: None
    with pytest.raises(SemanticGateClosed): oracle.click_shop_nav('月度商店')
    assert not backend.taps


def test_navigation_uses_one_pair_for_page_and_target():
    backend, oracle = navigation()
    oracle.read_state = Mock(wraps=oracle.read_state)
    oracle.read_ui_state = Mock(wraps=oracle.read_ui_state)
    oracle.munitions_page_visible = Mock(side_effect=AssertionError('independent page read'))
    oracle.click_shop_nav('月度商店')
    assert oracle.read_state.call_count == oracle.read_ui_state.call_count == 1
    assert len(backend.taps) == 1


def test_immutable_navigation_does_not_wait_on_split_publication():
    backend, live = navigation()
    backend.ui['generation'] = 13
    sleeps = []
    fixed = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        backend.tap, live.fingerprint, sleep=lambda _: sleeps.append(True), frame_guard=lambda: None)
    with pytest.raises(SemanticGateClosed, match='not coherent'): fixed.click_shop_nav('月度商店')
    assert not backend.taps and not sleeps


def test_uncertain_navigation_input_is_not_retried():
    backend, oracle = navigation()
    error = SemanticGateClosed('shop navigation outcome uncertain')
    def uncertain(*_): raise error
    backend.on_tap = uncertain
    with pytest.raises(SemanticGateClosed) as caught: oracle.click_shop_nav('月度商店')
    assert caught.value is error and len(backend.taps) == 1
