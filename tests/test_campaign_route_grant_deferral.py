"""A proven native route may run out of grants without losing its identity."""
from dataclasses import replace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.semantic_support.adapter_fixtures import (
    CampaignGridButton, FakeOracle, make_campaign_combat_decision,
    make_campaign_combat_state,
)


def route(*, viewport=1):
    oracle = FakeOracle()
    state = make_campaign_combat_state()
    oracle.campaign_map_state_value = state
    adapter = AlasSemanticAdapter(oracle, lambda: None,
        campaign_combat_budget=2, campaign_viewport_swipe_budget=viewport)
    adapter.begin_campaign_pre_sortie('12-4')
    current = adapter.campaign_map_state(columns=11, rows=8,
        land_cells=((0, 0),), expected_fleet_count=1)
    assert adapter.authorize_campaign_combat(make_campaign_combat_decision(), current)
    return adapter, oracle, state


def viewport_intent(adapter):
    return adapter.begin_campaign_map_swipe_vector((0., 80.),
        box=(123, 159, 1175, 628), random_range=(0, 0, 0, 0), padding=15,
        duration=(.1, .2), whitelist_area=None, blacklist_area=None,
        name='MAP_SWIPE_0_-1', distance_check=True)


@pytest.mark.parametrize('status', ['zero', 'spent', 'closed'])
def test_proven_combat_camera_scope_classifies_grant_before_input(status):
    adapter, oracle, _ = route(viewport=int(status != 'zero'))
    if status == 'spent':
        adapter._action_ledger.dispatch('campaign.viewport_swipe', lambda: None)
    elif status == 'closed':
        adapter._action_ledger.close()
    error = ActionLeaseError if status == 'closed' else AlasSemanticActionDeferred
    with pytest.raises(error):
        viewport_intent(adapter)
    assert oracle.campaign_map_swipe_calls == []


@pytest.mark.parametrize('status', ['spent', 'closed'])
def test_admitted_grid_classifies_grant_before_input(status):
    adapter, oracle, _ = route()
    if status == 'spent':
        for _ in range(2):
            adapter._action_ledger.dispatch('campaign.grid_click', lambda: None)
    else:
        adapter._action_ledger.close()
    with pytest.raises(ActionLeaseError if status == 'closed' else AlasSemanticActionDeferred):
        adapter.click(CampaignGridButton((3, 5)))
    assert oracle.click_calls == []


@pytest.mark.parametrize('status', ['spent', 'closed'])
def test_proven_no_progress_retry_classifies_grant_without_extra_tap(status):
    adapter, oracle, state = route()
    receipt = adapter.click(CampaignGridButton((3, 5)))
    oracle.campaign_map_state_value = replace(state, generation=receipt.generation + 1)
    if status == 'spent':
        adapter._action_ledger.dispatch('campaign.grid_click', lambda: None)
    else:
        adapter._action_ledger.close()
    with pytest.raises(ActionLeaseError if status == 'closed' else AlasSemanticActionDeferred):
        adapter.click(CampaignGridButton((3, 5)))
    assert oracle.click_calls == ['campaign/map/grid/D6']
    assert adapter._campaign_context.combat_input_retry_count == 0


def test_wrong_grid_target_remains_fatal_when_grant_spent():
    adapter, oracle, _ = route()
    for _ in range(2):
        adapter._action_ledger.dispatch('campaign.grid_click', lambda: None)
    with pytest.raises(SemanticGateClosed, match='target changed'):
        adapter.click(CampaignGridButton((3, 4)))
    assert oracle.click_calls == []


def test_unowned_viewport_is_fatal_even_with_zero_grant():
    adapter, oracle, _ = route(viewport=0)
    adapter._campaign_context.combat_admission = None
    with pytest.raises(SemanticGateClosed, match='not authorized'):
        viewport_intent(adapter)
    assert oracle.campaign_map_swipe_calls == []


@pytest.mark.parametrize('status', ['spent', 'closed'])
def test_final_viewport_dispatch_rechecks_grant_without_backend_input(status):
    adapter, oracle, _ = route()
    intent = viewport_intent(adapter)
    if status == 'spent':
        adapter._action_ledger.dispatch('campaign.viewport_swipe', lambda: None)
    else:
        adapter._action_ledger.close()
    try:
        with pytest.raises(ActionLeaseError if status == 'closed' else AlasSemanticActionDeferred):
            adapter.swipe((500, 370), (500, 450), duration=.35,
                name='MAP_SWIPE_0_-1', distance_check=True)
    finally:
        adapter.end_campaign_map_swipe_vector(intent)
    assert oracle.campaign_map_swipe_calls == []


def test_no_progress_retry_requires_state_newer_than_accepted_input():
    adapter, oracle, state = route()
    receipt = adapter.click(CampaignGridButton((3, 5)))
    oracle.campaign_map_state_value = replace(state, generation=receipt.generation)
    with pytest.raises(SemanticGateClosed, match='proven post-state'):
        adapter.click(CampaignGridButton((3, 5)))
    assert oracle.click_calls == ['campaign/map/grid/D6']
    assert adapter._action_ledger.remaining('campaign.grid_click') == 1
