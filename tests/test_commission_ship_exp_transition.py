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
def test_unproven_exp_exit_keeps_missing_input_closed(change):
    backend, adapter, previous = transition()
    context = adapter._commission_context
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
