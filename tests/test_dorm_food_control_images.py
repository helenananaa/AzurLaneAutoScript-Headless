"""Reviewed same-path Image controls are local to the real Feed/shop owner."""
from copy import deepcopy
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button, make_image
from tests.test_dorm_food_shop_preparation import shop_host, ROOT
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred


@pytest.mark.parametrize('drift',[False,True])
def test_retained_feed_opens_original_curry_card_with_typed_point(drift):
    backend,oracle,_=host(drift,'dorm-food-shop-entry-r192.json')
    assert oracle.enabled('dorm/feed/shop/open')
    receipt=oracle.click('dorm/feed/shop/open')
    assert receipt.path.endswith('food_50004/add')
    assert len(backend.taps)==1


@pytest.mark.parametrize('case',['covered','duplicate','missing-image','wrong-package','stale'])
def test_unproven_entry_remains_closed(case):
    backend,oracle,_=host(fixture='dorm-food-shop-entry-r192.json')
    path=next(b['path'] for b in backend.buttons['buttons'] if b['path'].endswith('food_50004/add'))
    if case=='covered':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count']+=1
    elif case=='duplicate':
        backend.ui['images'].append(deepcopy(next(i for i in backend.ui['images'] if i['path']==path)))
        backend.ui['image_count']+=1
    elif case=='missing-image':
        backend.ui['images']=[i for i in backend.ui['images'] if i['path']!=path]
        backend.ui['image_count']=len(backend.ui['images'])
    elif case=='wrong-package': backend.snapshot['package']='wrong.package'
    else: backend.snapshot['age_ms']=10001
    with pytest.raises(SemanticGateClosed): oracle.click('dorm/feed/shop/open')
    assert not backend.taps


def test_quantity_control_delegates_to_exact_image_without_purchase():
    backend,oracle,adapter=shop_host()
    for button in backend.buttons['buttons']:
        button['raycast_top']=None
    images = [
        make_image(ROOT+'cancel_btn','btn_grey',dict(left=360,top=460,right=440,bottom=540)),
        make_image(ROOT+'cal_panel/add_btn','+',dict(left=760,top=340,right=840,bottom=420))]
    for image in images:
        image['raycast_target'] = True
    backend.ui['images'].extend(images)
    backend.ui['image_count']=len(backend.ui['images'])
    assert oracle.enabled('dorm/feed/shop/plus')
    assert oracle.dorm_food_shop_state().quantity==10
    assert adapter.click('FOOD_PLUS').semantic_id=='dorm/feed/shop/plus'
    assert len(backend.taps)==1


@pytest.mark.parametrize('control', ['open', 'plus', 'minus', 'cancel'])
def test_absent_optional_food_control_is_false_in_owned_dorm(control):
    backend, oracle, adapter = shop_host()
    backend.buttons['buttons'] = []
    backend.buttons['button_count'] = 0
    assert oracle.enabled('dorm/feed/shop/' + control) is False
    assert adapter.appear('POPUP_CANCEL') is False
    assert not backend.taps


def test_retained_feed_has_no_shop_cancel_before_shop_mount():
    backend, oracle, adapter = host(fixture='dorm-food-shop-entry-r192.json')
    adapter.begin_dorm()
    assert oracle.enabled('dorm/feed/shop/cancel') is False
    assert adapter.appear('POPUP_CANCEL') is False
    assert oracle.enabled('dorm/feed/shop/open') is True
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_actual_native_curry_quote_defers_purchase_but_allows_cancel(drift):
    backend, oracle, adapter = host(drift, 'dorm-food-shop-quote-r194.json')
    generation = max(frame['generation'] for frame in (backend.snapshot, backend.buttons, backend.ui))
    for frame in (backend.snapshot, backend.buttons, backend.ui):
        frame['generation'] = generation
    adapter.begin_dorm()
    proposal = oracle.dorm_food_shop_state()
    assert (proposal.food_name, proposal.quantity, proposal.total_cost,
            proposal.currency_sprite, proposal.item_sprite) == ('海军咖喱', 10, 500, 'oil', 'haijungali')
    with pytest.raises(AlasSemanticActionDeferred, match='total=500'):
        adapter.click('DORM_BUY_FOOD_CONFIRM')
    assert not backend.taps
    adapter.end_dorm()
    assert adapter.appear('GOTO_MAIN')
    assert adapter.click('GOTO_MAIN').semantic_id == 'dorm/feed/shop/cancel'
    assert len(backend.taps) == 1
