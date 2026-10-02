from types import SimpleNamespace

import pytest
from alas_headless import AlasSemanticUnmapped
import time

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from unittest.mock import Mock, patch


@pytest.mark.parametrize('blocker', ['loading', 'unknown-overlay'])
def test_mounted_loading_sidebar_does_not_repeat_source_toggle(blocker):
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'reward/page/back'
    oracle.enabled = lambda target: False
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=blocker)]
    oracle.click = Mock(side_effect=SemanticGateClosed('semantic target is not actionable'))
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    receipt = SimpleNamespace(generation=10)
    host._main_more_entry_receipt = receipt
    host._main_more_entry_until = time.monotonic() + 8.0
    if blocker == 'loading':
        assert host._click_mapped('GOTO_MAIN_MORE', 'main/more') is receipt
        oracle.click.assert_not_called()
    else:
        with pytest.raises(SemanticGateClosed):
            host._click_mapped('GOTO_MAIN_MORE', 'main/more')


def test_mission_more_receipt_waits_for_real_destination_without_another_input():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_mission_reward(daily=True, weekly=True)
    receipt = SimpleNamespace(generation=10)
    host._mission_context.summary_entry_receipt = receipt
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    oracle.enabled = Mock(side_effect=[False, True])
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep'):
        assert host._click_mapped('MAIN_GOTO_REWARD', 'main/more') is receipt
    assert oracle.click_calls == []


@pytest.mark.parametrize('blocker', [None, 'unknown-overlay'])
def test_mission_sidebar_mount_uses_exact_root_and_actionable_child(blocker):
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_mission_reward(daily=True, weekly=True)
    receipt = SimpleNamespace(generation=10)
    host._mission_context.summary_entry_receipt = receipt
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    oracle.observation_target_present = lambda target: target == 'reward/page/back'
    oracle.enabled = lambda target: target == 'reward/tactical/go'
    oracle._blocking_rules = lambda *_: ([SimpleNamespace(blocker_id=blocker)] if blocker else [])
    if blocker:
        with pytest.raises(SemanticGateClosed, match='obscured'):
            host._click_mapped('MAIN_GOTO_REWARD', 'main/more')
    else:
        assert host._click_mapped('MAIN_GOTO_REWARD', 'main/more') is receipt
    assert oracle.click_calls == []


def test_mission_more_receipt_does_not_hide_a_failed_or_obscured_entry():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_mission_reward(daily=True, weekly=True)
    host._mission_context.summary_entry_receipt = SimpleNamespace(generation=10)
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    oracle.enabled = lambda _: False
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.monotonic', side_effect=[0, 6]):
        with pytest.raises(SemanticGateClosed, match='postcondition was not observed'):
            host._click_mapped('MAIN_GOTO_REWARD', 'main/more')
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id='msgbox')]
    with pytest.raises(SemanticGateClosed, match='obscured'):
        host._click_mapped('MAIN_GOTO_REWARD', 'main/more')
    assert oracle.click_calls == []


@pytest.mark.parametrize('present,enabled,generation,reuse', [
    (True, True, 11, True),
    (False, True, 11, False),
    (True, False, 11, False),
    (True, True, 10, False),
])
def test_more_reuses_receipt_only_after_observed_sidebar_transition(present, enabled, generation, reuse):
    receipt = SimpleNamespace(generation=10)
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'reward/page/back' and present
    oracle.enabled = lambda target: target == 'reward/page/back' and enabled
    oracle.read_state = lambda: SimpleNamespace(generation=generation)
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._main_more_entry_receipt = receipt
    result = host._click_mapped('GOTO_MAIN_MORE', 'main/more')
    assert (result is receipt) == reuse
    assert oracle.click_calls == ([] if reuse else ['main/more'])


@pytest.mark.parametrize('blocker,expected_reuse', [
    (None, True),
    ('reward-page', True),
    ('loading', True),
    ('unknown-overlay', False),
])
def test_more_repeated_during_fresh_mount_does_not_send_second_input(blocker, expected_reuse):
    receipt = SimpleNamespace(generation=10)
    oracle = FakeOracle()
    oracle.click = lambda target: (_ for _ in ()).throw(
        SemanticGateClosed('semantic target is not actionable'))
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    oracle._blocking_rules = lambda state, target: (
        [SimpleNamespace(blocker_id=blocker)] if blocker else [])
    oracle.observation_target_present = lambda target: False
    oracle.main_page_visible = lambda: True
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._main_more_entry_receipt = receipt
    host._main_more_entry_until = time.monotonic() + 8.0
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep') as sleep:
        if expected_reuse:
            assert host._click_mapped('GOTO_MAIN_MORE', 'main/more') is receipt
        else:
            with pytest.raises(SemanticGateClosed, match='not actionable'):
                host._click_mapped('GOTO_MAIN_MORE', 'main/more')
        sleep.assert_not_called()


@pytest.mark.parametrize('blocker,main_visible', [
    ('ship-exp', False), ('award-info', False), (None, True),
])
def test_commission_reward_overlay_hides_main_page_from_alas(blocker, main_visible):
    oracle = FakeOracle()
    oracle.main_page_visible = lambda: True
    oracle._blocking_rules = lambda state, target: (
        [SimpleNamespace(blocker_id=blocker)] if blocker else [])
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert host.appear(NamedButton('MAIN_GOTO_FLEET')) is main_visible


def test_interrupted_commission_closes_only_exact_ship_exp_overlay():
    oracle = FakeOracle()
    oracle.enabled_values['reward/ship-exp/close'] = True
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    button = NamedButton('GET_ITEMS_1')
    host.begin_commission()
    assert host.appear(button)
    assert host.click(button).semantic_id == 'reward/ship-exp/close'
    host.end_commission()
    with pytest.raises(SemanticGateClosed):
        host.click(button)


def test_retained_commission_page_allows_unrelated_task_page_scan():
    oracle = FakeOracle()
    oracle.exists_values['commission/page/back'] = True
    oracle.enabled_values['commission/page/back'] = True
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert not host.appear(NamedButton('FLEET_CHECK'))
    assert not host.appear(NamedButton('EXERCISE_CHECK'))
    assert host.appear(NamedButton('COMMISSION_CHECK'))
    with pytest.raises(SemanticGateClosed):
        host.click(NamedButton('FLEET_CHECK'))
    assert host.click(NamedButton('BACK_ARROW')).semantic_id == 'commission/page/back'
    host.begin_mission_reward(daily=False, weekly=False)
    assert host.click(NamedButton('BACK_ARROW')).semantic_id == 'commission/page/back'
    oracle.exists_values['commission/page/back'] = False
    oracle.enabled_values['commission/page/back'] = False
    assert not host.appear(NamedButton('GET_MISSION'))
    assert not host.appear(NamedButton('GET_ITEMS_1'))
    oracle._campaign_urgent_notice_matches = lambda state: True
    with pytest.raises(SemanticGateClosed, match='urgent commission notice'):
        host.appear(NamedButton('GET_MISSION'))


def test_task_back_transition_passively_skips_unrelated_page_checks():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._record_mission_transition(SimpleNamespace(semantic_id='task/page/back'))
    assert not host.appear(NamedButton('DOCK_CHECK'))
    oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='unknown-overlay')]
    with pytest.raises(SemanticGateClosed):
        host.appear(NamedButton('DOCK_CHECK'))


def test_guild_page_probe_from_unrelated_tactical_page_is_passive():
    oracle = FakeOracle()
    oracle.guild_page_visible = lambda: False
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert not host.appear(NamedButton('GUILD_CHECK'))
    with pytest.raises(SemanticGateClosed):
        host.click(NamedButton('GUILD_CHECK'))


def test_retained_meowfficer_page_skips_unrelated_page_probe():
    oracle = FakeOracle()
    oracle.exists_values['meowfficer/page/back'] = True
    oracle.enabled_values['meowfficer/page/back'] = True
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert not host.appear(NamedButton('FLEET_CHECK'))
    assert not host.appear(NamedButton('EXERCISE_CHECK'))
    assert host.appear(NamedButton('MEOWFFICER_CHECK'))
    with pytest.raises(SemanticGateClosed):
        host.click(NamedButton('FLEET_CHECK'))


def test_meowfficer_back_transition_skips_unowned_reward_probe():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._record_mission_transition(SimpleNamespace(semantic_id='meowfficer/page/back'))
    assert not host.appear(NamedButton('GET_ITEMS_1'))
    oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='unknown-overlay')]
    with pytest.raises(SemanticGateClosed):
        host.appear(NamedButton('GET_ITEMS_1'))


def test_main_guild_duplicate_during_loading_reuses_first_receipt():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    receipt = host.click(NamedButton('MAIN_GOTO_GUILD'))
    oracle.enabled_values['main/guild'] = False
    oracle.read_state = lambda: SimpleNamespace(generation=receipt.generation + 1)
    oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='loading')]
    assert host.click(NamedButton('MAIN_GOTO_GUILD')) is receipt
    assert oracle.click_calls == ['main/guild']
    oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='unknown-overlay')]
    assert host.click(NamedButton('MAIN_GOTO_GUILD')) is not receipt
    assert oracle.click_calls == ['main/guild', 'main/guild']


def test_retained_guild_page_owns_generic_page_scan():
    oracle = FakeOracle()
    oracle.exists_values['guild/page/back'] = True
    oracle.guild_page_visible = lambda: True
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert not host.appear(NamedButton('FLEET_CHECK'))
    assert host.appear(NamedButton('GUILD_CHECK'))


def test_main_to_guild_loading_skips_passive_page_scan_only():
    oracle = FakeOracle()
    oracle.main_page_visible = lambda: False
    oracle.guild_page_visible = lambda: False
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._main_guild_entry_until = time.monotonic() + 1.0
    assert not host.appear(NamedButton('FLEET_CHECK'))
    assert not host.appear(NamedButton('GET_MISSION'))
    oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='unknown-overlay')]
    assert host._appear_priority('FLEET_CHECK') is UNHANDLED


def test_guild_back_transition_skips_unowned_mission_probe():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._record_mission_transition(SimpleNamespace(semantic_id='guild/page/back'))
    assert not host.appear(NamedButton('GET_MISSION'))
    assert not host.appear(NamedButton('GET_ITEMS_1'))
    assert not host.appear(NamedButton('MONTHLY_PASS_NOTICE'))
    assert not host.appear(NamedButton('MAP_PREPARATION'))


def test_mail_entry_duplicate_during_loading_reuses_first_receipt():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_mail()
    receipt = host.click(NamedButton('MAIL_ENTER_WHITE'))
    oracle.read_state = lambda: SimpleNamespace(generation=receipt.generation + 1)
    oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='loading')]
    assert host.click(NamedButton('MAIL_ENTER_WHITE')) is receipt
    assert oracle.click_calls == ['main/mail']
    oracle._blocking_rules = lambda state, target: [SimpleNamespace(blocker_id='unknown-overlay')]
    assert host.click(NamedButton('MAIL_ENTER_WHITE')) is not receipt


def test_retained_mail_page_owns_generic_page_scan():
    oracle = FakeOracle()
    oracle.exists_values['mail/page/back'] = True
    oracle.enabled_values['mail/page/back'] = True
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert not host.appear(NamedButton('FLEET_CHECK'))
    assert host.appear(NamedButton('MAIL_CHECK'))


def test_daily_entry_receipt_skips_old_dock_page_probe():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    receipt = oracle.click_receipt('campaign-menu/daily')
    host._daily_entry_receipt = receipt
    host._daily_entry_transition_until = time.monotonic() + 12.0
    oracle.state_generation = receipt.generation + 1
    oracle.blocking_rules = (SimpleNamespace(blocker_id='campaign-menu'),)
    assert not host.appear(NamedButton('DOCK_CHECK'))


def test_exercise_entry_receipt_skips_old_dock_page_probe():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    receipt = oracle.click_receipt('campaign-menu/exercise')
    host._exercise_entry_receipt = receipt
    host._exercise_entry_transition_until = time.monotonic() + 12.0
    oracle.state_generation = receipt.generation + 1
    oracle.blocking_rules = (SimpleNamespace(blocker_id='campaign-menu'),)
    assert not host.appear(NamedButton('DOCK_CHECK'))


def test_campaign_menu_home_waits_for_exact_main_postcondition():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    oracle.exists_values['campaign-menu/page/back'] = True
    oracle.enabled_values['campaign-menu/page/back'] = True
    original = oracle.click

    def click_and_arrive(target):
        receipt = original(target)
        if target == 'campaign-menu/page/back':
            oracle.state_generation = receipt.generation + 1
            oracle.main_page_visible_value = True
            oracle.exists_values[target] = False
        return receipt

    oracle.click = click_and_arrive
    receipt = host.click(NamedButton('GOTO_MAIN'))
    assert receipt.semantic_id == 'campaign-menu/page/back'
    assert oracle.main_page_visible()


def test_campaign_chapter_back_waits_for_menu_before_next_home_edge():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    oracle.campaign_page_value = True
    oracle.exists_values['campaign-menu/page/back'] = True
    oracle.enabled_values['campaign-menu/page/back'] = True
    original = oracle.click

    def click_and_arrive(target):
        receipt = original(target)
        if target == 'campaign-menu/page/back':
            oracle.state_generation = receipt.generation + 1
            oracle.campaign_page_value = False
            oracle.campaign_menu_value = True
        return receipt

    oracle.click = click_and_arrive
    receipt = host.click(NamedButton('GOTO_MAIN'))
    assert receipt.semantic_id == 'campaign-menu/page/back'
    assert oracle.campaign_menu_is_entry()
    assert not oracle.main_page_visible()


def test_retained_commission_home_uses_exact_unblocked_return_only():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    oracle.exists_values['commission/page/back'] = True
    oracle.enabled_values['commission/page/back'] = True
    receipt = host.click(NamedButton('GOTO_MAIN'))
    assert receipt.semantic_id == 'commission/page/back'
    assert oracle.click_calls == ['commission/page/back']
    oracle.click_calls.clear()
    oracle.enabled_values['commission/page/back'] = False
    assert host._goto_main_target() is None
    assert oracle.click_calls == []
    oracle.enabled_values['commission/page/back'] = True
    oracle.exists_values['task/page/back'] = True
    oracle.enabled_values['task/page/back'] = True
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        host._goto_main_target()
    assert oracle.click_calls == []


def test_commission_home_transition_keeps_campaign_probes_passive_only_without_foreign_modal():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    oracle.exists_values['commission/page/back'] = True
    oracle.enabled_values['commission/page/back'] = True
    host.click(NamedButton('GOTO_MAIN'))
    oracle.main_page_visible_value = False
    oracle.blocking_rules = (SimpleNamespace(blocker_id='commission-page'),)
    assert not host.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))
    oracle.blocking_rules = (SimpleNamespace(blocker_id='msgbox'),)
    with pytest.raises(AlasSemanticUnmapped):
        host.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))
    assert oracle.click_calls == ['commission/page/back']


def test_unowned_mail_manager_recovery_uses_only_exact_layer_exit():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    oracle.exists_values['mail/manage/back'] = True
    oracle.enabled_values['mail/manage/back'] = True
    oracle.exists_values['mail/page/back'] = True
    oracle.enabled_values['mail/page/back'] = False
    assert not host.appear(NamedButton('FLEET_CHECK'))
    assert host.appear(NamedButton('GOTO_MAIN'))
    receipt = host.click(NamedButton('GOTO_MAIN'))
    assert receipt.semantic_id == 'mail/manage/back'
    assert oracle.click_calls == ['mail/manage/back']
    oracle.enabled_values['mail/manage/back'] = False
    assert host._goto_main_target() is None
    assert oracle.click_calls == ['mail/manage/back']
