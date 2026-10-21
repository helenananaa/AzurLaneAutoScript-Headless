from types import SimpleNamespace
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from alas_headless.adapter.semantic.contracts import StorageBoxCandidate

@pytest.mark.parametrize('case',['accepted','unknown-raycast','wrong-title','foreign','no-selection','old-selection'])
def test_final_disassembly_is_tied_to_owned_box_batch_and_exact_fresh_control(case):
    backend,o,a=host(fixture='storage-box-destroy-r46.json')
    a._storage_box_candidate=StorageBoxCandidate('311','克洛希德科..','30001',1,3300)
    a._storage_box_use_receipt=SimpleNamespace(generation=o.read_state().generation-20)
    a._storage_box_use_quantity=1
    a._storage_box_equipment_receipt=SimpleNamespace(generation=o.read_state().generation-10)
    if case!='unknown-raycast':
        next(b for b in backend.buttons['buttons'] if b['name']=='destroy_button')['raycast_top']=True
    if case=='wrong-title':next(t for t in backend.ui['texts'] if t['path'].endswith('/destroy_confirm/got/title'))['text']='unknown'
    if case=='foreign':backend.foreground='other/.Activity'
    if case=='no-selection':a._storage_box_equipment_receipt=None
    if case=='old-selection':a._storage_box_equipment_receipt=SimpleNamespace(generation=o.read_state().generation)
    a._fresh_input_oracle=lambda:o
    if case=='accepted':
        assert a.appear('EQUIP_CONFIRM_2')
        assert a.click('EQUIP_CONFIRM_2').semantic_id=='storage/box/equipment/confirm'
        assert len(backend.taps)==1
    else:
        with pytest.raises(SemanticGateClosed):a.click('EQUIP_CONFIRM_2')
        assert not backend.taps


def test_reset_releases_box_proofs_before_unrelated_task_admission():
    _,o,a=host(fixture='storage-material-page-r33.json')
    a._storage_box_candidate=object();a._storage_box_use_receipt=object();a._storage_box_equipment_receipt=object()
    a.reset_task_state()
    assert a._storage_box_candidate is None and a._storage_box_use_receipt is None and a._storage_box_equipment_receipt is None
    assert a.appear('STORAGE_CHECK')
