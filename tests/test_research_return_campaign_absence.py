from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.mark.parametrize('name', ['WITHDRAW', 'MAP_PREPARATION', 'FLEET_PREPARATION',
                                 'AUTO_SEARCH_MENU_EXIT', 'AUTO_SEARCH_REWARD'])
def test_retained_research_page_proves_unrelated_campaign_probe_absent(name):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.main_page_visible_value = False
    oracle.exists_values['research/page/back'] = True
    oracle.enabled_values['research/page/back'] = True
    oracle.blocking_rules = (SimpleNamespace(blocker_id='research-page'),)
    assert adapter._research_context is None and adapter._campaign_context is None
    assert adapter.appear(name) is False


@pytest.mark.parametrize('case', ['unknown-overlay', 'missing-page', 'disabled-page'])
def test_no_blanket_campaign_absence_for_unknown_or_covered_research(case):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.main_page_visible_value = False
    oracle.exists_values['research/page/back'] = case != 'missing-page'
    oracle.enabled_values['research/page/back'] = case != 'disabled-page'
    oracle.blocking_rules = (SimpleNamespace(blocker_id='unknown-popup' if case == 'unknown-overlay' else 'research-page'),)
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.appear('WITHDRAW')


@pytest.mark.parametrize('unknown_overlay', [False, True])
def test_research_loading_yields_only_passive_campaign_probe(unknown_overlay):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.main_page_visible_value = False
    oracle.exists_values['research/page/back'] = True
    oracle.enabled_values['research/page/back'] = False
    oracle.inherited_campaign_withdraw_control = lambda **kwargs: None
    oracle.blocking_rules = tuple(SimpleNamespace(blocker_id=name)
                                 for name in ('loading','research-page') + (('unknown-popup',) if unknown_overlay else ()))
    if unknown_overlay:
        with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
            adapter.appear('WITHDRAW')
    else:
        assert adapter.appear('WITHDRAW') is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click('WITHDRAW')
