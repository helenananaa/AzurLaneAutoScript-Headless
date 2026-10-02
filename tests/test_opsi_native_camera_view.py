from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless.alas_opsi_camera_view import AlasSemanticOpsiView,install_alas_opsi_camera_view
from alas_headless import SemanticGateClosed
from tests.test_semantic_oracle_opsi_map_geometry import setup_map

@pytest.fixture
def native(monkeypatch):
    runtime=Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream'
    if not runtime.exists():pytest.skip('materialized ALAS unavailable')
    monkeypatch.syspath_prepend(str(runtime))
    from module.map_detection.os_grid import OSGridInfo
    from module.os.map_base import OSCampaignMap
    return OSGridInfo,OSCampaignMap

def geometry():
    backend,oracle=setup_map()
    state=oracle.operation_siren_map_geometry('东北航道A',rows=3,columns=3)
    attachment=state.attachments[0]
    attachment=replace(attachment,sprites=((attachment.path+'/icon/model/1x1XWIsLand_1(Clone)','1x1XWIsLand_1'),))
    return replace(state,attachments=(attachment,),current_fleet=1,fleet_cells=((1,'B2'),))

def test_original_alas_grids_receive_only_visible_cells_and_native_global_coordinates(native):
    OSGridInfo,OSCampaignMap=native
    state=geometry();view=AlasSemanticOpsiView(state,SimpleNamespace(SCREEN_CENTER=(310,310)))
    assert all(isinstance(grid,OSGridInfo) for grid in view)
    assert 'A1' not in view.semantic_observation.visible_nodes
    assert view.select(is_current_fleet=True).count==1
    assert view.select(is_land=True).count==1
    # Original ALAS owns merging the local View into its map.
    original=OSCampaignMap();original.shape='H18'
    original.update(view,view.semantic_observation.camera_location)
    fleet=view.select(is_current_fleet=True).grids[0]
    offset=tuple(a-b for a,b in zip(view.semantic_observation.camera_location,view.center_loca))
    assert tuple(a+b for a,b in zip(offset,fleet.location))==(1,1)
    assert original.grids[(1,1)].location==(1,1)

def test_unknown_visible_attachment_does_not_become_an_empty_rescan(native):
    state=geometry();unknown=replace(state.attachments[0],object_id=123456)
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(unknown,)),SimpleNamespace(SCREEN_CENTER=(310,310)))


@pytest.mark.parametrize('event_id', range(9071,9080))
def test_second_native_island_family_fills_original_land_grid(native,event_id):
    state=geometry(); a=state.attachments[0]
    a=replace(a,object_id=event_id,sprites=((a.path+'/icon/model/1x1XWIsLand_2(Clone)','1x1XWIsLand_2'),))
    view=AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
    assert view.select(is_land=True).count==1
    assert view.select(is_enemy=True).count==0


@pytest.mark.parametrize('changed', ['id','model','extra'])
def test_second_island_requires_matching_id_and_complete_model(native,changed):
    state=geometry(); a=state.attachments[0]
    sprites=((a.path+'/icon/model/1x1XWIsLand_2(Clone)','1x1XWIsLand_2'),)
    if changed=='model': sprites=a.sprites
    if changed=='extra': sprites=sprites+((a.path+'/extra','unreviewed'),)
    a=replace(a,object_id=9080 if changed=='id' else 9075,sprites=sprites)
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))


@pytest.mark.parametrize('event_id', range(9031,9040))
def test_third_reviewed_island_family_fills_original_land_grid(native,event_id):
    state=geometry(); a=state.attachments[0]
    model='1x1XWIsLand_3'
    a=replace(a,object_id=event_id,sprites=((a.path+'/icon/model/'+model+'(Clone)',model),))
    view=AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
    assert view.select(is_land=True).count==1
    assert view.select(is_enemy=True).count==0


@pytest.mark.parametrize('changed', ['id-low','id-high','model','extra','kind'])
def test_third_island_requires_reviewed_id_and_complete_model(native,changed):
    state=geometry(); a=state.attachments[0]
    sprites=((a.path+'/icon/model/1x1XWIsLand_3(Clone)','1x1XWIsLand_3'),)
    if changed=='model': sprites=a.sprites
    if changed=='extra': sprites += ((a.path+'/extra','unreviewed'),)
    event_id=9030 if changed=='id-low' else 9040 if changed=='id-high' else 9032
    a=replace(a,object_id=event_id,kind='enemy' if changed=='kind' else 'event',sprites=sprites)
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))


@pytest.mark.parametrize('event_id', list(range(9051,9060)))
def test_reviewed_island_variants_are_native_land(native, event_id):
    state=geometry(); a=replace(state.attachments[0],object_id=event_id)
    view=AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
    assert view.select(is_land=True).count==1


@pytest.mark.parametrize('event_id', [9050, 9060, 86020])
def test_same_model_without_reviewed_obstacle_definition_remains_unknown(native,event_id):
    state=geometry();a=replace(state.attachments[0],object_id=event_id)
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))


@pytest.mark.parametrize('sprites', [('putongbaoxiang',), ('1x1XWIsLand_1', 'putongbaoxiang')])
def test_reviewed_island_id_with_changed_or_ambiguous_model_is_rejected(native, sprites):
    state=geometry(); a=state.attachments[0]
    a=replace(a,object_id=9057,sprites=tuple((a.path+'/icon/model/'+s+'(Clone)',s) for s in sprites))
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))

def test_install_does_not_apply_pending_original_alas_swipe_twice(native):
    host=SimpleNamespace(config=SimpleNamespace(SCREEN_CENTER=(310,310)),camera=(1,1),_prev_view=object())
    observed=install_alas_opsi_camera_view(host,geometry())
    assert host.camera==(1,1)
    assert observed.camera_location==(2,2)
    assert host.view.semantic_state.zone_name=='东北航道A'

@pytest.mark.parametrize('shape', ['H18', (7,17)])
def test_original_os_camera_accepts_zone_shape_notation(native,shape):
    import ast
    from module.map.map_base import location_ensure
    source=Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream/module/os/camera.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_load_semantic_os_view')
    calls=[]
    def read(name,**dimensions):
        calls.append((name,dimensions))
        return geometry()
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=SimpleNamespace(operation_siren_map_geometry=read)),
        appear=lambda *args,**kwargs: False,
        zone=SimpleNamespace(cn='Northeast Passage A',shape=shape),
        config=SimpleNamespace(SCREEN_CENTER=(310,310)),_prev_view=None)
    scope={'location_ensure':location_ensure,'logger':SimpleNamespace(info=lambda *a:None)}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),scope)
    assert scope['_load_semantic_os_view'](host) is True
    assert calls==[('Northeast Passage A',{'rows':18,'columns':8})]

@pytest.mark.parametrize('native_prediction,expected_camera',[(True,(1,4)),(False,(1,6))])
def test_original_camera_uses_actual_semantic_swipe_delta_with_os_pixel_prediction_disabled(native,native_prediction,expected_camera):
    import ast,numpy as np
    source=Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream/module/map/camera.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_update_view_data')
    view=SimpleNamespace(semantic_swipe_prediction=native_prediction,left_edge=False,right_edge=False,upper_edge=False,lower_edge=False)
    host=SimpleNamespace(config=SimpleNamespace(MAP_SWIPE_PREDICT=False,MAP_SWIPE_PREDICT_WITH_CURRENT_FLEET=False,MAP_SWIPE_PREDICT_WITH_SEA_GRIDS=False),
        _prev_view=SimpleNamespace(predict_swipe=lambda *a,**k:(0,3)),_prev_swipe=(0,5),camera=(1,1),view=view,
        show_camera=lambda:None,predict=lambda:None)
    scope={'np':np}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),scope)
    assert scope['_update_view_data'](host) is True
    assert host.camera==expected_camera and host._prev_view is None

def test_unresolved_native_fog_cannot_become_an_empty_original_alas_rescan(native):
    state=replace(geometry(),unresolved_fog_images=('LevelGrid/plane/cells/fogs/fog/dark_fog',))
    with pytest.raises(SemanticGateClosed,match='rescan visibility unavailable'):
        AlasSemanticOpsiView(state,SimpleNamespace(SCREEN_CENTER=(310,310)))


@pytest.mark.parametrize('event_id', [5103, 5204])
def test_reviewed_damaged_control_remains_passable_without_action_event(native,event_id):
    state=geometry();a=state.attachments[0]
    a=replace(a,object_id=event_id,sprites=((a.path+'/icon/model/qihouzhuangzhi_huai(Clone)','qihouzhuangzhi_huai'),))
    view=AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
    grid=next(g for g in view.grids.values() if g.semantic_passable_decorations)
    assert grid.semantic_passable_decorations==(a,)
    assert not grid.is_land
    assert not any(getattr(grid,k) for k in ('is_enemy','is_resource','is_question','is_exclamation','is_exploration_reward','is_exploration_container','is_fleet_mechanism'))

@pytest.mark.parametrize('event_id,sprite', [(5205,'qihouzhuangzhi_huai'),(5204,'qihouzhuangzhi'),(5204,'putongbaoxiang')])
def test_active_or_changed_control_is_not_silently_classified_inert(native,event_id,sprite):
    state=geometry();a=state.attachments[0]
    a=replace(a,object_id=event_id,sprites=((a.path+'/icon/model/'+sprite+'(Clone)',sprite),))
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))


@pytest.mark.parametrize('reversed_order',[False,True])
def test_native_chess_combat_event_is_not_an_empty_rescan(native,reversed_order):
    state=geometry(); a=state.attachments[0]
    a=replace(a,object_id=10240202,sprites=((a.path+'/live/icon/size/bg_m','zhong'),
                                          (a.path+'/live/icon/pic','qz1')))
    if reversed_order:a=replace(a,sprites=a.sprites[::-1])
    view=AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
    enemies=view.select(is_enemy=True)
    assert enemies.count==1
    assert enemies.grids[0].enemy_scale==2 and enemies.grids[0].enemy_genre=='Enemy'
    assert not enemies.grids[0].is_land and not enemies.grids[0].semantic_passable_decorations


@pytest.mark.parametrize('event_id,sprite', [(10240203,'qz1'), (10240202,'putongbaoxiang')])
def test_changed_chess_encounter_does_not_inherit_combat_classification(native,event_id,sprite):
    state=geometry(); a=state.attachments[0]
    a=replace(a,object_id=event_id,sprites=((a.path+'/live/icon/size/bg_m','zhong'),
                                          (a.path+'/live/icon/pic',sprite)))
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))


def test_stopped_reinforcement_preserves_native_passable_decoration(native):
    state=geometry(); a=state.attachments[0]
    a=replace(a,object_id=5705,sprites=((a.path+'/icon/model/fubiao1(Clone)','fubiao1'),))
    view=AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
    grid=next(g for g in view if g.semantic_passable_decorations)
    assert grid.semantic_passable_decorations==(a,)
    assert not any(getattr(grid,k) for k in ('is_land','is_enemy','is_resource','is_question',
        'is_exclamation','is_exploration_reward','is_exploration_container','is_fleet_mechanism'))


@pytest.mark.parametrize('change',['active-id','unknown-id','active-model','extra','kind'])
def test_active_or_changed_reinforcement_remains_unknown(native,change):
    state=geometry(); a=state.attachments[0]
    sprites=((a.path+'/icon/model/fubiao1(Clone)','fubiao1'),)
    if change=='active-model':sprites=((a.path+'/icon/model/fubiao2(Clone)','fubiao2'),)
    if change=='extra':sprites+=((a.path+'/extra','unknown'),)
    a=replace(a,object_id=5704 if change=='active-id' else 5706 if change=='unknown-id' else 5705,
        kind='enemy' if change=='kind' else 'event',sprites=sprites)
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))


def test_r209_exact_failed_reinforcement_maps_into_original_view(native):
    import json
    from alas_headless.oracle.opsi_map import OperationSirenMapGeometry,OperationSirenMapAttachment
    from alas_headless.oracle.contracts import Point,Bounds,CampaignMapCellState
    source=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r209-camera-view-failures.jsonl'
    if not source.exists():pytest.skip('retained r209 frame unavailable')
    raw=json.loads(source.read_text(encoding='utf-8').splitlines()[-1])['observation']['state']
    state=OperationSirenMapGeometry(**dict(raw,
        cells=tuple(CampaignMapCellState(**dict(c,point=Point(**c['point']),bounds=Bounds(**c['bounds']))) for c in raw['cells']),
        attachments=tuple(OperationSirenMapAttachment(**dict(a,sprites=tuple(map(tuple,a['sprites'])))) for a in raw['attachments']),
        fleet_cells=tuple(map(tuple,raw['fleet_cells']))))
    view=AlasSemanticOpsiView(state,SimpleNamespace(SCREEN_CENTER=(310,310)))
    stopped=[a for g in view for a in g.semantic_passable_decorations if a.object_id==5705]
    assert len(stopped)==1


@pytest.mark.parametrize('reversed_order', [False, True])
def test_native_information_device_uses_original_logging_tower_flow(native, reversed_order):
    state=geometry(); a=state.attachments[0]
    model=a.path+'/icon/model/xinxita(Clone)'
    sprites=((model,'xinxita1'),(model+'/0','xinxita'),(model+'/2','xinxita2'),
             (model+'/3','xinxita3'),(model+'/4','xinxita4'))
    a=replace(a,object_id=1101,sprites=sprites[::-1] if reversed_order else sprites)
    view=AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
    towers=view.select(is_logging_tower=True)
    assert towers.count==1
    assert towers.grids[0].enemy_genre=='LoggingTower' and towers.grids[0].is_enemy
    assert not towers.grids[0].is_land and not towers.grids[0].semantic_passable_decorations


@pytest.mark.parametrize('changed', ['event-id','sprite','missing'])
def test_unknown_or_incomplete_information_device_remains_unclassified(native, changed):
    state=geometry(); a=state.attachments[0]
    model=a.path+'/icon/model/xinxita(Clone)'
    sprites=((model,'xinxita1'),(model+'/0','xinxita'),(model+'/2','xinxita2'),
             (model+'/3','xinxita3'),(model+'/4','xinxita4'))
    if changed=='sprite': sprites=sprites[:-1]+((model+'/4','unknown'),)
    if changed=='missing': sprites=sprites[:-1]
    a=replace(a,object_id=1106 if changed=='event-id' else 1101,sprites=sprites)
    with pytest.raises(SemanticGateClosed,match='classification unavailable'):
        AlasSemanticOpsiView(replace(state,attachments=(a,)),SimpleNamespace(SCREEN_CENTER=(310,310)))
