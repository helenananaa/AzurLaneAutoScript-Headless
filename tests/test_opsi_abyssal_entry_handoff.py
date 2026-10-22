"""A disappearing accepted entry modal must not become a reconnect input."""
import copy
import json
import time
from pathlib import Path

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)

ROOT = 'root/Msgbox(Clone)/window/'
MAP = 'OverlayCamera/Overlay/UIMain/top/adapt/'


def local_buttons():
    return [make_button('back_button', MAP+'top_stage/back_button'),
            make_button('fleet_bar', MAP+'left_stage/other/fleet_bar')]


def accepted_entry():
    backend = FakeBackend([make_button('custom_button_'+str(i)+'(Clone)',
        ROOT+'button_container/custom_button_'+str(i)+'(Clone)') for i in (1, 2)])
    backend.ui = make_ui([make_text('深渊海域作战难度较高且不可重复进入，\n请确认舰队战备后前往作战',
                                   ROOT+'msg_panel/content')])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    def arrive(*_):
        backend.buttons['buttons'] = local_buttons()
        backend.buttons['button_count'] = 2
        backend.snapshot['generation'] = backend.buttons['generation'] = 11
        backend.ui = make_ui([], generation=11)
    backend.on_tap = arrive
    receipt = adapter.click('POPUP_CONFIRM')
    assert len(backend.taps) == 1 and oracle.input_dispatch_count == 1
    assert adapter._operation_siren_abyssal_entry_receipt is receipt
    return backend, adapter, receipt


def test_completed_entry_reuses_real_receipt_without_a_second_tap():
    backend, adapter, receipt = accepted_entry()
    backend.buttons['buttons'].reverse()
    backend.buttons['upstream_addition'] = {'version': 2}
    assert adapter.click('POPUP_CONFIRM') is receipt
    assert adapter._operation_siren_abyssal_entry_receipt is None
    assert len(backend.taps) == 1 and adapter.oracle.input_dispatch_count == 1
    with pytest.raises(SemanticGateClosed):
        adapter.click('POPUP_CONFIRM')
    assert len(backend.taps) == 1


@pytest.mark.parametrize('change', ['no_receipt', 'expired', 'later_input', 'old_generation',
    'missing_owner', 'duplicate', 'inactive', 'foreign_prompt', 'loading', 'foreign', 'stale', 'foreground'])
def test_entry_handoff_does_not_accept_an_unproven_destination(change):
    backend, adapter, receipt = accepted_entry()
    buttons = backend.buttons['buttons']
    if change == 'no_receipt': adapter._operation_siren_abyssal_entry_receipt = None
    elif change == 'expired': adapter._operation_siren_entry_transition_until = time.monotonic()-1
    elif change == 'later_input': adapter.oracle._tap(10, 10)
    elif change == 'old_generation':
        backend.snapshot['generation'] = backend.buttons['generation'] = receipt.generation
    elif change == 'missing_owner': buttons.pop(0)
    elif change == 'duplicate': buttons.append(copy.deepcopy(buttons[0]))
    elif change == 'inactive': buttons[0]['active_in_hierarchy'] = False
    elif change == 'foreign_prompt':
        buttons.append(make_button('custom_button_1(Clone)', ROOT+'button_container/custom_button_1(Clone)'))
        backend.ui = make_ui([make_text('购买礼包？', ROOT+'msg_panel/content')], generation=11)
    elif change == 'loading': buttons.append(make_button('loading', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    elif change == 'foreign': backend.snapshot['package'] = 'other.package'
    elif change == 'stale': backend.snapshot['age_ms'] = 99999
    else: backend.foreground = 'com.android.settings/.Settings'
    backend.buttons['button_count'] = len(buttons)
    count = len(backend.taps)
    with pytest.raises(SemanticGateClosed): adapter.click('POPUP_CONFIRM')
    assert len(backend.taps) == count


def test_uncertain_confirmation_never_creates_a_completion_receipt():
    backend, adapter, _ = accepted_entry()
    adapter._operation_siren_abyssal_entry_receipt = None
    # Restore the exact reviewed prompt, then fail after backend submission.
    backend.buttons['buttons'] = [make_button('custom_button_'+str(i)+'(Clone)',
        ROOT+'button_container/custom_button_'+str(i)+'(Clone)') for i in (1, 2)]
    backend.ui = make_ui([make_text('深渊海域作战难度较高且不可重复进入，\n请确认舰队战备后前往作战',
                                   ROOT+'msg_panel/content')], generation=11)
    def uncertain(*_): raise SemanticGateClosed('accepted input outcome uncertain')
    backend.on_tap = uncertain
    with pytest.raises(SemanticGateClosed, match='outcome uncertain'): adapter.click('POPUP_CONFIRM')
    assert len(backend.taps) == 2 and adapter._operation_siren_abyssal_entry_receipt is None


def test_retained_r100_failed_input_frame_proves_only_the_new_map_destination():
    path = Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r100.json'
    if not path.exists(): pytest.skip('retained r100 input frame unavailable')
    frame = json.loads(path.read_text(encoding='utf-8'))['tasks'][-1]['failure_leased_frame']
    backend, adapter, receipt = accepted_entry()
    backend.buttons['buttons'] = frame['buttons_snapshot']['buttons']
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    assert adapter.click('POPUP_CONFIRM') is receipt
    assert len(backend.taps) == 1
