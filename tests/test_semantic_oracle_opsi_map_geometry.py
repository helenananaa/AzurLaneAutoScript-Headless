import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_ui, make_image, make_text

ROOT = 'LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/'

def setup_map():
    backend = FakeBackend([])
    images=[]
    for row in range(3):
        for column in range(3):
            image=make_image(ROOT + f'quads/world_quad_{row}_{column}/walk_quad','cell_white')
            image['adb_bounds']={'left':100+column*100,'top':100+row*100,'right':200+column*100,'bottom':200+row*100}
            image['adb_point']={'x':150+column*100,'y':150+row*100}
            images.append(image)
    images.append(make_image(ROOT+'cells/cell_1_2/attachments/event_9052/icon/model/island(Clone)', 'island'))
    backend.ui=make_ui([make_text('东北航道A','OverlayCamera/Overlay/UIMain/top/adapt/top_stage/title/name')],images=images)
    oracle=make_oracle(backend)
    oracle.operation_siren_local_map_visible=lambda:True
    return backend,oracle

def test_complete_geometry_keeps_unknown_attachment_for_original_alas_classification():
    backend,oracle=setup_map()
    result=oracle.operation_siren_map_geometry('东北航道A',rows=3,columns=3)
    assert len(result.cells)==9
    assert result.cells[0].node=='A1'
    assert result.attachments[0].object_id==9052
    assert result.attachments[0].kind=='event'
    assert backend.taps==[]

@pytest.mark.parametrize('failure',['truncated','missing','duplicate','point','wrong-zone','shape'])
def test_geometry_rejects_incomplete_or_wrong_map_without_input(failure):
    backend,oracle=setup_map()
    if failure=='truncated':backend.ui['image_truncated']=True
    elif failure=='missing':backend.ui['images'].pop(0);backend.ui['image_count']-=1
    elif failure=='duplicate':backend.ui['images'].append(backend.ui['images'][0]);backend.ui['image_count']+=1
    elif failure=='point':backend.ui['images'][0]['adb_point']['x']=float('nan')
    elif failure=='wrong-zone':backend.ui['texts'][0]['text']='其他海域'
    with pytest.raises(SemanticGateClosed):
        oracle.operation_siren_map_geometry('东北航道A',rows=4 if failure=='shape' else 3,columns=3)
    assert backend.taps==[]

@pytest.mark.parametrize('alpha,unresolved',[(0.0,False),(1.0,True)])
def test_fog_opacity_is_retained_as_unknown_visibility_not_empty_cells(alpha,unresolved):
    backend,oracle=setup_map()
    fog=make_image(ROOT+'cells/fogs/fog/dark_fog','miwu01')
    fog['color']['alpha']=alpha
    backend.ui['images'].append(fog);backend.ui['image_count']+=1
    state=oracle.operation_siren_map_geometry('东北航道A',rows=3,columns=3)
    assert bool(state.unresolved_fog_images) is unresolved
    assert len(state.cells)==9 and backend.swipes==[]

@pytest.mark.parametrize('inherited,unknown',[(0.0,False),(1.0,True),(None,True),(float('nan'),True),(True,True)])
def test_native_parent_canvasgroup_transparency_remains_compatible(inherited,unknown):
    backend,oracle=setup_map()
    fog=make_image(ROOT+'cells/fogs/fog/dark_fog','miwu01')
    fog['color']['alpha']=1.0
    fog['inherited_alpha']=inherited
    backend.ui['images'].append(fog);backend.ui['image_count']+=1
    state=oracle.operation_siren_map_geometry('东北航道A',rows=3,columns=3)
    assert bool(state.unresolved_fog_images) is unknown
    assert len(state.cells)==9 and backend.swipes==[]
