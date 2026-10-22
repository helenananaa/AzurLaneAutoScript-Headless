"""A final EXP may return to the sidebar before native award aliases run."""
import copy
from dataclasses import replace

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import make_button
from tests.test_commission_next_reward_cycle import next_cycle


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
@pytest.mark.parametrize('drift', [False, True])
def test_final_exp_to_sidebar_returns_to_original_loop_without_input_or_fake_receipt(name, drift):
    backend, _, adapter = next_cycle()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.snapshot['optional_metadata'] = {'upstream': 'new'}
    before = tuple(adapter._commission_context.reward_close_receipts)
    assert adapter.click(name) is None
    assert not backend.taps
    assert tuple(adapter._commission_context.reward_close_receipts) == before
    assert adapter._action_ledger.remaining('commission.reward') == 1


@pytest.mark.parametrize('case', ['no_claim', 'no_close', 'same_generation', 'expired',
                                 'foreign', 'loading', 'duplicate_sidebar', 'unknown'])
def test_unproven_departure_remains_closed(case):
    backend, oracle, adapter = next_cycle()
    context = adapter._commission_context
    if case == 'no_claim':
        context.reward_claim_receipt = None
    elif case == 'no_close':
        context.reward_close_receipts.clear()
    elif case == 'same_generation':
        context.reward_close_receipts[-1] = replace(context.reward_close_receipts[-1],
                                                   generation=backend.snapshot['generation'])
    elif case == 'expired':
        context.passive_transition_until = 0
    elif case == 'foreign':
        backend.foreground = 'other.package/.Activity'
    elif case == 'loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    elif case == 'duplicate_sidebar':
        target = oracle._unique(oracle.read_state(), 'reward/page/back')
        backend.buttons['buttons'].append(copy.deepcopy(next(
            b for b in backend.buttons['buttons'] if b['path'] == target.path)))
    else:
        backend.buttons['buttons'] = []
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        adapter.click('GET_ITEMS_1')
    assert not backend.taps
