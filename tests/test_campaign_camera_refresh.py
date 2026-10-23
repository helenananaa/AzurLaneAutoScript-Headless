"""Camera observation refreshes the world; admitted inputs retain their proof."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.semantic_support.adapter_fixtures import (
    FakeOracle,
    make_campaign_combat_decision,
    make_campaign_combat_state,
)


def camera():
    oracle = FakeOracle()
    state = make_campaign_combat_state()
    oracle.campaign_map_state_value = replace(state, enemies=())
    adapter = AlasSemanticAdapter(oracle, lambda: None, campaign_combat_budget=2)
    adapter.begin_campaign_pre_sortie("12-4")
    adapter.campaign_map_state(
        columns=11, rows=8, land_cells=((0, 0),), expected_fleet_count=1
    )
    return adapter, oracle, state


def test_camera_accepts_initial_enemy_spawn_before_any_action_plan():
    adapter, oracle, state = camera()
    spawned = replace(state, generation=state.generation + 1)
    oracle.campaign_map_state_value = spawned

    assert adapter.campaign_camera_state() is spawned
    assert adapter._campaign_context.map_state is spawned
    assert oracle.click_calls == []
    assert adapter.authorize_campaign_combat(
        replace(make_campaign_combat_decision(), generation=spawned.generation), spawned
    ) is not None


def test_camera_rejects_enemy_change_under_an_admitted_input_plan():
    adapter, oracle, state = camera()
    oracle.campaign_map_state_value = state
    adapter.campaign_camera_state()
    adapter.authorize_campaign_combat(make_campaign_combat_decision(), state)
    oracle.campaign_map_state_value = replace(state, generation=state.generation + 1, enemies=())

    with pytest.raises(SemanticGateClosed, match="changed admitted map state"):
        adapter.campaign_camera_state()
    assert oracle.click_calls == []


def test_camera_refresh_preserves_the_oracle_validation_failure():
    adapter, oracle, _ = camera()
    oracle.campaign_map_state = Mock(side_effect=SemanticGateClosed("ambiguous enemy"))

    with pytest.raises(SemanticGateClosed, match="ambiguous enemy"):
        adapter.campaign_camera_state()
    assert oracle.click_calls == []


def test_camera_uses_same_screenshot_frame_when_live_state_has_entered_precombat():
    adapter, live, state = camera()
    frame = FakeOracle()
    frame.campaign_map_state_value = state
    adapter._frame_observation_oracle = lambda: frame
    live.campaign_map_state = Mock(side_effect=SemanticGateClosed('campaign map and blocking identities overlap'))
    assert adapter.campaign_camera_state() is state
    live.campaign_map_state.assert_not_called()
    assert live.click_calls == frame.click_calls == []


def test_camera_uses_live_read_only_after_input_invalidates_screenshot_lease():
    adapter, live, state = camera()
    adapter._frame_observation_oracle = Mock(side_effect=StaleFrameError())
    live.campaign_map_state_value = state
    assert adapter.campaign_camera_state() is state
    assert live.click_calls == []


@pytest.mark.parametrize('case', ['arrived', 'before_arrival', 'before_tap', 'identity', 'input'])
def test_only_completed_enemy_arrival_allows_its_fighting_flag(case):
    from tests.test_campaign_viewport_preflight import native_route
    adapter, oracle, state, decision = native_route(0, covered=False)
    admission = adapter.authorize_campaign_combat(decision, state)
    context = adapter._campaign_context
    receipt = oracle.click_receipt('campaign/grid')
    context.combat_route_receipts = [receipt] * len(admission.input_nodes)
    context.combat_receipt = receipt
    arrived = replace(state, generation=state.generation + 1,
        fleets=(replace(state.fleets[0], node=admission.target_node),),
        enemies=(replace(state.enemies[0], fighting=True),))
    if case == 'before_arrival':
        arrived = replace(arrived, fleets=state.fleets)
    elif case == 'before_tap':
        context.combat_route_receipts = []
        context.combat_receipt = None
    elif case == 'identity':
        arrived = replace(arrived, enemies=(replace(arrived.enemies[0], level=999),))
    validate = adapter._validate_campaign_combat_route_state
    if case == 'arrived':
        validate(context, arrived, for_next_input=False)
    else:
        with pytest.raises(SemanticGateClosed):
            validate(context, arrived, for_next_input=(case == 'input'))
    assert oracle.click_calls == []
