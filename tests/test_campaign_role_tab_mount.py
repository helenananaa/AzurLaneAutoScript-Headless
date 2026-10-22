"""A covered duty tab admits no input and does not stop unrelated native tasks."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from alas_headless.oracle.errors import SemanticTargetNotActionable
from alas_headless.semantic_oracle import CampaignAutoSearchRoleState
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_toggle, make_ui,
)
from tests.test_central_task_grant_deferral import session_for


TARGET = 'campaign/fleet-preparation/roles/tab'
PATH = 'OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/RightTabs/duty_btn'


def tab_backend():
    backend = FakeBackend([])
    backend.ui = make_ui([], toggles=[make_toggle(PATH, checked=False, raycast_top=False)])
    return backend, make_oracle(backend)


@pytest.mark.parametrize('case', ['covered', 'loading', 'unknown-modal', 'disabled', 'ambiguous', 'missing', 'ready'])
def test_only_unique_enabled_tab_raycast_mount_is_classified_before_input(case):
    backend, oracle = tab_backend()
    if case in ('loading', 'unknown-modal'):
        backend.buttons['buttons'].append(make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)') if case == 'loading' else
            make_button('custom_button_1(Clone)',
                'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'disabled':
        backend.ui['toggles'][0]['interactable'] = False
    elif case == 'ambiguous':
        backend.ui['toggles'].append(dict(backend.ui['toggles'][0]))
        backend.ui['toggle_count'] += 1
    elif case == 'missing':
        backend.ui['toggles'] = []
        backend.ui['toggle_count'] = 0
    elif case == 'ready':
        backend.ui['toggles'][0]['raycast_top'] = True
        # Additive unrelated UI does not invalidate the reviewed target.
        backend.ui['toggles'].append(make_toggle('new/page/toggle', checked=False))
        backend.ui['toggle_count'] += 1
    if case == 'ready':
        assert oracle.click_toggle(TARGET).semantic_id == TARGET
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed) as caught:
            oracle.click_toggle(TARGET)
        assert isinstance(caught.value, SemanticTargetNotActionable) == (case in ('covered', 'loading'))
        assert backend.taps == []
        assert oracle.input_dispatch_count == 0


def role_adapter(monkeypatch, *, settle=False, post_input_failure=False, passive_event=False):
    import alas_headless.adapter.semantic.campaign_preparation as preparation
    backend, oracle = tab_backend()
    elapsed = [0.0]
    def sleep(seconds):
        elapsed[0] += seconds
        if settle:
            backend.ui['toggles'][0]['raycast_top'] = True
    monkeypatch.setattr(preparation, 'time', SimpleNamespace(monotonic=lambda: elapsed[0], sleep=sleep))
    def tap():
        backend.ui['toggles'][0]['checked'] = True
        if post_input_failure:
            if post_input_failure == 'classified':
                raise SemanticTargetNotActionable(TARGET, 10)
            raise SemanticGateClosed('accepted tab input failed')
    backend.on_tap = tap
    oracle.campaign_auto_search_role_state = Mock(return_value=CampaignAutoSearchRoleState(
        generation=10, fleet1_role='mob', fleet2_role='boss'))
    adapter = AlasSemanticAdapter(oracle, lambda: None, campaign_fleet_mutation_budget=0 if passive_event else 2)
    adapter.begin_campaign_pre_sortie('SP' if passive_event else '12-4')
    adapter._campaign_context.requested_fleets = (1, 2, 0)
    adapter._campaign_context.prepared_fleet_state = SimpleNamespace(hard_mode=passive_event)
    return adapter, oracle, backend, elapsed


def test_mount_settles_with_one_actual_input_and_one_grant(monkeypatch):
    adapter, oracle, backend, elapsed = role_adapter(monkeypatch, settle=True)
    state = adapter.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
    assert (state.fleet1_role, state.fleet2_role) == ('mob', 'boss')
    assert elapsed[0] > 0
    assert len(backend.taps) == 1
    assert oracle.input_dispatch_count == 1
    assert adapter._action_ledger.remaining('campaign.fleet_mutation') == 1


@pytest.mark.parametrize('settle', [False, True])
def test_existing_event_zero_mutation_inspection_keeps_its_authority(monkeypatch, settle):
    adapter, oracle, backend, _ = role_adapter(monkeypatch, settle=settle, passive_event=True)
    if settle:
        state = adapter.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
        assert (state.fleet1_role, state.fleet2_role) == ('mob', 'boss')
    else:
        with pytest.raises(AlasSemanticActionDeferred):
            adapter.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
    assert len(backend.taps) == int(settle)
    assert oracle.input_dispatch_count == int(settle)
    assert adapter._action_ledger.remaining('campaign.fleet_mutation') == 0


def test_persistent_no_input_refusal_is_local_without_consuming_grants(monkeypatch):
    adapter, oracle, backend, elapsed = role_adapter(monkeypatch)
    session = session_for(adapter)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'hard'):
            adapter.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert 5 <= elapsed[0] < 5.3
    assert adapter._action_ledger.remaining('campaign.fleet_mutation') == 2
    assert oracle.input_dispatch_count == 0 and backend.taps == []
    target = oracle._mapping('guild/page/back')
    backend.buttons['buttons'] = [make_button(target.name, 'root/' + target.path_suffix)]
    backend.buttons['button_count'] = 1
    with semantic_task_scope(session, 'guild'):
        assert oracle.click('guild/page/back').semantic_id == 'guild/page/back'
    assert session.last_task_outcome == {'task': 'guild', 'outcome': 'returned'}
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['closed', 'accepted-input', 'accepted-classified', 'unknown-modal'])
def test_authority_and_uncertain_input_errors_never_become_mount_deferrals(monkeypatch, case):
    accepted = case.startswith('accepted-')
    adapter, oracle, backend, _ = role_adapter(monkeypatch, settle=True,
        post_input_failure='classified' if case == 'accepted-classified' else accepted)
    if case == 'closed':
        adapter._action_ledger.close()
    elif case == 'unknown-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises((ActionLeaseError, SemanticGateClosed) if case == 'closed' else SemanticGateClosed) as caught:
        adapter.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
    assert not isinstance(caught.value, AlasSemanticActionDeferred)
    assert len(backend.taps) == int(accepted)
    assert oracle.input_dispatch_count == int(accepted)
