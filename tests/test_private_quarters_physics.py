import copy
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_ui, make_oracle

BODY = 'xinzexi_noshoes(Clone)/all/Bip001/Bip001 Pelvis/Bip001 Spine/Bip001 Spine1/BodyCollider'


def backend():
    b = FakeBackend([make_button('btn_back','UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/base/btn_back')])
    b.ui = make_ui([])
    b.ui['private_quarters_physics'] = {
        'schema':'alas-headless.private-colliders/v1', 'status':1, 'truncated':False,
        'error_count':0, 'camera_path':'BackYardMainCamera', 'colliders':[
            {'name':'BodyCollider','path':BODY,'instance_id':-31,'is_trigger':False,'truncated':False,
             'world_center':[0,1,1], 'extents':[.2,.5,.2], 'screen':[600.2,400.1,1],
             'input_point':[600,400], 'raycast_top':True, 'ui_clear':True, 'nearest_id':-31}]}
    return b


def test_input_uses_verified_integer_physics_point_without_fake_ui_bounds():
    b = backend();o = make_oracle(b)
    receipt = o.click('private-quarters/character/new-jersey')
    assert receipt.collider_id == -31 and receipt.path == BODY
    assert not hasattr(receipt, 'bounds')
    assert len(b.taps) == 1


def test_native_target_presence_reads_exact_visible_collider():
    b = backend()
    assert make_oracle(b).private_quarters_new_jersey_visible()
    b.ui['private_quarters_physics']['colliders'][0]['screen'] = [600,400,-1]
    assert not make_oracle(b).private_quarters_new_jersey_visible()
    b.ui['private_quarters_physics']['colliders'][0]['path'] = 'another-character/BodyCollider'
    with pytest.raises(SemanticGateClosed, match='absent or ambiguous'):
        make_oracle(b).private_quarters_new_jersey_visible()
    assert b.taps == []


@pytest.mark.parametrize('field,value', [('raycast_top',False),('raycast_top',None),
    ('ui_clear',False),('ui_clear',None),('nearest_id',42),('input_point',None),
    ('input_point',[600.5,400]),('screen',None),('screen',[600,400,-1])])
def test_unqualified_physics_never_emits_input(field,value):
    b = backend();b.ui['private_quarters_physics']['colliders'][0][field]=value
    with pytest.raises(SemanticGateClosed):make_oracle(b).click_private_quarters_new_jersey_body()
    assert b.taps == []


@pytest.mark.parametrize('field,value', [('status',0),('status',2),('status',True),
    ('truncated',True),('error_count',1)])
def test_unavailable_or_incomplete_set_is_not_an_empty_safe_scene(field,value):
    b=backend();b.ui['private_quarters_physics'][field]=value;o=make_oracle(b)
    with pytest.raises(SemanticGateClosed):o.private_quarters_physics()
    assert b.taps == []
    assert o.click_private_quarters_room_back().semantic_id == 'private-quarters/room/back'


def test_duplicate_collider_ids_rejected_but_additive_metadata_tolerated():
    b=backend();b.ui['private_quarters_physics']['new_metadata']='compatible'
    assert len(make_oracle(b).private_quarters_physics().colliders)==1
    rows=b.ui['private_quarters_physics']['colliders'];rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(SemanticGateClosed,match='ambiguous'):make_oracle(b).private_quarters_physics()


@pytest.mark.parametrize('field,value', [('world_center',[0,float('nan'),1]),
    ('extents',[1,-1,1]),('screen',[1,2]),('input_point',[True,400])])
def test_malformed_geometry_never_becomes_an_input(field,value):
    b=backend();b.ui['private_quarters_physics']['colliders'][0][field]=value
    with pytest.raises(SemanticGateClosed):make_oracle(b).click_private_quarters_new_jersey_body()
    assert b.taps == []


def test_reviewed_room_receiver_is_allowed_but_other_ui_modes_are_not():
    b=backend();row=b.ui['private_quarters_physics']['colliders'][0]
    row.update(ui_clear=False,ui_top_path='UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/POVControl/Move')
    receipt=make_oracle(b).click_private_quarters_new_jersey_body()
    assert receipt.ui_receiver.endswith('/POVControl/Move')
    b.buttons['buttons'].append(make_button('gift','UICamera/Canvas/UIMain/Dorm3dGiftUI(Clone)/buy'))
    b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):make_oracle(b).click_private_quarters_new_jersey_body()
    assert len(b.taps)==1


def test_unknown_ui_receiver_is_not_treated_as_room_touch_layer():
    b=backend();b.ui['private_quarters_physics']['colliders'][0].update(ui_clear=False,ui_top_path='other/Move')
    with pytest.raises(SemanticGateClosed):make_oracle(b).click_private_quarters_new_jersey_body()
    assert b.taps==[]
