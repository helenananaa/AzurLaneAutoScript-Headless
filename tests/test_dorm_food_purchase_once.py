"""Human-approved quote is single use; native ALAS owns purchase completion."""
import json
from dataclasses import replace
from types import SimpleNamespace
import pytest
from alas_headless.adapter.semantic.dorm_food_purchase import AUTH_ENV, purchase_food_once, note_food_purchase_result
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.test_game_tips_loading_presence import host


def approved(tmp_path, monkeypatch):
    path = tmp_path/'one-purchase.json'
    path.write_text(json.dumps(dict(state='approved',quantity=10,food_name='海军咖喱',
        item_sprite='haijungali',currency_sprite='oil',max_total_cost=500)),encoding='utf-8')
    monkeypatch.setenv(AUTH_ENV,str(path))
    backend,oracle,adapter=host(fixture='dorm-food-shop-quote-r194.json')
    generation=max(f['generation'] for f in (backend.snapshot,backend.buttons,backend.ui))
    for frame in (backend.snapshot,backend.buttons,backend.ui):frame['generation']=generation
    adapter.begin_dorm()
    return path,backend,oracle,adapter


def test_exact_actual_quote_dispatches_once_without_generic_shop_grant(tmp_path, monkeypatch):
    path,backend,oracle,adapter=approved(tmp_path,monkeypatch)
    assert not adapter._action_ledger.allowed('shop.purchase')
    receipt=adapter.click('DORM_BUY_FOOD_CONFIRM')
    assert receipt.semantic_id=='dorm/feed/shop/confirm'
    assert len(backend.taps)==1
    saved=json.loads(path.read_text(encoding='utf-8'))
    assert saved['state']=='dispatched' and saved['stock_before']==341
    with pytest.raises(AlasSemanticActionDeferred):adapter.click('DORM_BUY_FOOD_CONFIRM')
    assert len(backend.taps)==1
    note_food_purchase_result(SimpleNamespace(items=[SimpleNamespace(item_id=50004,count=351)]),receipt.generation+1)
    assert json.loads(path.read_text(encoding='utf-8'))['state']=='confirmed'


@pytest.mark.parametrize('change', [dict(quantity=11),dict(total_cost=501),dict(currency_sprite='gems'),dict(item_sprite='other-food')])
def test_changed_offer_is_refused_before_input(tmp_path,monkeypatch,change):
    path,backend,oracle,_=approved(tmp_path,monkeypatch)
    proposal=replace(oracle.dorm_food_shop_state(),**change)
    with pytest.raises(AlasSemanticActionDeferred):
        purchase_food_once(proposal,341,lambda: pytest.fail('unexpected input'),lambda:0)
    assert json.loads(path.read_text(encoding='utf-8'))['state']=='approved'
    assert not backend.taps


@pytest.mark.parametrize('dispatched', [False,True])
def test_only_proven_zero_input_refusal_can_restore_authorization(tmp_path,monkeypatch,dispatched):
    path,_,oracle,_=approved(tmp_path,monkeypatch)
    count=[0]
    def operation():
        count[0]+=int(dispatched)
        raise RuntimeError('controlled refusal or uncertain backend failure')
    with pytest.raises(RuntimeError):purchase_food_once(oracle.dorm_food_shop_state(),341,operation,lambda:count[0])
    assert json.loads(path.read_text(encoding='utf-8'))['state']==('input-uncertain' if dispatched else 'approved')


def test_stock_delta_and_generation_are_required_for_confirmation_record(tmp_path,monkeypatch):
    path,_,oracle,adapter=approved(tmp_path,monkeypatch)
    receipt=adapter.click('DORM_BUY_FOOD_CONFIRM')
    note_food_purchase_result(SimpleNamespace(items=[SimpleNamespace(item_id=50004,count=350)]),receipt.generation+1)
    assert json.loads(path.read_text(encoding='utf-8'))['state']=='dispatched'
    note_food_purchase_result(SimpleNamespace(items=[SimpleNamespace(item_id=50004,count=351)]),receipt.generation)
    assert json.loads(path.read_text(encoding='utf-8'))['state']=='dispatched'
