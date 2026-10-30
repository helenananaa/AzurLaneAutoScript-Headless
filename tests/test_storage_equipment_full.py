"""The native StorageFull branch closes only its exact owned modal."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.contracts import StorageBoxCandidate
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button

ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/'


def owned(drift=False):
    backend, oracle, adapter = host(drift, 'research-equipment-full-20261027.json')
    adapter._storage_box_candidate = StorageBoxCandidate('311', '克洛希德科..', '30001', 1, 3295)
    adapter._storage_box_use_receipt = SimpleNamespace(
        semantic_id='storage/box/amount/confirm', generation=4090)
    adapter._fresh_input_oracle = lambda: oracle
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_captured_full_modal_yields_to_original_equipment_full_branch(drift):
    backend, oracle, adapter = owned(drift)
    assert oracle.storage_equipment_full_prompt()[0] == 4098
    for probe in ('BOX_USE', 'MATERIAL_CHECK', 'BOX_AMOUNT_CONFIRM', 'GET_ITEMS_1', 'EQUIP_CONFIRM_2'):
        assert adapter._storage_box_resource_present(probe) is False
    assert adapter._storage_box_resource_present('EQUIPMENT_FULL') is True
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        adapter.click('MATERIAL_ENTER')
    assert not backend.taps


def material_after(backend):
    data = json.loads((Path(__file__).parent/'fixtures/storage-material-page-r33.json').read_text(encoding='utf-8'))
    for kind in ('snapshot', 'buttons', 'ui'):
        record = copy.deepcopy(data[kind])
        for key in ('package', 'pid', 'driver_revision', 'scene_handle'):
            if key in record and key in backend.snapshot:
                record[key] = backend.snapshot[key]
        record['generation'] = 4099
        setattr(backend, kind, record)


def test_original_material_enter_closes_one_verified_button_then_material_postcondition():
    backend, oracle, adapter = owned()
    close = next(b for b in backend.buttons['buttons'] if b['path'] == ROOT+'window/top/btnBack')
    close['raycast_top'] = True
    backend.on_tap = lambda: material_after(backend)
    receipt = adapter.click('MATERIAL_ENTER')
    assert receipt.semantic_id == 'storage/equipment-full/close'
    assert receipt.path == ROOT+'window/top/btnBack'
    assert len(backend.taps) == 1
    assert oracle.storage_material_visible()


@pytest.mark.parametrize('damage', ['covered', 'duplicate-close', 'wrong-label', 'foreign', 'no-proof', 'old-proof', 'foreign-modal'])
def test_full_close_requires_current_identity_ownership_and_unique_top_target(damage):
    backend, _, adapter = owned()
    close = next(b for b in backend.buttons['buttons'] if b['path'] == ROOT+'window/top/btnBack')
    close['raycast_top'] = damage != 'covered'
    if damage == 'duplicate-close':
        backend.buttons['buttons'].append(copy.deepcopy(close))
        backend.buttons['button_count'] += 1
    elif damage == 'wrong-label':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/custom_button_1(Clone)/pic'))['text'] = '购买'
    elif damage == 'foreign':
        backend.foreground = 'other/.Activity'
    elif damage == 'no-proof':
        adapter._storage_box_use_receipt.semantic_id = 'unrelated'
    elif damage == 'old-proof':
        adapter._storage_box_use_receipt.generation = 4098
    elif damage == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('confirm_btn', 'OverlayCamera/Overlay/UIMain/DestoryConfirmWindow(Clone)/window/confirm_btn'))
        backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        adapter.click('MATERIAL_ENTER')
    assert not backend.taps


def test_missing_postcondition_never_replays_an_accepted_close():
    backend, oracle, adapter = owned()
    next(b for b in backend.buttons['buttons'] if b['path'] == ROOT+'window/top/btnBack')['raycast_top'] = True
    oracle._sleep = lambda _: None
    with pytest.raises(SemanticGateClosed, match='has not returned'):
        adapter.click('MATERIAL_ENTER')
    assert len(backend.taps) == 1


def test_close_uses_new_live_postcondition_after_input_invalidates_its_frame():
    from alas_headless.adapter import StaleFrameError
    from alas_headless.adapter.frame import _FrameBoundSemanticOracle
    backend, oracle, adapter = owned()
    next(b for b in backend.buttons['buttons'] if b['path'] == ROOT+'window/top/btnBack')['raycast_top'] = True
    valid = [True]
    def guard():
        if not valid[0]:
            raise StaleFrameError()
    frame = _FrameBoundSemanticOracle(
        backend.request, backend.foreground_component, backend.tap,
        oracle.fingerprint, frame_guard=guard, sleep=lambda _: None)
    adapter._frame_observation_oracle = lambda: frame
    adapter._fresh_input_oracle = lambda: frame
    def accepted():
        valid[0] = False
        material_after(backend)
    backend.on_tap = accepted
    receipt = adapter.click('MATERIAL_ENTER')
    assert receipt.semantic_id == 'storage/equipment-full/close'
    assert len(backend.taps) == 1
    assert oracle.storage_material_visible()
