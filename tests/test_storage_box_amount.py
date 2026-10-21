import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('drift',[False,True])
def test_actual_box_use_amount_reports_preview_without_claiming_consumption(drift):
    backend,o,_=host(drift,'storage-box-amount-r38.json')
    d=o.storage_box_amount()
    assert d.name=='克洛希德科技箱T1' and d.rarity==1 and d.quantity==1 and d.remaining_preview==3300
    with pytest.raises(SemanticGateClosed,match='not actionable'):o.click_storage_box_amount('confirm',expected_name=d.name,expected_rarity=1,expected_quantity=1)
    assert not backend.taps

@pytest.mark.parametrize('action',['confirm','cancel','plus','minus'])
@pytest.mark.parametrize('case',['accepted','covered','changed-amount','changed-name','foreign'])
def test_amount_controls_require_full_identity_quantity_and_actual_raycast(action,case):
    backend,o,_=host(fixture='storage-box-amount-r38.json')
    for b in backend.buttons['buttons']:
        if '/ItemInfoUI(Clone)/operate/actions/' in b['path']:b['raycast_top']=True
    for i in backend.ui['images']:
        if '/operate/count/number_panel/' in i['path']:i['raycast_top']=True
    if case=='covered':
        from tests.semantic_support.observer_fixtures import make_button
        backend.buttons['buttons'].append(make_button('Loading(Clone)','OverlayCamera/Overlay/UIOverlay/Loading(Clone)'));backend.buttons['button_count']+=1
    if case=='changed-amount':next(t for t in backend.ui['texts'] if t['path'].endswith('/number_panel/InputField/Text'))['text']='2'
    if case=='changed-name':next(t for t in backend.ui['texts'] if t['path'].endswith('/name_container/name/Text'))['text']='另一个科技箱T1'
    if case=='foreign':backend.foreground='other/.Activity'
    if case=='accepted':
        assert o.click_storage_box_amount(action,expected_name='克洛希德科技箱T1',expected_rarity=1,expected_quantity=1).semantic_id=='storage/box/amount/'+action
        assert len(backend.taps)==1
    else:
        with pytest.raises(SemanticGateClosed):o.click_storage_box_amount(action,expected_name='克洛希德科技箱T1',expected_rarity=1,expected_quantity=1)
        assert not backend.taps
