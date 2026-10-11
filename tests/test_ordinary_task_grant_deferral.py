"""A spent task grant must not terminate unrelated native ALAS tasks."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import MissionDisposition, ResearchProjectStatus, SemanticGateClosed
from alas_headless.adapter import (ActionLedger, ActionLeaseError, CapabilityClosureError,
    DEFAULT_CAPABILITY_INVENTORY, RecoveryPolicy, TaskCapabilityProfile,
    compatibility_policy_sha256)
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.test_opsi_native_camera_view import native


def action_case(kind, budget):
    authority = {
        'dorm': {'dorm_collect_budget': budget},
        'commission': {'commission_start_budget': budget},
        'tactical_start': {'tactical_assign_budget': budget},
        'tactical_confirm': {'tactical_assign_budget': budget},
        'mission_all': {'allow_mission_claim_once': bool(budget)},
        'mission_single': {'allow_mission_claim_once': bool(budget)},
        'research': {'research_start_budget': budget},
        'research_reward': {'research_reward_budget': budget},
    }[kind]
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(**authority)
    if kind == 'dorm':
        adapter.begin_dorm()
        call = lambda: adapter.click(NamedButton('DORM_QUICK_COLLECT'))
        capability = 'dorm.collect'
    elif kind == 'commission':
        adapter.begin_commission()
        adapter._commission_context.selected_signature = (0, 'Test', 3600, 'daily')
        call = lambda: adapter.click(NamedButton('COMMISSION_START'))
        capability = 'commission.start'
    elif kind.startswith('tactical'):
        adapter.begin_tactical()
        call = lambda: adapter.click(NamedButton(
            'TACTICAL_CLASS_START' if kind.endswith('start') else 'POPUP_CONFIRM'))
        capability = 'tactical.assign'
    elif kind.startswith('mission'):
        adapter.begin_mission_reward(True, True)
        state = SimpleNamespace(disposition=MissionDisposition.CLAIMABLE_ALL,
                                claim_all=object(), rows=())
        if kind.endswith('single'):
            state.disposition = MissionDisposition.CLAIMABLE_ROW
            state.claim_rows = (SimpleNamespace(path='task/claim/row/1'),)
        adapter._stable_mission_state = Mock(return_value=state)
        call = lambda: adapter.click(NamedButton(
            'MISSION_MULTI' if kind.endswith('all') else 'MISSION_SINGLE'))
        capability = 'mission.claim'
    elif kind == 'research_reward':
        adapter.begin_research()
        oracle.research_project_values = [SimpleNamespace(
            slot=1, code='G-236-MI', status=ResearchProjectStatus.FINISHED)]
        call = lambda: adapter.click(NamedButton('ENTRANCE_1'))
        capability = 'research.reward'
    else:
        adapter.begin_research()
        adapter._research_context.selected_code = 'G-236-MI'
        adapter.click_research_project_code = Mock()
        adapter.research_detail_stable = Mock()
        oracle.research_detail_state = Mock(return_value=SimpleNamespace(
            code='G-236-MI', is_running=False, can_start=True))
        call = lambda: adapter.start_research_project_code('G-236-MI')
        capability = 'research.start'
    return adapter, oracle, call, capability


KINDS = ['dorm', 'commission', 'tactical_start', 'tactical_confirm',
         'mission_all', 'mission_single', 'research', 'research_reward']


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('spent', [False, True])
def test_ordinary_port_defers_without_input_and_other_task_can_run(kind, spent):
    adapter, oracle, call, capability = action_case(kind, int(spent))
    if spent:
        adapter._action_ledger.dispatch(capability, lambda: None)
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, kind):
            call()
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining(capability) == 0
    with semantic_task_scope(session, 'unrelated'):
        adapter.begin_dorm()
        adapter.click(NamedButton('DORM_GOTO_MAIN'))
    assert oracle.click_calls == ['dorm/page/back']


@pytest.mark.parametrize('kind', KINDS)
def test_closed_ledger_is_still_fatal_even_when_budget_is_zero(kind):
    adapter, oracle, call, _ = action_case(kind, 0)
    adapter._action_ledger.close()
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(ActionLeaseError):
        with semantic_task_scope(session, kind):
            call()
    assert oracle.click_calls == []


def test_bad_mission_target_remains_fatal_before_budget_deferral():
    adapter, oracle, call, _ = action_case('mission_all', 0)
    adapter._stable_mission_state.return_value = None
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(SemanticGateClosed, match='stable mission claim-all is absent'):
        with semantic_task_scope(session, 'reward'):
            call()
    assert oracle.click_calls == []


def test_positive_grant_is_consumed_once_and_only_new_task_ledger_reopens_it():
    adapter, oracle, call, capability = action_case('dorm', 1)
    adapter._require_action_grant(capability)
    assert adapter._action_ledger.remaining(capability) == 1
    call()
    with pytest.raises(AlasSemanticActionDeferred):
        call()
    assert oracle.click_calls == ['dorm/collect']
    fresh, fresh_oracle, fresh_call, _ = action_case('dorm', 1)
    fresh_call()
    assert fresh_oracle.click_calls == ['dorm/collect']
    assert adapter._action_ledger.remaining(capability) == 0
    assert fresh._action_ledger.remaining(capability) == 0


@pytest.mark.parametrize('incomplete', [False, True])
def test_missing_capability_or_incomplete_preflight_is_not_budget_deferral(incomplete):
    actions = frozenset({'dorm.collect'}) if incomplete else frozenset()
    profile = TaskCapabilityProfile(profile_id='missing-grant-test', required_actions=actions,
                                   required_grants=actions)
    ledger = ActionLedger(profile=profile, inventory=DEFAULT_CAPABILITY_INVENTORY,
        grants={}, recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
        policy_sha256=compatibility_policy_sha256(profile.profile_id, {}))
    with pytest.raises(CapabilityClosureError if incomplete else ActionLeaseError) as caught:
        ledger.require_available('dorm.collect')
    assert not isinstance(caught.value, AlasSemanticActionDeferred)


@pytest.mark.parametrize('spent', [False, True])
def test_real_budget_refusal_reaches_original_zero_interval_native_scheduler(native, spent):
    from tests.test_native_zero_interval_task_isolation import harness
    host, cfg, _, _ = harness(interval=0)
    adapter, oracle, call, capability = action_case('dorm', int(spent))
    if spent:
        adapter._action_ledger.dispatch(capability, lambda: None)
    host.device.semantic_adapter = SimpleNamespace(discard_task_state=adapter.reset_task_state,
                                                  trace=None)
    host.opsi_explore = Mock(side_effect=call)
    assert host.run('opsi_explore') is None
    assert cfg.get_next().command == 'Minigame'
    assert adapter._action_ledger.remaining(capability) == 0
    assert oracle.click_calls == []
