"""Accepted tactical entry survives its actual loading publication without input."""
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button, make_oracle, FakeBackend


def loading(drift=False, accepted=True):
    backend, oracle, _ = host(drift, 'tactical-entry-tactical-r444.json')
    generation = max(x['generation'] for x in (backend.snapshot, backend.buttons, backend.ui))
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] = generation
    adapter = AlasSemanticAdapter(oracle, lambda: None, allow_tactical_rewards=True)
    adapter.begin_tactical()
    receipt = SimpleNamespace(semantic_id='reward/tactical/go', generation=88285)
    if accepted:
        # The raw source fixture retains the actual accepted action at88285.
        adapter._commission_context.tactical_entry_receipt = receipt
        adapter._commission_context.tactical_entry_input_count = oracle.input_dispatch_count
        adapter._record_mission_transition(receipt)
    return backend, oracle, adapter, receipt


@pytest.mark.parametrize('drift', [False, True])
def test_actual_loading_frame_reuses_accepted_entry_with_zero_additional_input(drift):
    backend, oracle, adapter, receipt = loading(drift)
    assert adapter.click('REWARD_GOTO_TACTICAL') is receipt
    assert not backend.taps and not backend.swipes
    assert oracle.input_dispatch_count == 0


def test_first_entry_accepted_receipt_and_dispatch_count_are_recorded():
    root = 'OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
    backend = FakeBackend([make_button('CommissionInfoUI4Mellow(Clone)', root),
        make_button('go_btn', root + '/frame/main/content/class/frame/go_btn')])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_tactical()
    receipt = adapter.click('REWARD_GOTO_TACTICAL')
    assert adapter._commission_context.tactical_entry_receipt is receipt
    assert adapter._commission_context.tactical_entry_input_count == 1
    assert len(backend.taps) == 1


@pytest.mark.parametrize('damage', ['no-accepted-input', 'another-input', 'expired',
    'foreign-modal', 'foreign-package', 'truncated', 'same-generation'])
def test_loading_handoff_does_not_hide_unrelated_or_unowned_failure(damage):
    backend, oracle, adapter, receipt = loading(accepted=damage != 'no-accepted-input')
    context = adapter._commission_context
    if damage == 'another-input':
        context.tactical_entry_input_count = -1
    elif damage == 'expired':
        context.passive_transition_until = 0
    elif damage == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif damage == 'foreign-package':
        backend.foreground = 'other/.Activity'
    elif damage == 'truncated':
        backend.buttons['truncated'] = True
    elif damage == 'same-generation':
        receipt.generation = backend.snapshot['generation']
    with pytest.raises(SemanticGateClosed):
        adapter.click('REWARD_GOTO_TACTICAL')
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
    'MAINTENANCE_ANNOUNCE'])
@pytest.mark.parametrize('drift', [False, True])
def test_exact_failed_return_frame_yields_passive_notices_to_next_native_screenshot(name, drift):
    backend, oracle, adapter = host(drift, 'tactical-return-notice-frame-r444.json')
    assert adapter.appear(name) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(name)
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('damage', ['foreign-modal', 'foreign-package', 'truncated'])
@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'MAINTENANCE_ANNOUNCE'])
def test_return_notice_absence_still_rejects_unknown_or_invalid_state(damage, name):
    backend, oracle, adapter = host(fixture='tactical-return-notice-frame-r444.json')
    if damage == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif damage == 'foreign-package':
        backend.foreground = 'other/.Activity'
    else:
        backend.buttons['truncated'] = True
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.appear(name)
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('drift', [False, True])
def test_actual_post_training_maintenance_probe_yields_only_its_known_loading(drift):
    backend, oracle, adapter = host(drift, 'tactical-return-maintenance-r449.json')
    assert adapter.appear('MAINTENANCE_ANNOUNCE') is False
    assert not backend.taps and not backend.swipes
