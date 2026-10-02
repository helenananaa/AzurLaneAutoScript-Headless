from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui

ROOT = 'UICamera/Canvas/UIMain/CombatLoadUI(Clone)/loading/loading_label'


@pytest.mark.parametrize('change', [None, 'additive-images', 'missing', 'duplicate', 'stale', 'popup', 'wrong-owner'])
def test_typed_loading_requires_complete_coherent_unique_owner(change):
    b = FakeBackend([])
    b.ui = make_ui([make_text('NOW LOADING...', ROOT), make_text('100.00%', ROOT+'/percent')])
    if change == 'additive-images':
        b.ui['image_truncated'] = True
    elif change == 'missing':
        b.ui['texts'].pop()
    elif change == 'duplicate':
        b.ui['texts'].append(dict(b.ui['texts'][-1]))
    elif change == 'stale':
        b.ui['generation'] = 13
    elif change == 'popup':
        b.buttons['buttons'].append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] = 1
    elif change == 'wrong-owner':
        for t in b.ui['texts']:
            t['path'] = t['path'].replace('CombatLoadUI', 'UnknownUI')
    b.ui['text_count'] = len(b.ui['texts'])
    o = make_oracle(b)
    if change == 'stale':
        with pytest.raises(SemanticGateClosed):
            o.daily_battle_loading_visible()
    else:
        assert o.daily_battle_loading_visible() is (change in (None, 'additive-images'))
    assert not b.taps


def test_pending_beacon_start_returns_receipt_during_typed_loading_without_second_input():
    o = FakeOracle()
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    prior = o.click_receipt('daily/precombat/start', generation=7)
    a._meta_precombat_start_receipt = prior
    a._meta_precombat_start_until = float('inf')
    o.read_state = lambda: SimpleNamespace(generation=8)
    o.daily_battle_loading_visible = lambda: True
    o.daily_combat_visible = lambda: False
    o.click_daily_precombat_start = Mock(side_effect=AssertionError('must not reclick'))
    assert a.click_meta_precombat_start() is prior
    o.click_daily_precombat_start.assert_not_called()
