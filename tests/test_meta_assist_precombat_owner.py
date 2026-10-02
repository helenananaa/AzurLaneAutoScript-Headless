import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui)

ROOT = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/'

def fixture():
    b = FakeBackend([]); o = make_oracle(b)
    start = o._targets['meta/assist/start']
    b.buttons['buttons'] = [
        make_button(start.name, 'root/'+start.path_suffix, raycast_top=False),
        make_button('5', ROOT+'list_panel/mask/bg/container/5'),
        make_button('start', 'OverlayCamera/Overlay/UIMain/PreCombatUI(Clone)/adapt/right/start', raycast_top=None)]
    b.buttons['button_count'] = 3
    b.ui = make_ui([
        make_text('',ROOT+'list_panel/mask/bg/container/5/selected/challenging/Text'),
        make_text('3/3',ROOT+'point/Text'),
        make_text('HP:1820000',ROOT+'main/hp/Text'),
        make_text('15',ROOT+'main/hp/level/Text')])
    return b,o

def test_owned_assist_start_accepts_exact_underlay_and_preserves_daily_isolation():
    b,o = fixture()
    with pytest.raises(SemanticGateClosed, match='meta-assist'):
        o.click_daily_precombat_start()
    assert not b.taps
    receipt = o.click_meta_assist_precombat_start()
    assert receipt.semantic_id == 'daily/precombat/start'
    assert len(b.taps) == 1

@pytest.mark.parametrize('case', ['empty', 'missing_candidate', 'ambiguous', 'wrong_level', 'truncated', 'coherence', 'loading', 'foreign_modal', 'foreground'])
def test_unproven_assist_owner_or_foreign_blocker_never_grants_input(case):
    b,o = fixture()
    if case == 'empty': b.ui['texts'][1]['text'] = '0/3'
    elif case == 'missing_candidate': b.buttons['buttons'] = [b.buttons['buttons'][0],b.buttons['buttons'][2]]; b.buttons['button_count'] = 2
    elif case == 'ambiguous':
        b.ui['texts'].append(make_text('',ROOT+'list_panel/mask/bg/container/6/selected/challenging/Text')); b.ui['text_count'] += 1
    elif case == 'wrong_level': b.ui['texts'][3]['text'] = '未知'
    elif case == 'truncated': b.ui['texts'][2]['flags'] |= 0x10
    elif case == 'coherence': b.ui['generation'] += 3
    elif case in ('loading','foreign_modal'):
        path = ('OverlayCamera/Overlay/UIOverlay/Loading(Clone)/block' if case == 'loading'
                else 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')
        b.buttons['buttons'].append(make_button('block',path)); b.buttons['button_count'] += 1
    else: o._foreground_component = lambda: 'com.android.launcher/.Launcher'
    with pytest.raises(SemanticGateClosed): o.click_meta_assist_precombat_start()
    assert not b.taps
