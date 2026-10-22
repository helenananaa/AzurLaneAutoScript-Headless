from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.contracts import EnhancementDockCandidate
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_text, make_ui

PATH='UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/ships/101104'
COUNT='OverlayCamera/Overlay/UIMain/blur_panel/select_panel/bottom_info/bg_input/count'


@pytest.mark.parametrize('change', [None, 'sprite', 'occupied', 'duplicate', 'covered', 'foreground', 'level'])
def test_meta_selects_the_exact_ship_and_proves_one_selection(change):
    b=FakeBackend([make_button('101104',PATH,raycast_top=change!='covered')])
    b.ui=make_ui([make_text('1/1' if change=='occupied' else '0/1',COUNT),
        make_text('威廉·D·波特',PATH+'/content/info/name_mask/name'),
        make_text('124' if change=='level' else '125',PATH+'/content/dockyard/lv/Text')],
        images=[make_image(PATH+'/content/ship_icon','unknown' if change=='sprite' else 'bote')])
    o=make_oracle(b)
    button=o.read_state().buttons[0]
    candidate=EnhancementDockCandidate(0,101104,'威廉·D·波特',125,button)
    o.enhancement_dock_candidates=Mock(return_value=[candidate,candidate] if change=='duplicate' else [candidate])
    o._enhancement_dock_records=lambda:(o.read_state(),o.read_ui_state())
    if change=='foreground':
        o._foreground_component=Mock(return_value='other/activity')
    def selected():
        b.snapshot['generation']=b.buttons['generation']=b.ui['generation']=11
        b.ui['texts'][0]['text']='<color=#FFFFFFFF>1</color>/1'
    b.on_tap=selected
    if change is None:
        assert o.click_meta_formation_ship(candidate,'bote').semantic_id=='tactical/dock/ship'
        assert len(b.taps)==1
    else:
        with pytest.raises(SemanticGateClosed):
            o.click_meta_formation_ship(candidate,'bote')
        assert not b.taps


@pytest.mark.parametrize('change', [None, 'other-selected', 'sprite', 'count'])
def test_meta_confirmation_owns_only_the_selected_ship(change):
    b=FakeBackend([])
    selected_id='101105' if change=='other-selected' else '101104'
    selected=make_image(PATH.replace('101104',selected_id)+'/content/front/selected/text','status_select')
    b.ui=make_ui([make_text('0/1' if change=='count' else '1/1',COUNT)],images=[
        selected,make_image(PATH+'/content/ship_icon','other' if change=='sprite' else 'bote')])
    o=make_oracle(b)
    o._enhancement_dock_records=lambda:(o.read_state(),o.read_ui_state())
    receipt=Mock()
    def confirm(_):
        b.snapshot['generation']=b.buttons['generation']=b.ui['generation']=11
        return receipt
    o.click=Mock(side_effect=confirm)
    o.meta_precombat_ship_visible=Mock(return_value=True)
    if change is None:
        assert o.confirm_meta_formation_ship(101104,'bote','vanguard') is receipt
        o.click.assert_called_once_with('tactical/dock/confirm')
    else:
        with pytest.raises(SemanticGateClosed):
            o.confirm_meta_formation_ship(101104,'bote','vanguard')
        o.click.assert_not_called()
