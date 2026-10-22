from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui, make_image


def setup():
    root='root/OverlayCamera/Overlay/UIMain/CommanderReserveUI(Clone)/'
    bounds=dict(left=0,top=0,right=1280,bottom=720)
    frame=dict(left=233,top=136,right=1055,bottom=527)
    backend=FakeBackend([make_button('bg',root+'bg',bounds=bounds,raycast_top=None),
                         make_button('max',root+'frame/bg1/max'),
                         make_button('Button',root+'frame/bg1/Button')])
    images=[make_image(root+'bg','white_dot',bounds),make_image(root+'frame','buy_bg',frame),
            make_image('root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/background','commander_bg_1',bounds)]
    for image in images:image['raycast_target']=True
    backend.ui=make_ui([make_text('15',root+'frame/bg1/count/Text'),
                       make_text('17220',root+'frame/bg1/price_all/Text')],images=images)
    oracle=make_oracle(backend)
    oracle.meowfficer_dock_state=Mock(return_value=object())
    def close():
        backend.buttons['buttons']=[];backend.buttons['button_count']=0
        backend.buttons['generation']=11;backend.snapshot['generation']=11
    backend.on_tap=close
    return backend,oracle


def test_close_uses_native_background_bounds_and_advancing_postcondition():
    backend,oracle=setup()
    receipt=oracle.click('meowfficer/buy/close')
    assert receipt.path.endswith('CommanderReserveUI(Clone)/bg')
    assert backend.taps==[(116,332)]
    oracle.meowfficer_dock_state.assert_called_once()


@pytest.mark.parametrize('obscured', ['prompt','foreign','foreground'])
def test_close_rejects_obscured_or_changed_foreground(obscured):
    backend,oracle=setup()
    if obscured=='prompt':
        backend.buttons['buttons'].append(make_button('confirm_btn','root/CommanderMsgBoxUI(Clone)/frame/confirm_btn'))
        backend.buttons['button_count']+=1
    elif obscured=='foreign':
        image=make_image('root/foreign','unknown',dict(left=0,top=0,right=1280,bottom=720))
        image['raycast_target']=True
        backend.ui['images'].append(image);backend.ui['image_count']+=1
    else:
        # Observation remains valid; the last input check sees the change.
        oracle._foreground_component=Mock(side_effect=[backend.foreground]*4+['foreign'])
    with pytest.raises(SemanticGateClosed):oracle.click('meowfficer/buy/close')
    assert backend.taps==[]


def test_meow_buy_underlay_allows_only_actual_award_close():
    backend,oracle=setup()
    backend.buttons['buttons'].append(make_button('close','root/AwardInfoUI(Clone)/items/close'))
    backend.buttons['button_count']+=1
    assert oracle.enabled('reward/award-info/close')
    assert not oracle.enabled('meowfficer/buy/submit')
