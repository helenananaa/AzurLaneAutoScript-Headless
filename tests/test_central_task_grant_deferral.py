"""Direct mutation ports share the ordinary no-input grant outcome."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import (ActionGrantExhausted, ActionLedger, ActionLeaseError, DEFAULT_CAPABILITY_INVENTORY,
    RecoveryPolicy, compatibility_policy_sha256, compatibility_profile)
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


def adapter_with_grants(grants):
    profile = compatibility_profile('ordinary-task-deferral', grants)
    ledger = ActionLedger(profile=profile, inventory=DEFAULT_CAPABILITY_INVENTORY,
        grants=grants, recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
        policy_sha256=compatibility_policy_sha256(profile.profile_id, grants))
    return AlasSemanticAdapterTestsSupport().make_adapter(action_ledger=ledger)


def session_for(adapter):
    return SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)


def test_guild_third_reward_defers_without_repeating_first_two_or_stopping_dorm():
    adapter, oracle, _ = adapter_with_grants({'guild.claim': 2, 'dorm.collect': 1})
    oracle.guild_logistics_state = Mock(return_value=SimpleNamespace(
        supply_claimable=True, mission_claimable=True))
    oracle.enabled_values['guild/report/claim-all'] = True
    adapter.claim_guild_supply()
    adapter.claim_guild_mission()
    session = session_for(adapter)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'guild'):
            adapter.claim_all_guild_reports()
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert oracle.click_calls == ['guild/logistics/supply', 'guild/logistics/mission']
    assert adapter._action_ledger.remaining('guild.claim') == 0
    with semantic_task_scope(session, 'dorm'):
        adapter.begin_dorm()
        adapter.click(NamedButton('DORM_QUICK_COLLECT'))
    assert oracle.click_calls[-1] == 'dorm/collect'


@pytest.mark.parametrize('capability', ['guild.dispatch', 'exercise.execute', 'shop.purchase'])
def test_explicit_zero_direct_grant_is_local_and_never_calls_backend(capability):
    adapter, _, _ = adapter_with_grants({capability: 0})
    operation = Mock()
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session_for(adapter), capability):
            adapter._dispatch_mutation(capability, operation)
    operation.assert_not_called()


@pytest.mark.parametrize('error_type', [ActionLeaseError, ActionGrantExhausted])
def test_backend_failure_after_reservation_keeps_fatal_outcome(error_type):
    adapter, _, _ = adapter_with_grants({'guild.claim': 1})
    failure = error_type()
    operation = Mock(side_effect=failure)
    with pytest.raises(ActionLeaseError) as caught:
        with semantic_task_scope(session_for(adapter), 'guild'):
            adapter._dispatch_mutation('guild.claim', operation)
    assert caught.value is failure
    assert not isinstance(caught.value, AlasSemanticActionDeferred)
    operation.assert_called_once()
    assert adapter._action_ledger.remaining('guild.claim') == 0


@pytest.mark.parametrize('capability', ['guild.claim', 'shop.purchase'])
def test_closed_zero_ledger_remains_fatal_at_direct_dispatch(capability):
    adapter, _, _ = adapter_with_grants({capability: 0})
    adapter._action_ledger.close()
    operation = Mock()
    with pytest.raises(ActionLeaseError):
        with semantic_task_scope(session_for(adapter), capability):
            adapter._dispatch_mutation(capability, operation)
    operation.assert_not_called()


def test_batch_feed_budget_shortfall_is_local_before_any_food_input():
    adapter, oracle, _ = adapter_with_grants({'dorm.feed': 1})
    adapter.begin_dorm()
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session_for(adapter), 'dorm'):
            adapter.dorm_feed_food(0, 2)
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining('dorm.feed') == 1


def test_feed_invalid_count_and_overflow_still_fail_in_original_boundary():
    adapter, oracle, _ = adapter_with_grants({'dorm.feed': 1})
    adapter.begin_dorm()
    with pytest.raises(ValueError):
        adapter.dorm_feed_food(0, -1)
    adapter._fresh_dorm_feed_state = Mock(return_value=SimpleNamespace(
        food=100, capacity=100, items=[SimpleNamespace(count=1, value=10)]))
    with pytest.raises(SemanticGateClosed, match='overflow'):
        with semantic_task_scope(session_for(adapter), 'dorm'):
            adapter.dorm_feed_food(0, 1)
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining('dorm.feed') == 1


@pytest.mark.parametrize('kind', ['commission', 'tactical'])
def test_reward_grant_refusal_is_local_when_reward_state_is_valid(kind):
    adapter, oracle, _ = adapter_with_grants({kind + '.reward': 0})
    if kind == 'commission':
        adapter.begin_commission()
        oracle.exists_values['reward/commission/finish'] = True
        oracle.enabled_values['reward/commission/finish'] = True
        oracle.reward_summary_values = [1]
    else:
        adapter.begin_tactical()
        oracle.reward_sidebar_control_offscreen = Mock(return_value=False)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session_for(adapter), kind):
            adapter.click(NamedButton('REWARD_1' if kind == 'commission' else 'REWARD_2'))
    assert oracle.click_calls == []


@pytest.mark.parametrize('blocked', [False, True])
def test_commission_absent_or_blocked_reward_is_not_a_budget_failure(blocked):
    adapter, oracle, _ = adapter_with_grants({'commission.reward': 0})
    adapter.begin_commission()
    oracle.exists_values['reward/commission/finish'] = blocked
    oracle.enabled_values['reward/commission/finish'] = False
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session_for(adapter), 'commission'):
            adapter.click(NamedButton('REWARD_1'))
    assert not isinstance(caught.value, AlasSemanticActionDeferred)
    assert oracle.click_calls == []


@pytest.mark.parametrize('method, selected', [('default', 0), ('default', 1), ('selected', 0), ('selected', 5)])
def test_minigame_ticket_observation_does_not_need_play_authority(method, selected):
    adapter, oracle, _ = adapter_with_grants({'minigame.play': 0})
    adapter.begin_minigame()
    adapter._minigame_context.coins_owned = 20
    oracle.new_year_challenge_ticket_count = Mock(return_value=(selected, 20))
    observe = (adapter.minigame_prepare_default_ticket if method == 'default'
               else adapter.minigame_prepare_selected_tickets)
    assert observe() == selected
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining('minigame.play') == 0
    if selected:
        operation = Mock()
        oracle.click_new_year_challenge_prepare_control = operation
        with pytest.raises(TaskCapabilityUnavailable):
            with semantic_task_scope(session_for(adapter), 'minigame'):
                adapter.click(NamedButton('NEW_YEAR_CHALLENGE_START'))
        operation.assert_not_called()


def test_minigame_zero_grant_does_not_hide_ticket_inventory_drift():
    adapter, oracle, _ = adapter_with_grants({'minigame.play': 0})
    adapter.begin_minigame()
    adapter._minigame_context.coins_owned = 20
    oracle.new_year_challenge_ticket_count = Mock(return_value=(1, 19))
    with pytest.raises(SemanticGateClosed, match='inconsistent'):
        adapter.minigame_prepare_default_ticket()
    assert oracle.click_calls == []


def test_minigame_coin_selection_without_play_grant_is_local():
    adapter, oracle, _ = adapter_with_grants({'minigame.play': 0})
    adapter.begin_minigame()
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session_for(adapter), 'minigame'):
            adapter.click(NamedButton('NEW_YEAR_CHALLENGE_ADD_COIN'))
    assert oracle.click_calls == []


@pytest.mark.parametrize('kind', ['mail', 'weekly'])
def test_reward_only_budget_prechecks_do_not_override_central_deferral(kind):
    capability = 'mail.mutation' if kind == 'mail' else 'mission.claim'
    adapter, oracle, _ = adapter_with_grants({capability: 0})
    if kind == 'mail':
        adapter.begin_mail()
        oracle.enabled_values['mail/manage/claim'] = True
        action = lambda: adapter.click(NamedButton('MAIL_BATCH_CLAIM'))
    else:
        adapter.begin_mission_reward(True, True)
        oracle.weekly_mission_progress_claim_available = Mock(return_value=True)
        oracle.click_weekly_mission_progress_claim = Mock()
        action = adapter.claim_weekly_mission_progress_once
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session_for(adapter), kind):
            action()
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining(capability) == 0
