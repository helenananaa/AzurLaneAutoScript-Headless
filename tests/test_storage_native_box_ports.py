from types import SimpleNamespace
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.contracts import StorageBoxCandidate
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('fixture',['storage-box-detail-r37.json','storage-box-amount-r38.json','storage-box-equipment-r41.json','storage-box-preserve-r41.json'])
def test_known_foreground_dialogs_do_not_parse_storage_underlay_tabs(fixture):
    _,o,_=host(fixture=fixture)
    assert not o.storage_page_visible()

@pytest.mark.parametrize('drift',[False,True])
def test_native_resource_probes_are_owned_by_selected_full_box_detail(drift):
    backend,o,a=host(drift,'storage-box-detail-r37.json')
    a._storage_box_candidate=StorageBoxCandidate('311','克洛希德科..','30001',1,3301)
    for b in backend.buttons['buttons']:
        if b['path'].endswith('/window/actions/use_one_button'):b['raycast_top']=True
    assert a.appear('BOX_USE')
    for name in ('MATERIAL_CHECK','BOX_AMOUNT_CONFIRM','AMOUNT_PLUS','EQUIP_CONFIRM_2','GET_ITEMS_1'):
        assert not a.appear(name)
    a._fresh_input_oracle=lambda:o
    assert a.click('BOX_USE').semantic_id=='storage/box/detail/use'
    assert len(backend.taps)==1


def test_native_amount_confirm_keeps_use_receipt_for_its_own_equipment_batch():
    backend,o,a=host(fixture='storage-box-amount-r38.json')
    a._storage_box_candidate=StorageBoxCandidate('311','克洛希德科..','30001',1,3301)
    for b in backend.buttons['buttons']:
        if b['path'].endswith('/operate/actions/confirm_button'):b['raycast_top']=True
    a._fresh_input_oracle=lambda:o
    assert a.appear('BOX_AMOUNT_CONFIRM')
    receipt=a.click('BOX_AMOUNT_CONFIRM')
    assert a._storage_box_use_receipt is receipt and a._storage_box_use_quantity==1
    assert len(backend.taps)==1

@pytest.mark.parametrize('batch',[1,2])
def test_equipment_confirmation_is_scoped_to_actual_box_batch(batch):
    backend,o,a=host(fixture='storage-box-equipment-r41.json')
    a._storage_box_candidate=StorageBoxCandidate('311','克洛希德科..','30001',1,3301)
    a._storage_box_use_receipt=SimpleNamespace(generation=o.read_state().generation-10)
    a._storage_box_use_quantity=batch
    for b in backend.buttons['buttons']:
        if b['path'].endswith('/ResolveEquipmentUI(Clone)/main/ok_btn'):b['raycast_top']=True
    a._fresh_input_oracle=lambda:o
    if batch==1:
        assert a.appear('EQUIP_CONFIRM')
        assert a.click('EQUIP_CONFIRM').semantic_id=='storage/box/equipment/confirm-selection'
        assert len(backend.taps)==1
    else:
        with pytest.raises(SemanticGateClosed,match='does not match'):a.click('EQUIP_CONFIRM')
        assert not backend.taps
