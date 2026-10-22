"""A duty-tab animation may delay actionable rows, but never authorizes input."""
from itertools import count
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('case', ['settles', 'covered', 'ambiguous-selection', 'stale'])
def test_role_mount_wait_requires_a_new_complete_role_proof(case, monkeypatch):
    oracle = FakeOracle()
    oracle.campaign_role_tab_selected = True
    refresh = Mock()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None,
        campaign_fleet_mutation_budget=2, input_frame_refresher=refresh,
        frame_observation_oracle=lambda: oracle)
    host.begin_campaign_pre_sortie('12-4')
    host._campaign_context.requested_fleets = (1, 2, 0)
    host._campaign_context.prepared_fleet_state = SimpleNamespace(hard_mode=False)
    errors = {
        'covered': 'campaign auto-search role control is incomplete',
        'ambiguous-selection': 'campaign auto-search role selection is ambiguous',
        'stale': 'semantic frame is stale',
    }
    ready = SimpleNamespace(generation=12, fleet1_role='mob', fleet2_role='boss')
    if case == 'settles':
        oracle.campaign_auto_search_role_state = Mock(side_effect=[
            SemanticGateClosed('campaign auto-search role control is incomplete'), ready])
    else:
        oracle.campaign_auto_search_role_state = Mock(side_effect=SemanticGateClosed(errors[case]))
    clock = count(0, 1)
    monkeypatch.setattr('alas_headless.adapter.semantic.campaign_preparation.time.monotonic', lambda: next(clock))
    monkeypatch.setattr('alas_headless.adapter.semantic.campaign_preparation.time.sleep', lambda _: None)
    if case == 'settles':
        assert host.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss') is ready
        assert oracle.campaign_auto_search_role_state.call_count == 2
        assert refresh.call_count >= 2
    else:
        with pytest.raises(SemanticGateClosed, match=errors[case]):
            host.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
        if case != 'covered':
            assert oracle.campaign_auto_search_role_state.call_count == 1
        assert host._campaign_context.auto_search_role_state is None
    assert oracle.click_calls == []
    assert host._action_ledger.remaining('campaign.fleet_mutation') == 2
