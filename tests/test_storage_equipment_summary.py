"""Native selection-to-summary boundary; final destruction is not authorized here."""
from dataclasses import replace
import copy

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.storage import StorageEquipmentSelectionReceipt
from alas_headless.oracle.contracts import ActionReceipt
from tests.test_game_tips_loading_presence import host
from tests.test_storage_equipment_selection import session_host, selected_marker, COUNT


def advance(backend):
    for payload in (backend.snapshot, backend.buttons, backend.ui): payload['generation'] += 1


def set_surface(backend, fixture):
    """Controlled widget model: retain this fake process, not a stitched live receipt."""
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parent/'fixtures'/fixture).read_bytes())
    previous = backend.snapshot
    for key in ('snapshot', 'buttons', 'ui'):
        value = copy.deepcopy(data[key])
        value.update(package=previous['package'], pid=previous['pid'],
                     driver_revision=previous['driver_revision'], generation=previous['generation']+1)
        setattr(backend, key, value)


def selected_host(drift=False):
    backend, oracle, adapter = host(drift, 'storage-equipment-selected-stack-20261027.json')
    item = oracle.storage_equipment_item('0')
    before = replace(item, generation=item.generation-1, selected=False)
    action = ActionReceipt('storage/equipment/select/0', before.generation,
                           item.button.point, item.button.bounds, item.button.path)
    proof = StorageEquipmentSelectionReceipt(action, before, 0, item.quantity)
    return backend, oracle, adapter, proof


@pytest.mark.parametrize('drift', [False, True])
def test_owned_complete_stack_opens_only_native_summary_boundary(drift):
    backend, oracle, _, proof = selected_host(drift)
    receipt = oracle.click_storage_equipment_summary((proof,))
    assert receipt.semantic_id == 'storage/equipment/summary/open'
    assert len(backend.taps) == 1
    assert backend.taps[0] != (int(proof.action.point.x), int(proof.action.point.y))


@pytest.mark.parametrize('damage', ['no-proof', 'wrong-stack', 'wrong-count', 'unknown-raycast',
                                   'label', 'duplicate', 'foreign', 'truncated'])
def test_incomplete_or_unowned_selection_cannot_open_summary(damage):
    backend, oracle, _, proof = selected_host()
    proofs = (proof,)
    target = next(b for b in backend.buttons['buttons'] if b['path'].endswith('/select_panel/confirm_button'))
    if damage == 'no-proof': proofs = ()
    elif damage == 'wrong-stack': proofs = (replace(proof, item=replace(proof.item, quantity=24)),)
    elif damage == 'wrong-count':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/bg_input/count'))['text'] = '24'
    elif damage == 'unknown-raycast': target['raycast_top'] = None
    elif damage == 'label':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/confirm_button/Image'))['text'] = '扩展'
    elif damage == 'duplicate':
        backend.buttons['buttons'].append(dict(target)); backend.buttons['button_count'] += 1
    elif damage == 'foreign': backend.foreground = 'other/.Activity'
    else: backend.ui['text_truncated'] = True
    with pytest.raises(SemanticGateClosed): oracle.click_storage_equipment_summary(proofs)
    assert not backend.taps


def test_retained_destroy_summary_cancel_has_no_final_destroy_input():
    backend, oracle, _ = host(fixture='storage-box-destroy-r46.json')
    target = next(b for b in backend.buttons['buttons'] if b['path'].endswith('/actions/cancel_button'))
    target['raycast_top'] = True
    receipt = oracle.click_storage_equipment_summary_cancel()
    assert receipt.semantic_id == 'storage/equipment/summary/cancel'
    assert receipt.path.endswith('/actions/cancel_button')
    assert len(backend.taps) == 1


@pytest.mark.parametrize('summary_fixture', ['storage-box-destroy-r46.json',
                                           'storage-equipment-summary-actionable-20261027.json'])
def test_session_native_summary_cancel_and_selection_cancel_release_only_after_typed_result(summary_fixture):
    backend, session = session_host()
    try:
        session.click(session.storage_equipment_items()[0])
        advance(backend)
        next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
        selected_marker(backend)
        session.refresh_frame()
        assert session.appear('DISASSEMBLE_CONFIRM')
        assert session.click('DISASSEMBLE_CONFIRM').semantic_id == 'storage/equipment/summary/open'
        with pytest.raises(SemanticGateClosed, match='no input replay'): session.click('DISASSEMBLE_CONFIRM')
        set_surface(backend, summary_fixture)
        next(b for b in backend.buttons['buttons'] if b['path'].endswith(('/actions/cancel_button', '/actions/cancel_btn')))['raycast_top'] = True
        session.refresh_frame()
        assert not session.appear('DISASSEMBLE_CONFIRM')
        assert session.appear('POPUP_CONFIRM') and session.appear('POPUP_CANCEL')
        assert session.appear('DISASSEMBLE_POPUP_CONFIRM')
        for alias in ('DISASSEMBLE_POPUP_CONFIRM', 'POPUP_CONFIRM_DISASSEMBLE'):
            with pytest.raises(SemanticGateClosed): session.click(alias)
        assert session.click('POPUP_CANCEL_DISASSEMBLE').semantic_id == 'storage/equipment/summary/cancel'
        set_surface(backend, 'storage-equipment-selection-20261027.json')
        session.refresh_frame()
        assert session.click('DISASSEMBLE_CANCEL').semantic_id == 'storage/equipment/disassemble-cancel'
        assert session._storage_equipment_selection_pending is not None
        set_surface(backend, 'storage-equipment-warehouse-20261027.json')
        session.refresh_frame()
        assert session.appear('DISASSEMBLE')
        assert session._storage_equipment_selection_pending is None
        assert session._storage_equipment_summary_open_receipt is None
        assert session._storage_equipment_last_cancelled['generation'] == backend.snapshot['generation']
        assert len(backend.taps) == 4  # cell, summary entry, summary cancel, selection cancel
    finally: session.close()


def test_missing_summary_owner_does_not_capture_retirement_or_box_cancel():
    backend, session = session_host()
    try:
        set_surface(backend, 'storage-box-destroy-r46.json')
        session.refresh_frame()
        with pytest.raises(SemanticGateClosed): session.click('POPUP_CANCEL_DISASSEMBLE')
        assert not backend.taps
    finally: session.close()


def test_actual_storehouse_summary_is_observed_but_unexported_input_stays_closed():
    backend, oracle, _ = host(fixture='storage-equipment-summary-20261027.json')
    summary = oracle.storage_equipment_summary()
    assert summary.rewards == (('物资', 23),)
    assert summary.cancel_button.raycast_top is None
    with pytest.raises(SemanticGateClosed): oracle.click_storage_equipment_summary_cancel()
    assert not backend.taps


def test_actual_current_summary_cancel_is_actionable_without_final_destruction():
    backend, oracle, _ = host(fixture='storage-equipment-summary-actionable-20261027.json')
    summary = oracle.storage_equipment_summary()
    assert summary.rewards == (('物资', 23),)
    assert summary.confirm_button.actionable and summary.cancel_button.actionable
    receipt = oracle.click_storage_equipment_summary_cancel()
    assert receipt.path.endswith('/actions/cancel_btn')
    assert len(backend.taps) == 1


def test_unrecognized_summary_after_entry_does_not_become_false_native_wait():
    backend, session = session_host()
    try:
        session.click(session.storage_equipment_items()[0]); advance(backend)
        next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
        selected_marker(backend); session.refresh_frame(); session.click('DISASSEMBLE_CONFIRM')
        set_surface(backend, 'storage-equipment-summary-actionable-20261027.json')
        for values in (backend.buttons['buttons'], backend.ui['images'], backend.ui['texts']):
            for value in values:
                value['path'] = value['path'].replace('StoreHouseDestroyConfirmView(Clone)', 'UnknownSummary(Clone)')
        session.refresh_frame()
        with pytest.raises(SemanticGateClosed): session.appear('DISASSEMBLE_POPUP_CONFIRM')
        assert len(backend.taps) == 2
    finally: session.close()


@pytest.mark.parametrize('damage', ['title', 'reward', 'duplicate', 'foreign'])
def test_actual_storehouse_summary_rejects_unproven_metadata(damage):
    backend, oracle, _ = host(fixture='storage-equipment-summary-20261027.json')
    if damage == 'title':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/title_text/Text'))['text'] = '扩展仓库'
    elif damage == 'reward':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/equipment_tpl/icon_bg/count'))['text'] = '?'
    elif damage == 'duplicate':
        target = next(b for b in backend.buttons['buttons'] if b['path'].endswith('/actions/cancel_btn'))
        backend.buttons['buttons'].append(dict(target)); backend.buttons['button_count'] += 1
    else: backend.foreground = 'other/.Activity'
    with pytest.raises(SemanticGateClosed): oracle.storage_equipment_summary()
    assert not backend.taps
