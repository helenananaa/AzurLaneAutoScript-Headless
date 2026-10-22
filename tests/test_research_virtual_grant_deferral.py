"""Original virtual research inputs retain task-local grant outcomes."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import ResearchProjectStatus, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.test_central_task_grant_deferral import adapter_with_grants, session_for
from tests.semantic_support.adapter_fixtures import NamedButton


def research_port(kind):
    capability = 'research.reward' if kind == 'reward' else 'research.start'
    a, o, _ = adapter_with_grants({capability: 0})
    a.begin_research()
    c = a._research_context
    if kind == 'start':
        o.research_detail_state = Mock(return_value=SimpleNamespace(can_start=True))
        name = 'RESEARCH_START'
    elif kind == 'start_confirm':
        c.start_receipt = object()
        c.pending_resource_costs = (('coin', 100),)
        o.research_start_prompt_costs = Mock(return_value=c.pending_resource_costs)
        name = 'POPUP_CONFIRM'
    elif kind == 'queue_confirm':
        c.queue_add_receipt = object()
        c.queue_add_requires_start_grant = True
        name = 'POPUP_CONFIRM'
    elif kind == 'queue_add':
        c.selected_status = ResearchProjectStatus.RUNNING
        a.research_detail_is_running = Mock(return_value=True)
        a.research_detail_can_queue = Mock(return_value=True)
        name = 'RESEARCH_QUEUE_ADD'
    else:
        o.research_queue_state = Mock(return_value=SimpleNamespace(reward_claimable=True))
        name = 'QUEUE_CLAIM_REWARD'
    return a, o, lambda:a.click(NamedButton(name))


@pytest.mark.parametrize('kind', ['start','start_confirm','queue_confirm','queue_add','reward'])
def test_zero_virtual_research_port_is_local_before_input(kind):
    a, o, call = research_port(kind)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session_for(a), 'research'):
            call()
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert o.click_calls == []


@pytest.mark.parametrize('kind', ['start','start_confirm','reward'])
def test_invalid_research_resource_or_claim_state_stays_fatal(kind):
    a, o, call = research_port(kind)
    if kind == 'start':
        o.research_detail_state.return_value.can_start = False
    elif kind == 'start_confirm':
        o.research_start_prompt_costs.return_value = (('cube', 999),)
    else:
        o.research_queue_state.return_value.reward_claimable = False
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session_for(a), 'research'):
            call()
    assert not isinstance(caught.value, AlasSemanticActionDeferred)
    assert o.click_calls == []


def test_closed_research_queue_ledger_stays_fatal():
    a, o, call = research_port('queue_confirm')
    a._action_ledger.close()
    with pytest.raises(ActionLeaseError):
        with semantic_task_scope(session_for(a), 'research'):
            call()
    assert o.click_calls == []


def test_confirmed_start_queue_add_does_not_require_second_start_grant():
    a, o, call = research_port('queue_add')
    a._research_context.start_confirm_receipt = object()
    result = call()
    assert result.semantic_id == 'research/detail/queue'
    assert not a._research_context.queue_add_requires_start_grant
    assert a._action_ledger.remaining('research.start') == 0
    assert o.click_calls == ['research/detail/queue']
