"""Empty destinations reuse original ALAS planning and exact map receipts."""
from dataclasses import replace
import pytest

from alas_headless import SemanticGateClosed, synchronize_alas_campaign_map, preview_alas_campaign_decision
from alas_headless import AlasSemanticAdapter
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from types import SimpleNamespace
from alas_headless.alas_combat_admission import prepare_alas_campaign_combat_admission, prove_alas_campaign_combat_transition
from tests.test_alas_map_sync import FakeCampaign, FakeMap, make_state


class ClickMap(FakeMap):
    def find_path(self, location, **kwargs):
        # Original ALAS click routes omit the fleet's origin.
        return super().find_path(location, **kwargs)[1:]


class MoveCampaign(FakeCampaign):
    def battle_function(self):
        self.fleet_ensure(2)
        self.goto(self.map[(2, 1)])


def admitted_move():
    state = make_state()
    campaign = MoveCampaign()
    campaign.MAP = ClickMap()
    projection = synchronize_alas_campaign_map(campaign, state)
    decision = preview_alas_campaign_decision(campaign, projection)
    assert decision.target_kind == 'move'
    assert decision.route_nodes == ('B2', 'C2')
    admission = prepare_alas_campaign_combat_admission(decision, state, input_generation=state.generation)
    post = replace(state, generation=state.generation + 1, displayed_fleet_index=2,
        current_fleet_marker='beta', current_fleet_roster_sprites=('beta',),
        fleets=tuple(replace(f, node='C2') if f.marker == 'beta' else f for f in state.fleets))
    return decision, admission, state, post


def test_original_fleet_two_empty_move_preserves_battle_count_ammo_and_enemies():
    _, admission, _, post = admitted_move()
    proof = prove_alas_campaign_combat_transition(admission, post,
        battle_count_after=admission.battle_count, input_path=admission.cell_path)
    assert proof.battle_count_before == proof.battle_count_after
    assert proof.ammo_before == proof.ammo_after == 4
    assert proof.enemy_object_id is None


@pytest.mark.parametrize('mutation', ['ammo', 'enemy', 'other_fleet', 'stale', 'off_route', 'count'])
def test_empty_move_rejects_unrelated_changes_and_unproven_arrival(mutation):
    _, admission, _, post = admitted_move()
    count = admission.battle_count
    if mutation == 'ammo':
        post = replace(post, fleets=tuple(replace(f, ammo=3) if f.marker == 'beta' else f for f in post.fleets))
    elif mutation == 'enemy':
        post = replace(post, enemies=())
    elif mutation == 'other_fleet':
        post = replace(post, fleets=tuple(replace(f, node='C1') if f.marker == 'alpha' else f for f in post.fleets))
    elif mutation == 'stale':
        post = replace(post, generation=admission.input_generation)
    elif mutation == 'off_route':
        post = replace(post, fleets=tuple(replace(f, node='B2') if f.marker == 'beta' else f for f in post.fleets))
    else:
        count += 1
    with pytest.raises(SemanticGateClosed):
        prove_alas_campaign_combat_transition(admission, post, battle_count_after=count, input_path=admission.cell_path)


@pytest.mark.parametrize('mutation', ['enemy', 'pickup', 'fleet', 'land', 'combat_expectation'])
def test_movement_does_not_authorize_combat_or_occupied_destinations(mutation):
    decision, _, state, _ = admitted_move()
    if mutation == 'enemy':
        state = replace(state, enemies=(replace(state.enemies[0], node='C2', row=2, column=3),))
    elif mutation == 'pickup':
        state = replace(state, pickups=(replace(state.pickups[0], node='C2', row=2, column=3),))
    elif mutation == 'fleet':
        state = replace(state, fleets=(replace(state.fleets[0], node='C2'), state.fleets[1]))
    elif mutation == 'land':
        state = replace(state, cells=tuple(c for c in state.cells if c.node != 'C2'))
    else:
        decision = replace(decision, expected='combat')
    with pytest.raises(SemanticGateClosed):
        prepare_alas_campaign_combat_admission(decision, state, input_generation=state.generation)


@pytest.mark.parametrize('partial_input', [False, True])
def test_original_next_iteration_can_replace_only_an_unused_grid_authorization(partial_input):
    _, admission, _, _ = admitted_move()
    adapter = AlasSemanticAdapter(SimpleNamespace(), package_gate=lambda: None)
    context = _CampaignFlowContext(stage_code='12-4', combat_admission=admission)
    adapter._campaign_context = context
    context.map_fleet_switch_receipts.append(object())
    if partial_input:
        context.combat_route_receipts.append(object())
        with pytest.raises(SemanticGateClosed, match='unclosed input'):
            adapter.complete_campaign_combat_round(0)
        assert context.combat_admission is admission
    else:
        assert adapter.complete_campaign_combat_round(0) is None
        assert context.combat_admission is None
        assert context.map_fleet_switch_receipts == []


def test_cached_movement_proof_does_not_turn_into_a_completed_battle():
    _, admission, _, post = admitted_move()
    proof = prove_alas_campaign_combat_transition(admission, post,
        battle_count_after=0, input_path=admission.cell_path)
    adapter = AlasSemanticAdapter(SimpleNamespace(), package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='12-4', combat_proof=proof)
    assert adapter.confirm_campaign_combat(0) is proof
    with pytest.raises(SemanticGateClosed, match='battle count changed'):
        adapter.confirm_campaign_combat(1)


def test_empty_final_grid_requires_ordinary_top_raycast_not_enemy_coverage():
    from tests.semantic_support.adapter_fixtures import FakeOracle, CampaignGridButton
    _, admission, before, _ = admitted_move()
    state = replace(before, displayed_fleet_index=2, current_fleet_marker='beta',
                    current_fleet_roster_sprites=('beta',))
    oracle = FakeOracle()
    oracle.campaign_map_state_value = state
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None, campaign_combat_budget=1)
    adapter._campaign_context = _CampaignFlowContext(stage_code='12-4', combat_admission=admission,
        map_state=state, map_columns=3, map_rows=2, map_land_cells=((0,1),), map_expected_fleet_count=2)
    receipt = adapter.click_campaign_combat_grid(CampaignGridButton((2, 1)))
    assert receipt.path == admission.cell_path
    assert oracle.campaign_map_cell_input_calls
    assert all(covered is False for _, covered in oracle.campaign_map_cell_input_calls)
    assert adapter.campaign_combat_active()
    assert not adapter.campaign_combat_committed()
    adapter._campaign_context.ambush_receipt = object()
    assert adapter.campaign_combat_committed()


def test_next_preview_honors_original_pending_fleet_switch_before_branch():
    state = replace(make_state(), displayed_fleet_index=2, current_fleet_marker='beta',
                    current_fleet_roster_sprites=('beta',))
    campaign = FakeCampaign()
    projection = synchronize_alas_campaign_map(campaign, state)
    decision = preview_alas_campaign_decision(campaign, projection, initial_fleet_index=1)
    assert decision.fleet_index == 1
    assert decision.fleet_marker == 'alpha'
    assert decision.origin_node == 'A2'
    # Previewing the requested switch never changes the observed real fleet.
    assert campaign.fleet_current_index == 2
    assert projection.current_fleet_index == 2
    with pytest.raises(SemanticGateClosed, match='index is invalid'):
        preview_alas_campaign_decision(campaign, projection, initial_fleet_index=True)
