from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_text, make_ui

ROOT = 'OverlayCamera/Overlay/UIMain/PreCombatUI(Clone)/'
PATH = ROOT+'adapt/middle/mask/GridFrame/vanguard_1/tip'


@pytest.mark.parametrize('invalid', [None, 'occupied', 'sprite', 'blocked', 'duplicate', 'foreground', 'owner'])
def test_empty_meta_slot_opens_only_reviewed_empty_preparation(invalid):
    b = FakeBackend([make_button('tip', PATH, raycast_top=None)])
    if invalid != 'owner':
        b.buttons['buttons'].append(make_button('list_btn', 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)/list_btn'))
        b.buttons['button_count'] += 1
    b.ui = make_ui([make_text('0', ROOT+'adapt/middle/gear_score/'+side+'/Text')
                   for side in ('main', 'vanguard')], images=[make_image(PATH, 'add_icon')])
    b.ui['images'][0]['raycast_target'] = True
    b.ui['images'][0]['flags'] |= 0x200
    if invalid == 'occupied':
        b.ui['texts'][0]['text'] = '123'
    if invalid == 'sprite':
        b.ui['images'][0]['sprite'] = 'unknown'
    if invalid == 'blocked':
        b.buttons['buttons'].append(make_button('confirm', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    if invalid == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][0]))
        b.buttons['button_count'] += 1
    o = make_oracle(b)
    o.daily_precombat_visible = Mock(return_value=True)
    o._enhancement_dock_records = Mock(return_value='coherent dock')
    if invalid == 'foreground':
        o._foreground_component = Mock(return_value='other/activity')
    if invalid is None:
        assert o.click_meta_precombat_empty_vanguard().semantic_id == 'meta/precombat/vanguard/add'
        assert len(b.taps) == 1
        o._enhancement_dock_records.assert_called_once()
    else:
        with pytest.raises(SemanticGateClosed):
            o.click_meta_precombat_empty_vanguard()
        assert not b.taps
        o._enhancement_dock_records.assert_not_called()


def test_empty_slot_uses_exact_image_interior_instead_of_bottom_pivot():
    b = FakeBackend([make_button('tip', PATH, x=358.8, y=473.8, raycast_top=None),
        make_button('list_btn', 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)/list_btn')])
    bounds = {'left':304.8, 'top':353.133, 'right':412.8, 'bottom':473.8}
    b.buttons['buttons'][0]['adb_bounds'] = bounds
    b.ui = make_ui([make_text('0', ROOT+'adapt/middle/gear_score/'+side+'/Text')
                   for side in ('main', 'vanguard')], images=[make_image(PATH, 'add_icon', bounds)])
    b.ui['images'][0]['raycast_target'] = True
    b.ui['images'][0]['flags'] |= 0x200
    o = make_oracle(b)
    o.daily_precombat_visible = Mock(return_value=True)
    o._enhancement_dock_records = Mock(return_value='coherent dock')
    receipt = o.click_meta_precombat_empty_vanguard()
    assert b.taps == [(359, 413)]
    assert receipt.bounds.contains(receipt.point)


@pytest.mark.parametrize('companion', ['bote', 'other'])
def test_empty_main_preserves_the_requested_existing_vanguard(companion):
    path=PATH.replace('vanguard_1','main_1')
    b=FakeBackend([make_button('tip',path,raycast_top=None),
        make_button('list_btn','UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)/list_btn')])
    image=make_image(path,'add_icon')
    image['raycast_target']=True
    image['flags']|=0x200
    b.ui=make_ui([make_text('0',ROOT+'adapt/middle/gear_score/main/Text'),
                 make_text('5049',ROOT+'adapt/middle/gear_score/vanguard/Text')],images=[image,
        make_image(ROOT+'adapt/middle/HeroContainer/heroInfo(Clone)/bote_root/mouseChild','text01_1')])
    o=make_oracle(b)
    o.daily_precombat_visible=Mock(return_value=True)
    o._enhancement_dock_records=Mock(return_value='coherent dock')
    if companion=='bote':
        assert o.click_meta_precombat_empty_main(companion).semantic_id=='meta/precombat/main/add'
        assert len(b.taps)==1
    else:
        with pytest.raises(SemanticGateClosed,match='existing vanguard changed'):
            o.click_meta_precombat_empty_main(companion)
        assert not b.taps
