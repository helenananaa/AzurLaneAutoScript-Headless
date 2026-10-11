"""Food quantity preparation is reversible; confirmation is not authorized."""
import copy
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed, AlasSemanticUnmapped
from alas_headless import AlasSemanticSession
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_text, make_ui, make_oracle)

ROOT = 'root/BackYardFeedUI(Clone)/BackYardFeedShopPanel(Clone)/frame/'


def shop_host():
    backend = FakeBackend([
        make_button('cancel_btn', ROOT + 'cancel_btn', 400, 500),
        make_button('add_btn', ROOT + 'cal_panel/add_btn', 800, 380),
        make_button('minus_btn', ROOT + 'cal_panel/minus_btn', 500, 380),
        make_button('ok_btn', ROOT + 'ok_btn', 800, 500)])
    backend.ui = make_ui([
        make_text('海军咖喱', ROOT + 'name'),
        make_text('10', ROOT + 'cal_panel/value/Text'),
        make_text('500', ROOT + 'cal_panel/total/Text')], images=[
        make_image(ROOT + 'cal_panel/total/icon', 'oil'),
        make_image(ROOT + 'icon_bg/icon', 'food3')])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    adapter.begin_dorm()
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_price_proposal_and_quantity_ocr_do_not_spend(drift):
    backend, oracle, adapter = shop_host()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['compatible_new_field'] = True
        backend.ui['texts'][1]['text'] = '2000'
        backend.ui['texts'][2]['text'] = '90001'
    state = oracle.dorm_food_shop_state()
    assert state.currency_sprite == 'oil'
    assert state.food_name == '海军咖喱'
    assert state.total_cost == (90001 if drift else 500)
    assert adapter.ocr_text([(653, 374, 706, 395)], alphabet='0123456789') == str(state.quantity)
    assert adapter.appear('DORM_BUY_FOOD_CHECK')
    with pytest.raises(AlasSemanticActionDeferred, match='explicit authorization'):
        adapter.click('DORM_BUY_FOOD_CONFIRM')
    assert not backend.taps


def test_plus_is_typed_quantity_control_without_purchase():
    backend, oracle, adapter = shop_host()
    assert adapter.appear('FOOD_PLUS')
    def changed():
        backend.ui['texts'][1]['text'] = '11'
        backend.ui['texts'][2]['text'] = '550'
        for snapshot in (backend.snapshot, backend.buttons, backend.ui):
            snapshot['generation'] += 1
    backend.on_tap = changed
    receipt = adapter.click('FOOD_PLUS')
    assert receipt.semantic_id == 'dorm/feed/shop/plus'
    assert oracle.dorm_food_shop_state().quantity == 11
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['foreign-package', 'foreign-modal', 'duplicate-price',
                                 'incoherent', 'truncated-currency'])
def test_unproven_price_never_becomes_purchase(case):
    backend, oracle, adapter = shop_host()
    if case == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    elif case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'duplicate-price':
        backend.ui['texts'].append(copy.deepcopy(backend.ui['texts'][2]))
        backend.ui['text_count'] += 1
    elif case == 'incoherent': backend.ui['generation'] += 10
    else: backend.ui['images'][0]['flags'] |= 0x10
    with pytest.raises(SemanticGateClosed): oracle.dorm_food_shop_state()
    assert not backend.taps


def test_task_without_dorm_owner_cannot_use_food_quantity_input():
    backend, _, adapter = shop_host()
    adapter.end_dorm()
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('FOOD_PLUS')
    assert not backend.taps


@pytest.mark.parametrize('case', ['covered-feed', 'no-price'])
def test_native_return_cancels_inherited_shop_before_feed(case):
    backend, _, adapter = shop_host()
    adapter.end_dorm()
    backend.buttons['buttons'].append(make_button('close',
        'root/BackYardFeedUI(Clone)/close', 900, 600))
    backend.buttons['button_count'] += 1
    if case == 'no-price':
        backend.ui['texts'] = []
        backend.ui['text_count'] = 0
    assert adapter.appear('GOTO_MAIN')
    for name in ('GOTO_MAIN_WHITE', 'RPG_HOME', 'DORM_CHECK',
                 'CAMPAIGN_WITHDRAW_CONFIRM', 'POPUP_SINGLE_WHITE'):
        assert adapter.appear(name) is False
    receipt = adapter.click('GOTO_MAIN')
    assert receipt.semantic_id == 'dorm/feed/shop/cancel'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['duplicate-cancel', 'foreign-modal'])
def test_inherited_shop_cancel_does_not_bypass_ambiguity_or_blockers(case):
    backend, _, adapter = shop_host()
    adapter.end_dorm()
    if case == 'duplicate-cancel':
        backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][0]))
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('GOTO_MAIN')
    assert not backend.taps


def test_existing_refresh_reclassifies_new_food_shop_owner():
    from tests.test_game_tips_loading_presence import host
    _, _, before = host(fixture='dorm-feed-unmount-r188.json')
    backend, _, after = shop_host()
    after.end_dorm()
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    current, refreshes = [before], []
    session.open = lambda: current[0]
    def refresh():
        refreshes.append(True)
        current[0] = after
    session.refresh_frame = refresh
    assert session.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
    assert len(refreshes) == 1
    assert after.appear('GOTO_MAIN') is True
    assert not backend.taps
