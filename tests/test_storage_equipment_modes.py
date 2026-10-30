import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_equipment_mode_is_present_even_before_new_button_raycast_export(drift):
    backend, _, adapter = host(drift,'storage-equipment-warehouse-20261027.json')
    assert adapter.appear('DISASSEMBLE') is True
    assert adapter.appear('DISASSEMBLE_CANCEL') is False
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        adapter.click('DISASSEMBLE')
    assert not backend.taps


@pytest.mark.parametrize('damage', ['label', 'duplicate', 'foreign', 'covered'])
def test_equipment_entry_preserves_unique_owned_actionable_control(damage):
    backend, oracle, adapter = host(fixture='storage-equipment-warehouse-20261027.json')
    control=next(b for b in backend.buttons['buttons'] if b['name']=='dispos')
    control['raycast_top']=damage!='covered'
    if damage=='label':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/bottom_back/dispos/Image'))['text']='购买'
    elif damage=='duplicate':
        backend.buttons['buttons'].append(dict(control));backend.buttons['button_count']+=1
    elif damage=='foreign':
        backend.foreground='other/.Activity'
    adapter._fresh_input_oracle=lambda:oracle
    with pytest.raises(SemanticGateClosed):adapter.click('DISASSEMBLE')
    assert not backend.taps


def test_exact_native_batch_entry_is_navigation_only():
    backend, oracle, adapter = host(fixture='storage-equipment-warehouse-20261027.json')
    next(b for b in backend.buttons['buttons'] if b['name']=='dispos')['raycast_top']=True
    adapter._fresh_input_oracle=lambda:oracle
    assert adapter.click('DISASSEMBLE').semantic_id=='storage/equipment/disassemble-enter'
    assert len(backend.taps)==1

    with pytest.raises(SemanticGateClosed):
        oracle.click_storage_equipment_control('DISASSEMBLE_CONFIRM')
    assert len(backend.taps)==1


def test_actual_selection_frame_has_cancel_and_rejects_offscreen_batch_entry():
    backend,oracle,adapter=host(fixture='storage-equipment-selection-20261027.json')
    assert adapter.appear('DISASSEMBLE_CANCEL') is True
    assert adapter.appear('DISASSEMBLE') is False
    assert adapter.appear('EQUIPMENT_FILTER_CONFIRM') is False
    adapter._fresh_input_oracle=lambda:oracle
    with pytest.raises(SemanticGateClosed):adapter.click('DISASSEMBLE')
    with pytest.raises(SemanticGateClosed):adapter.click('EQUIPMENT_FILTER')
    assert not backend.taps


def test_selection_filter_requires_fresh_owned_raycast_point():
    backend,oracle,adapter=host(fixture='storage-equipment-selection-20261027.json')
    target=next(b for b in backend.buttons['buttons'] if b['name']=='index_button')
    target['raycast_top']=True
    adapter._fresh_input_oracle=lambda:oracle
    assert adapter.click('EQUIPMENT_FILTER').semantic_id=='storage/equipment/filter-open'
    assert len(backend.taps)==1


def test_actual_session_gate_and_fresh_frame_allow_only_reviewed_batch_entry():
    from alas_headless import AlasSemanticSession
    from alas_headless.adapter import semantic_runtime_fingerprint_sha256
    from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
    backend,_,_=host(fixture='storage-equipment-warehouse-20261027.json')
    next(b for b in backend.buttons['buttons'] if b['name']=='dispos')['raycast_top']=True
    revision=backend.snapshot['driver_revision']
    handle=FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=backend.snapshot['package'],component=backend.foreground,
        driver_revision=revision,required_primary_abi='x86_64'))
    handle.pid=backend.snapshot['pid'];handle.observer_request=backend.request
    handle.foreground_component=backend.foreground_component
    handle.tap=backend.tap;handle.swipe=backend.swipe
    session=AlasSemanticSession(driver_revision=revision,runtime_handle=handle)
    try:
        session.open();session.refresh_frame()
        assert session.appear('DISASSEMBLE') is True
        receipt=session.click('DISASSEMBLE')
        assert receipt.semantic_id=='storage/equipment/disassemble-enter'
        assert len(backend.taps)==1
    finally:
        session.close()
