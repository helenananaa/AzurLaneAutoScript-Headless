import pytest
from alas_headless import AlasSemanticUnmapped
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP'])
def test_reward_hub_proves_generic_reward_absence_without_task_context(name):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.enabled_values['reward/page/back'] = True
    assert adapter.appear(NamedButton(name)) is False
    assert oracle.click_calls == []


def test_obscured_reward_hub_does_not_prove_reward_absence():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.enabled_values['reward/page/back'] = False
    with pytest.raises(AlasSemanticUnmapped):
        adapter.appear(NamedButton('GET_ITEMS_1'))
    assert oracle.click_calls == []


@pytest.mark.parametrize('ready', [False, True])
@pytest.mark.parametrize('child', ['reward/commission/go', 'reward/commission/finish',
                                 'reward/tactical/go', 'reward/tactical/finish',
                                 'reward/research/go', 'reward/research/finish'])
def test_ready_reward_hub_does_not_inherit_previous_mission_context(ready, child):
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._mission_context=object() if ready else None
    oracle.exists_values['reward/page/back']=True
    oracle.enabled_values['reward/page/back']=False
    for target in ('reward/commission/go', 'reward/commission/finish',
                   'reward/tactical/go', 'reward/tactical/finish',
                   'reward/research/go', 'reward/research/finish'):
        oracle.enabled_values[target] = False
    oracle.enabled_values[child]=ready
    if ready:
        assert not adapter.appear(NamedButton('GET_ITEMS_1'))
        assert adapter.appear(NamedButton('REWARD_CHECK'))
        for alias in ('GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'):
            assert not adapter.appear(NamedButton(alias))
    else:
        with pytest.raises(AlasSemanticUnmapped):adapter.appear(NamedButton('GET_ITEMS_1'))
    assert oracle.click_calls==[]


@pytest.mark.parametrize('covered', [False, True])
def test_sidebar_ready_uses_real_oracle_blocker_and_target_proof(covered):
    from alas_headless.adapter.semantic.dispatch_observation import DispatchObservationPorts
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    root='OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
    buttons=[make_button('CommissionInfoUI4Mellow(Clone)',root,raycast_top=False),
             make_button('finish_btn',root+'/frame/main/content/technology/frame/finish_btn')]
    if covered:
        buttons.append(make_button('cancel_button',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button'))
    backend=FakeBackend(buttons)
    oracle=make_oracle(backend)
    assert DispatchObservationPorts._reward_sidebar_ready(oracle) is (not covered)
    assert backend.taps==[]


@pytest.mark.parametrize('name', ['WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM',
    'MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION',
    'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD', 'MONTHLY_PASS_NOTICE'])
@pytest.mark.parametrize('retained_context', [False, True])
def test_ready_sidebar_owns_unrelated_campaign_probes(name, retained_context):
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    root = 'OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
    backend = FakeBackend([
        make_button('CommissionInfoUI4Mellow(Clone)', root, raycast_top=False),
        make_button('go_btn', root+'/frame/main/content/class/frame/go_btn'),
    ])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    if retained_context: adapter._campaign_context = object()
    assert adapter.appear(NamedButton(name)) is False
    assert backend.taps == []


def test_obscured_sidebar_does_not_hide_withdraw_confirmation():
    from alas_headless import AlasSemanticAdapter, SemanticGateClosed
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    root = 'OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
    backend = FakeBackend([
        make_button('CommissionInfoUI4Mellow(Clone)', root, raycast_top=False),
        make_button('go_btn', root+'/frame/main/content/class/frame/go_btn'),
        make_button('cancel_button', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button'),
    ])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))
    assert backend.taps == []


@pytest.mark.parametrize('covered', [False, True])
def test_monthly_probe_requires_real_unobscured_reward_hub(covered):
    from alas_headless import AlasSemanticAdapter, SemanticGateClosed
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    root = 'OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)'
    records = [make_button('CommissionInfoUI4Mellow(Clone)', root, raycast_top=False),
               make_button('go_btn', root+'/frame/main/content/class/frame/go_btn')]
    if covered:
        records.append(make_button('cancel_button',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button'))
    backend = FakeBackend(records)
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    if covered:
        with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
            adapter.appear(NamedButton('MONTHLY_PASS_NOTICE'))
    else:
        assert adapter.appear(NamedButton('MONTHLY_PASS_NOTICE')) is False
    assert backend.taps == []
