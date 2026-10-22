from types import SimpleNamespace
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.contracts import StorageBoxCandidate
from tests.test_game_tips_loading_presence import host


def test_owned_disassembly_wait_yields_native_loop_but_never_authorizes_repeat():
    backend,o,a=host(fixture='storage-box-destroy-loading-r50.json')
    a._storage_box_candidate=StorageBoxCandidate('311','克洛希德科..','30001',1,3299)
    a._storage_box_use_receipt=SimpleNamespace(generation=o.read_state().generation-20)
    a._storage_box_use_quantity=1
    a._storage_box_equipment_receipt=SimpleNamespace(generation=o.read_state().generation-10)
    a._storage_box_destroy_receipt=SimpleNamespace(generation=o.read_state().generation-5)
    a._fresh_input_oracle=lambda:o
    for name in ('MATERIAL_CHECK','GET_ITEMS_1','BOX_AMOUNT_CONFIRM','EQUIP_CONFIRM','EQUIP_CONFIRM_2'):
        assert not a.appear(name)
    with pytest.raises(SemanticGateClosed):a.click('EQUIP_CONFIRM_2')
    assert not backend.taps


def test_loading_after_info_use_entry_waits_before_any_box_consumption():
    backend,o,a=host(fixture='storage-box-detail-loading-r53.json')
    a._storage_box_candidate=StorageBoxCandidate('311','克洛希德科..','30001',1,3298)
    a._fresh_input_oracle=lambda:o
    for name in ('MATERIAL_CHECK','GET_ITEMS_1','BOX_USE','BOX_AMOUNT_CONFIRM','EQUIP_CONFIRM_2'):
        assert not a.appear(name)
    with pytest.raises(SemanticGateClosed):a.click('BOX_USE')
    assert not backend.taps
