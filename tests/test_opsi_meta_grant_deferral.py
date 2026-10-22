"""Zero/spent resource grants defer locally; lifecycle failures do not."""
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.test_central_task_grant_deferral import adapter_with_grants, session_for
from tests.semantic_support.adapter_fixtures import NamedButton


CAPS = {'daemon': 'operation_siren.daemon_move', 'ap': 'operation_siren.action_point_use',
        'repair': 'operation_siren.port_repair', 'meta': 'meta.assist'}


def port(kind, grants):
    adapter, oracle, _ = adapter_with_grants(grants)
    operation = Mock(return_value=oracle.click_receipt('test/resource'))
    if kind == 'daemon':
        oracle.click_operation_siren_daemon_target = operation
        invoke = lambda: adapter.click_operation_siren_daemon_target(object())
    elif kind == 'ap':
        oracle.click_operation_siren_action_point_control = operation
        invoke = lambda: adapter.click_operation_siren_action_point_control(True)
    elif kind == 'repair':
        oracle.click_operation_siren_port_repair = operation
        invoke = lambda: adapter.click_operation_siren_port_repair(True)
    else:
        adapter.begin_meta_assist()
        oracle.meta_precombat_fleet_ready = Mock(return_value=True)
        oracle.click_meta_assist_precombat_start = operation
        invoke = adapter.click_meta_precombat_start
    return adapter, oracle, operation, invoke


@pytest.mark.parametrize('kind', CAPS)
@pytest.mark.parametrize('budget', ['zero', 'spent'])
def test_zero_or_spent_port_is_local_before_backend_and_other_task_can_run(kind, budget):
    cap = CAPS[kind]
    adapter, oracle, backend, invoke = port(kind, {cap: int(budget == 'spent'), 'dorm.collect': 1})
    if budget == 'spent':
        adapter._action_ledger.dispatch(cap, lambda: None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session_for(adapter), kind):
            invoke()
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    backend.assert_not_called()
    assert adapter._action_ledger.remaining(cap) == 0
    with semantic_task_scope(session_for(adapter), 'dorm'):
        adapter.begin_dorm()
        adapter.click(NamedButton('DORM_QUICK_COLLECT'))
    assert oracle.click_calls == ['dorm/collect']


@pytest.mark.parametrize('kind', CAPS)
def test_closed_port_ledger_stays_fatal(kind):
    cap = CAPS[kind]
    adapter, _, backend, invoke = port(kind, {cap: 0})
    adapter._action_ledger.close()
    with pytest.raises(ActionLeaseError):
        with semantic_task_scope(session_for(adapter), kind):
            invoke()
    backend.assert_not_called()


@pytest.mark.parametrize('kind', CAPS)
def test_positive_port_dispatch_consumes_exactly_once(kind):
    cap = CAPS[kind]
    adapter, _, backend, invoke = port(kind, {cap: 1})
    receipt = invoke()
    assert receipt.semantic_id == backend.return_value.semantic_id
    assert receipt.generation == backend.return_value.generation
    assert receipt.capability_id == cap
    backend.assert_called_once()
    assert adapter._action_ledger.remaining(cap) == 0


@pytest.mark.parametrize('kind', ['ap', 'repair'])
def test_zero_grant_still_allows_typed_cancel_without_consumption(kind):
    cap = CAPS[kind]
    adapter, _, backend, _ = port(kind, {cap: 0})
    if kind == 'ap':
        result = adapter.click_operation_siren_action_point_control(False)
    else:
        result = adapter.click_operation_siren_port_repair(False)
    assert result is backend.return_value
    backend.assert_called_once_with(False)
    assert adapter._action_ledger.remaining(cap) == 0


def test_meta_missing_fleet_with_positive_grant_stays_fatal_without_reserving():
    adapter, oracle, backend, invoke = port('meta', {'meta.assist': 1})
    oracle.meta_precombat_fleet_ready.return_value = False
    with pytest.raises(SemanticGateClosed, match='non-empty'):
        invoke()
    backend.assert_not_called()
    assert adapter._action_ledger.remaining('meta.assist') == 1
