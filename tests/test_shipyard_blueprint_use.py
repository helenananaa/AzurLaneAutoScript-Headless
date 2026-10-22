"""Stored blueprints follow ALAS's existing use/confirmation flow."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.test_shipyard_purchase import purchase_backend, PANEL
from tests.test_shipyard_state import CARD
from tests.semantic_support.observer_fixtures import make_oracle
from tests.test_alas_config_branch_compatibility import method


def use_backend():
    b = purchase_backend(series=9, owned=13, quantity=1)
    b.ui['texts'] = [t for t in b.ui['texts'] if '/pursuing_cost/' not in t['path']]
    b.ui['text_count'] = len(b.ui['texts'])
    b.ui['shipyard_strengthen'].update(pursuing=0, gems_known=True, paid_gems=5, free_gems=17)
    return b


def finish(b, *, hide_quantity=True):
    b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
    native = b.ui['shipyard_strengthen']
    native['exp'] += 1
    next(t for t in b.ui['texts'] if t['path'] == CARD + '/count' and t['text'] == '13')['text'] = '12'
    if hide_quantity:
        b.ui['texts'] = [t for t in b.ui['texts'] if '/calc_panel/' not in t['path']
                        and '/level_bg/' not in t['path']]
    b.ui['text_count'] = len(b.ui['texts'])


def test_new_series_without_coin_purchasing_can_use_its_own_blueprints():
    b = use_backend(); o = make_oracle(b)
    before = o.shipyard_blueprint_use_state(3)
    assert before.panel.blueprint_count == 13 and before.panel.quantity == 1
    assert before.native.series == 9
    o.click_shipyard_blueprint_use(before)
    assert len(b.taps) == 1


@pytest.mark.parametrize('field', ['stock', 'quantity', 'coins', 'gems', 'phase', 'ship', 'coin_quote', 'obscured'])
def test_use_rechecks_exact_item_request_before_any_input(field):
    b = use_backend(); o = make_oracle(b); before = o.shipyard_blueprint_use_state(3)
    if field == 'stock':
        next(t for t in b.ui['texts'] if t['path'] == CARD + '/count' and t['text'] == '13')['text'] = '12'
    elif field == 'quantity':
        next(t for t in b.ui['texts'] if t['path'].endswith('/calc/base/count/Text'))['text'] = '2'
    elif field == 'coins': b.ui['shipyard_strengthen']['coins'] += 1
    elif field == 'gems': b.ui['shipyard_strengthen']['free_gems'] += 1
    elif field == 'ship': b.ui['shipyard_strengthen']['blueprint_id'] += 1
    elif field == 'phase':
        for t in b.ui['texts']:
            t['path'] = t['path'].replace('/mod_panel/desc/calc_panel', '/fitting_panel/desc/bottom')
    elif field == 'coin_quote':
        from tests.semantic_support.observer_fixtures import make_text
        b.ui['texts'].append(make_text('0', PANEL + '/confirm_btn/pursuing_cost/Text'))
        b.ui['text_count'] += 1
    elif field == 'obscured': b.buttons['buttons'][-2]['raycast_top'] = False
    with pytest.raises(SemanticGateClosed): o.click_shipyard_blueprint_use(before)
    assert b.taps == []


def test_missing_optional_gem_balances_closes_only_item_consumption():
    b = use_backend(); b.ui['shipyard_strengthen']['gems_known'] = False
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='premium balances'): o.shipyard_blueprint_use_state(3)
    assert o.shipyard_blueprint_count(3) == 13
    assert o.shipyard_page_visible()
    purchase = purchase_backend()
    assert make_oracle(purchase).shipyard_purchase_state(3).panel.quantity == 2
    assert b.taps == []


@pytest.mark.parametrize('field', ['stock', 'coins', 'paid_gems', 'free_gems', 'purchased', 'identity', 'progress', 'stale'])
def test_use_completion_requires_exact_inventory_progress_and_unchanged_balances(field):
    b = use_backend(); o = make_oracle(b); before = o.shipyard_blueprint_use_state(3)
    finish(b)
    after = o.shipyard_blueprint_use_result(3)
    assert o.verify_shipyard_blueprint_use(before, after) is after
    if field == 'stock': after = replace(after, blueprint_count=11)
    elif field in ('paid_gems', 'free_gems'):
        after = replace(after, **{field: getattr(after, field) - 1})
    else:
        key, value = {'coins': ('coins', after.native.coins - 1),
            'purchased': ('purchased', after.native.purchased + 1),
            'identity': ('blueprint_id', after.native.blueprint_id + 1),
            'progress': ('exp', before.native.exp),
            'stale': ('generation', before.native.generation)}[field]
        after = replace(after, native=replace(after.native, **{key: value}))
    with pytest.raises(SemanticGateClosed): o.verify_shipyard_blueprint_use(before, after)
    assert b.taps == []


def test_completed_fate_inventory_read_is_independent_of_dev_and_quantity():
    b = use_backend(); finish(b)
    o = make_oracle(b)
    assert o.shipyard_blueprint_count(3) == 12
    b.ui['shipyard_strengthen']['status'] = 2
    assert o.shipyard_blueprint_use_result(3) is None
    b.ui['pid'] += 1
    with pytest.raises(SemanticGateClosed): o.shipyard_blueprint_use_result(3)


def test_inventory_rejects_active_truncated_owner_duplicate():
    b = use_backend(); finish(b)
    field = next(t for t in b.ui['texts'] if t['path'] == CARD + '/count' and t['text'] == '12')
    b.ui['texts'].append({**field, 'flags': field['flags'] | 0x10})
    b.ui['text_count'] += 1
    with pytest.raises(SemanticGateClosed): make_oracle(b).shipyard_blueprint_use_result(3)


def test_actual_patched_use_keeps_remaining_inventory_strategy(monkeypatch):
    session = Mock()
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    host = SimpleNamespace(_shipyard_get_bp_count=Mock(side_effect=[13, 12]),
        _shipyard_buy_enter=lambda: True, _shipyard_cannot_strengthen=Mock(side_effect=[False, True]),
        _shipyard_ensure_index=lambda count: count - 1, _shipyard_buy_confirm=Mock())
    use = method('module/shipyard/shipyard_reward.py', 'RewardShipyard', '_shipyard_use')
    use(host, 3)
    session.begin_shipyard_blueprint_use.assert_called_once_with(3, 1)
    session.end_shipyard_blueprint_use.assert_called_once_with()
    host._shipyard_buy_confirm.assert_called_once_with('BP_USE')
    assert host._shipyard_get_bp_count.call_count == 2


def test_actual_patched_inventory_port_does_not_consume_dev_level(monkeypatch):
    b = use_backend(); finish(b)
    adapter = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: adapter)
    read = method('module/shipyard/ui.py', 'ShipyardUI', '_shipyard_get_bp_count',
                  SHIPYARD_BP_COUNT_GRID=SimpleNamespace(buttons=[object()] * 6))
    assert read(SimpleNamespace(), 3) == 12


def test_failed_decrease_cannot_expand_the_original_requested_quantity(monkeypatch):
    session = SimpleNamespace(shipyard_change_quantity=Mock(return_value=False))
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    ensure = method('module/shipyard/ui.py', 'ShipyardUI', '_shipyard_ensure_index')
    host = SimpleNamespace(_shipyard_focus_index=3, device=Mock(),
        _shipyard_get_total=lambda: (object(), object(), 13))
    with pytest.raises(SemanticGateClosed, match='could not be reduced'): ensure(host, 1)
    session.shipyard_change_quantity.assert_called_once_with(3, -1)
    host.device.multi_click.assert_not_called()


def test_one_blueprint_original_confirmation_waits_through_native_animation(monkeypatch):
    b = use_backend(); o = make_oracle(b)
    session = AlasSemanticAdapter(o, package_gate=lambda: None)
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    session.begin_shipyard_blueprint_use(3, 1)
    def submit():
        b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
        b.ui['shipyard_strengthen']['status'] = 2
    b.on_tap = submit
    def info():
        if b.ui['shipyard_strengthen']['status'] == 2:
            b.ui['shipyard_strengthen']['status'] = 1
            finish(b)
            return True
        return False
    class Timer:
        def __init__(self, *args, **kwargs): pass
        def start(self): return self
        def reset(self): return self
        def reached(self): return True
    host = SimpleNamespace(_shipyard_get_append=lambda: 'DEV', device=Mock(),
        _shipyard_get_total=Mock(side_effect=AssertionError('hidden quantity must not be consumed')),
        interval_clear=Mock(), interval_reset=Mock(), story_skip=Mock(return_value=False),
        handle_info_bar=Mock(side_effect=info), handle_popup_confirm=Mock(side_effect=AssertionError('no msgbox')),
        appear_then_click=Mock(return_value=False), _shipyard_in_ui=lambda: True)
    confirm = method('module/shipyard/ui.py', 'ShipyardUI', '_shipyard_buy_confirm',
        Timer=Timer, SHIPYARD_CONFIRM_DEV=object(), LOGIN_ANNOUNCE=object(), area_pad=lambda value, pad: value)
    confirm(host, 'BP_USE')
    assert len(b.taps) == 1
    host.handle_popup_confirm.assert_not_called()
    host._shipyard_get_total.assert_not_called()
    assert session.shipyard_blueprint_use_completed()
    assert not session.shipyard_blueprint_use_submit()
    session.end_shipyard_blueprint_use()
    with pytest.raises(SemanticGateClosed): session.shipyard_blueprint_use_submit()
