import copy
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.semantic_oracle import ActionReceipt
from tests.test_game_tips_loading_presence import host


def next_cycle():
    b, o, _ = host(fixture='commission-next-finished-cycle-r142.json')
    b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation']
    a = AlasSemanticAdapter(o, lambda: None, commission_reward_budget=1)
    a.begin_commission()
    gen = b.snapshot['generation']
    a._commission_context.reward_claim_receipt = ActionReceipt('reward/commission/finish', gen-2, None, None, 'previous-claim')
    a._commission_context.reward_detected_count = 1
    a._commission_context.reward_close_receipts = [ActionReceipt('reward/ship-exp/close', gen-1, None, None, 'previous-close')]
    return b, o, a


def test_actual_fresh_sidebar_allows_next_budgeted_native_claim_cycle():
    b, o, a = next_cycle()
    previous = a._commission_context.reward_claim_receipt
    assert o.reward_summary_count('commission', 'finished') == 1
    assert o.enabled('reward/commission/finish')
    result = a.click('REWARD_1')
    assert result != previous
    assert len(b.taps) == 1
    assert a._action_ledger.remaining('commission.reward') == 0
    assert len(a._commission_context.reward_prior_claims) == 1
    assert a._commission_context.reward_prior_claims[0][0] == previous
    assert len(a._commission_context.reward_prior_claims[0][1]) == 1
    assert a.click('REWARD_1_WHITE') == result
    assert len(b.taps) == 1


@pytest.mark.parametrize('case', ['same-claim-generation', 'same-close-generation'])
def test_duplicate_request_before_a_completed_cycle_reuses_receipt(case):
    b, o, a = next_cycle()
    if case == 'same-claim-generation':
        a._commission_context.reward_close_receipts = []
        old = a._commission_context.reward_claim_receipt
        a._commission_context.reward_claim_receipt = ActionReceipt(old.semantic_id, b.snapshot['generation'], None, None, old.path)
    else:
        old = a._commission_context.reward_close_receipts[-1]
        a._commission_context.reward_close_receipts[-1] = ActionReceipt(old.semantic_id, b.snapshot['generation'], None, None, old.path)
    previous = a._commission_context.reward_claim_receipt
    assert a.click('REWARD_1') == previous
    assert not b.taps


def test_fresh_settled_sidebar_without_popup_allows_native_budgeted_retry():
    b, o, a = next_cycle()
    a._commission_context.reward_close_receipts = []
    old = a._commission_context.reward_claim_receipt
    receipt = a.click('REWARD_1')
    assert receipt != old
    assert len(b.taps) == 1
    assert a._action_ledger.remaining('commission.reward') == 0
    assert a._commission_context.reward_prior_claims == [(old, (), 1)]
    assert a.click('REWARD_1_WHITE') == receipt
    assert len(b.taps) == 1


@pytest.mark.parametrize('case', ['truncated', 'foreign-package', 'duplicate-finish'])
def test_next_cycle_revalidates_input_boundary(case):
    b, o, a = next_cycle()
    if case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'foreign-package':
        b.snapshot['package'] = 'unrelated.package'
    else:
        target = o._unique(o.read_state(), 'reward/commission/finish')
        b.buttons['buttons'].append(copy.deepcopy(next(v for v in b.buttons['buttons'] if v['path']==target.path)))
        b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        a.click('REWARD_1')
    assert not b.taps


@pytest.mark.parametrize('with_close', [False, True])
def test_next_cycle_exhaustion_defers_instead_of_reusing_old_claim_forever(with_close):
    b, o, previous_adapter = next_cycle()
    if not with_close:
        previous_adapter._commission_context.reward_close_receipts = []
    a = AlasSemanticAdapter(o, lambda: None, commission_reward_budget=0)
    a._commission_context = previous_adapter._commission_context
    with pytest.raises(AlasSemanticActionDeferred):
        a.click('REWARD_1')
    assert not b.taps


def test_no_popup_retry_remains_closed_while_loading_covers_sidebar():
    b, o, a = next_cycle()
    a._commission_context.reward_close_receipts = []
    old = a._commission_context.reward_claim_receipt
    loading = copy.deepcopy(b.buttons['buttons'][0])
    loading['path'] = 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)/loading'
    b.buttons['buttons'].append(loading)
    b.buttons['button_count'] = len(b.buttons['buttons'])
    assert a.click('REWARD_1') == old
    assert not b.taps
