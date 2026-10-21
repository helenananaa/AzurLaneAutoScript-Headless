from types import SimpleNamespace
from unittest.mock import Mock
import dataclasses
import pytest
from alas_headless import AlasSemanticSession, AlasSemanticUnmapped
from alas_headless.oracle.storage import StorageBoxAmountActionReceipt
from alas_headless.oracle.contracts import ActionReceipt, Point, Bounds
from tests.test_game_tips_loading_presence import host
from tests.test_alas_config_branch_compatibility import method

@pytest.mark.parametrize('drift',[False,True])
def test_actual_confirmation_receipt_retains_fresh_selected_count(drift):
    backend,o,a=host(drift,'storage-box-amount-r38.json')
    target=next(b for b in backend.buttons['buttons'] if b['path'].endswith('/operate/actions/confirm_button'))
    target['raycast_top']=True
    receipt=o.click_storage_box_amount('confirm',expected_name='克洛希德科技箱T1',expected_rarity=1,expected_quantity=1)
    assert receipt.quantity==1 and receipt.remaining_preview==3300
    assert receipt.item_name=='克洛希德科技箱T1'
    assert dataclasses.asdict(receipt)['quantity']==1
    assert len(backend.taps)==1


def confirmed(quantity):
    return StorageBoxAmountActionReceipt('storage/box/amount/confirm',20,Point(1,1),Bounds(0,0,2,2),'typed-control',quantity=quantity)

@pytest.mark.parametrize('stale,actual,semantic',[(15,15,True),(16,15,True),(15,14,True),(16,15,False)])
def test_original_single_box_loop_counts_fresh_confirmation_and_keeps_pixel_mode(stale,actual,semantic):
    names=('MATERIAL_CHECK BOX_USE GET_ITEMS_1 GET_ITEMS_2 EQUIPMENT_FULL BOX_AMOUNT_CONFIRM EQUIP_CONFIRM EQUIP_CONFIRM_2 MATERIAL_ENTER').split()
    namespace={n:n for n in names}
    run=method('module/storage/storage.py','StorageHandler','_storage_use_one_box',**namespace)
    session=AlasSemanticSession.__new__(AlasSemanticSession)
    receipt=confirmed(actual)
    device=SimpleNamespace(click=Mock(return_value=receipt))
    if semantic:device.semantic_adapter=session
    state={'phase':None}
    def loop():
        for phase in ('amount','equipment','confirm','material'):
            state['phase']=phase
            yield None
    h=SimpleNamespace(device=device,loop=loop,
        interval_clear=Mock(),interval_reset=Mock(),
        _storage_in_material=lambda **_:state['phase']=='material',
        appear=lambda *_,**__:False,
        match_template_color=lambda name,**_:state['phase']=='amount' and name=='BOX_AMOUNT_CONFIRM',
        appear_then_click=lambda name,**_:((state['phase']=='equipment' and name=='EQUIP_CONFIRM') or (state['phase']=='confirm' and name=='EQUIP_CONFIRM_2')),
        _handle_use_box_amount=Mock(return_value=stale))
    assert run(h,object(),15)==(actual if semantic else stale)
    h._handle_use_box_amount.assert_called_once_with(15)
    device.click.assert_called_once_with('BOX_AMOUNT_CONFIRM')

@pytest.mark.parametrize('receipt',[None,ActionReceipt('storage/box/amount/confirm',20,Point(1,1),Bounds(0,0,2,2),'x'),confirmed(0),dataclasses.replace(confirmed(1),semantic_id='storage/box/amount/plus')])
def test_missing_or_nonconfirmation_receipt_never_counts_as_consumption(receipt):
    s=AlasSemanticSession.__new__(AlasSemanticSession)
    with pytest.raises(AlasSemanticUnmapped):s.storage_box_confirmed_quantity(receipt)



def test_confirmed_quantity_accepts_compatible_receipt_shape_and_additive_fields():
    s=AlasSemanticSession.__new__(AlasSemanticSession)
    receipt=SimpleNamespace(semantic_id='storage/box/amount/confirm',quantity=15,new_metadata={'future':True})
    assert s.storage_box_confirmed_quantity(receipt)==15
