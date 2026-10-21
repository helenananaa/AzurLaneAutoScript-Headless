import pytest
from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('drift',[False,True])
@pytest.mark.parametrize('fixture',['storage-return-probe-r56.json','storage-return-main-r56.json'])
def test_actual_storage_return_does_not_admit_unrelated_mission_ship_probe(drift,fixture):
    backend,o,a=host(drift,fixture)
    assert o.storage_material_visible() if 'probe' in fixture else o.main_page_visible()
    assert not a.appear('GET_SHIP')
    with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):a.click('GET_SHIP')
    assert not backend.taps


def test_storage_under_unreviewed_dialog_keeps_ship_probe_unavailable():
    backend,o,a=host(fixture='storage-return-probe-r56.json')
    from tests.semantic_support.observer_fixtures import make_button
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'));backend.buttons['button_count']+=1
    with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):a.appear('GET_SHIP')
    assert not backend.taps
