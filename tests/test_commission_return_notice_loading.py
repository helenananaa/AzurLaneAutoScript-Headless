import time,copy
import pytest
from alas_headless import AlasSemanticUnmapped,SemanticGateClosed
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('drift',[False,True])
@pytest.mark.parametrize('fixture',['commission-return-notice-loading-r59.json','commission-return-meow-loading-r80.json'])
def test_accepted_commission_return_yields_notices_during_its_loading(drift,fixture):
    b,o,a=host(drift,fixture)
    a._commission_return_transition_until=time.monotonic()+12
    for name in ('MONTHLY_PASS_NOTICE','BATTLE_PASS_NOTICE','BATTLE_PASS_NEW_SEASON','MEOWFFICER_INFO','MEOWFFICER_BUY','MAINTENANCE_ANNOUNCE'):
        assert a.appear(name) is False
        with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):a.click(name)
    assert not b.taps

@pytest.mark.parametrize('case',['no-return','expired','other-modal','duplicate-back','foreign'])
@pytest.mark.parametrize('name',['MONTHLY_PASS_NOTICE','MEOWFFICER_INFO','MAINTENANCE_ANNOUNCE'])
def test_known_loading_covers_notices_without_return_input_authority(case,name):
    b,o,a=host(fixture='commission-return-notice-loading-r59.json')
    a._commission_return_transition_until=time.monotonic()+12
    if case=='no-return':a._commission_return_transition_until=0
    if case=='expired':a._commission_return_transition_until=time.monotonic()-1
    if case=='foreign':b.foreground='other/.Activity'
    if case=='other-modal':
        from tests.semantic_support.observer_fixtures import make_button
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'));b.buttons['button_count']+=1
    if case=='duplicate-back':
        b.buttons['buttons'].append(copy.deepcopy(next(x for x in b.buttons['buttons'] if x['path'].endswith('/EventUI(Clone)/blur_panel/adapt/top/back_btn'))));b.buttons['button_count']+=1
    if case in ('other-modal', 'foreign'):
        with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):a.appear(name)
    else:
        # The complete known loading layer itself covers these passive probes.
        # A return lease or its hidden back target is not an input authority.
        assert a.appear(name) is False
    with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):a.click(name)
    assert not b.taps

@pytest.mark.parametrize('drift',[False,True])
def test_reward_sidebar_proves_maintenance_notice_absent_without_admitting_input(drift):
    b,o,a=host(drift,fixture='commission-next-finished-cycle-r142.json')
    assert a.appear('MAINTENANCE_ANNOUNCE') is False
    with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):a.click('MAINTENANCE_ANNOUNCE')
    assert not b.taps

def test_foreign_prompt_keeps_its_blocker_and_cannot_be_dismissed_as_maintenance():
    b,o,a=host(fixture='commission-next-finished-cycle-r142.json')
    from tests.semantic_support.observer_fixtures import make_button
    b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b.buttons['button_count']+=1
    assert not a._reward_sidebar_ready(o)
    assert o._blocking_rules(o.read_state(),'reward/page/back')
    # Existing generic observation can classify unrelated notices as absent;
    # that must never permit this alias to dismiss the actual prompt.
    a.appear('MAINTENANCE_ANNOUNCE')
    with pytest.raises((AlasSemanticUnmapped,SemanticGateClosed)):a.click('MAINTENANCE_ANNOUNCE')
    assert not b.taps
