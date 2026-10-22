"""AwardInfo can mount after accepted EXP input before close is actionable.

The live r522 traceback shows AwardInfo at generation232636; its complete frame
was not retained before ALAS' error handler refreshed. Replay below uses the
retained r77 hierarchy with an explicitly modeled mounting close Button.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def mounting(drift=False, close='missing'):
    b, o, a = host(drift, 'commission-award-close-r77.json')
    a.begin_commission()
    generation = b.snapshot['generation']
    c = a._commission_context
    c.reward_claim_receipt = ActionReceipt('reward/commission/finish', generation-2, None, None, 'claim')
    c.reward_close_receipts = [ActionReceipt('reward/ship-exp/close', generation-1, None, None, 'exp')]
    target = o._unique(o.read_state(), 'reward/award-info/close')
    if close == 'missing':
        b.buttons['buttons'] = [x for x in b.buttons['buttons'] if x['path'] != target.path]
    else:
        next(x for x in b.buttons['buttons'] if x['path'] == target.path)['raycast_top'] = False
    b.buttons['button_count'] = len(b.buttons['buttons'])
    return b, o, a


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
@pytest.mark.parametrize('close', ['missing', 'covered'])
@pytest.mark.parametrize('drift', [False, True])
def test_known_mount_returns_to_native_screenshot_without_input_or_new_receipt(name, close, drift):
    b, _, a = mounting(drift, close)
    before = tuple(a._commission_context.reward_close_receipts)
    assert a.click(name) is None
    assert tuple(a._commission_context.reward_close_receipts) == before
    assert not b.taps and not b.swipes


@pytest.mark.parametrize('damage', ['no-claim', 'no-close', 'expired', 'same-generation',
                                  'foreign', 'stale', 'truncated', 'duplicate-owner',
                                  'foreign-modal', 'loading', 'ship-exp'])
def test_passive_mount_wait_does_not_hide_unproven_or_obscured_state(damage):
    b, _, a = mounting()
    c = a._commission_context
    if damage == 'no-claim':
        c.reward_claim_receipt = None
    elif damage == 'no-close':
        c.reward_close_receipts.clear()
    elif damage == 'expired':
        c.passive_transition_until = 0
    elif damage == 'same-generation':
        c.reward_close_receipts[-1] = ActionReceipt('reward/ship-exp/close', b.snapshot['generation'], None, None, 'exp')
    elif damage == 'foreign':
        b.foreground = 'other/.Activity'
    elif damage == 'stale':
        b.snapshot['age_ms'] = 10001
    elif damage == 'truncated':
        b.buttons['truncated'] = True
    elif damage == 'duplicate-owner':
        other = deepcopy(next(x for x in b.buttons['buttons'] if '/AwardInfoUI(Clone)/' in x['path']))
        other['path'] = 'OtherCanvas/' + other['path']
        b.buttons['buttons'].append(other)
    elif damage == 'foreign-modal':
        b.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif damage == 'loading':
        b.buttons['buttons'].append(make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    else:
        b.buttons['buttons'].append(make_button('skipLayer',
            'OverlayCamera/Overlay/UIMain/ShipExpUI(Clone)/skipLayer'))
    b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        a.click('GET_ITEMS_1')
    assert not b.taps and not b.swipes
