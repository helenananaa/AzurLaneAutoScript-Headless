"""Native META recovery may leave its own precombat overlay after a result."""
import copy
import re

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import make_button
from tests.test_opsi_repair_input_frame import host


def setup(drift=False):
    backend, session = host('meta-assist-precombat-back-r1254.json')
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['compatible_extra'] = True
    session.begin_meta_assist()
    session.open().oracle._sleep = lambda _: None
    return backend, session


@pytest.mark.parametrize('drift', [False, True])
def test_retained_meta_recovery_back_uses_owned_coherent_frame_once(drift):
    backend, session = setup(drift)
    assert session.open().oracle.meta_assist_state().remaining_attempts == 2
    receipt = session.click('BACK_ARROW')
    assert receipt.semantic_id == 'daily/precombat/back'
    assert len(backend.taps) == 1
    assert session.open()._meta_precombat_back_receipt is receipt
    assert session.action_ledger.remaining('shop.purchase') == 0


def test_daily_back_still_rejects_meta_underlay_without_owned_port():
    backend, session = setup()
    with pytest.raises(SemanticGateClosed, match='meta-assist'):
        session.open().oracle.click_daily_precombat_back()
    assert backend.taps == []


def test_exhausted_attempts_do_not_prevent_return_navigation():
    backend, session = setup()
    for text in backend.ui['texts']:
        if text['path'].endswith('CurrentWorldBossChallengeUI(Clone)/point/Text'):
            text['text'] = '0/3'
    assert session.click('BACK_ARROW').semantic_id == 'daily/precombat/back'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['foreign', 'loading', 'modal', 'duplicate',
                                 'covered', 'ambiguous', 'malformed', 'incoherent',
                                 'stale', 'package'])
def test_invalid_owner_or_target_never_dispatches(case):
    backend, session = setup()
    if case == 'foreign':
        backend.foreground = 'other.package/.Activity'
    elif case in ('loading', 'modal'):
        path = ('OverlayCamera/Overlay/UIOverlay/Loading(Clone)/block' if case == 'loading'
                else 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')
        backend.buttons['buttons'].append(make_button('block', path))
        backend.buttons['button_count'] += 1
    elif case in ('duplicate', 'covered'):
        target = next(b for b in backend.buttons['buttons']
                      if b['path'].endswith('PreCombatUI(Clone)/blur_panel/top/back_btn'))
        if case == 'duplicate':
            backend.buttons['buttons'].append(copy.deepcopy(target))
            backend.buttons['button_count'] += 1
        else:
            target['raycast_top'] = False
    elif case == 'ambiguous':
        selected = next(t for t in backend.ui['texts'] if '/selected/' in t['path'])
        extra = copy.deepcopy(selected)
        extra['path'] = re.sub(r'/container/[0-9]+/', '/container/99/', extra['path'])
        backend.ui['texts'].append(extra)
        backend.ui['text_count'] += 1
    elif case == 'malformed':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/point/Text'))['text'] = 'unknown'
    elif case == 'incoherent':
        backend.ui['generation'] += 3
    elif case == 'stale':
        backend.snapshot['age_ms'] = 20000
    else:
        backend.snapshot['package'] = 'other.package'
    with pytest.raises(SemanticGateClosed):
        session.click('BACK_ARROW')
    assert backend.taps == []
