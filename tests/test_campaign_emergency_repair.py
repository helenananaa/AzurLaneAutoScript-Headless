"""Repair inventory, action ownership, and harmless zero-stock coverage."""

from types import SimpleNamespace
import time

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from alas_headless.oracle.campaign_health import PRECOMBAT
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


def repair_backend(count=0, panel=False):
    strategy = PRECOMBAT + 'adapt/middle/strategy'
    buttons = [make_button('start', PRECOMBAT + 'adapt/right/start', raycast_top=True),
               make_button('strategy', strategy, raycast_top=not panel)]
    texts = [make_text(str(count), strategy + '/nums')]
    for group in ('main', 'vanguard'):
        texts.append(make_text('12000', PRECOMBAT + f'adapt/middle/gear_score/{group}/Text'))
    images = [make_image(strategy + '/icon', '4')]
    if count == 0:
        images.append(make_image(strategy + '/mask', 'danyao_bar'))
    if panel:
        root = 'OverlayCamera/Overlay/UIMain/strategy_info/window/panel/'
        texts += [make_text('应急维修', root + 'item/name'),
                  make_text('当前舰队存活角色回复总血量的10%', root + 'item/desc'),
                  make_text(str(count), root + 'item/icon_bg/count')]
        images.append(make_image(root + 'item/icon_bg/icon', '4'))
        buttons += [make_button(action + '_button', root + f'actions/{action}_button',
                                raycast_top=True) for action in ('use', 'cancel')]
    backend = FakeBackend(buttons)
    backend.ui = make_ui(texts, images=images)
    return backend


def test_zero_stock_is_a_real_negative_observation_and_does_not_disable_task():
    backend = repair_backend()
    oracle = make_oracle(backend)
    assert oracle.campaign_emergency_repair_state()['count'] == 0
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='12-4')
    assert adapter._appear_campaign('EMERGENCY_REPAIR_AVAILABLE') is False
    assert backend.taps == []


def test_zero_stock_details_can_be_opened_but_never_consumed():
    backend = repair_backend()
    make_oracle(backend).click_campaign_emergency_repair('open')
    assert len(backend.taps) == 1
    backend = repair_backend(panel=True)
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed, match='empty'):
        oracle.click_campaign_emergency_repair('use')
    oracle.click_campaign_emergency_repair('cancel')
    assert len(backend.taps) == 1


def test_inventory_and_mask_must_agree():
    backend = repair_backend()
    backend.ui['texts'][0]['text'] = '2'
    with pytest.raises(SemanticGateClosed, match='mask disagree'):
        make_oracle(backend).campaign_emergency_repair_state()


def test_positive_stock_routes_only_the_exact_repair_panel():
    backend = repair_backend(2, panel=True)
    oracle = make_oracle(backend)
    oracle.click_campaign_emergency_repair('use')
    assert len(backend.taps) == 1
    next(t for t in backend.ui['texts'] if t['path'].endswith('item/name'))['text'] = '购买维修道具'
    with pytest.raises(SemanticGateClosed, match='identity changed'):
        oracle.click_campaign_emergency_repair('use')
    assert len(backend.taps) == 1


def test_repair_uses_the_observer_proven_hit_point():
    backend = repair_backend(2)
    backend.buttons['buttons'][1]['adb_point']['x'] += 5
    make_oracle(backend).click_campaign_emergency_repair('open')
    assert backend.taps == [(645, 360)]


def test_stale_panel_count_cannot_spend_changed_inventory():
    backend = repair_backend(2, panel=True)
    backend.ui['texts'][0]['text'] = '1'
    with pytest.raises(SemanticGateClosed, match='inventory changed before input'):
        make_oracle(backend).click_campaign_emergency_repair('use')
    assert backend.taps == []


def test_positive_but_unreviewed_raycast_does_not_silently_skip_repair():
    backend = repair_backend(2)
    backend.buttons['buttons'][1]['raycast_top'] = None
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='12-4')
    with pytest.raises(SemanticGateClosed, match='top target'):
        adapter._appear_campaign('EMERGENCY_REPAIR_AVAILABLE')


def test_repair_confirmation_requires_a_pending_open():
    backend = repair_backend(2, panel=True)
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='12-4')
    with pytest.raises(SemanticGateClosed, match='unowned'):
        adapter.click_campaign_repair('EMERGENCY_REPAIR_CONFIRM')
    assert backend.taps == []


def test_repair_entry_animation_can_become_actionable_without_input(monkeypatch):
    backend = repair_backend(3)
    backend.buttons['buttons'][1]['raycast_top'] = None
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='10-2')
    def refresh():
        backend.buttons['buttons'][1]['raycast_top'] = True
        return make_oracle(backend)
    monkeypatch.setattr(adapter, '_fresh_input_oracle', refresh)
    assert adapter._appear_campaign('EMERGENCY_REPAIR_AVAILABLE') is True
    assert backend.taps == []


@pytest.mark.parametrize('remaining, hp_after, expected', [
    (1, (0.8,) * 6, 'complete'),
    (2, (0.5,) * 6, 'pending'),
    (1, (0.5,) * 6, 'pending'),
    (0, (0.8,) * 6, 'inventory'),
    (1, (0.5,) * 6, 'HP improvement'),
])
def test_repair_postcondition_proves_one_item_and_health_effect(remaining, hp_after, expected):
    backend = repair_backend(2)
    oracle = make_oracle(backend)
    oracle.campaign_emergency_repair_panel = lambda: None
    oracle.campaign_emergency_repair_state = lambda: dict(generation=11, count=remaining)
    oracle.campaign_hp_control_snapshot = lambda *a, **kw: (hp_after, (True,) * 6)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    context = _CampaignFlowContext(stage_code='12-4')
    context.repair_use_receipt = SimpleNamespace(generation=10)
    context.repair_open_receipt = SimpleNamespace(generation=9)
    context.repair_count_before = 2
    context.repair_hp_before = (0.5,) * 6
    context.repair_post_deadline = time.monotonic() + 5
    if expected == 'HP improvement':
        context.repair_post_deadline = time.monotonic() - 1
    context.combat_admission = SimpleNamespace(fleet_index=1)
    adapter._campaign_context = context
    if expected in ('complete', 'pending'):
        assert adapter.campaign_repair_postcondition() == expected
        if expected == 'complete':
            assert adapter.campaign_repair_postcondition() is None
            assert len(context.repair_history) == 1
    else:
        with pytest.raises(SemanticGateClosed, match=expected):
            adapter.campaign_repair_postcondition()
    assert backend.taps == []
