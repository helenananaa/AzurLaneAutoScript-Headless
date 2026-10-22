"""Replay the fixed hard fleet presentation encountered in native r26."""
import json
from pathlib import Path
import pytest
from types import SimpleNamespace
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_ui, make_oracle
from tests.semantic_support.adapter_fixtures import FakeOracle
from alas_headless import AlasSemanticAdapter


def retained_backend():
    source = Path(__file__).resolve().parents[1] / 'artifacts/semantic-cn-original-scheduler-r26-20260930.json'
    if not source.exists():
        pytest.skip('retained native r26 observation unavailable')
    observed = json.loads(source.read_text(encoding='utf-8'))['tasks'][-1]['failure_observation']
    backend = FakeBackend(observed['state']['buttons_snapshot']['buttons'])
    ui = observed['ui']['snapshot']
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    return backend


def test_fixed_hard_fleet_is_readable_without_manufacturing_operators():
    backend = retained_backend()
    state = make_oracle(backend)._campaign_fleet_selection_state_once('d3')
    assert state.hard_mode and state.surface_fleets == (2, 2)
    assert state.submarine_fleets == (0, 0)
    for row in state.rows[:2]:
        assert row.hard_satisfied is True
        assert len(row.ship_levels) == 6
        assert not row.available
        assert row.select_button is None and row.clear_button is None
    assert backend.taps == []


@pytest.mark.parametrize('mutation', ['missing-duty', 'duplicate-duty', 'missing-ship'])
def test_fixed_hard_fleet_does_not_accept_partial_or_ambiguous_presentation(mutation):
    backend = retained_backend()
    buttons = backend.buttons['buttons']
    duty = next(b for b in buttons if b['path'].endswith('/fleet/1/DutySelect/Item1'))
    if mutation == 'missing-duty':
        buttons.remove(duty)
    elif mutation == 'duplicate-duty':
        buttons.append(dict(duty))
    else:
        images = backend.ui['images']
        ship = next(i for i in images if '/fleet/1/' in i['path'] and i['path'].endswith('/icon_bg/icon'))
        images.remove(ship)
        backend.ui['image_count'] = len(images)
    backend.buttons['button_count'] = len(buttons)
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend)._campaign_fleet_selection_state_once('d3')
    assert backend.taps == []


@pytest.mark.parametrize('budget', [0, 1, 4])
def test_hard_sortie_budget_retains_positive_grant_and_fleet_proof_boundaries(budget):
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None, campaign_sortie_budget=budget)
    adapter.begin_campaign_pre_sortie('D3', mode='hard')
    options = dict(use_auto_search=True, use_2x_book=False,
                   submarine_mode='do_not_use', fleet_order='fleet1_mob_fleet2_boss')
    if budget == 0:
        assert adapter.authorize_campaign_sortie(**options) is False
    else:
        with pytest.raises(SemanticGateClosed, match='fleet selection was not proven'):
            adapter.authorize_campaign_sortie(**options)
    assert oracle.click_calls == []


@pytest.mark.parametrize('budget, authorized_budget, allowed', [(4, 4, True), (0, 0, False), (4, 3, False)])
def test_hard_sortie_consumes_one_unchanged_authorized_unit(budget, authorized_budget, allowed):
    oracle = FakeOracle()
    calls = []
    oracle.click_campaign_sortie = lambda *a, **kw: (calls.append(a) or oracle.click_receipt('campaign/sortie/d3', 7))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None, campaign_sortie_budget=budget)
    adapter.begin_campaign_pre_sortie('D3', mode='hard')
    context = adapter._campaign_context
    context.sortie_authorized = True
    context.sortie_budget_before = authorized_budget
    context.prepared_fleet_state = SimpleNamespace(generation=6)
    if allowed:
        adapter._click_campaign_fleet('FLEET_PREPARATION', None)
        assert adapter._action_ledger.remaining('campaign.sortie') == budget - 1
        with pytest.raises(SemanticGateClosed, match='authorized budget unit'):
            adapter._click_campaign_fleet('FLEET_PREPARATION', None)
        assert len(calls) == 1
    else:
        with pytest.raises(SemanticGateClosed, match='authorized budget unit'):
            adapter._click_campaign_fleet('FLEET_PREPARATION', None)
        assert calls == []
