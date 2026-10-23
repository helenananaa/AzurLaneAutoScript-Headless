from tests.alas_test_source import patched_alas_root
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import ast
import pytest
from alas_headless import SemanticGateClosed
from tests.test_semantic_oracle_opsi_port_geometry import fixture

START=(508,425);END=(808,442);ROOT='WorldMap3D/entity/Plane'

def proof():
    return {'status':1,'handler_instance_id':55,'handler_path':ROOT,'endpoints':[*START,*END],
        'samples':[{'x':START[0]+300*i/32,'y':START[1]+17*i/32,'owned':True,'top_path':ROOT} for i in range(33)]}

def reader(data,field='operation_siren_globe_drag'):
    backend,oracle=fixture();oracle._sleep=lambda _:None
    oracle._require_operation_siren_globe_visible=Mock(return_value=True)
    snapshots=[SimpleNamespace(generation=1,snapshot={}),SimpleNamespace(generation=2,snapshot={field:data})]
    oracle.read_ui_state=Mock(side_effect=lambda **k:snapshots.pop(0) if len(snapshots)>1 else snapshots[0])
    original_request=oracle._request
    oracle._request=Mock(side_effect=lambda request: {'status':'ok','scope':'read-only-globe-map-drag'}
        if request.startswith('GET /v1/globe-map-drag ') else original_request(request))
    return backend,oracle


@pytest.mark.parametrize('error', ['observer generation moved backwards',
    'game activity is not top-resumed', 'button snapshot is truncated'])
def test_drag_identity_preserves_observation_error_without_input(error):
    backend,oracle=fixture()
    oracle.read_state=Mock(side_effect=SemanticGateClosed(error))
    assert oracle.operation_siren_globe_visible() is False
    with pytest.raises(SemanticGateClosed,match=error):
        oracle.operation_siren_globe_drag_proof(START,END)
    assert backend.taps==backend.swipes==[]


def test_ready_globe_identity_still_accepts_r208_retained_frame():
    import json
    from tests.semantic_support.observer_fixtures import FakeBackend,make_oracle
    source=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-scheduler-r208-20261002.json'
    if not source.exists():pytest.skip('retained r208 frame unavailable')
    task=json.loads(source.read_text(encoding='utf-8'))['tasks'][-1]
    backend=FakeBackend(task['failure_leased_frame']['buttons_snapshot']['buttons'])
    oracle=make_oracle(backend)
    assert oracle.operation_siren_globe_visible() is True
    oracle._require_operation_siren_globe_visible()
    assert backend.taps==backend.swipes==[]

def test_native_globe_handler_proof_is_readonly_and_preserves_points():
    backend,oracle=reader(proof())
    assert oracle.operation_siren_globe_drag_owned(START,END) is True
    drag_requests=[call.args[0] for call in oracle._request.call_args_list
        if call.args[0].startswith('GET /v1/globe-map-drag ')]
    assert drag_requests==['GET /v1/globe-map-drag 508 425 808 442\n']
    assert backend.swipes==backend.taps==[]

def test_background_path_is_observed_unowned_without_dispatch():
    data=proof()
    for s in data['samples']:s.update(owned=False,top_path='UICamera/Canvas/UIMain/WorldUI(Clone)/main/bg')
    backend,oracle=reader(data)
    assert oracle.operation_siren_globe_drag_owned(START,END) is False
    assert backend.swipes==[]


def test_retained_r202_half_leg_still_rejects_its_background_tail():
    import json
    source=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-scheduler-r202-20261002.json'
    if not source.exists():pytest.skip('retained r202 diagnostic unavailable')
    task=json.loads(source.read_text(encoding='utf-8'))['tasks'][-1]
    data=task['failure_observation']['ui']['snapshot']['operation_siren_globe_drag']
    assert len(data['samples'])==33
    assert sum(sample['owned'] for sample in data['samples'])==26
    backend,oracle=reader(data)
    assert data['endpoints']==[int(value) for value in data['endpoints']]
    start=tuple(int(value) for value in data['endpoints'][:2])
    end=tuple(int(value) for value in data['endpoints'][2:])
    assert oracle.operation_siren_globe_drag_owned(start,end) is False
    assert backend.swipes==backend.taps==[]

@pytest.mark.parametrize('case',['foreign-handler','incomplete','missing-owned','wrong-point','false-owned-path','scope-local'])
def test_incomplete_or_foreign_proof_fails_closed(case):
    data=deepcopy(proof());field='operation_siren_globe_drag'
    if case=='foreign-handler':data['handler_path']='LevelCamera/Canvas/UIMain/LevelGrid/DragLayer'
    if case=='incomplete':data['samples'].pop()
    if case=='missing-owned':data['samples'][0].pop('owned')
    if case=='wrong-point':data['samples'][0]['x']+=5
    if case=='false-owned-path':data['samples'][0]['top_path']='Overlay/popup'
    if case=='scope-local':field='operation_siren_map_drag'
    backend,oracle=reader(data,field)
    with pytest.raises(SemanticGateClosed):oracle.operation_siren_globe_drag_owned(START,END)
    assert backend.swipes==[]

@pytest.mark.parametrize('operation',['camera','unpin'])
def test_unowned_plane_cannot_receive_globe_input(operation):
    backend,oracle=fixture()
    oracle.operation_siren_globe_drag_owned=Mock(return_value=False)
    if operation=='camera':
        with pytest.raises(SemanticGateClosed,match='outside the owned plane'):
            oracle.operation_siren_globe_swipe(START,END,300)
    else:
        from tests.semantic_support.observer_fixtures import make_image
        backend.ui['images']=[make_image('root/SVFloatPanel(Clone)/point','click_point_safe')];backend.ui['image_count']=1
        backend.ui['globe_geometry']={'status':1,'truncated':False,'error_count':0,'camera_path':'WorldMap3D/Main Camera',
            'objects':[{'name':'port','truncated':False,'plane_hit':True,'ui_clear':True,'ui_top_path':ROOT,'plane_instance_id':55,'input_point':list(START)}]}
        oracle.operation_siren_globe_state=lambda:None
        with pytest.raises(SemanticGateClosed,match='outside the owned plane'):oracle.operation_siren_globe_unpin()
    assert backend.swipes==[]

@pytest.mark.parametrize('outcome',['resample','exhausted','unavailable'])
def test_original_alas_sampler_rejects_unowned_candidates_before_input(outcome):
    source=patched_alas_root() / 'module/device/control.py'
    node=next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef) and n.name=='swipe_vector')
    samples=Mock(return_value=(START,END));token=object()
    owned=Mock(side_effect=[False,True] if outcome=='resample' else SemanticGateClosed('missing native proof') if outcome=='unavailable' else None,return_value=False)
    adapter=SimpleNamespace(begin_operation_siren_globe_swipe_vector=Mock(return_value=token),end_operation_siren_globe_swipe_vector=Mock(),operation_siren_globe_drag_owned=owned)
    host=SimpleNamespace(semantic_adapter=adapter,swipe=Mock())
    ns={'random_rectangle_vector_opted':samples,'logger':Mock()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),ns)
    if outcome=='resample':
        ns['swipe_vector'](host,(300,17),name='GLOBE_SWIPE_300_17')
        assert samples.call_count==2;host.swipe.assert_called_once()
    else:
        with pytest.raises(SemanticGateClosed):ns['swipe_vector'](host,(300,17),name='GLOBE_SWIPE_300_17')
        assert samples.call_count==(8 if outcome=='exhausted' else 1);host.swipe.assert_not_called()
    adapter.end_operation_siren_globe_swipe_vector.assert_called_once_with(token)


def test_new_blocker_after_native_proof_prevents_input():
    from tests.semantic_support.observer_fixtures import make_button,make_buttons
    backend,oracle=fixture();back=backend.buttons['buttons'][0]
    def accepted(*args):
        backend.buttons=make_buttons([back,make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')],generation=11)
        return True
    oracle.operation_siren_globe_drag_owned=accepted
    with pytest.raises(SemanticGateClosed,match='changed after camera drag proof'):
        oracle.operation_siren_globe_swipe(START,END,300)
    assert backend.swipes==[]


def test_loading_after_final_camera_proof_reproves_before_single_input():
    from tests.semantic_support.observer_fixtures import make_buttons
    backend, oracle = fixture()
    oracle._sleep = lambda _: None
    loading = (SimpleNamespace(blocker_id='loading'),)
    oracle._blocking_rules = Mock(side_effect=[(), loading, (), ()])
    oracle.operation_siren_globe_drag_owned = Mock(return_value=True)
    backend.on_swipe = lambda: setattr(backend, 'buttons',
        make_buttons(backend.buttons['buttons'], generation=13))
    receipt = oracle.operation_siren_globe_swipe(START, END, 300)
    assert oracle.operation_siren_globe_drag_owned.call_count == 2
    assert backend.swipes == [(*START, *END, 2000)]
    assert receipt.post_generation > receipt.pre_generation


def test_persistent_loading_after_camera_proof_still_sends_no_input():
    backend, oracle = fixture()
    oracle._sleep = lambda _: None
    loading = (SimpleNamespace(blocker_id='loading'),)
    oracle._blocking_rules = Mock(side_effect=[()] + [loading] * 30)
    oracle.operation_siren_globe_drag_owned = Mock(return_value=True)
    with pytest.raises(SemanticGateClosed, match='obscured before swipe'):
        oracle.operation_siren_globe_swipe(START, END, 300)
    oracle.operation_siren_globe_drag_owned.assert_called_once_with(START, END)
    assert not backend.swipes


def test_loading_between_sample_and_final_proof_waits_without_input():
    backend,oracle=fixture();oracle._sleep=lambda _:None
    loading=(SimpleNamespace(blocker_id='loading'),)
    oracle._blocking_rules=Mock(side_effect=[(),loading,(),()])
    blocked=proof()
    for row in blocked['samples']:row.update(owned=False,top_path='OverlayCamera/Overlay/UIOverlay/Loading(Clone)')
    oracle.operation_siren_globe_drag_proof=Mock(side_effect=[(11,blocked),(12,proof())])
    assert oracle.operation_siren_globe_drag_owned(START,END) is True
    assert oracle.operation_siren_globe_drag_proof.call_count==2 and backend.swipes==[]


def test_nonloading_blocker_is_not_retried_as_transient_globe_loading():
    backend,oracle=fixture();oracle._sleep=lambda _:None
    oracle._blocking_rules=Mock(return_value=(SimpleNamespace(blocker_id='message'),))
    oracle.operation_siren_globe_drag_proof=Mock()
    with pytest.raises(SemanticGateClosed,match='obscured'):
        oracle.operation_siren_globe_drag_owned(START,END)
    oracle.operation_siren_globe_drag_proof.assert_not_called()
    assert backend.swipes==[]
