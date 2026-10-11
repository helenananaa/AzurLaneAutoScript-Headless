"""A closed transaction ledger is distinct from an ordinary zero grant."""
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


@pytest.mark.parametrize('port', ['purchase', 'refresh', 'opsi_purchase', 'opsi_resume', 'opsi_voucher'])
@pytest.mark.parametrize('status', ['zero', 'spent', 'closed'])
def test_shop_ports_classify_grants_before_reading_or_opening_a_transaction(port, status):
    oracle = FakeOracle()
    oracle.general_shop_items = Mock()
    oracle.shop_selected_nav_label = Mock()
    oracle.click_shop_item = Mock()
    oracle.click_shop_refresh = Mock()
    oracle._retry_transition_read = Mock()
    oracle.shop_purchase_dialog_quantity = Mock()
    oracle.click_shop_purchase_confirm = Mock()
    adapter = AlasSemanticAdapter(oracle, lambda: None,
        shop_purchase_budget=int(status != 'zero'))
    if status == 'spent':
        adapter._action_ledger.dispatch('shop.purchase', lambda: None)
    elif status == 'closed':
        adapter._action_ledger.close()
    error = ActionLeaseError if status == 'closed' else AlasSemanticActionDeferred
    with pytest.raises(error):
        if port == 'purchase':
            adapter.purchase_shop_item_once(6, 'DR', 'Medal', 20)
        elif port == 'refresh':
            adapter.refresh_shop_once()
        elif port == 'opsi_purchase':
            adapter.purchase_operation_siren_shop_item_once(6, 'DR', 20)
        elif port == 'opsi_resume':
            adapter.resume_operation_siren_shop_purchase_once(6, 'DR', 'Blueprint', 20, 2, 100)
        else:
            adapter.purchase_operation_siren_voucher_item_once(6, 'DR', 20)
    oracle.general_shop_items.assert_not_called()
    oracle.shop_selected_nav_label.assert_not_called()
    oracle.click_shop_item.assert_not_called()
    oracle.click_shop_refresh.assert_not_called()
    oracle._retry_transition_read.assert_not_called()
    oracle.shop_purchase_dialog_quantity.assert_not_called()
    oracle.click_shop_purchase_confirm.assert_not_called()


@pytest.mark.parametrize('port, args', [
    ('purchase_operation_siren_shop_item_once', (6, 'DR', 20)),
    ('resume_operation_siren_shop_purchase_once', (6, 'DR', 'Blueprint', 20, 2, 100)),
    ('purchase_operation_siren_voucher_item_once', (6, 'DR', 20)),
])
def test_zero_opsi_shop_grant_defers_its_task_and_dorm_still_collects(port, args):
    oracle = FakeOracle()
    oracle._retry_transition_read = Mock()
    oracle.shop_purchase_dialog_quantity = Mock()
    adapter = AlasSemanticAdapter(oracle, lambda: None,
        shop_purchase_budget=0, dorm_collect_budget=1)
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'opsi_shop'):
            getattr(adapter, port)(*args)
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert session.last_task_outcome == {'task': 'opsi_shop', 'outcome': 'action-deferred'}
    oracle._retry_transition_read.assert_not_called()
    oracle.shop_purchase_dialog_quantity.assert_not_called()
    assert oracle.click_calls == []
    with semantic_task_scope(session, 'dorm'):
        adapter.begin_dorm()
        adapter.click(NamedButton('DORM_QUICK_COLLECT'))
    assert oracle.click_calls == ['dorm/collect']
    assert adapter._action_ledger.remaining('shop.purchase') == 0
    assert adapter._action_ledger.remaining('dorm.collect') == 0
