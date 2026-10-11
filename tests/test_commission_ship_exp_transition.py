from dataclasses import replace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_snapshot, make_ui,
)


EXP = 'root/OverlayCamera/Overlay/UIMain/ShipExpUI(Clone)/skipLayer'
AWARD = 'root/OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close'


def transition():
    backend = FakeBackend([make_button('skipLayer', EXP)])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    adapter.begin_commission()
    previous = adapter.click('EXP_INFO_S_REWARD')
    context = adapter._commission_context
    context.reward_claim_receipt = replace(previous, semantic_id='reward/commission/finish')
    backend.snapshot = make_snapshot(generation=11)
    backend.ui = make_ui([], generation=11)
    backend.buttons = make_buttons([make_button('skipLayer', EXP)], generation=11)
    assert adapter.appear('EXP_INFO_S_REWARD')
    backend.snapshot = make_snapshot(generation=12)
    backend.ui = make_ui([], generation=12)
    backend.buttons = make_buttons([make_button('close', AWARD)], generation=12)
    return backend, adapter, previous


def test_native_award_after_recorded_exp_close_consumes_positive_probe_without_input():
    backend, adapter, previous = transition()
    assert adapter.click('EXP_INFO_S_REWARD') is previous
    assert backend.taps == [(640, 360)]
    assert adapter._commission_context.reward_close_receipts == [previous]
    assert adapter._commission_context.ship_exp_observation_generation is None
    with pytest.raises(SemanticGateClosed):
        adapter.click('EXP_INFO_S_REWARD')
    assert len(backend.taps) == 1


@pytest.mark.parametrize('change', [
    'no_probe', 'no_claim', 'no_previous', 'different_previous', 'stale',
    'unknown_page', 'foreign_prompt', 'expired', 'tactical', 'inactive_award',
])
def test_unproven_exp_exit_keeps_missing_input_closed(change, monkeypatch):
    backend, adapter, previous = transition()
    context = adapter._commission_context
    # Model the original transition deadline without spending wall-clock
    # seconds on a deliberately unchanging retained frame.
    import time
    clock = [time.monotonic()]
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.sleep', lambda _: clock.__setitem__(0, clock[0] + 21))
    if change == 'no_probe':
        context.ship_exp_observation_generation = None
    elif change == 'no_claim':
        context.reward_claim_receipt = None
    elif change == 'no_previous':
        context.reward_close_receipts = []
    elif change == 'different_previous':
        context.reward_close_receipts = [replace(previous, semantic_id='reward/award-info/close')]
    elif change == 'stale':
        backend.snapshot = make_snapshot(generation=11)
        backend.buttons['generation'] = 11
    elif change == 'unknown_page':
        backend.buttons = make_buttons([], generation=12)
    elif change == 'foreign_prompt':
        backend.buttons = make_buttons([
            make_button('close', AWARD),
            make_button('confirm', 'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'),
        ], generation=12)
    elif change == 'expired':
        context.passive_transition_until = 0
    elif change == 'tactical':
        context.flow_kind = 'tactical'
    elif change == 'inactive_award':
        button = make_button('close', AWARD)
        button['active_in_hierarchy'] = False
        backend.buttons = make_buttons([button], generation=12)
    with pytest.raises(SemanticGateClosed):
        adapter.click('EXP_INFO_S_REWARD')
    assert backend.taps == [(640, 360)]


def test_mounted_exp_still_uses_original_input_instead_of_acknowledgement():
    backend, adapter, previous = transition()
    backend.buttons = make_buttons([make_button('skipLayer', EXP)], generation=12)
    receipt = adapter.click('EXP_INFO_S_REWARD')
    assert receipt.generation == 12
    assert receipt is not previous
    assert len(backend.taps) == 2


def test_exp_disappearing_between_presence_and_click_reuses_proven_close():
    backend, adapter, previous = transition()
    # The preliminary presence read raced ahead of the guarded click's fresh
    # frame, which already contains the next actual native award.
    original = adapter.oracle.observation_target_present
    adapter.oracle.observation_target_present = lambda target: (
        True if target == 'reward/ship-exp/close' else original(target))
    assert adapter.click('EXP_INFO_S_REWARD') is previous
    assert backend.taps == [(640, 360)]
    assert adapter._commission_context.ship_exp_observation_generation is None


def test_missing_exp_after_a_dispatched_input_is_not_acknowledged():
    from alas_headless.semantic_oracle import SemanticTargetMissing
    backend, adapter, previous = transition()
    adapter.oracle.observation_target_present = lambda target: True
    def dispatched_then_missing(target):
        adapter.oracle._tap(640, 360)
        raise SemanticTargetMissing('semantic target is absent: ' + target)
    adapter.oracle.click = dispatched_then_missing
    with pytest.raises(SemanticTargetMissing):
        adapter.click('EXP_INFO_S_REWARD')
    assert len(backend.taps) == 2
    assert adapter._commission_context.reward_close_receipts == [previous]


@pytest.mark.parametrize('transient', ['same_generation', 'award_mounting'])
def test_preliminary_incomplete_proof_does_not_erase_guarded_race_recovery(transient):
    backend, adapter, previous = transition()
    original = adapter._commission_ship_exp_completed_transition
    calls = []
    observed = 12 if transient == 'same_generation' else 11
    adapter._commission_context.ship_exp_observation_generation = observed

    def transition_proof(**kwargs):
        calls.append(True)
        if len(calls) == 1:
            if transient == 'same_generation':
                backend.snapshot = make_snapshot(generation=12)
                backend.buttons = make_buttons([make_button('close', AWARD)], generation=12)
            else:
                backend.buttons = make_buttons([], generation=12)
            assert original() is None
            assert adapter._commission_context.ship_exp_observation_generation == observed
            backend.snapshot = make_snapshot(generation=13)
            backend.buttons = make_buttons([make_button('close', AWARD)], generation=13)
            # Harmless additive metadata does not change the destination.
            backend.snapshot['upstream_metadata'] = 'new release'
            return None
        return original(**kwargs)

    adapter._commission_ship_exp_completed_transition = transition_proof
    assert adapter.click('EXP_INFO_S_REWARD') is previous
    assert len(calls) == 2
    assert backend.taps == [(640, 360)]
    assert adapter._commission_context.ship_exp_observation_generation is None
    assert adapter._commission_context.reward_close_receipts == [previous]


def test_passive_exp_close_ack_does_not_require_next_award_actionability():
    backend, adapter, previous = transition()
    backend.buttons['buttons'][0]['raycast_top'] = False
    assert adapter.click('EXP_INFO_S_REWARD') is previous
    assert backend.taps == [(640, 360)]
    with pytest.raises(SemanticGateClosed):
        adapter.click('GET_ITEMS_1')
    assert backend.taps == [(640, 360)]


def test_departing_exp_waits_readonly_for_award_inside_existing_transition(monkeypatch):
    backend, adapter, previous = transition()
    backend.buttons = make_buttons([], generation=12)
    sleeps = []
    def mount_award(_):
        sleeps.append(True)
        assert backend.taps == [(640, 360)]
        backend.snapshot = make_snapshot(generation=13)
        backend.buttons = make_buttons([make_button('close', AWARD, raycast_top=False)], generation=13)
        backend.ui = make_ui([], generation=13)
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.sleep', mount_award)
    assert adapter.click('EXP_INFO_S_REWARD') is previous
    assert len(sleeps) == 1
    assert backend.taps == [(640, 360)]


def sidebar_transition():
    backend, adapter, previous = transition()
    backend.buttons = make_buttons([make_button('CommissionInfoUI4Mellow(Clone)',
        'root/OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)')], generation=12)
    return backend, adapter, previous


def test_final_recorded_exp_close_can_return_to_actual_reward_sidebar_without_new_input():
    backend, adapter, previous = sidebar_transition()
    assert adapter.click('EXP_INFO_S_REWARD') is previous
    assert backend.taps == [(640, 360)]
    assert adapter._commission_context.reward_close_receipts == [previous]
    assert adapter._commission_context.ship_exp_observation_generation is None
    with pytest.raises(SemanticGateClosed): adapter.click('EXP_INFO_S_REWARD')
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['same_generation', 'no_claim', 'no_previous', 'covered', 'inactive', 'duplicate', 'foreign_prompt'])
def test_sidebar_acknowledgement_requires_the_original_close_and_proven_return(case, monkeypatch):
    backend, adapter, previous = sidebar_transition()
    context = adapter._commission_context
    import time
    clock = [time.monotonic()]
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.sleep', lambda _: clock.__setitem__(0, clock[0] + 21))
    if case == 'same_generation':
        backend.snapshot['generation'] = backend.buttons['generation'] = backend.ui['generation'] = 11
    elif case == 'no_claim': context.reward_claim_receipt = None
    elif case == 'no_previous': context.reward_close_receipts = []
    elif case == 'covered': backend.buttons['buttons'][0]['raycast_top'] = False
    elif case == 'inactive': backend.buttons['buttons'][0]['active_in_hierarchy'] = False
    elif case == 'duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count'] += 1
    else:
        backend.buttons['buttons'].append(make_button('confirm',
            'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed): adapter.click('EXP_INFO_S_REWARD')
    assert backend.taps == [(640, 360)]
