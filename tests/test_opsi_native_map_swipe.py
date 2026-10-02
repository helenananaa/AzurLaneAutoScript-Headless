from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter,SemanticGateClosed
from alas_headless.oracle.contracts import Point
from tests.test_semantic_oracle_opsi_map_geometry import setup_map
from tests.semantic_support.adapter_fixtures import FakeOracle

ROOT='LevelCamera/Canvas/UIMain/LevelGrid/DragLayer'
START=(500,500);END=(500,300)

def proof():
    return {'status':1,'handler_instance_id':123,'handler_path':ROOT,'endpoints':[*START,*END],
        'samples':[{'x':500,'y':500-i*200/32,'owned':True,'top_path':ROOT} for i in range(33)]}

def reader(result):
    backend,oracle=setup_map()
    oracle._sleep=lambda _:None
    oracle.read_ui_state=Mock(side_effect=[SimpleNamespace(generation=1,snapshot={}),
        SimpleNamespace(generation=2,snapshot={'operation_siren_map_drag':result})])
    oracle._request=Mock(return_value={'status':'ok','scope':'read-only-os-map-drag'})
    return backend,oracle

def test_native_readonly_drag_proof_keeps_original_alas_endpoints():
    backend,oracle=reader(proof())
    generation,result=oracle.operation_siren_map_drag_proof(START,END)
    assert generation==2 and result['handler_instance_id']==123
    oracle._request.assert_called_once_with('GET /v1/os-map-drag 500 500 500 300\n')
    assert backend.swipes==[] and backend.taps==[]

@pytest.mark.parametrize('failure',['unavailable','handler','disabled','missing-sample','obscured','child','point','nan'])
def test_unsafe_native_drag_proof_never_dispatches(failure):
    result=proof()
    if failure=='unavailable':result['status']=2
    elif failure=='handler':result['handler_path']='other'
    elif failure=='disabled':result['handler_instance_id']=0
    elif failure=='missing-sample':result['samples'].pop()
    elif failure=='obscured':result['samples'][8]['owned']=False
    elif failure=='child':result['samples'][0]['top_path']='OverlayCamera/Popup'
    elif failure=='point':result['samples'][12]['x']+=1
    elif failure=='nan':result['samples'][12]['y']=float('nan')
    backend,oracle=reader(result)
    with pytest.raises(SemanticGateClosed):oracle.operation_siren_map_drag_proof(START,END)
    assert backend.swipes==[] and backend.taps==[]

def map_state(oracle):
    state=oracle.operation_siren_map_geometry('东北航道A',rows=3,columns=3)
    return replace(state,current_fleet=1,fleet_cells=((1,'B2'),))

@pytest.mark.parametrize('moves',[True,False])
def test_real_dispatch_requires_native_postcondition_and_retains_consumed_attempt(moves):
    backend,oracle=setup_map();state=map_state(oracle)
    after=replace(state,generation=100,cells=tuple(replace(c,point=Point(c.point.x,c.point.y-200 if moves else c.point.y)) for c in state.cells))
    oracle.operation_siren_map_geometry=Mock(side_effect=[state]+[after]*12)
    oracle.operation_siren_map_drag_proof=Mock(return_value=(state.generation+1,proof()))
    oracle._blocking_rules=lambda *a:()
    oracle._sleep=lambda _:None
    oracle._foreground_component=lambda:oracle.fingerprint.component
    if moves:
        receipt=oracle.operation_siren_map_swipe(state,START,END,300)
        assert receipt.observed_displacement==(0,-200)
    else:
        with pytest.raises(SemanticGateClosed,match='did not advance'):
            oracle.operation_siren_map_swipe(state,START,END,300)
    assert backend.swipes==[(500,500,500,300,300)]
    attempt=oracle._operation_siren_map_swipe_attempts[0]
    assert attempt['dispatched'] is True and attempt['postcondition_proven'] is moves

def arm(adapter):
    return adapter.begin_operation_siren_map_swipe_vector((0,-200),box=(239,128,993,628),
        random_range=(0,0,0,0),padding=15,duration=(0.1,0.2),whitelist_area=None,
        blacklist_area=None,name='MAP_SWIPE_0_5',distance_check=True)

def test_adapter_only_routes_the_owned_alas_gesture_and_cleans_token():
    oracle=FakeOracle();adapter=AlasSemanticAdapter(oracle,lambda:None)
    adapter._operation_siren_camera_geometry=SimpleNamespace(zone_name='东北航道A')
    adapter._operation_siren_allows_passive_probe=lambda:True
    oracle.operation_siren_map_swipe=Mock(return_value='receipt')
    token=arm(adapter)
    assert adapter.swipe(START,END,duration=.3,name=token.name,distance_check=True)=='receipt'
    oracle.operation_siren_map_swipe.assert_called_once_with(token.geometry,START,END,300)
    adapter.end_operation_siren_map_swipe_vector(token)
    assert adapter._operation_siren_map_swipe_intent is None

@pytest.mark.parametrize('failure',['unowned','campaign-owner','changed-vector','changed-name','duration'])
def test_adapter_does_not_admit_unowned_or_changed_os_swipe(failure):
    oracle=FakeOracle();adapter=AlasSemanticAdapter(oracle,lambda:None)
    adapter._operation_siren_camera_geometry=SimpleNamespace(zone_name='东北航道A')
    adapter._operation_siren_allows_passive_probe=lambda:failure!='unowned'
    oracle.operation_siren_map_swipe=Mock()
    if failure=='campaign-owner':adapter.begin_campaign_pre_sortie('12-4')
    with pytest.raises(SemanticGateClosed):
        token=arm(adapter)
        adapter.swipe(START,(500,301) if failure=='changed-vector' else END,
            duration=5 if failure=='duration' else .3,name='OTHER' if failure=='changed-name' else token.name,distance_check=True)
    oracle.operation_siren_map_swipe.assert_not_called()

@pytest.mark.parametrize('stage',['before-proof','after-proof'])
def test_new_blocker_cannot_be_bypassed_by_native_drag_proof(stage):
    backend,oracle=setup_map();state=map_state(oracle)
    oracle.operation_siren_map_geometry=Mock(return_value=state)
    oracle.operation_siren_map_drag_proof=Mock(return_value=(state.generation+1,proof()))
    oracle._blocking_rules=Mock(side_effect=[(SimpleNamespace(blocker_id='popup'),)] if stage=='before-proof'
                               else [(),(SimpleNamespace(blocker_id='popup'),)])
    with pytest.raises(SemanticGateClosed,match='obscured'):
        oracle.operation_siren_map_swipe(state,START,END,300)
    assert backend.swipes==[]

@pytest.mark.parametrize('start,end,duration',[(START,START,300),(START,END,False),(START,END,0)])
def test_empty_or_invalid_direct_gesture_is_rejected_before_input(start,end,duration):
    backend,oracle=setup_map();state=map_state(oracle)
    with pytest.raises(SemanticGateClosed):oracle.operation_siren_map_swipe(state,start,end,duration)
    assert backend.swipes==[]

@pytest.mark.parametrize('areas',[None,[]])
def test_harmless_empty_original_alas_areas_are_compatible(areas):
    oracle=FakeOracle();adapter=AlasSemanticAdapter(oracle,lambda:None)
    adapter._operation_siren_camera_geometry=SimpleNamespace(zone_name='东北航道A')
    adapter._operation_siren_allows_passive_probe=lambda:True
    token=adapter.begin_operation_siren_map_swipe_vector((0,-200),box=(239,128,993,628),
        random_range=(0,0,0,0),padding=15,duration=(0.1,0.2),whitelist_area=areas,
        blacklist_area=areas,name='MAP_SWIPE_0_5',distance_check=True)
    assert token.blacklist_areas==()
    adapter.end_operation_siren_map_swipe_vector(token)

def test_original_alas_forbidden_area_still_blocks_before_dispatch():
    oracle=FakeOracle();adapter=AlasSemanticAdapter(oracle,lambda:None)
    adapter._operation_siren_camera_geometry=SimpleNamespace(zone_name='东北航道A')
    adapter._operation_siren_allows_passive_probe=lambda:True
    oracle.operation_siren_map_swipe=Mock()
    token=adapter.begin_operation_siren_map_swipe_vector((0,-200),box=(239,128,993,628),
        random_range=(0,0,0,0),padding=15,duration=(0.1,0.2),whitelist_area=[],
        blacklist_area=[(490,290,510,310)],name='MAP_SWIPE_0_5',distance_check=True)
    with pytest.raises(SemanticGateClosed,match='forbidden'):
        adapter.swipe(START,END,duration=.3,name=token.name,distance_check=True)
    oracle.operation_siren_map_swipe.assert_not_called()

def test_loading_only_wait_reproves_owned_map_and_handler_before_dispatch():
    backend,oracle=setup_map();state=map_state(oracle)
    after=replace(state,generation=100,cells=tuple(replace(c,point=Point(c.point.x,c.point.y-200)) for c in state.cells))
    oracle.operation_siren_map_geometry=Mock(side_effect=[state,state,after])
    oracle.operation_siren_map_drag_proof=Mock(return_value=(state.generation+1,proof()))
    loading=(SimpleNamespace(blocker_id='loading'),)
    oracle._blocking_rules=Mock(side_effect=[loading,(),loading,(),()])
    oracle._sleep=lambda _:None
    oracle._foreground_component=lambda:oracle.fingerprint.component
    result=oracle.operation_siren_map_swipe(state,START,END,300)
    assert result.post_generation==100 and backend.swipes==[(500,500,500,300,300)]
    assert oracle.operation_siren_map_drag_proof.call_count==2

def test_loading_that_never_clears_does_not_dispatch_or_hide_blocker():
    backend,oracle=setup_map();state=map_state(oracle)
    oracle._blocking_rules=lambda *a:(SimpleNamespace(blocker_id='loading'),)
    oracle._sleep=lambda _:None
    with pytest.raises(SemanticGateClosed,match='loading did not clear'):
        oracle.operation_siren_map_swipe(state,START,END,300)
    assert backend.swipes==[]

def test_live_recorder_encodes_native_map_observation_without_hiding_consumed_input():
    import importlib.util,json
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'scripts/python/run_alas_configured_task_live.py'
    spec=importlib.util.spec_from_file_location('configured_task_receipt',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    backend,oracle=setup_map();state=map_state(oracle)
    encoded=module.encode_navigation_intent((state,START,END,300))
    decoded=json.loads(json.dumps({'intent':encoded}))['intent']
    assert decoded[0]['zone_name']==state.zone_name
    assert len(decoded[0]['cells'])==9
    assert decoded[1:]==[[500,500],[500,300],300]
