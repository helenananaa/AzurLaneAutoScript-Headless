"""Unrelated pass notices do not block native idle return from the exact META menu."""
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button
from tests.test_meta_reward_entry import SYN, make_oracle, sync_backend

NATIVE_IDLE_PROBES = (
    'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
    'POPUP_SINGLE_WHITE', 'PLAYER_CHECK', 'GAME_TIPS', 'DORM_TROPHY_CONFIRM',
    'MEOWFFICER_INFO', 'MEOWFFICER_BUY', 'MAINTENANCE_ANNOUNCE',
    'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION', 'WITHDRAW',
)

@pytest.mark.parametrize('drift',[False,True])
def test_actual_inherited_meta_menu_proves_absence_without_task_context(drift):
    backend,oracle,adapter=host(drift,'meta-character-idle-r34.json')
    assert oracle.meta_character_menu_visible()
    assert adapter._meta_assist_active is False
    for name in NATIVE_IDLE_PROBES:
        assert adapter.appear(name) is False
    assert not backend.taps


def test_foreground_modal_does_not_inherit_meta_notice_absence():
    backend,oracle,adapter=host(fixture='meta-character-idle-r34.json')
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count']+=1
    with pytest.raises(AlasSemanticUnmapped):adapter.appear('MONTHLY_PASS_NOTICE')
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_inherited_sync_reward_frame_proves_notice_absence(drift):
    backend = sync_backend()
    if drift:
        backend.buttons['buttons'][0]['path'] = SYN + 'TaskPanel/BtnGetAll'
        backend.buttons['buttons'][0]['name'] = 'BtnGetAll'
        backend.ui['images'][0]['path'] = SYN + 'TaskPanel/BtnGetAll'
        backend.ui['texts'].reverse()
        backend.ui['optional_metadata'] = {'new_field': True}
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    assert not oracle.meta_character_menu_visible()
    assert oracle.meta_character_sync_rewards() == (250, 2, 2)
    for name in NATIVE_IDLE_PROBES:
        assert adapter.appear(name) is False
    assert not backend.taps


@pytest.mark.parametrize('case', ['modal', 'ambiguous-control', 'unknown-sprite',
                                 'incoherent-ui', 'foreign-package'])
def test_inherited_sync_notice_absence_requires_complete_owner(case):
    backend = sync_backend()
    if case == 'modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif case == 'ambiguous-control':
        backend.buttons['buttons'].append(make_button('BtnGetAll', SYN + 'TaskPanel/BtnGetAll'))
    elif case == 'unknown-sprite':
        backend.ui['images'][0]['sprite'] = 'unknown'
    elif case == 'incoherent-ui':
        backend.ui['generation'] += 3
    else:
        backend.snapshot['package'] = 'unrelated.package'
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter._appear_once('MONTHLY_PASS_NOTICE')
    assert not backend.taps



def test_accepted_meta_back_yields_once_during_unmounted_destination_gap():
    import time
    from types import SimpleNamespace
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    previous=SimpleNamespace(semantic_id='meta/character/back')
    adapter._inherited_home_return_receipt=previous
    adapter._inherited_home_return_until=time.monotonic()+12
    adapter._goto_main_target=lambda:None
    oracle.enabled_values['overlay/network-reconnect/confirm']=False
    oracle.main_page_visible=lambda:False
    assert adapter._click_main('GOTO_MAIN',None) is previous
    assert adapter._inherited_home_return_receipt is None
    assert not oracle.click_calls
    with pytest.raises(AlasSemanticUnmapped):adapter._click_main('GOTO_MAIN',None)
    assert not oracle.click_calls
