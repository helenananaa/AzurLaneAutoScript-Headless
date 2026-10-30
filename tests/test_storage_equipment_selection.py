"""Reversible first-stack selection; final disassembly remains closed."""
from dataclasses import replace
import copy

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_storage_equipment_inventory import ROOT, COUNT


def selection_host(drift=False):
    backend, oracle, adapter = host(drift, 'storage-equipment-selection-20261027.json')
    next(b for b in backend.buttons['buttons'] if b['path'] == ROOT+'equipment_grid/0')['raycast_top'] = True
    return backend, oracle, adapter


def selected_marker(backend, slot='0'):
    marker = copy.deepcopy(next(i for i in backend.ui['images'] if i['path'].endswith('/'+slot+'/frame/bg/icon_bg')))
    marker.update(path=ROOT+'equipment_grid/'+slot+'/frame/bg/selected', name='selected', sprite='select_bg')
    backend.ui['images'].append(marker); backend.ui['image_count'] += 1


@pytest.mark.parametrize('drift', [False, True])
def test_first_stack_uses_fresh_point_and_retains_whole_stack_count(drift):
    backend, oracle, _ = selection_host(drift)
    item = oracle.storage_equipment_item('0')
    action = oracle.click_storage_equipment_item(item)
    assert action.quantity == 23 and action.selected_before == 0
    assert len(backend.taps) == 1
    for payload in (backend.snapshot, backend.buttons, backend.ui):
        payload['generation'] += 1
    assert oracle.storage_equipment_selection_postcondition(action) is False
    next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
    selected_marker(backend)
    assert oracle.storage_equipment_selection_postcondition(action) is True
    assert len(backend.taps) == 1


@pytest.mark.parametrize('damage', ['pid', 'instance', 'icon', 'quantity', 'level', 'clipped',
                                   'raycast', 'duplicate', 'foreign', 'stale', 'selected'])
def test_changed_cell_or_unproven_selection_never_dispatches(damage):
    backend, oracle, _ = selection_host()
    item = oracle.storage_equipment_item('0')
    target = next(b for b in backend.buttons['buttons'] if b['path'] == item.button.path)
    if damage == 'pid':
        item = replace(item, pid=item.pid+1)
    elif damage == 'instance': target['instance_id'] -= 1
    elif damage == 'icon':
        next(i for i in backend.ui['images'] if i['path'].endswith('/0/frame/bg/icon_bg/icon'))['sprite'] = 'other'
    elif damage == 'quantity':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/0/frame/bg/icon_bg/count'))['text'] = '24'
    elif damage == 'level': item = replace(item, upgrade_level=7)
    elif damage == 'clipped': target['adb_bounds']['top'] = -5
    elif damage == 'raycast': target['raycast_top'] = None
    elif damage == 'duplicate':
        backend.buttons['buttons'].append(dict(target)); backend.buttons['button_count'] += 1
    elif damage == 'foreign': backend.foreground = 'other/.Activity'
    elif damage == 'stale': backend.snapshot['age_ms'] = 10001
    else:
        next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
        selected_marker(backend)
    with pytest.raises(SemanticGateClosed): oracle.click_storage_equipment_item(item)
    assert not backend.taps


def test_unexpected_count_is_unknown_outcome_and_never_replayed():
    backend, oracle, _ = selection_host()
    action = oracle.click_storage_equipment_item(oracle.storage_equipment_item('0'))
    for payload in (backend.snapshot, backend.buttons, backend.ui): payload['generation'] += 1
    next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '7'
    with pytest.raises(SemanticGateClosed): oracle.storage_equipment_selection_postcondition(action)
    assert len(backend.taps) == 1


def session_host(backend_error=False, policy_grants=None):
    from alas_headless import AlasSemanticSession
    from alas_headless.adapter import semantic_runtime_fingerprint_sha256
    from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
    backend, _, _ = selection_host()
    handle = FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=backend.snapshot['package'], component=backend.foreground,
        driver_revision=backend.snapshot['driver_revision'], required_primary_abi='x86_64'))
    handle.pid = backend.snapshot['pid']; handle.observer_request = backend.request
    handle.foreground_component = backend.foreground_component
    handle.tap = backend.tap; handle.swipe = backend.swipe
    if backend_error:
        original = handle.tap
        def tap(*args):
            original(*args)
            raise RuntimeError('backend interrupted after submission')
        handle.tap = tap
    session = AlasSemanticSession(driver_revision=backend.snapshot['driver_revision'], runtime_handle=handle,
                                  policy_grants=policy_grants)
    session.open(); session.refresh_frame()
    return backend, session


@pytest.mark.parametrize('backend_error', [False, True])
def test_session_records_before_backend_and_never_repeats_accepted_or_unknown_input(backend_error):
    backend, session = session_host(backend_error)
    try:
        item = session.storage_equipment_items()[0]
        if backend_error:
            with pytest.raises(RuntimeError): session.click(item)
        else:
            assert session.click(item).semantic_id == 'storage/equipment/select/0'
        assert len(backend.taps) == 1
        for payload in (backend.snapshot, backend.buttons, backend.ui): payload['generation'] += 1
        with pytest.raises(SemanticGateClosed, match='no input replay'): session.click(item)
        for payload in (backend.snapshot, backend.buttons, backend.ui): payload['generation'] += 1
        next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
        selected_marker(backend)
        session.refresh_frame()
        assert session.storage_equipment_selection_result() is True
        assert session.storage_equipment_selected_count() == 23
        with pytest.raises(SemanticGateClosed): session.click('DISASSEMBLE_POPUP_CONFIRM')
        assert len(backend.taps) == 1
    finally: session.close()


def test_actual_selected_marker_distinguishes_toggle_from_new_selection():
    backend, oracle, _ = host(fixture='storage-equipment-selected-stack-20261027.json')
    item = oracle.storage_equipment_item('0')
    assert item.selected and item.quantity == 23
    assert oracle.storage_equipment_selected_count() == 23
    with pytest.raises(SemanticGateClosed): oracle.click_storage_equipment_item(item)
    assert not backend.taps


def test_nonzero_count_does_not_block_a_different_unselected_cell():
    backend, oracle, _ = host(fixture='storage-equipment-selected-stack-20261027.json')
    item = oracle.storage_equipment_item('1')
    assert not item.selected and item.button.actionable
    receipt = oracle.click_storage_equipment_item(item)
    assert receipt.selected_before == 23 and receipt.quantity == item.quantity
    assert len(backend.taps) == 1


def test_session_next_native_cell_requires_previous_marker_and_count_postcondition():
    backend, session = session_host()
    try:
        next(b for b in backend.buttons['buttons'] if b['path'] == ROOT+'equipment_grid/1')['raycast_top'] = True
        session.refresh_frame()
        first, second = session.storage_equipment_items()[:2]
        session.click(first)
        for payload in (backend.snapshot, backend.buttons, backend.ui): payload['generation'] += 1
        next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
        selected_marker(backend)
        session.click(second)
        assert len(backend.taps) == 2
        assert session._storage_equipment_selection_pending.selected_before == 23
        assert session._storage_equipment_selection_pending.quantity == second.amount
    finally: session.close()


@pytest.mark.parametrize('damage', ['missing', 'unknown', 'duplicate'])
def test_selected_marker_and_count_must_agree_after_input(damage):
    backend, oracle, _ = selection_host()
    receipt = oracle.click_storage_equipment_item(oracle.storage_equipment_item('0'))
    for payload in (backend.snapshot, backend.buttons, backend.ui): payload['generation'] += 1
    next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
    if damage != 'missing':
        selected_marker(backend)
        if damage == 'unknown': backend.ui['images'][-1]['sprite'] = 'unknown'
        else:
            backend.ui['images'].append(copy.deepcopy(backend.ui['images'][-1])); backend.ui['image_count'] += 1
    with pytest.raises(SemanticGateClosed): oracle.storage_equipment_selection_postcondition(receipt)
    assert len(backend.taps) == 1
