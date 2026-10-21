import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('drift',[False,True])
def test_equipment_box_detail_uses_full_name_and_keeps_unknown_raycast_closed(drift):
    backend,o,_=host(drift,'storage-box-detail-r37.json')
    d=o.storage_box_detail()
    assert d.name=='克洛希德科技箱T1' and d.rarity==1 and d.quantity==3301
    with pytest.raises(SemanticGateClosed,match='not actionable'):
        o.click_storage_box_detail('use',expected_name=d.name,expected_rarity=1)
    assert not backend.taps

@pytest.mark.parametrize('case',['changed-name','non-box','covered','wrong-rarity','foreign','accepted'])
def test_detail_action_requires_its_actual_identity_and_blockers(case):
    backend,o,_=host(fixture='storage-box-detail-r37.json')
    for b in backend.buttons['buttons']:
        if b['path'].endswith('/ItemInfoUI(Clone)/window/actions/use_one_button'):b['raycast_top']=True
    if case in ('changed-name','non-box'):
        next(t for t in backend.ui['texts'] if t['path'].endswith('/name_container/name/Text'))['text']=('另一个科技箱T1' if case=='changed-name' else '红尖尖')
    if case=='covered':
        from tests.semantic_support.observer_fixtures import make_button
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'));backend.buttons['button_count']+=1
    if case=='foreign':backend.foreground='other/.Activity'
    if case=='accepted':
        assert o.click_storage_box_detail('use',expected_name='克洛希德科技箱T1',expected_rarity=1).semantic_id=='storage/box/detail/use'
        assert len(backend.taps)==1
    else:
        with pytest.raises(SemanticGateClosed):o.click_storage_box_detail('use',expected_name='克洛希德科技箱T1',expected_rarity=2 if case=='wrong-rarity' else 1)
        assert not backend.taps
