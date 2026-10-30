"""Commission tab input uses one fresh typed frame rather than split live reads."""
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_combat_screenshot_observation import host
from tests.semantic_support.observer_fixtures import (
    make_button,make_buttons,make_image,make_snapshot,make_ui,
)


def tab(backend,*,mode='urgent',generation=11,blocked=False,drift=False):
    root='root/UICamera/Canvas/UIMain/EventUI(Clone)/'
    backend.snapshot=make_snapshot(generation=generation)
    backend.buttons=make_buttons([make_button('back_btn',root+'blur_panel/adapt/top/back_btn')],generation=generation)
    name,sprite=('urgency_btn','toggle_jinji_unsel 1') if mode=='urgent' else ('daily_btn','toggle_meiri_unsel 1')
    image=make_image(root+'blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/'+name+'/Image',sprite)
    image.update(raycast_target=True,raycast_top=not blocked)
    backend.ui=make_ui([],images=[image],generation=generation)
    if drift:
        backend.ui['optional_metadata']='additive'


@pytest.mark.parametrize('mode',['daily','urgent'])
@pytest.mark.parametrize('drift',[False,True])
def test_tab_click_uses_fresh_frame_despite_split_live_reader(mode,drift):
    backend,session,_=host('combat',False)
    tab(backend,mode=mode,drift=drift)
    session.refresh_frame()
    session.begin_commission()
    session.open().oracle.click_image=Mock(side_effect=SemanticGateClosed('button and image snapshots are not coherent'))
    receipt=session.click('COMMISSION_'+mode.upper())
    assert receipt.semantic_id=='commission/nav/'+mode
    assert receipt.generation==11 and len(backend.taps)==1


def test_tab_click_rejects_newly_covered_target_after_old_positive_screenshot():
    backend,session,_=host('combat',False)
    tab(backend)
    session.refresh_frame()
    session.begin_commission()
    tab(backend,generation=12,blocked=True)
    with pytest.raises(SemanticGateClosed):
        session.click('COMMISSION_URGENT')
    assert not backend.taps
