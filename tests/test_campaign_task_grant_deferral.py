"""Separate campaign grant shortfalls from owned-transaction safety checks."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.test_central_task_grant_deferral import adapter_with_grants, session_for
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


KINDS=['stage','normal_continue','hard_continue','switch','clear','option',
       'normal_preflight','hard_preflight','gems_unmount','gems_equipment','gems_confirm']


def campaign_port(kind,budget=0):
    cap='campaign.stage_entry' if kind=='stage' else (
        'campaign.sortie' if 'continue' in kind else 'campaign.fleet_mutation')
    a,o,_=adapter_with_grants({cap:budget,'dorm.collect':1})
    a.begin_campaign_pre_sortie('12-4','hard' if kind in ('hard_continue','hard_preflight') else 'normal')
    c=a._campaign_context
    if kind=='stage':
        button=NamedButton('12-4');button.semantic_campaign_stage_code='12-4'
        call=lambda:a.click(button)
    elif kind=='normal_continue':
        c.auto_search_completion=object();c.sortie_proof=object()
        c.prepared_fleet_state=SimpleNamespace(required_sortie_oil=97)
        c.auto_search_role_state=SimpleNamespace(fleet1_role='mob',fleet2_role='boss')
        c.requested_fleets=(1,2,0)
        o.campaign_auto_search_reentry_available=Mock(return_value=True)
        o._campaign_2x_book_control=Mock(return_value=(None,None,False,100))
        call=lambda:a.authorize_campaign_auto_search_continue(use_2x_book=False,fleet1=1,fleet2=2,
            fleet_order='fleet1_mob_fleet2_boss')
    elif kind=='hard_continue':
        c.auto_search_completion=object()
        call=a.continue_campaign_hard_auto_search
    elif kind=='switch':
        c.combat_admission=SimpleNamespace(fleet_index=2)
        o.campaign_map_displayed_fleet_index=Mock(return_value=1)
        o.click_campaign_map_fleet_switch=Mock(return_value=o.click_receipt('campaign/map/fleet-switch'))
        call=lambda:a.click(NamedButton('SWITCH_OVER'))
    elif kind in ('clear','option'):
        c.initial_fleet_state=o.campaign_fleet_selection_state('12-4')
        c.requested_fleets=(3,4,0);c.required_fleet_mutations=1
        if kind=='clear':call=lambda:a.click(NamedButton('FLEET_1_CLEAR'))
        else:
            c.fleet_dropdown_row='fleet1';o.campaign_fleet_dropdown_row='fleet1'
            call=lambda:a.click(NamedButton('FLEET_1_BAR_INDEX_3'))
    elif 'preflight' in kind:
        AlasSemanticAdapterTestsSupport.seed_owned_campaign_fleet_overlay(a)
        if kind=='hard_preflight':
            o.campaign_hard_mode=True;o.campaign_fleets['fleet1']=0
            call=lambda:a.authorize_campaign_fleet_preparation(1,2,0)
        else:call=lambda:a.authorize_campaign_fleet_preparation(3,4,0)
    elif kind=='gems_unmount':call=lambda:a.gems_farming_hard_unmount('11-4',1,'flagship')
    elif kind=='gems_equipment':call=lambda:a.gems_farming_equipment_take_off('flagship')
    else:call=lambda:a.gems_farming_confirm_candidate_selection(object(),'flagship')
    return a,o,call,cap


@pytest.mark.parametrize('kind',KINDS)
def test_zero_campaign_port_is_local_before_input_and_unrelated_dorm_runs(kind):
    a,o,call,_=campaign_port(kind)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session_for(a),'campaign'):call()
    assert isinstance(caught.value.cause,AlasSemanticActionDeferred)
    assert o.click_calls==[]
    assert o.gems_calls==[]
    if kind=='switch':o.click_campaign_map_fleet_switch.assert_not_called()
    with semantic_task_scope(session_for(a),'dorm'):
        a.begin_dorm();a.click(NamedButton('DORM_QUICK_COLLECT'))
    assert o.click_calls==['dorm/collect']


@pytest.mark.parametrize('kind',['stage','normal_continue','switch'])
def test_consumed_campaign_grant_is_local_without_input(kind):
    a,o,call,cap=campaign_port(kind,1)
    a._action_ledger.dispatch(cap,lambda:None)
    with pytest.raises(AlasSemanticActionDeferred):call()
    assert o.click_calls==[]
    if kind=='switch':o.click_campaign_map_fleet_switch.assert_not_called()


@pytest.mark.parametrize('kind',['normal_continue','gems_equipment','normal_preflight'])
def test_closed_campaign_ledger_stays_fatal(kind):
    a,o,call,_=campaign_port(kind)
    a._action_ledger.close()
    with pytest.raises(ActionLeaseError):call()
    assert o.click_calls==[]
    assert o.gems_calls==[]


@pytest.mark.parametrize('bad',['stage_already_entered','switch_already_used','clear_unplanned',
                              'option_already_selected','continue_without_result','continue_without_oil'])
def test_campaign_unsafe_transaction_does_not_become_a_budget_deferral(bad):
    kind=bad.split('_')[0]
    kind='normal_continue' if kind=='continue' else kind
    a,o,call,_=campaign_port(kind)
    c=a._campaign_context
    if bad=='stage_already_entered':c.entry_receipt=object()
    elif bad=='switch_already_used':c.map_fleet_switch_receipts.append(object())
    elif bad=='clear_unplanned':c.required_fleet_mutations=0
    elif bad=='option_already_selected':
        o.campaign_fleets['fleet1']=3
    elif bad=='continue_without_result':c.auto_search_completion=None
    else:o.campaign_oil_value=0
    with pytest.raises(SemanticGateClosed) as caught:call()
    assert not isinstance(caught.value,AlasSemanticActionDeferred)
    assert o.click_calls==[]


@pytest.mark.parametrize('kind',['normal_preflight','hard_preflight'])
def test_positive_but_insufficient_batch_grant_defers_before_any_partial_mutation(kind):
    a,o,call,cap=campaign_port(kind,1)
    with pytest.raises(AlasSemanticActionDeferred,match='budget is below'):call()
    assert a._action_ledger.remaining(cap)==1
    assert o.click_calls==[]


def test_exact_fleet_noop_preflight_remains_available_without_mutation_grants():
    a,o,_,_=campaign_port('normal_preflight')
    o.campaign_fleets['submarine']=0
    assert a.authorize_campaign_fleet_preparation(1,2,0)
    assert a._campaign_context.required_fleet_mutations==0
    assert a._campaign_context.expected_fleet_mutations==()
    assert o.click_calls==[]
