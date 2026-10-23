"""Ammunition uses the original ALAS goto and existing movement lease."""
from dataclasses import replace
import ast
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import (AlasSemanticAdapter, SemanticGateClosed,
    preview_alas_campaign_decision, synchronize_alas_campaign_map)
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from alas_headless.alas_combat_admission import (
    prepare_alas_campaign_combat_admission, prove_alas_campaign_combat_transition)
from tests.test_campaign_empty_movement import ClickMap
from tests.test_alas_map_sync import FakeCampaign, make_state
from tests.semantic_support.adapter_fixtures import CampaignGridButton


class AmmoCampaign(FakeCampaign):
    def battle_function(self):
        self.fleet_ensure(2)
        self.goto(self.map[(2, 0)], expected='')


def admitted_pickup(ammo_before=0):
    state = make_state()
    state = replace(state, fleets=(state.fleets[0], replace(state.fleets[1], ammo=ammo_before)))
    campaign = AmmoCampaign()
    campaign.MAP = ClickMap()
    projection = synchronize_alas_campaign_map(campaign, state)
    decision = preview_alas_campaign_decision(campaign, projection)
    assert decision.target_kind == 'ammo'
    admission = prepare_alas_campaign_combat_admission(decision, state,
        input_generation=state.generation)
    post = replace(state, generation=state.generation + 1,
        displayed_fleet_index=2, current_fleet_marker='beta', current_fleet_roster_sprites=('beta',),
        fleets=(state.fleets[0], replace(state.fleets[1], node='C1', ammo=min(5, ammo_before + 3))))
    return decision, admission, state, post


@pytest.mark.parametrize('retained', [False, True])
@pytest.mark.parametrize('ammo_before', [0, 3, 4])
def test_pickup_preserves_battle_count_and_proves_bounded_ammunition(retained, ammo_before):
    _, admission, _, post = admitted_pickup(ammo_before)
    if not retained:
        post = replace(post, pickups=())
    proof = prove_alas_campaign_combat_transition(admission, post,
        battle_count_after=admission.battle_count, input_path=admission.cell_path)
    assert proof.battle_count_after == proof.battle_count_before
    assert proof.ammo_after == min(5, ammo_before + 3)
    adapter = AlasSemanticAdapter(SimpleNamespace(), package_gate=lambda: None)
    adapter._campaign_context = _CampaignFlowContext(stage_code='12-4',
        combat_admission=admission, combat_proof=proof, combat_receipt=object())
    assert adapter.campaign_movement_completed()
    assert not adapter.campaign_combat_committed()
    assert adapter.finish_campaign_movement(admission.battle_count) is proof


@pytest.mark.parametrize('mutation', ['absent', 'duplicate', 'kind', 'enemy', 'fleet', 'expected'])
def test_pickup_admission_requires_unique_typed_ammo_without_conflicting_occupants(mutation):
    decision, _, state, _ = admitted_pickup()
    if mutation == 'absent':
        state = replace(state, pickups=())
    elif mutation == 'duplicate':
        state = replace(state, pickups=state.pickups * 2)
    elif mutation == 'kind':
        state = replace(state, pickups=(replace(state.pickups[0], kind='unknown'),))
    elif mutation == 'enemy':
        state = replace(state, enemies=(replace(state.enemies[0], node='C1'),))
    elif mutation == 'fleet':
        state = replace(state, fleets=(replace(state.fleets[0], node='C1'), state.fleets[1]))
    else:
        decision = replace(decision, expected='combat')
    with pytest.raises(SemanticGateClosed):
        prepare_alas_campaign_combat_admission(decision, state, input_generation=state.generation)


@pytest.mark.parametrize('mutation', ['no_gain', 'excess_gain', 'enemy', 'other_fleet', 'pickup', 'count', 'stale'])
def test_pickup_rejects_unproven_gain_or_unrelated_map_changes(mutation):
    _, admission, _, post = admitted_pickup()
    count = admission.battle_count
    if mutation in ('no_gain', 'excess_gain'):
        post = replace(post, fleets=(post.fleets[0], replace(post.fleets[1],
            ammo=0 if mutation == 'no_gain' else 4)))
    elif mutation == 'enemy':
        post = replace(post, enemies=())
    elif mutation == 'other_fleet':
        post = replace(post, fleets=(replace(post.fleets[0], ammo=4), post.fleets[1]))
    elif mutation == 'pickup':
        post = replace(post, pickups=(replace(post.pickups[0], sprite='unknown'),))
    elif mutation == 'count':
        count += 1
    else:
        post = replace(post, generation=admission.input_generation)
    with pytest.raises(SemanticGateClosed):
        prove_alas_campaign_combat_transition(admission, post,
            battle_count_after=count, input_path=admission.cell_path)


def test_original_arrival_refresh_keeps_explicit_global_grid_identity():
    root = os.environ.get('ALAS_TEST_ROOT')
    if not root:
        pytest.skip('set ALAS_TEST_ROOT to the verified patched ALAS tree')
    tree = ast.parse(Path(root, 'module/map/fleet.py').read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_goto')
    refresh = next(n for n in ast.walk(method) if isinstance(n, ast.If)
        and ast.unparse(n.test) == 'self.is_in_map()'
        and any(isinstance(s, ast.Assign) and isinstance(s.value, ast.Call)
                and ast.unparse(s.value.func) == 'self.convert_global_to_local' for s in n.body))
    statements = [s for s in refresh.body if isinstance(s, ast.Assign)]
    button = CampaignGridButton((5, 1))
    del button.__str__
    assert AlasSemanticAdapter._campaign_grid_location(button) is None
    scope = dict(self=SimpleNamespace(convert_global_to_local=lambda _: button), location=(5, 1))
    exec(compile(ast.fix_missing_locations(ast.Module(body=statements, type_ignores=[])),
                 '<original map arrival refresh>', 'exec'), scope)
    assert AlasSemanticAdapter._campaign_grid_location(scope['grid']) == (5, 1)
