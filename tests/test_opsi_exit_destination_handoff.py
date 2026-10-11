"""Original page navigation must not repeat a completed OpSi back edge."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle

MENU = 'UICamera/Canvas/UIMain/LevelMainScene(Clone)/'


def case(change=None):
    records = [make_button('back_button', MENU+'top/top_chapter/back_button'),
               make_button('enter_main', MENU+'entrance/enters/enter_main')]
    if change == 'duplicate': records.append(dict(records[0]))
    if change in ('foreign', 'loading'):
        path = ('OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button'
                if change == 'foreign' else 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')
        records.append(make_button('blocker', path))
    if change == 'source_present':
        records.append(make_button('back_button', 'OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button', raycast_top=None))
    if change == 'unknown': records = []
    backend = FakeBackend(records)
    if change == 'stale': backend.snapshot['age_ms'] = backend.buttons['age_ms'] = 99999
    if change == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    # Reproduce original ALAS' previously observed page edge; fresh destination
    # proof below uses the real typed oracle rather than this leased decision.
    adapter._goto_main_target = lambda: 'os/page/back'
    previous = SimpleNamespace(semantic_id='os/exit/cancel' if change == 'cancel' else 'os/exit/confirm',
                               generation=10 if change == 'old_generation' else 9)
    if change != 'no_receipt': adapter._operation_siren_exit_receipt = previous
    return backend, adapter, previous


def test_completed_exit_consumes_old_map_edge_without_a_second_input():
    backend, adapter, previous = case()
    assert adapter.click(SimpleNamespace(name='GOTO_MAIN')) is previous
    assert adapter._operation_siren_exit_receipt is None
    assert backend.taps == []


@pytest.mark.parametrize('retained_destination', [False, True])
def test_confirmed_exit_awaits_a_new_frame_when_old_map_still_fades(retained_destination):
    source_backend, adapter, previous = case('source_present')
    destination_backend, destination_adapter, _ = case()
    if retained_destination:
        source = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r39.json'
        if not source.exists():
            pytest.skip('retained r39 destination unavailable')
        run = json.loads(source.read_text(encoding='utf-8'))
        task = next(row for row in reversed(run['tasks']) if row['selected_task'] == 'ShopOnce')
        # This later frame proves the destination; it is not the failing frame.
        destination_backend = FakeBackend(task['failure_leased_frame']['buttons_snapshot']['buttons'])
        destination_adapter = AlasSemanticAdapter(make_oracle(destination_backend), package_gate=lambda: None)
    from unittest.mock import Mock
    adapter._operation_siren_entry_transition_until = time.monotonic() + 30
    adapter._fresh_input_oracle = Mock(side_effect=[adapter.oracle, destination_adapter.oracle])
    assert adapter.click(SimpleNamespace(name='GOTO_MAIN')) is previous
    assert adapter._fresh_input_oracle.call_count == 2
    assert adapter._operation_siren_exit_receipt is None
    assert source_backend.taps == destination_backend.taps == []


@pytest.mark.parametrize('change', ['no_receipt', 'cancel', 'source_present', 'unknown',
                                  'old_generation', 'duplicate', 'foreign', 'loading', 'stale', 'foreground'])
def test_exit_handoff_keeps_destination_and_input_guards(change, monkeypatch):
    backend, adapter, previous = case(change)
    # Advance the bounded destination wait without spending wall time on
    # unchanged closed cases; receipt-less cases never enter that wait.
    monkeypatch.setattr('alas_headless.adapter.semantic.dispatch_actions.time.monotonic',
                        iter([100.0, 106.0, 112.0, 118.0]).__next__)
    with pytest.raises(SemanticGateClosed): adapter.click(SimpleNamespace(name='GOTO_MAIN'))
    assert backend.taps == []
    if change != 'no_receipt': assert adapter._operation_siren_exit_receipt is previous


def test_cleared_passive_lease_does_not_cancel_an_accepted_exit_destination_wait():
    from unittest.mock import Mock
    source_backend, adapter, previous = case('source_present')
    destination_backend, destination_adapter, _ = case()
    adapter._operation_siren_entry_transition_until = 0.0
    adapter._fresh_input_oracle = Mock(side_effect=[adapter.oracle, destination_adapter.oracle])
    assert adapter.click(SimpleNamespace(name='GOTO_MAIN')) is previous
    assert adapter._fresh_input_oracle.call_count == 2
    assert source_backend.taps == destination_backend.taps == []


def test_r198_native_daily_menu_failure_frame_is_a_proven_destination():
    source = Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-scheduler-r198-20261002.json'
    if not source.exists(): pytest.skip('retained r198 frame unavailable')
    run = json.loads(source.read_text(encoding='utf-8'))
    task = next(row for row in run['tasks'] if row['selected_task'] == 'Daily')
    frame = task['failure_leased_frame']
    backend = FakeBackend(frame['buttons_snapshot']['buttons'])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    adapter._goto_main_target = lambda: 'os/page/back'
    previous = SimpleNamespace(semantic_id='os/exit/confirm', generation=9)
    adapter._operation_siren_exit_receipt = previous
    assert adapter.click(SimpleNamespace(name='GOTO_MAIN')) is previous
    assert backend.taps == []
