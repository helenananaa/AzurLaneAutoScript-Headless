"""Tactical preparation/acknowledgement is distinct from another course input."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.test_central_task_grant_deferral import adapter_with_grants, session_for
from tests.semantic_support.adapter_fixtures import NamedButton


def tactical_port(kind, count=0):
    cap = 'tactical.reward' if kind == 'ack' else 'tactical.assign'
    a, o, _ = adapter_with_grants({cap: count, 'dorm.collect': 1})
    a.begin_tactical()
    o.tactical_skills = Mock(return_value=(SimpleNamespace(max_level=False, position=1),))
    o.tactical_candidate_ships = Mock(return_value=(SimpleNamespace(ship_id=1, level=100),))
    o.tactical_book_values = [SimpleNamespace(position=1, count=5, selected=False)]
    o.click_tactical_skill = Mock()
    o.click_tactical_book = Mock()
    o.click_tactical_ship = Mock()
    o.click_tactical_first_empty_slot = Mock()
    o.click_tactical_completion_ack = Mock()
    if kind == 'ship':
        call = lambda: a.tactical_select_suitable_ship(False, 1, 0)
    elif kind == 'skill':
        call = a.tactical_select_first_trainable_skill
    elif kind == 'book':
        call = lambda: a.tactical_select_book(1)
    else:
        call = lambda:a.click(NamedButton('GET_MISSION' if kind=='ack' else 'ADD_NEW_STUDENT'))
    return a, o, call, cap


def assert_no_input(o):
    assert o.click_calls == []
    assert o.enhancement_calls == []
    for name in ('click_tactical_skill','click_tactical_book','click_tactical_ship',
                 'click_tactical_first_empty_slot','click_tactical_completion_ack'):
        getattr(o,name).assert_not_called()


@pytest.mark.parametrize('kind',['ship','skill','book','empty','ack'])
@pytest.mark.parametrize('spent',[False,True])
def test_tactical_preparation_exhaustion_is_local_and_unrelated_dorm_runs(kind,spent):
    a,o,call,cap=tactical_port(kind,int(spent))
    if spent:a._action_ledger.dispatch(cap,lambda:None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session_for(a),'tactical'):call()
    assert isinstance(caught.value.cause,AlasSemanticActionDeferred)
    assert_no_input(o)
    with semantic_task_scope(session_for(a),'dorm'):
        a.begin_dorm()
        a.click(NamedButton('DORM_QUICK_COLLECT'))
    assert o.click_calls==['dorm/collect']


@pytest.mark.parametrize('kind',['ship','skill','book','empty','ack'])
def test_closed_tactical_preparation_ledger_remains_fatal(kind):
    a,o,call,_=tactical_port(kind)
    a._action_ledger.close()
    with pytest.raises(ActionLeaseError):call()
    assert_no_input(o)


def test_proven_dock_transition_reuses_spent_empty_slot_receipt_without_input():
    a,o,call,cap=tactical_port('empty',1)
    a._action_ledger.dispatch(cap,lambda:None)
    prior=o.click_receipt('tactical/slot/1',generation=1)
    a._commission_context.tactical_empty_slot_receipt=prior
    o.enabled_values['tactical/dock/back']=True
    assert call() is prior
    assert a._commission_context.tactical_empty_slot_receipt is None
    assert_no_input(o)


def test_already_selected_book_is_observed_without_another_course_grant():
    a,o,call,_=tactical_port('book')
    image=SimpleNamespace(bounds=SimpleNamespace(left=0,right=2,top=0,bottom=2),path='tactical/book/1')
    o.tactical_book_values[0].selected=True
    o.tactical_book_values[0].image=image
    assert call().semantic_id=='tactical/book/1'
    assert_no_input(o)


def test_no_trainable_skill_can_return_false_without_a_grant():
    a,o,call,_=tactical_port('skill')
    o.tactical_skills.return_value=(SimpleNamespace(max_level=True),)
    assert call() is False
    assert_no_input(o)


def test_consumed_reward_receipt_allows_exact_completion_ack():
    a,o,call,_=tactical_port('ack',1)
    a._commission_context.tactical_reward_receipt=a._dispatch_mutation(
        'tactical.reward',lambda:o.click_receipt('reward/tactical/finish'))
    o.enabled_values['tactical/completion/ack']=True
    assert a.appear(NamedButton('GET_MISSION'))
    assert call() is o.click_tactical_completion_ack.return_value
    o.click_tactical_completion_ack.assert_called_once()
    assert a._action_ledger.remaining('tactical.reward')==0


def test_typed_continue_cancel_without_reward_grant_does_not_start_a_course():
    a,o,_,_=tactical_port('ack')
    o.tactical_prompt_text='「舰船」学习完成，「技能」技能获得450点经验是否继续学习该技能？'
    assert a.cancel_tactical_continue_if_present()
    assert o.click_calls==['tactical/continue/cancel']
    assert a._action_ledger.remaining('tactical.reward')==0


@pytest.mark.parametrize('kind',['ship','skill','book'])
def test_wrong_preparation_flow_stays_fatal(kind):
    a,o,call,_=tactical_port(kind)
    a._commission_context.flow_kind='commission'
    with pytest.raises(SemanticGateClosed) as caught:call()
    assert not isinstance(caught.value,AlasSemanticActionDeferred)
    assert_no_input(o)


def test_unavailable_book_stays_fatal_before_grant_classification():
    a,o,call,_=tactical_port('book')
    o.tactical_book_values[0].count=0
    with pytest.raises(SemanticGateClosed,match='unavailable'):call()
    assert_no_input(o)
