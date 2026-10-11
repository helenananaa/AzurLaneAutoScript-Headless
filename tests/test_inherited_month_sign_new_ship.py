"""An actual month-sign ship popup must reach ALAS' existing popup handler."""
import copy
import pytest

from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def ship_host(drift=False):
    b, o, a = host(drift, 'month-sign-new-ship-r136.json')
    # Controlled static replay: keep the original fixture unchanged, and model
    # subsequent reads of this same settled tree at its later UI generation.
    generation = b.ui['generation']
    b.snapshot['generation'] = b.buttons['generation'] = generation
    return b, o, a


@pytest.mark.parametrize('drift', [False, True])
def test_inherited_ship_hides_month_sign_and_reaches_native_handler(drift):
    b, o, a = ship_host(drift)
    a.begin_tactical()
    assert o.new_ship_reward_visible()
    for name in ('FLEET_CHECK', 'EVENT_LIST_CHECK', 'GOTO_MAIN', 'GET_ITEMS_1',
                 'CAMPAIGN_WITHDRAW_CONFIRM', 'POPUP_SINGLE_WHITE', 'GET_MISSION',
                 'AUTO_SEARCH_REWARD', 'GAME_TIPS', 'DORM_TROPHY_CONFIRM'):
        assert a.appear(name) is False
    assert a.appear('GET_SHIP') is True
    before = a._action_ledger.remaining('tactical.reward')
    def close():
        b.snapshot['generation'] += 1
        b.buttons['generation'] = b.ui['generation'] = b.snapshot['generation']
        b.buttons['buttons'] = [v for v in b.buttons['buttons'] if 'NewShipUI(Clone)' not in v['path']]
        b.buttons['button_count'] = len(b.buttons['buttons'])
    b.on_tap = close
    receipt = a.click('GET_SHIP')
    assert receipt.semantic_id == 'reward/new-ship/continue'
    assert len(b.taps) == 1
    assert a._commission_context.tactical_reward_receipt is None
    assert a._action_ledger.remaining('tactical.reward') == before


@pytest.mark.parametrize('case', ['duplicate', 'foreign-modal', 'truncated', 'foreign-package', 'identity', 'stale', 'foreground'])
def test_inherited_ship_keeps_complete_input_proof(case):
    b, o, a = ship_host()
    if case == 'duplicate':
        b.buttons['buttons'].append(copy.deepcopy(next(v for v in b.buttons['buttons'] if v['path'].endswith('/shake_panel/click'))))
    elif case == 'foreign-modal':
        b.buttons['buttons'].append(make_button('confirm', 'root/UIOverlay/Msgbox(Clone)/confirm'))
    elif case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'foreign-package':
        b.snapshot['package'] = 'unrelated.package'
    elif case == 'stale':
        b.snapshot['age_ms'] = 10001
    elif case == 'foreground':
        b.foreground = 'unrelated.package/OtherActivity'
    else:
        next(v for v in b.ui['texts'] if v['path'].endswith('/dialogue/bg/name'))['text'] = 'different identity'
    b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        a.click('GET_SHIP')
    assert not b.taps


def test_uncertain_inherited_acknowledgement_never_retries_input(monkeypatch):
    import itertools
    import alas_headless.adapter.semantic.dispatch_actions as actions
    b, o, a = ship_host()
    clock = itertools.count(step=13.0)
    monkeypatch.setattr(actions.time, 'monotonic', lambda: next(clock))
    with pytest.raises(SemanticGateClosed, match='postcondition unavailable'):
        a.click('GET_SHIP')
    assert len(b.taps) == 1


def test_mounting_ship_hides_underlay_without_authorizing_acknowledgement():
    b, o, a = ship_host()
    # Controlled additive/mount drift of the actual settled result fixture:
    # the companion dialogue has not mounted, but the popup owns the page.
    b.ui['texts'] = [v for v in b.ui['texts'] if not v['path'].endswith('/dialogue/bg/name')]
    b.ui['text_count'] = len(b.ui['texts'])
    assert o.new_ship_reward_page_visible()
    assert not o.new_ship_reward_visible()
    assert a.appear('EVENT_LIST_CHECK') is False
    assert a.appear('GET_SHIP') is False
    with pytest.raises(SemanticGateClosed):
        a.click('GET_SHIP')
    assert not b.taps
