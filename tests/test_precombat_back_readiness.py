import pytest
from unittest.mock import Mock
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle

ROOT = 'OverlayCamera/Overlay/UIMain/PreCombatUI(Clone)/'


def backend():
    return FakeBackend([make_button('start', ROOT+'adapt/right/start', raycast_top=None),
                        make_button('back_btn', ROOT+'blur_panel/top/back_btn', raycast_top=None)])


@pytest.mark.parametrize('popup', [False, True])
@pytest.mark.parametrize('action', ['start', 'back'])
def test_current_meta_detail_underlay_yields_only_to_mounted_precombat(action, popup):
    b = backend()
    b.buttons['buttons'].append(make_button('start_btn',
        'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossDetailUI(Clone)/btns/start_btn'))
    if popup:
        b.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b.buttons['button_count'] = len(b.buttons['buttons'])
    o = make_oracle(b)
    o._sleep = lambda _: None
    method = getattr(o, 'click_daily_precombat_' + action)
    if popup:
        with pytest.raises(SemanticGateClosed, match='blocked'):
            method()
        assert not b.taps
    else:
        assert method().semantic_id == 'daily/precombat/' + action
        assert len(b.taps) == 1


def test_current_meta_detail_does_not_admit_absent_precombat():
    b = FakeBackend([make_button('start_btn',
        'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossDetailUI(Clone)/btns/start_btn')])
    o = make_oracle(b)
    o._sleep = lambda _: None
    assert [r.blocker_id for r in o._blocking_rules(o.read_state(), 'daily/precombat/start')] == ['meta-current-detail']
    with pytest.raises(SemanticGateClosed, match='absent'):
        o.click_daily_precombat_start()
    assert not b.taps


@pytest.mark.parametrize('change', [None, 'loading', 'foreground'])
def test_back_checks_blockers_and_foreground_before_one_input(change):
    b = backend()
    if change == 'loading':
        b.buttons['buttons'].append(make_button('block', 'root/UIOverlay/Loading(Clone)/block'))
        b.buttons['button_count'] += 1
    o = make_oracle(b)
    o._sleep = lambda _: None
    if change == 'foreground': o._foreground_component = Mock(return_value='other/activity')
    if change:
        with pytest.raises(SemanticGateClosed): o.click_daily_precombat_back()
        assert not b.taps
    else:
        assert o.click_daily_precombat_back().semantic_id == 'daily/precombat/back'
        assert len(b.taps) == 1


@pytest.mark.parametrize('change', [None, 'loading', 'foreground'])
def test_start_checks_readiness_before_one_typed_tap(change):
    b = backend()
    if change == 'loading':
        b.buttons['buttons'].append(make_button('block', 'root/UIOverlay/Loading(Clone)/block'))
        b.buttons['button_count'] += 1
    o = make_oracle(b)
    o._sleep = lambda _: None
    if change == 'foreground': o._foreground_component = Mock(return_value='other/activity')
    if change in ('loading', 'foreground'):
        with pytest.raises(SemanticGateClosed): o.click_daily_precombat_start()
        assert not b.taps and not b.swipes
    else:
        receipt = o.click_daily_precombat_start()
        x, y = round(receipt.point.x), round(receipt.point.y)
        assert b.taps == [(x,y)] and not b.swipes
        assert o.input_dispatch_count == 1
