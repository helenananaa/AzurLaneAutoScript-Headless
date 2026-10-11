from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.fake_oracle import FakeOracle


def batch(delta,food_delta=None):
    oracle=FakeOracle()
    original=oracle.click_dorm_food
    def native_click(item_id):
        receipt=original(item_id)
        state=oracle.dorm_feed_state_value
        chosen=state.items[0]
        chosen.count-=delta-1
        oracle.dorm_feed_state_value=SimpleNamespace(
            food=state.food+chosen.value*(delta-1) if food_delta is None else food_delta,
            capacity=state.capacity,items=state.items)
        return receipt
    oracle.click_dorm_food=native_click
    adapter=AlasSemanticAdapter(oracle,lambda:None,dorm_feed_budget=3)
    adapter.begin_dorm()
    return oracle,adapter


def test_two_units_consumed_by_one_input_complete_native_two_unit_batch():
    oracle,adapter=batch(2)
    receipts=adapter.dorm_feed_food(0,2)
    assert len(receipts)==1
    assert oracle.click_calls==['dorm/feed/item/50001']
    assert adapter._action_ledger.remaining('dorm.feed')==2
    assert adapter._dorm_feed_consumption_proofs[0]['consumed_units']==2


def test_late_second_unit_is_observed_before_another_input():
    oracle,adapter=batch(1)
    original=adapter._fresh_dorm_feed_state
    reads=[0]
    def fresh():
        reads[0]+=1
        if reads[0]==3:
            # The first post-input read saw one unit; its second unit arrives
            # before ALAS' next card input preparation.
            state=oracle.dorm_feed_state_value
            state.items[0].count-=1
            oracle.dorm_feed_state_value=SimpleNamespace(
                food=state.food+1000,capacity=state.capacity,items=state.items)
        return original()
    adapter._fresh_dorm_feed_state=fresh
    receipts=adapter.dorm_feed_food(0,2)
    assert oracle.dorm_feed_state_value.items[0].count==3
    assert oracle.dorm_feed_state_value.food==2000
    assert len(receipts)==1
    assert oracle.click_calls==['dorm/feed/item/50001']


@pytest.mark.parametrize('stock_change,food_change',[(2,2000),(-1,-1000),(1,0)])
def test_invalid_late_inventory_or_food_update_does_not_send_another_input(stock_change,food_change):
    oracle,adapter=batch(1)
    original=adapter._fresh_dorm_feed_state
    reads=[0]
    def fresh():
        reads[0]+=1
        if reads[0]==3:
            state=oracle.dorm_feed_state_value
            state.items[0].count-=stock_change
            oracle.dorm_feed_state_value=SimpleNamespace(
                food=state.food+food_change,capacity=state.capacity,items=state.items)
        return original()
    adapter._fresh_dorm_feed_state=fresh
    with pytest.raises(SemanticGateClosed):
        adapter.dorm_feed_food(0,2)
    assert oracle.click_calls==['dorm/feed/item/50001']


@pytest.mark.parametrize('delta,food_delta,requested',[(3,None,2),(2,1000,2),(1,3000,2),(2,None,1)])
def test_excess_or_inconsistent_consumption_never_repeats_input(delta,food_delta,requested,monkeypatch):
    oracle,adapter=batch(delta,food_delta)
    import time
    clock=[time.monotonic()]
    monkeypatch.setattr('alas_headless.adapter.semantic.dorm.time.monotonic',lambda:clock[0])
    monkeypatch.setattr('alas_headless.adapter.semantic.dorm.time.sleep',lambda _:clock.__setitem__(0,clock[0]+6))
    with pytest.raises(SemanticGateClosed,match='mutation was not proven'):
        adapter.dorm_feed_food(0,requested)
    assert oracle.click_calls==['dorm/feed/item/50001']
    assert adapter._dorm_feed_consumption_proofs==[]
