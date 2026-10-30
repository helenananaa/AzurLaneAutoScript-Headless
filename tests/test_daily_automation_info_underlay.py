"""Daily's retained selector cannot block its proven automation-info modal."""
from copy import deepcopy
import pytest
from alas_headless import AlasSemanticSession,SemanticGateClosed
from alas_headless.adapter import semantic_runtime_fingerprint_sha256
from tests.test_game_tips_loading_presence import host
from tests.test_combat_automation_info import backend as popup_backend
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
from tests.semantic_support.observer_fixtures import make_button
from tests.test_presence_driven_reward_refresh import session_for
from tests.test_alas_config_branch_compatibility import method
from types import SimpleNamespace
from unittest.mock import Mock


def actual(drift=False):
    b,o,_=host(drift,'daily-classic-precombat-20261027.json')
    popup=popup_backend()
    # Controlled static observer turn; original fixtures remain unchanged.
    generation=max(x['generation']for x in (b.snapshot,b.buttons,b.ui))
    for part in (b.snapshot,b.buttons,b.ui):part['generation']=generation
    b.buttons['buttons']+=deepcopy([v for v in popup.buttons['buttons']if '/Msgbox(Clone)/'in v['path']])
    b.buttons['button_count']=len(b.buttons['buttons'])
    b.ui['texts']+=deepcopy(popup.ui['texts']);b.ui['text_count']=len(b.ui['texts'])
    return b,o


def dismiss(b):
    for packet in (b.snapshot,b.buttons,b.ui):packet['generation']+=1
    b.buttons['buttons']=[v for v in b.buttons['buttons']if '/Msgbox(Clone)/'not in v['path']]
    b.buttons['button_count']=len(b.buttons['buttons'])
    b.ui['texts']=[v for v in b.ui['texts']if '/Msgbox(Clone)/'not in v['path']]
    b.ui['text_count']=len(b.ui['texts'])


@pytest.mark.parametrize('drift',[False,True])
def test_information_owner_accepts_real_daily_underlay_and_restores_precombat(drift):
    b,o=actual(drift);b.on_tap=lambda:dismiss(b)
    assert o.combat_automation_info_visible()
    receipt=o.click_combat_automation_info()
    assert receipt.semantic_id=='os/precombat/info/confirm'and len(b.taps)==1
    assert o.daily_precombat_visible()and not o.combat_automation_info_visible()


@pytest.mark.parametrize('damage',['loading','foreign-choice','foreign-title','no-precombat','covered','duplicate-choice'])
def test_daily_underlay_never_yields_to_an_unproven_or_covered_information_target(damage):
    b,o=actual()
    if damage=='loading':b.buttons['buttons'].append(make_button('Loading(Clone)','OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    if damage in ('covered','duplicate-choice'):
        target=next(v for v in b.buttons['buttons']if '/Msgbox(Clone)/window/button_container/'in v['path'])
        if damage=='covered':target['raycast_top']=False
        else:b.buttons['buttons'].append(deepcopy(target))
    if damage=='foreign-choice':b.ui['texts'][-1]['text']='购买'
    if damage=='foreign-title':b.ui['texts'][-2]['text']='是否购买资源'
    if damage=='no-precombat':b.buttons['buttons']=[v for v in b.buttons['buttons']if '/PreCombatUI(Clone)/'not in v['path']]
    b.buttons['button_count']=len(b.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):o.click_combat_automation_info()
    assert not b.taps


def test_actual_session_preinput_information_proof_uses_its_fresh_frame():
    b,_=actual();b.on_tap=lambda:dismiss(b)
    revision=b.snapshot['driver_revision']
    handle=FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(package=b.snapshot['package'],
        component=b.foreground,driver_revision=revision,required_primary_abi='x86_64'))
    handle.pid=b.snapshot['pid'];handle.observer_request=b.request;handle.foreground_component=b.foreground_component
    handle.tap,handle.swipe=b.tap,b.swipe
    session=AlasSemanticSession(driver_revision=revision,runtime_handle=handle)
    try:
        session.refresh_frame();adapter=session.open();adapter._daily_kind='advance_mission'
        live=adapter._live_oracle;original=live._combat_automation_info_state
        def no_split_before_tap(*args,**kwargs):
            if not b.taps:raise AssertionError('input proof used split live pair')
            return original(*args,**kwargs)
        live._combat_automation_info_state=no_split_before_tap
        assert session.click('AUTOMATION_CONFIRM').semantic_id=='os/precombat/info/confirm'
        assert len(b.taps)==1
    finally:session.close()


@pytest.mark.parametrize('damage',[None,'missing-daily','duplicate-daily','other-underlay'])
def test_inherited_information_owner_is_only_unique_ordinary_daily_precombat(damage):
    b,o=actual()
    rows=[v for v in b.buttons['buttons']if '/DailyLevelUI(Clone)/list_panel/list/'in v['path']]
    if damage=='missing-daily':b.buttons['buttons']=[v for v in b.buttons['buttons']if v not in rows]
    if damage=='duplicate-daily':b.buttons['buttons'].append(deepcopy(rows[0]))
    if damage=='other-underlay':
        for row in rows:row['path']=row['path'].replace('DailyLevelUI(Clone)','WorldBossUI(Clone)')
    b.buttons['button_count']=len(b.buttons['buttons'])
    assert o.inherited_daily_automation_info_visible()is(damage is None)
    assert not b.taps


def test_original_daily_recovery_acks_information_before_attempting_back():
    b,o=actual();session,adapter=session_for(o);adapter._minigame_context=None
    assert adapter._daily_kind is None
    events=[]
    def accepted():events.append('ack');dismiss(b)
    b.on_tap=accepted
    class ReachedBack(Exception):pass
    def back():
        assert not o.combat_automation_info_visible()
        events.append('back');raise ReachedBack
    session.click_daily_precombat_back=back
    handler=method('module/combat/combat.py','Combat','handle_combat_automation_confirm',
        AUTOMATION_CONFIRM_CHECK='AUTOMATION_CONFIRM_CHECK',AUTOMATION_CONFIRM='AUTOMATION_CONFIRM')
    recovery=method('module/daily/daily.py','Daily','daily_run_one',logger=Mock())
    runner=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session,sleep=Mock(),
        screenshot=lambda:events.append('screenshot')),
        appear=lambda b,**_:session.appear(b),
        appear_then_click=lambda b,**_:session.click_if_present(b)is not None)
    runner.handle_combat_automation_confirm=lambda:handler(runner)
    with pytest.raises(ReachedBack):recovery(runner)
    assert events==['ack','screenshot','back']and len(b.taps)==1


def test_inherited_owner_must_still_be_daily_on_the_actual_input_frame():
    b,o=actual();session,adapter=session_for(o);adapter._minigame_context=None
    def changed():
        for row in b.buttons['buttons']:
            if '/DailyLevelUI(Clone)/'in row['path']:row['path']=row['path'].replace('DailyLevelUI(Clone)','OtherScene(Clone)')
    session.refresh_frame.side_effect=changed
    with pytest.raises(SemanticGateClosed,match='inherited Daily information owner changed'):
        session.click('AUTOMATION_CONFIRM')
    assert not b.taps
