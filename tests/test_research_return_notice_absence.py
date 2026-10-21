"""Original idle return probes notices through Research loading and its menu."""
from copy import deepcopy

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('phase', ['loading', 'menu'])
@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE',
                                 'BATTLE_PASS_NEW_SEASON', 'MAINTENANCE_ANNOUNCE',
                                 'MEOWFFICER_INFO', 'MEOWFFICER_BUY'])
def test_retained_return_frames_yield_unrelated_notices_without_input(phase, drift, name):
    b, _, a = host(drift, 'research-return-notice-' + phase + '-r537.json')
    assert a._research_context is None
    assert a.appear(name) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        a.click(name)
    assert not b.taps and not b.swipes


@pytest.mark.parametrize('phase', ['loading', 'menu'])
@pytest.mark.parametrize('damage', ['foreign-modal', 'foreign', 'stale', 'truncated'])
def test_invalid_or_foreign_state_does_not_prove_notice_absence(phase, damage):
    b, _, a = host(fixture='research-return-notice-' + phase + '-r537.json')
    if damage == 'foreign-modal':
        b.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    elif damage == 'foreign':
        b.foreground = 'other/.Activity'
    elif damage == 'stale':
        b.snapshot['age_ms'] = 10001
    else:
        b.buttons['truncated'] = True
    if damage == 'foreign-modal' and phase == 'menu':
        # The existing generic Research-menu discovery returns passiveFalse
        # even with an unrelated mounted prompt. No notice input is granted.
        # Loading's new fast path must leave this to existing owner handling.
        from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
        assert a._appear_priority('MONTHLY_PASS_NOTICE') is UNHANDLED
        with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
            a.click('MONTHLY_PASS_NOTICE')
        assert not b.taps and not b.swipes
        return
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        a._appear_once('MONTHLY_PASS_NOTICE')
    assert not b.taps and not b.swipes


def test_ambiguous_menu_cannot_submit_back_or_notice_input():
    b, o, a = host(fixture='research-return-notice-menu-r537.json')
    target = o._unique(o.read_state(), 'research-menu/page/back')
    b.buttons['buttons'].append(deepcopy(next(x for x in b.buttons['buttons'] if x['path'] == target.path)))
    b.buttons['button_count'] += 1
    # Generic menu discovery already treats unrelated probes as passiveFalse.
    # This change grants no permission to cross an ambiguous input boundary.
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        o.click('research-menu/page/back')
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        a.click('MONTHLY_PASS_NOTICE')
    assert not b.taps and not b.swipes
