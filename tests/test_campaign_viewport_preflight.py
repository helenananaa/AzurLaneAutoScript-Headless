"""Native route admission does not reserve camera input for visible waypoints."""
from dataclasses import replace

import pytest
from alas_headless import AlasSemanticAdapter, Bounds, Point, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.test_central_task_grant_deferral import session_for
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.adapter_fixtures import FakeOracle, CampaignGridButton, make_campaign_combat_state, make_campaign_combat_decision


def native_route(viewport, covered=True):
    oracle=FakeOracle();base=make_campaign_combat_state()
    nodes=('D6','C6','C5','C4','C3','D3')
    cells=tuple(replace(base.cells[0],node=n,row=int(n[1:]),column=ord(n[0])-64,
        button_path='root/DragLayer/plane/quads/'+n,
        point=Point(300+i*80,300+i*20),bounds=Bounds(270+i*80,270+i*20,330+i*80,330+i*20))
        for i,n in enumerate(nodes))
    before=replace(base,cells=cells,enemies=(replace(base.enemies[0],node='D3',fighting=False),))
    oracle.campaign_map_state_value=before
    oracle.campaign_map_target_raycast_top=not covered
    original=oracle.campaign_map_cell_viewport_target
    oracle.campaign_map_cell_viewport_target=lambda s,n:replace(original(s,n),
        raycast_top=True if n!='C6' else oracle.campaign_map_target_raycast_top)
    adapter=AlasSemanticAdapter(oracle,lambda:None,campaign_combat_budget=2,
        campaign_viewport_swipe_budget=viewport,dorm_collect_budget=1)
    adapter.begin_campaign_pre_sortie('12-4')
    state=adapter.campaign_map_state(columns=11,rows=8,land_cells=((0,0),),expected_fleet_count=1)
    decision=replace(make_campaign_combat_decision(),origin_node='D6',target_node='D3',cost=5,
        route_nodes=nodes,goto_nodes=('C6','D3'))
    return adapter,oracle,state,decision


def test_one_available_camera_move_allows_native_route_with_another_visible_waypoint():
    adapter,oracle,state,decision=native_route(1)
    admission=adapter.authorize_campaign_combat(decision,state)
    assert admission.input_nodes==('C6','D3')
    intent=adapter.begin_campaign_map_swipe_vector((200.,0.),box=(123,159,1175,628),
        random_range=(0,0,0,0),padding=15,duration=(.1,.2),whitelist_area=None,
        blacklist_area=None,name='MAP_SWIPE_-2_0',distance_check=True)
    try:
        adapter.swipe((500,400),(700,400),duration=.157,name='MAP_SWIPE_-2_0',distance_check=True)
    finally:
        adapter.end_campaign_map_swipe_vector(intent)
    assert adapter._action_ledger.remaining('campaign.viewport_swipe')==0
    assert len(oracle.campaign_map_swipe_calls)==1
    assert adapter.recheck_campaign_combat_target_after_camera_view(
        adapter.campaign_camera_state()).target_node=='C6'
    first=adapter.click(CampaignGridButton((2,5)))
    after=oracle.campaign_map_state_value
    oracle.campaign_map_state_value=replace(after,generation=first.generation+1,
        fleets=(replace(after.fleets[0],node='C6'),))
    adapter.campaign_camera_state()
    last=adapter.click(CampaignGridButton((3,2)))
    assert not adapter.campaign_map_viewport_swipe_committed()
    assert adapter._campaign_context.target_recheck_proof is None
    assert oracle.campaign_map_cell_click_calls==[('C6',False),('D3',True)]
    assert adapter._action_ledger.remaining('campaign.grid_click')==0
    after=oracle.campaign_map_state_value
    oracle.campaign_map_state_value=replace(after,generation=last.generation+1,enemies=(),
        fleets=(replace(after.fleets[0],node='D3',ammo=4),))
    assert adapter.confirm_campaign_combat(battle_count_after=1).target_node=='D3'


@pytest.mark.parametrize('status',['zero','spent','closed'])
def test_covered_route_without_available_camera_grant_defers_before_any_input(status):
    adapter,oracle,state,decision=native_route(int(status!='zero'))
    if status=='spent':adapter._action_ledger.dispatch('campaign.viewport_swipe',lambda:None)
    elif status=='closed':adapter._action_ledger.close()
    with pytest.raises(ActionLeaseError if status=='closed' else AlasSemanticActionDeferred):
        adapter.authorize_campaign_combat(decision,state)
    assert oracle.click_calls==[] and oracle.campaign_map_swipe_calls==[]
    assert adapter._campaign_context.combat_admission is None


def test_visible_route_uses_no_camera_grant():
    adapter,oracle,state,decision=native_route(0,covered=False)
    assert adapter.authorize_campaign_combat(decision,state)
    assert adapter._action_ledger.remaining('campaign.viewport_swipe')==0
    assert oracle.click_calls==[] and oracle.campaign_map_swipe_calls==[]


def test_route_identity_failure_remains_closed_before_camera_grant_classification():
    adapter,oracle,state,decision=native_route(0)
    with pytest.raises(SemanticGateClosed,match='exact orthogonal route'):
        adapter.authorize_campaign_combat(replace(decision,route_nodes=('D6','D3')),state)
    assert oracle.click_calls==[] and oracle.campaign_map_swipe_calls==[]


def test_zero_camera_preflight_is_local_and_unrelated_dorm_collect_runs():
    adapter,oracle,state,decision=native_route(0)
    session=session_for(adapter)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session,'campaign'):
            adapter.authorize_campaign_combat(decision,state)
    assert oracle.click_calls==[] and oracle.campaign_map_swipe_calls==[]
    with semantic_task_scope(session,'dorm'):
        adapter.begin_dorm()
        adapter.click(NamedButton('DORM_QUICK_COLLECT'))
    assert oracle.click_calls==['dorm/collect']
