"""Purchase proof is per selected ship/quantity, never a series allowlist."""
from dataclasses import replace
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.oracle.errors import SemanticSnapshotStale
from tests.test_shipyard_state import backend, CARD
from tests.semantic_support.observer_fixtures import make_button, make_text, make_image, make_oracle
from tests.test_alas_config_branch_compatibility import method

PANEL = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/right_panel/mod_panel/desc/calc_panel'


def purchase_backend(*, series=12, rarity=1, quantity=2, price=150, coins=2000, owned=0):
    b = backend(False)
    for t in b.ui['texts']:
        if t['path'] == CARD + '/count' and t['text'] == '50':
            t['text'] = str(owned)
    b.ui['texts'] += [make_text(str(quantity), PANEL + '/calc/base/count/Text'),
                     make_text('库存:' + str(coins if not owned else owned), PANEL + '/item_bg/kc'),
                     make_text('物资' if not owned else '蓝图：selected ship', PANEL + '/item_bg/name/Text')]
    if quantity:
        b.ui['texts'].append(make_text(str(price), PANEL + '/confirm_btn/pursuing_cost/Text'))
    b.ui['images'] += [make_image('root/blur_panel/adapt/bottom_panel/ships/bg/version/version_btn', 'version_' + str(series)),
                       make_image(PANEL + '/confirm_btn/pursuing_cost/Text/Image', 'res_icon')]
    b.buttons['buttons'] += [make_button('confirm_btn', PANEL + '/confirm_btn'),
                             make_button('plus', PANEL + '/calc/base/plus')]
    b.buttons['button_count'] = len(b.buttons['buttons'])
    b.ui['text_count'] = len(b.ui['texts']); b.ui['image_count'] = len(b.ui['images'])
    b.ui['shipyard_strengthen'] = dict(status=1, truncated=0, stack_balanced=1,
        blueprint_id=29901, ship_index=3, series=series, rarity=rarity, pursuing=1,
        purchased=2, coins=coins, level=15, fate_level=-1, exp=10)
    return b


@pytest.mark.parametrize('series,rarity', [(1, 1), (9, 2), (12, 1)])
def test_purchase_observation_uses_present_capability_not_series_catalog(series, rarity):
    b = purchase_backend(series=series, rarity=rarity)
    s = make_oracle(b).shipyard_purchase_state(3)
    assert s.panel.quantity == 2 and s.panel.total_price == 150
    assert s.panel.series == series and s.rarity == ('pr' if rarity == 1 else 'dr')
    assert b.taps == []


@pytest.mark.parametrize('change', ['native_missing', 'wrong_index', 'wrong_series', 'not_pursuing',
    'unknown_rarity', 'price_missing', 'wrong_currency', 'owned_blueprints', 'duplicate_quantity',
    'bad_native_number', 'incoherent'])
def test_unproven_purchase_stays_local_and_never_inputs(change):
    b = purchase_backend()
    native = b.ui['shipyard_strengthen']
    if change == 'native_missing': del b.ui['shipyard_strengthen']
    elif change == 'wrong_index': native['ship_index'] = 4
    elif change == 'wrong_series': native['series'] = 2
    elif change == 'not_pursuing': native['pursuing'] = 0
    elif change == 'unknown_rarity': native['rarity'] = 3
    elif change == 'bad_native_number': native['purchased'] = True
    elif change == 'incoherent': b.ui['generation'] = 15
    elif change == 'wrong_currency': b.ui['images'][-1]['sprite'] = 'diamond'
    elif change == 'owned_blueprints': b = purchase_backend(owned=1)
    elif change == 'duplicate_quantity':
        b.ui['texts'].append(make_text('2', PANEL + '/calc/base/count/Text')); b.ui['text_count'] += 1
    elif change == 'price_missing':
        b.ui['texts'] = [t for t in b.ui['texts'] if not t['path'].endswith('pursuing_cost/Text')]
        b.ui['text_count'] -= 1
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed): o.shipyard_purchase_state(3)
    # A genuinely incoherent observer frame invalidates that read globally;
    # capability-local missing purchase fields do not affect page navigation.
    if change != 'incoherent':
        assert o.shipyard_page_visible()
    assert b.taps == []


def test_original_request_binds_rarity_amount_and_coin_ceiling():
    b = purchase_backend()
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    assert a.begin_shipyard_purchase(3, 'PR', 2, 150).purchased == 2
    for rarity, count, maximum in [('DR', 2, 150), ('PR', 1, 150), ('PR', 2, 149)]:
        with pytest.raises(SemanticGateClosed): a.begin_shipyard_purchase(3, rarity, count, maximum)
    assert b.taps == []


@pytest.mark.parametrize('price,ceiling', [(0, 0), (100, 150)])
def test_compatible_cheaper_quote_preserves_original_budget(price, ceiling):
    b = purchase_backend(price=price)
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    assert a.begin_shipyard_purchase(3, 'PR', 2, ceiling).panel.total_price == price
    assert b.taps == []


@pytest.mark.parametrize('field', ['quantity', 'price', 'name', 'currency_icon', 'prompt'])
@pytest.mark.parametrize('active', [True, False])
def test_incomplete_active_owner_record_cannot_be_filtered_out(field, active):
    b = purchase_backend(); o = make_oracle(b); before = o.shipyard_purchase_state(3)
    if field == 'prompt':
        add_prompt(b)
        original = b.ui['texts'][-3]
    elif field == 'currency_icon':
        original = b.ui['images'][-1]
    else:
        suffix = {'quantity': '/calc/base/count/Text', 'price': '/pursuing_cost/Text',
                  'name': '/name/name_mask/Text'}[field]
        original = next(t for t in b.ui['texts'] if t['path'].endswith(suffix))
    duplicate = deepcopy(original)
    duplicate['flags'] |= 0x10
    duplicate['active_in_hierarchy'] = active
    family = 'images' if field == 'currency_icon' else 'texts'
    b.ui[family].append(duplicate)
    b.ui['image_count' if family == 'images' else 'text_count'] += 1
    read = (lambda: o.shipyard_purchase_prompt(before)) if field == 'prompt' else (
        lambda: o.shipyard_purchase_state(3))
    if active:
        with pytest.raises(SemanticGateClosed): read()
    else:
        assert read()
    assert b.taps == []


@pytest.mark.parametrize('change', ['quota', 'coins', 'identity', 'no_progress', 'stale'])
def test_postcondition_requires_exact_counter_cost_and_identity(change):
    o = make_oracle(purchase_backend()); before = o.shipyard_purchase_state(3)
    panel = replace(before.panel, generation=11, quantity=0, total_price=None, resource_count=1850)
    after = replace(before, panel=panel, purchased=4, coins=1850, exp=12)
    assert o.verify_shipyard_purchase(before, after) is after
    if change == 'quota': after = replace(after, purchased=3)
    elif change == 'coins': after = replace(after, coins=1849)
    elif change == 'identity': after = replace(after, blueprint_id=29902)
    elif change == 'no_progress': after = replace(after, exp=10)
    elif change == 'stale': after = replace(after, panel=replace(panel, generation=10))
    with pytest.raises(SemanticGateClosed): o.verify_shipyard_purchase(before, after)


@pytest.mark.parametrize('change', ['quote', 'obscured', 'foreground'])
def test_submit_rechecks_quote_and_actionability_before_input(change):
    b = purchase_backend(); o = make_oracle(b); before = o.shipyard_purchase_state(3)
    if change == 'quote': b.ui['shipyard_strengthen']['purchased'] += 1
    elif change == 'obscured': b.buttons['buttons'][-2]['raycast_top'] = False
    else: o._foreground_component = lambda: 'other/activity'
    with pytest.raises(SemanticGateClosed): o.click_shipyard_purchase_submit(before)
    assert b.taps == []


def test_submit_performs_only_one_reviewed_panel_input():
    b = purchase_backend(); o = make_oracle(b)
    assert o.click_shipyard_purchase_submit(o.shipyard_purchase_state(3)).semantic_id == 'shipyard/purchase/submit'
    assert len(b.taps) == 1


def add_prompt(b):
    path = 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'
    b.buttons['buttons'].append(make_button('custom_button_1(Clone)', path))
    b.buttons['button_count'] += 1
    b.ui['texts'] += [make_text('本次强化操作需要消耗150物资，是否确认？',
                                'root/Msgbox(Clone)/window/msg_panel/content'),
        make_text('取消', 'root/Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic'),
        make_text('确定', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic')]
    b.ui['text_count'] = len(b.ui['texts'])


def test_purchase_requires_grant_before_opening_prompt_and_charges_confirmation_once():
    b = purchase_backend()
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_shipyard_purchase(3, 'PR', 2, 150)
    with pytest.raises(AlasSemanticActionDeferred):
        a.shipyard_purchase_submit()
    assert b.taps == []
    assert a._action_ledger.remaining('shop.purchase') == 0

    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None, shop_purchase_budget=1)
    a.begin_shipyard_purchase(3, 'PR', 2, 150)
    assert a.shipyard_purchase_submit()
    assert not a.shipyard_purchase_submit()
    assert a._action_ledger.remaining('shop.purchase') == 1
    add_prompt(b)
    assert a.shipyard_purchase_confirm('BP_BUY')
    assert not a.shipyard_purchase_confirm('BP_BUY')
    assert a._action_ledger.remaining('shop.purchase') == 0
    assert len(b.taps) == 2
    a.end_shipyard_purchase()
    a.begin_shipyard_purchase(3, 'PR', 2, 150)
    with pytest.raises(AlasSemanticActionDeferred):
        a.shipyard_purchase_submit()
    assert len(b.taps) == 2


def test_confirmation_rechecks_grant_consumed_after_submit():
    b = purchase_backend()
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None, shop_purchase_budget=1)
    a.begin_shipyard_purchase(3, 'PR', 2, 150)
    a.shipyard_purchase_submit()
    add_prompt(b)
    a._action_ledger.dispatch('shop.purchase', lambda: None)
    with pytest.raises(AlasSemanticActionDeferred):
        a.shipyard_purchase_confirm('BP_BUY')
    assert len(b.taps) == 1


@pytest.mark.parametrize('dispatched', [False, True])
def test_failed_confirmation_refunds_only_when_no_input_was_dispatched(dispatched, monkeypatch):
    b = purchase_backend()
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None, shop_purchase_budget=1)
    a.begin_shipyard_purchase(3, 'PR', 2, 150)
    a.shipyard_purchase_submit()
    add_prompt(b)
    error = SemanticSnapshotStale(12000)
    def fail(*args):
        raise error
    if dispatched:
        b.on_tap = fail
    else:
        monkeypatch.setattr(o, 'click_shipyard_purchase_confirm', fail)
    with pytest.raises(SemanticSnapshotStale) as caught:
        a.shipyard_purchase_confirm('BP_BUY')
    assert caught.value is error
    assert error.input_outcome_uncertain is dispatched
    assert a._action_ledger.remaining('shop.purchase') == (0 if dispatched else 1)
    assert len(b.taps) == (2 if dispatched else 1)


@pytest.mark.parametrize('change', ['stable', 'different_prompt', 'generation_jump'])
def test_confirmation_uses_the_last_proven_prompt_frame(change):
    b = purchase_backend(); o = make_oracle(b); before = o.shipyard_purchase_state(3)
    add_prompt(b)
    first = deepcopy(b.buttons); last = deepcopy(first)
    if change == 'different_prompt':
        last['generation'] = 11
        last['buttons'].append(make_button('retry', 'root/Msgbox(Clone)/window/retry'))
        last['button_count'] += 1
    elif change == 'generation_jump':
        last['generation'] = 13
    b.buttons_sequence = [first, first, last]
    if change == 'stable':
        assert o.click_shipyard_purchase_confirm(before).semantic_id == 'shipyard/purchase/confirm'
        assert len(b.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed): o.click_shipyard_purchase_confirm(before)
        assert b.taps == []


def test_completion_uses_exact_native_result_when_quantity_panel_has_disappeared():
    b = purchase_backend(); o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_shipyard_purchase(3, 'PR', 2, 150)
    a._shipyard_purchase_context['confirm'] = object()
    b.ui['texts'] = []; b.ui['text_count'] = 0
    b.ui['images'] = []; b.ui['image_count'] = 0
    b.ui['toggles'] = []; b.ui['toggle_count'] = 0
    b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
    native = b.ui['shipyard_strengthen']
    native['status'] = 2
    assert not a.shipyard_purchase_completed()
    native.update(status=1, purchased=4, coins=1850, exp=12)
    assert a.shipyard_purchase_completed()
    b.ui['pid'] += 1
    with pytest.raises(SemanticGateClosed): a.shipyard_purchase_completed()
    assert b.taps == []


def test_actual_confirmation_loop_keeps_native_handlers_through_hidden_quantity(monkeypatch):
    b = purchase_backend(); o = make_oracle(b)
    session = AlasSemanticAdapter(o, package_gate=lambda: None)
    session.begin_shipyard_purchase(3, 'PR', 2, 150)
    session._shipyard_purchase_context.update(submit=object(), confirm=object())
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    b.ui['texts'] = []; b.ui['text_count'] = 0
    b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
    b.ui['shipyard_strengthen']['status'] = 2
    def handle_info():
        b.ui['shipyard_strengthen'].update(status=1, purchased=4, coins=1850, exp=12)
        return True
    class Timer:
        def __init__(self, *args, **kwargs): pass
        def start(self): return self
        def reset(self): return self
        def reached(self): return True
    host = SimpleNamespace(_shipyard_get_append=lambda: 'DEV', device=Mock(),
        _shipyard_get_total=Mock(side_effect=AssertionError('hidden quantity must not be read')),
        interval_clear=Mock(), interval_reset=Mock(), story_skip=Mock(return_value=False),
        handle_info_bar=Mock(side_effect=[handle_info, False]),
        appear_then_click=Mock(return_value=False), _shipyard_in_ui=lambda: True)
    # Mock side effects containing callables return them instead of invoking
    # them, so execute the real transition in a bounded first handler call.
    host.handle_info_bar.side_effect = lambda: handle_info() if b.ui['shipyard_strengthen']['status'] == 2 else False
    confirm = method('module/shipyard/ui.py', 'ShipyardUI', '_shipyard_buy_confirm',
        Timer=Timer, SHIPYARD_CONFIRM_DEV=object(), LOGIN_ANNOUNCE=object(),
        area_pad=lambda value, pad: value)
    confirm(host, 'BP_BUY')
    assert host.handle_info_bar.call_count == 2
    host._shipyard_get_total.assert_not_called()
    assert b.taps == []


@pytest.mark.parametrize('capacity', [0, 2, 5])
def test_actual_patched_quantity_adjustment_preserves_native_partial_capacity(monkeypatch, capacity):
    selected = [0]
    def change(index, delta):
        assert index == 3 and delta == 1
        if selected[0] == capacity: return False
        selected[0] += delta
        return True
    session = SimpleNamespace(shipyard_change_quantity=Mock(side_effect=change))
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    host = SimpleNamespace(_shipyard_focus_index=3, device=Mock(),
        _shipyard_get_total=lambda: (object(), object(), selected[0]))
    ensure = method('module/shipyard/ui.py', 'ShipyardUI', '_shipyard_ensure_index')
    assert ensure(host, 5) == 5 - capacity
    assert session.shipyard_change_quantity.call_count == min(capacity + 1, 5)
    host.device.multi_click.assert_not_called()


@pytest.mark.parametrize('capacity', [0, 2])
def test_actual_patched_buy_never_submits_or_dates_a_zero_quantity(monkeypatch, capacity):
    session = Mock()
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    old = datetime(2026, 1, 1)
    host = SimpleNamespace(_shipyard_focus_index=3, _shipyard_bp_rarity='PR',
        config=SimpleNamespace(Shipyard_LastRun=old),
        _shipyard_buy_calc=Mock(side_effect=[(6, 5), (6, 0)]),
        _shipyard_buy_enter=lambda: True, _shipyard_cannot_strengthen=lambda: False,
        _shipyard_ensure_index=lambda count: count-capacity,
        _shipyard_get_cost=lambda index: 100,
        _shipyard_buy_confirm=Mock(), _shipyard_pay_calc=Mock(return_value=(3, capacity)))
    buy = method('module/shipyard/shipyard_reward.py', 'RewardShipyard', '_shipyard_buy', datetime=datetime)
    buy(host, 5)
    if capacity == 0:
        assert host.config.Shipyard_LastRun == old
        session.begin_shipyard_purchase.assert_not_called()
        host._shipyard_buy_confirm.assert_not_called()
        host._shipyard_pay_calc.assert_not_called()
    else:
        assert host.config.Shipyard_LastRun != old
        session.begin_shipyard_purchase.assert_called_once_with(3, 'PR', 2, 200)
        host._shipyard_buy_confirm.assert_called_once_with('BP_BUY')
        session.end_shipyard_purchase.assert_called_once_with()
        host._shipyard_pay_calc.assert_called_once_with(1, 2)


@pytest.mark.parametrize('advanced', [True, False])
def test_quantity_step_reports_native_capacity_without_repeated_input(advanced):
    b = purchase_backend(); o = make_oracle(b)
    def update():
        b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
        if advanced:
            next(t for t in b.ui['texts'] if t['path'].endswith('/calc/base/count/Text'))['text'] = '3'
    b.on_tap = update
    receipt, moved = o.click_shipyard_quantity(3, 1)
    assert moved is advanced and receipt.semantic_id == 'shipyard/quantity'
    assert len(b.taps) == 1


@pytest.mark.parametrize('change', ['none', 'price', 'currency', 'quantity', 'duplicate', 'obscured'])
def test_confirmation_checks_exact_message_underlying_quote_and_topmost_control(change):
    b = purchase_backend(); o = make_oracle(b); before = o.shipyard_purchase_state(3)
    path = 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'
    button = make_button('custom_button_1(Clone)', path)
    b.buttons['buttons'].append(button); b.buttons['button_count'] += 1
    message = '本次强化操作需要消耗150物资，是否确认？'
    if change == 'price': message = message.replace('150', '151')
    elif change == 'currency': message = message.replace('物资', '钻石')
    elif change == 'quantity':
        next(t for t in b.ui['texts'] if t['path'].endswith('/calc/base/count/Text'))['text'] = '3'
    elif change == 'duplicate': b.buttons['buttons'].append(dict(button)); b.buttons['button_count'] += 1
    elif change == 'obscured': button['raycast_top'] = False
    b.ui['texts'] += [make_text(message, 'root/Msgbox(Clone)/window/msg_panel/content'),
        make_text('取消', 'root/Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic'),
        make_text('确定', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic')]
    b.ui['text_count'] = len(b.ui['texts'])
    if change == 'none':
        assert o.click_shipyard_purchase_confirm(before).semantic_id == 'shipyard/purchase/confirm'
        assert len(b.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed): o.click_shipyard_purchase_confirm(before)
        assert b.taps == []


def test_fate_navigation_and_maximum_do_not_require_a_quantity_panel():
    b = purchase_backend(quantity=0, owned=1)
    b.ui['texts'] = [t for t in b.ui['texts'] if '/calc_panel/' not in t['path']]
    b.ui['text_count'] = len(b.ui['texts'])
    b.buttons['buttons'].append(make_button('fitting_btn', PANEL.replace('/calc_panel', '/fitting_btn')))
    b.buttons['button_count'] += 1
    def enter_fate():
        b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
        b.ui['texts'] = [t for t in b.ui['texts'] if '/level_bg/' not in t['path']]
        b.ui['texts'].append(make_text('MAX', 'root/right_panel/fitting_panel/desc/top/precent'))
        b.ui['text_count'] = len(b.ui['texts'])
    b.on_tap = enter_fate
    o = make_oracle(b)
    assert o.click_shipyard_fate(3).semantic_id == 'shipyard/fate/open'
    assert o.shipyard_cannot_strengthen(3)
    assert len(b.taps) == 1


def test_future_series_requires_its_exact_live_actionable_choice():
    b = purchase_backend()
    b.buttons['buttons'].append(make_button('version_12',
        'OverlayCamera/Overlay/UIMain/version_panel/window/content/version_12'))
    b.buttons['button_count'] += 1
    o = make_oracle(b)
    assert o.shipyard_series_choice_available(12)
    assert o.click_shipyard_series(12).semantic_id == 'shipyard/series/12'
    with pytest.raises(SemanticGateClosed): o.click_shipyard_series(13)
    assert len(b.taps) == 1
