import copy
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('drift',[False,True])
def test_actual_bottom_item_opens_information_without_using_it(drift):
    backend,oracle,_=host(drift,'storage-bottom-items-r37.json')
    item=oracle.storage_material_item('311')
    assert item.display_label=='克洛希德科..'
    assert item.quantity==3301 and item.icon_sprite=='30001'
    assert oracle.click_storage_material_item('311',expected_label=item.display_label,expected_icon=item.icon_sprite).semantic_id=='storage/material/inspect/311'
    assert len(backend.taps)==1

@pytest.mark.parametrize('case',['covered','unknown-raycast','duplicate','foreign','offscreen','changed','missing-count','wrong-tab','wrong-owner'])
def test_item_inspection_does_not_guess_identity_or_actionability(case):
    backend,oracle,_=host(fixture='storage-bottom-items-r37.json')
    target=next(b for b in backend.buttons['buttons'] if b['name']=='311')
    if case=='covered':target['raycast_top']=False
    if case=='unknown-raycast':target['raycast_top']=None
    if case=='duplicate':
        backend.buttons['buttons'].append(copy.deepcopy(target));backend.buttons['button_count']+=1
    if case=='foreign':backend.foreground='foreign/.Activity'
    if case=='offscreen':
        target['adb_point']['y']=-100;target['adb_bounds']['top']=-150;target['adb_bounds']['bottom']=-50
    if case=='changed':next(t for t in backend.ui['texts'] if t['path']==target['path']+'/bg/name')['text']='another item'
    if case=='missing-count':backend.ui['texts']=[t for t in backend.ui['texts'] if t['path']!=target['path']+'/bg/icon_bg/count']
    if case=='wrong-tab':
        for t in backend.ui['toggles']:
            if t['name']=='material':t['checked']=False
            if t['name']=='weapon':t['checked']=True
    if case=='wrong-owner':target['path']=target['path'].replace('StoreHouseUI','OtherUI')
    with pytest.raises(SemanticGateClosed):oracle.click_storage_material_item('311',expected_label='克洛希德科..',expected_icon='30001')
    assert not backend.taps
