"""Paid Commander Cat boxes share purchase authority; free claims stay usable."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


def transaction(*, free=False, budget=0, bad_postcondition=False):
    oracle = FakeOracle()
    count = 1 if free else 3
    before = SimpleNamespace(purchased=0 if free else 1, purchase_total=15,
                             coins=5400, box_counts=(1, 1, 1))
    cost = 0 if free else 3690
    after = SimpleNamespace(purchased=before.purchased+count, purchase_total=15,
                            coins=5400 if bad_postcondition else 5400-cost,
                            box_counts=(1+count, 1, 1))
    oracle.meowfficer_dock_state = Mock(side_effect=[before, after])
    oracle.meowfficer_purchase_state = Mock(side_effect=[
        SimpleNamespace(generation=10+i, count=i+1, total_price=0 if free else 1230*(i+1))
        for i in range(count)])
    adapter = AlasSemanticAdapter(oracle, lambda: None,
                                  shop_purchase_budget=budget, dorm_collect_budget=1)
    return adapter, oracle, count, after


@pytest.mark.parametrize('status', ['zero', 'spent', 'closed'])
def test_paid_purchase_refusal_precedes_any_panel_or_input(status):
    adapter, oracle, count, _ = transaction(budget=int(status != 'zero'))
    if status == 'spent':
        adapter._action_ledger.dispatch('shop.purchase', lambda: None)
    elif status == 'closed':
        adapter._action_ledger.close()
    with pytest.raises(ActionLeaseError if status == 'closed' else AlasSemanticActionDeferred):
        adapter.buy_meowfficer_boxes(count)
    oracle.meowfficer_purchase_state.assert_not_called()
    assert oracle.click_calls == []


def test_free_daily_box_needs_no_purchase_grant():
    adapter, oracle, count, after = transaction(free=True)
    assert adapter.buy_meowfficer_boxes(count) is after
    assert oracle.click_calls == ['meowfficer/buy/enter', 'meowfficer/buy/submit']
    assert adapter._action_ledger.remaining('shop.purchase') == 0


def test_explicit_paid_grant_accepts_typed_discount_and_burns_one_transaction():
    adapter, oracle, count, after = transaction(budget=1)
    assert adapter.buy_meowfficer_boxes(count) is after
    assert oracle.click_calls == ['meowfficer/buy/enter', 'meowfficer/buy/add',
                                  'meowfficer/buy/add', 'meowfficer/buy/submit']
    assert adapter._action_ledger.remaining('shop.purchase') == 0


def test_accepted_purchase_with_wrong_coin_result_stays_fatal():
    adapter, oracle, count, _ = transaction(budget=1, bad_postcondition=True)
    with pytest.raises(SemanticGateClosed, match='coin postcondition'):
        adapter.buy_meowfficer_boxes(count)
    assert adapter._action_ledger.remaining('shop.purchase') == 0
    assert oracle.click_calls[-1] == 'meowfficer/buy/submit'


def test_refused_paid_branch_is_local_and_unrelated_dorm_collect_executes():
    adapter, oracle, count, _ = transaction()
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'meowfficer'):
            adapter.buy_meowfficer_boxes(count)
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert oracle.click_calls == []
    with semantic_task_scope(session, 'dorm'):
        adapter.begin_dorm()
        adapter.click(NamedButton('DORM_QUICK_COLLECT'))
    assert oracle.click_calls == ['dorm/collect']
