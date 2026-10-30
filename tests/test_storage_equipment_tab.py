import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


def material_host(drift=False):
    backend, oracle, adapter = host(drift, 'storage-material-warehouse-20261027.json')
    # This fixture is a later live pair rather than an immutable screenshot.
    # Model a static observer turn explicitly; keep the captured raw fixture
    # intact instead of cycling its older state after the newer UI endpoint.
    generation = max(backend.snapshot['generation'], backend.buttons['generation'],
                     backend.ui['generation'])
    for record in (backend.snapshot, backend.buttons, backend.ui):
        record['generation'] = generation
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_original_equipment_mode_probes_are_absent_on_observed_material_page(drift):
    backend, oracle, adapter = material_host(drift)
    assert oracle.storage_material_visible()
    assert adapter.appear('DISASSEMBLE') is False
    assert adapter.appear('DISASSEMBLE_CANCEL') is False
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        adapter.click('EQUIPMENT_ENTER')
    assert not backend.taps


@pytest.mark.parametrize('case', ['accepted', 'covered', 'foreign', 'duplicate'])
def test_native_equipment_enter_requires_unique_top_typed_weapon_tab(case):
    backend, oracle, adapter = material_host()
    weapon = next(t for t in backend.ui['toggles'] if t['name'] == 'weapon')
    weapon['raycast_top'] = case != 'covered'
    if case == 'foreign':
        backend.foreground = 'other/.Activity'
    if case == 'duplicate':
        backend.ui['toggles'].append(dict(weapon))
        backend.ui['toggle_count'] += 1
    adapter._fresh_input_oracle = lambda: oracle
    if case == 'accepted':
        receipt = adapter.click('EQUIPMENT_ENTER')
        assert receipt.semantic_id == 'storage/tab/weapon'
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            adapter.click('EQUIPMENT_ENTER')
        assert not backend.taps


def test_original_session_admits_reviewed_storage_edge_and_keeps_frame_input_proof():
    from alas_headless import AlasSemanticSession
    from alas_headless.adapter import semantic_runtime_fingerprint_sha256
    from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
    backend, _, _ = material_host()
    next(t for t in backend.ui['toggles'] if t['name'] == 'weapon')['raycast_top'] = True
    component = backend.foreground
    revision = backend.snapshot['driver_revision']
    handle = FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=backend.snapshot['package'],component=component,
        driver_revision=revision,required_primary_abi='x86_64'))
    handle.pid = backend.snapshot['pid']
    handle.observer_request = backend.request
    handle.foreground_component = backend.foreground_component
    handle.tap = backend.tap
    handle.swipe = backend.swipe
    session = AlasSemanticSession(driver_revision=revision,runtime_handle=handle)
    try:
        session.open()
        session.refresh_frame()
        receipt = session.click('EQUIPMENT_ENTER')
        assert receipt.semantic_id == 'storage/tab/weapon'
        assert len(backend.taps) == 1
    finally:
        session.close()


def test_actual_already_selected_equipment_tab_is_not_replayed_for_missing_mode():
    backend, oracle, adapter = host(fixture='storage-equipment-warehouse-20261027.json')
    adapter._fresh_input_oracle = lambda: oracle
    with pytest.raises(SemanticGateClosed, match='already selected'):
        adapter.click('EQUIPMENT_ENTER')
    assert not backend.taps
