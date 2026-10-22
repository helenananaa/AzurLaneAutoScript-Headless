"""Finite caller grants bound camera work; task-local exhaustion is distinct."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from alas_headless import (AlasSemanticAdapter, AlasSemanticSession, Bounds, Point,
                          CampaignMapCellState, SemanticGateClosed)
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.semantic_support.adapter_fixtures import FakeOracle, make_campaign_combat_state


def positioning(budget):
    o=FakeOracle()
    empty=CampaignMapCellState(row=3,column=6,node='F3',
        button_path='root/DragLayer/plane/quads/chapter_cell_quad_3_6',
        point=Point(400,80),bounds=Bounds(360,40,440,120))
    state=make_campaign_combat_state()
    o.campaign_map_state_value=replace(state,cells=state.cells+(empty,))
    a=AlasSemanticAdapter(o,lambda:None,campaign_camera_positioning_budget=budget)
    a.begin_campaign_pre_sortie('12-4')
    current=a.campaign_map_state(columns=11,rows=8,land_cells=((0,0),),expected_fleet_count=1)
    return a,o,current


def swipe_once(a):
    intent=a.begin_campaign_map_swipe_vector((0.,80.),box=(123,159,1175,628),
        random_range=(0,0,0,0),padding=15,duration=(.1,.2),whitelist_area=None,
        blacklist_area=None,name='MAP_SWIPE_0_-1',distance_check=True)
    try:
        return a.swipe((500,370),(500,450),duration=.35,name='MAP_SWIPE_0_-1',distance_check=True)
    finally:a.end_campaign_map_swipe_vector(intent)


@pytest.mark.parametrize('budget',[1,2,3])
def test_camera_corrections_use_declared_finite_budget_and_each_post_state(budget):
    a,o,state=positioning(budget)
    admission=a.authorize_campaign_camera_positioning('F3',state)
    proofs=[]
    for remaining in range(budget-1,-1,-1):
        proof=swipe_once(a);proofs.append(proof)
        assert proof.target_node=='F3'
        assert proof.post_generation>proof.pre_generation
        assert a._action_ledger.remaining('campaign.camera_positioning')==remaining
    final=a.campaign_camera_state()
    assert final.signature==admission.map_signature
    assert a.complete_campaign_camera_positioning(final)==tuple(proofs)
    assert len(o.campaign_map_swipe_calls)==budget
    with pytest.raises(SemanticGateClosed):swipe_once(a)
    assert len(o.campaign_map_swipe_calls)==budget


def test_three_camera_grants_are_preserved_by_session_constructor():
    s=AlasSemanticSession('emulator-test','be80ce591a481c12d60c50d6040d40c035b40a2b',
        campaign_camera_positioning_budget=3)
    assert s.campaign_camera_positioning_budget==3


def test_zero_camera_grant_is_local_without_a_swipe():
    a,o,state=positioning(0)
    with pytest.raises(AlasSemanticActionDeferred):a.authorize_campaign_camera_positioning('F3',state)
    assert o.campaign_map_swipe_calls==[]


def test_closed_camera_ledger_is_fatal_before_authorization():
    a,o,state=positioning(1);a._action_ledger.close()
    with pytest.raises(ActionLeaseError):a.authorize_campaign_camera_positioning('F3',state)
    assert o.campaign_map_swipe_calls==[]


@pytest.mark.parametrize('status', ['spent', 'closed'])
def test_admitted_camera_correction_checks_shared_grant_before_swipe(status):
    a, o, state = positioning(1)
    a.authorize_campaign_camera_positioning('F3', state)
    if status == 'spent':
        swipe_once(a)
    else:
        a._action_ledger.close()
    before = len(o.campaign_map_swipe_calls)
    with pytest.raises(ActionLeaseError if status == 'closed' else AlasSemanticActionDeferred):
        swipe_once(a)
    assert len(o.campaign_map_swipe_calls) == before


@pytest.mark.parametrize('budget',[True,-1])
def test_malformed_camera_budget_still_rejected(budget):
    with pytest.raises(ValueError):positioning(budget)
    with pytest.raises(ValueError):AlasSemanticSession('emulator-test','be80ce591a481c12d60c50d6040d40c035b40a2b',
        campaign_camera_positioning_budget=budget)


@pytest.mark.parametrize('status',['zero','spent','closed'])
def test_ambush_budget_exhaustion_is_local_but_closed_ledger_is_fatal(status):
    o=FakeOracle()
    a=AlasSemanticAdapter(o,lambda:None,campaign_combat_budget=int(status!='zero'))
    a.begin_campaign_pre_sortie('12-4')
    o.campaign_ambush_visible=Mock(return_value=True)
    o.click_campaign_ambush=Mock()
    if status=='spent':a._action_ledger.dispatch('campaign.grid_click',lambda:None)
    elif status=='closed':a._action_ledger.close()
    with pytest.raises(ActionLeaseError if status=='closed' else AlasSemanticActionDeferred):
        a.handle_campaign_ambush(evade=True)
    o.click_campaign_ambush.assert_not_called()


def test_unfinished_ambush_still_fatal_even_after_grant_spent():
    o=FakeOracle();a=AlasSemanticAdapter(o,lambda:None)
    a.begin_campaign_pre_sortie('12-4');a._campaign_context.ambush_receipt=object()
    o.campaign_ambush_visible=Mock(return_value=True);o.click_campaign_ambush=Mock()
    with pytest.raises(SemanticGateClosed,match='postcondition'):a.handle_campaign_ambush(evade=True)
    o.click_campaign_ambush.assert_not_called()
