import time
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.mark.parametrize('owned,expired', [(True, False), (False, False), (True, True)])
def test_stage_entry_owns_only_bounded_passive_mount_wait(owned, expired):
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_campaign_pre_sortie('D3')
    ctx = host._campaign_context
    if owned: ctx.entry_receipt = SimpleNamespace(generation=10)
    ctx.passive_transition_until = time.monotonic() + (-1 if expired else 20)
    oracle.event_campaign_page_visible = Mock(return_value=True)
    host._campaign_preparation_state_with_stage = Mock(side_effect=SemanticGateClosed('partial panel'))
    if owned and not expired:
        assert host._appear_event_selector('FLEET_PREPARATION', None) is UNHANDLED
    else:
        with pytest.raises(SemanticGateClosed, match='partial panel'):
            host._appear_event_selector('FLEET_PREPARATION', None)
    assert not oracle.click_calls and not ctx.fleet_mutation_receipts


@pytest.mark.parametrize('advances', [True, False])
def test_difficulty_input_requires_fresh_complete_destination_without_repeat(monkeypatch, advances):
    monkeypatch.setattr('alas_headless.adapter.semantic.campaign_preparation.time.sleep', lambda _: None)
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_campaign_pre_sortie('D3')
    host.campaign_map_preparation_mode_state = Mock(return_value='normal')
    host._campaign_preparation_state_with_stage = Mock(return_value=(SimpleNamespace(kind='map'), 'b3'))
    receipt = SimpleNamespace(generation=10)
    oracle.click_campaign_map_preparation_mode = Mock(return_value=receipt)
    oracle.campaign_map_preparation_mode_state = Mock(return_value='hard')
    oracle.campaign_preparation_state = Mock(side_effect=[SemanticGateClosed('mounting')] +
        [SimpleNamespace(kind='map', generation=12 if advances else 10)] * 20)
    host._input_frame_refresher = Mock()
    if advances:
        assert host.set_campaign_map_preparation_mode('hard') is receipt
    else:
        with pytest.raises(SemanticGateClosed, match='postcondition was not proven'):
            host.set_campaign_map_preparation_mode('hard')
    oracle.click_campaign_map_preparation_mode.assert_called_once_with('b3', 'hard')


@pytest.mark.parametrize('fleets', [(1, 2, 0), (5, 6, 0)])
def test_hard_fixed_presets_preserve_original_alas_enabled_fleet_semantics(fleets):
    oracle = FakeOracle()
    oracle.campaign_hard_mode = True
    oracle.campaign_fleets['submarine'] = 0
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None, campaign_fleet_mutation_budget=0)
    host.begin_campaign_pre_sortie('D3', mode='hard')
    AlasSemanticAdapterTestsSupport.seed_owned_campaign_fleet_overlay(host)
    assert host.authorize_campaign_fleet_preparation(*fleets)
    assert host._campaign_context.requested_fleets == (1, 2, 0)
    assert not oracle.click_calls


def test_ordinary_fleet_indices_do_not_bypass_missing_hard_panel():
    oracle = FakeOracle()
    oracle.campaign_hard_mode = False
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_campaign_pre_sortie('D3', mode='hard')
    AlasSemanticAdapterTestsSupport.seed_owned_campaign_fleet_overlay(host)
    with pytest.raises(SemanticGateClosed, match='hard campaign fleet restrictions are not present'):
        host.authorize_campaign_fleet_preparation(5, 6, 0)
    assert not oracle.click_calls


def test_owned_fleet_presence_waits_for_complete_rows_in_same_observation_frame():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_campaign_pre_sortie('12-4', mode='hard')
    ctx = host._campaign_context
    ctx.entry_receipt = SimpleNamespace(generation=10)
    ctx.map_preparation_receipt = SimpleNamespace(generation=11)
    ctx.passive_transition_until = time.monotonic() + 20
    host._campaign_preparation_state_with_stage = Mock(
        return_value=(SimpleNamespace(kind='fleet'), '12-4'))
    partial = SemanticGateClosed(
        'campaign fleet row ship identity is inconsistent: fleet1')
    oracle.campaign_fleet_selection_state = Mock(side_effect=partial)
    assert host._appear_campaign('FLEET_PREPARATION') is False
    assert ctx.initial_fleet_state is None
    assert not oracle.click_calls and not ctx.fleet_mutation_receipts

    # The next ALAS screenshot supplies a complete frame; no extra input or
    # live observation replaces the earlier screenshot's immutable state.
    oracle.campaign_fleet_selection_state.side_effect = None
    oracle.campaign_fleet_selection_state.return_value = SimpleNamespace(rows=())
    assert host._appear_campaign('FLEET_PREPARATION') is True

    oracle.campaign_fleet_selection_state.side_effect = SemanticGateClosed(
        'campaign fleet row name is ambiguous: fleet1')
    with pytest.raises(SemanticGateClosed, match='name is ambiguous'):
        host._appear_campaign('FLEET_PREPARATION')

    ctx.passive_transition_until = time.monotonic() - 1
    oracle.campaign_fleet_selection_state.side_effect = partial
    with pytest.raises(SemanticGateClosed, match='ship identity is inconsistent'):
        host._appear_campaign('FLEET_PREPARATION')
    assert ctx.initial_fleet_state is None and not oracle.click_calls
