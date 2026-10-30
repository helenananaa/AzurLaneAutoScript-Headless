"""Final common equipment input, quantity ledger, and original-screenshot postcondition."""
from dataclasses import replace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import translate_legacy_semantic_environment
from tests.test_storage_equipment_selection import session_host, selected_marker, COUNT
from tests.test_storage_equipment_summary import set_surface, advance


def prepared(budget=23):
    backend, session = session_host(policy_grants={'storage.disassemble': budget})
    set_surface(backend, 'storage-equipment-filter-20261027.json')
    root = 'OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/layout/'
    for image in backend.ui['images']:
        if image['path'] == root+'container/indexsort_rarity/bg/tpl': image['sprite'] = 'btn_index_grey'
        if image['path'] == root+'container/indexsort_rarity/bg/1': image['sprite'] = 'btn_index_yellow'
    next(b for b in backend.buttons['buttons'] if b['path'] == root+'btns/ok')['raycast_top'] = True
    session.refresh_frame(); session.click('EQUIPMENT_FILTER_CONFIRM')
    set_surface(backend, 'storage-equipment-selection-20261027.json')
    next(b for b in backend.buttons['buttons'] if b['path'].endswith('/equipment_grid/0'))['raycast_top'] = True
    session.refresh_frame(); session.click(session.storage_equipment_items()[0])
    advance(backend)
    next(t for t in backend.ui['texts'] if t['path'] == COUNT)['text'] = '23'
    selected_marker(backend); session.refresh_frame(); session.click('DISASSEMBLE_CONFIRM')
    assert session._storage_equipment_destroy_intent.rarities == (1,)
    set_surface(backend, 'storage-equipment-summary-actionable-20261027.json')
    session.refresh_frame()
    return backend, session


def test_new_environment_budget_is_gear_units_and_defaults_to_zero():
    env = {'ALAS_SEMANTIC_MODE':'1', 'ALAS_SEMANTIC_DRIVER_REVISION':'a'*40}
    assert translate_legacy_semantic_environment(env).grant('storage.disassemble') == 0
    env['ALAS_SEMANTIC_STORAGE_DISASSEMBLE_BUDGET'] = '23'
    assert translate_legacy_semantic_environment(env).grant('storage.disassemble') == 23


@pytest.mark.parametrize('budget', [0, 22])
def test_finite_gear_budget_cannot_be_treated_as_one_click(budget):
    backend, session = prepared(budget)
    try:
        with pytest.raises(SemanticGateClosed): session.click('DISASSEMBLE_POPUP_CONFIRM')
        assert session.action_ledger.remaining('storage.disassemble') == budget
        assert session.storage_equipment_disassembly_pending() is None
        assert len(backend.taps) == 3
    finally: session.close()


def test_confirm_uses_23_units_and_native_next_screenshot_proves_stock_result():
    backend, session = prepared()
    try:
        action = session.click('DISASSEMBLE_POPUP_CONFIRM')
        assert action.capability_id == 'storage.disassemble'
        assert session.action_ledger.remaining('storage.disassemble') == 0
        assert len(backend.taps) == 4
        with pytest.raises(SemanticGateClosed, match='no input replay'): session.click('DISASSEMBLE_POPUP_CONFIRM')
        set_surface(backend, 'storage-equipment-selection-20261027.json')
        next(t for t in backend.ui['texts'] if t['path'].endswith('/tip/capcity/Text'))['text'] = '680/375'
        session.refresh_frame()
        assert session.appear('DISASSEMBLE_CANCEL')
        receipt, = session.storage_equipment_disassembly_receipts()
        assert receipt.request.intent.quantity == 23 and receipt.capacity_after == 680
        assert receipt.request.expected_rewards == (('物资', 23),)
        assert receipt.request.action.capability_id == 'storage.disassemble'
        assert session.storage_equipment_disassembly_pending() is None
        assert session._storage_equipment_selection_pending is None
    finally: session.close()


@pytest.mark.parametrize('damage', ['raycast', 'capacity', 'rarity', 'upgrade', 'pid'])
def test_unsafe_confirmation_is_zero_input_and_refunds_only_reserved_units(damage):
    backend, session = prepared()
    try:
        intent = session._storage_equipment_destroy_intent
        if damage == 'raycast':
            next(b for b in backend.buttons['buttons'] if b['path'].endswith('/actions/confirm_btn'))['raycast_top'] = None
        elif damage == 'capacity':
            next(t for t in backend.ui['texts'] if t['path'].endswith('/tip/capcity/Text'))['text'] = '702/375'
        elif damage == 'rarity': intent = replace(intent, rarities=(2,))
        elif damage == 'upgrade': intent = replace(intent, items=(replace(intent.items[0], upgrade_level=7),))
        else: intent = replace(intent, pid=intent.pid+1)
        session._storage_equipment_destroy_intent = intent
        advance(backend)
        with pytest.raises(SemanticGateClosed): session.click('DISASSEMBLE_POPUP_CONFIRM')
        assert session.action_ledger.remaining('storage.disassemble') == 23
        assert not session.storage_equipment_disassembly_pending() and len(backend.taps) == 3
    finally: session.close()


def test_backend_unknown_keeps_23_units_spent_and_pending_input_unreplayed():
    backend, session = prepared()
    try:
        original = session.open().oracle._tap_backend
        def interrupted(*args):
            original(*args)
            raise RuntimeError('accepted input response lost')
        session.open().oracle._tap_backend = interrupted
        with pytest.raises(RuntimeError): session.click('DISASSEMBLE_POPUP_CONFIRM')
        assert session.action_ledger.remaining('storage.disassemble') == 0
        assert session.storage_equipment_disassembly_pending() is not None
        with pytest.raises(SemanticGateClosed): session.click('DISASSEMBLE_POPUP_CONFIRM')
        assert len(backend.taps) == 4
    finally: session.close()


def test_wrong_stock_delta_does_not_clear_or_recredit_pending_input():
    backend, session = prepared()
    try:
        session.click('DISASSEMBLE_POPUP_CONFIRM')
        set_surface(backend, 'storage-equipment-selection-20261027.json')
        next(t for t in backend.ui['texts'] if t['path'].endswith('/tip/capcity/Text'))['text'] = '702/375'
        session.refresh_frame()
        with pytest.raises(SemanticGateClosed): session.appear('DISASSEMBLE_CANCEL')
        assert session.storage_equipment_disassembly_pending() is not None
        assert not session.storage_equipment_disassembly_receipts()
        assert session.action_ledger.remaining('storage.disassemble') == 0
    finally: session.close()


def test_native_get_items_closes_the_accepted_reward_without_another_destruction():
    backend, session = prepared()
    try:
        session.click('DISASSEMBLE_POPUP_CONFIRM')
        set_surface(backend, 'storage-equipment-disassembly-award-20261027.json'); session.refresh_frame()
        assert not session.appear('DISASSEMBLE_CANCEL')
        receipt, = session.storage_equipment_disassembly_receipts()
        assert receipt.observed_rewards == (('物资', 23),) and receipt.reward_overlay
        assert not session.appear('DISASSEMBLE_CONFIRM')
        assert not session.appear('POPUP_CANCEL')
        assert session.appear('GET_ITEMS_1')
        assert session.click('DISASSEMBLE_CONFIRM').semantic_id == 'storage/equipment/reward/close'
        assert session.action_ledger.remaining('storage.disassemble') == 0
        set_surface(backend, 'storage-equipment-selection-20261027.json')
        next(t for t in backend.ui['texts'] if t['path'].endswith('/tip/capcity/Text'))['text'] = '680/375'
        session.refresh_frame(); assert session.appear('DISASSEMBLE_CANCEL')
        assert session._storage_equipment_award_request is None
        assert len(backend.taps) == 5
    finally: session.close()


def test_wrong_reward_never_recredits_or_closes_unknown_outcome():
    backend, session = prepared()
    try:
        session.click('DISASSEMBLE_POPUP_CONFIRM')
        set_surface(backend, 'storage-equipment-disassembly-award-20261027.json')
        next(t for t in backend.ui['texts'] if 'AwardInfoUI' in t['path'] and t['path'].endswith('/icon_bg/count'))['text'] = '22'
        session.refresh_frame()
        with pytest.raises(SemanticGateClosed): session.appear('DISASSEMBLE_CANCEL')
        assert session.storage_equipment_disassembly_pending() is not None
        assert session.action_ledger.remaining('storage.disassemble') == 0
        assert not session.storage_equipment_disassembly_receipts() and len(backend.taps) == 4
    finally: session.close()
