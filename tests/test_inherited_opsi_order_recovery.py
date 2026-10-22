import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('drift',[False,True])
def test_inherited_order_panel_owns_native_discovery_without_an_os_task_context(drift):
    backend,o,a=host(drift,'opsi-order-inherited-r56.json')
    assert o.operation_siren_order_panel_visible()
    assert not a.appear('EXERCISE_CHECK')
    assert not a.appear('GOTO_MAIN')
    with pytest.raises(SemanticGateClosed):a.click('GOTO_MAIN')
    with pytest.raises(SemanticGateClosed):o.click('os/order/back')
    assert not backend.taps

@pytest.mark.parametrize('case',['ready','loading','foreign','wrong-owner','wrong-sprite'])
def test_order_back_uses_actual_measured_hit_and_keeps_blockers(case):
    backend,o,a=host(fixture='opsi-order-inherited-r56.json')
    b=next(b for b in backend.buttons['buttons'] if b['path'].endswith('/SVOrderPanel(Clone)/adapt/back'))
    b['adb_point']={'x':147.,'y':80.};b['raycast_top']=True
    if case=='loading':
        from tests.semantic_support.observer_fixtures import make_button
        backend.buttons['buttons'].append(make_button('Loading(Clone)','OverlayCamera/Overlay/UIOverlay/Loading(Clone)'));backend.buttons['button_count']+=1
    if case=='foreign':backend.foreground='other/.Activity'
    if case=='wrong-owner':b['path']=b['path'].replace('SVOrderPanel','UnknownPanel')
    if case=='wrong-sprite':next(i for i in backend.ui['images'] if i['path'].endswith('/SVOrderPanel(Clone)/adapt/back'))['sprite']='unknown'
    a._fresh_input_oracle=lambda:o
    if case=='ready':
        assert a.appear('GOTO_MAIN')
        assert a.click('GOTO_MAIN').semantic_id=='os/order/back'
        assert backend.taps==[(147,80)]
    else:
        with pytest.raises(SemanticGateClosed):o.click_operation_siren_order_back()
        assert not backend.taps


@pytest.mark.parametrize('case',['missing-back-image','duplicate-back-button'])
def test_complete_button_ownership_and_local_back_metadata_are_required(case):
    backend,o,a=host(fixture='opsi-order-inherited-r56.json')
    if case=='missing-back-image':
        backend.ui['images']=[i for i in backend.ui['images'] if not i['path'].endswith('/SVOrderPanel(Clone)/adapt/back')]
        backend.ui['image_count']=len(backend.ui['images'])
    else:
        import copy
        backend.buttons['buttons'].append(copy.deepcopy(next(b for b in backend.buttons['buttons'] if b['name']=='back')))
        backend.buttons['button_count']+=1
    with pytest.raises(SemanticGateClosed):o.operation_siren_order_panel_visible()
    assert not backend.taps
