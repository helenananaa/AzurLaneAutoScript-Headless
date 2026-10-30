"""A shared popup's optional shop classifier must use the leased view."""
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from alas_headless.oracle.surfaces import RESET_SHOP_ROOT, RESET_SHOP_MESSAGE
from tests.test_combat_screenshot_observation import host
from tests.semantic_support.observer_fixtures import (
    make_button, make_buttons, make_snapshot, make_text, make_ui,
)


def popup(backend, *, message, label='确 定', drift=False):
    path=RESET_SHOP_ROOT+'button_container/custom_button_1(Clone)'
    backend.snapshot=make_snapshot(generation=11)
    backend.buttons=make_buttons([make_button('custom_button_1(Clone)',path,raycast_top=None)],generation=11)
    texts=[make_text(message,RESET_SHOP_ROOT+'msg_panel/content'),make_text(label,path+'/pic')]
    if drift:
        texts.reverse()
        backend.buttons['optional_upstream_field']='additive'
    backend.ui=make_ui(texts,generation=11)


@pytest.mark.parametrize('drift',[False,True])
def test_unrelated_shared_prompt_does_not_read_live_shop_pair(drift):
    backend,session,_=host('combat',False)
    popup(backend,message='需要暂时离开大型作战么？',drift=drift)
    session.refresh_frame()
    adapter=session.open()
    adapter.oracle.observation_surface_present=Mock(side_effect=AssertionError('split live optional Msgbox pair'))
    assert adapter._click_priority('POPUP_CONFIRM') is UNHANDLED
    adapter.oracle.observation_surface_present.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('label',['确 定','购买'])
def test_shop_routing_retains_actual_final_message_and_action_checks(label):
    backend,session,_=host('combat',False)
    popup(backend,message=RESET_SHOP_MESSAGE,label=label)
    session.refresh_frame()
    adapter=session.open()
    adapter.oracle.observation_surface_present=Mock(side_effect=AssertionError('split live optional Msgbox pair'))
    if label=='确 定':
        receipt=adapter._click_priority('POPUP_CONFIRM')
        assert receipt.semantic_id=='os/reset/shop'
        assert len(backend.taps)==1
    else:
        with pytest.raises(SemanticGateClosed):
            adapter._click_priority('POPUP_CONFIRM')
        assert not backend.taps
