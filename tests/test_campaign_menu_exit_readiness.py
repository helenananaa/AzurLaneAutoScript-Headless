from unittest.mock import patch
from types import SimpleNamespace

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('case', ['settles', 'blocked', 'owner-lost'])
def test_existing_campaign_back_edge_waits_without_guessing_another_exit(case):
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._goto_main_target = lambda: None
    oracle.main_page_visible = lambda: bool(oracle.click_calls)
    oracle.campaign_page_is_normal = lambda: False
    oracle.read_state = lambda: SimpleNamespace(generation=100)
    calls = [0]
    present_calls = [0]

    def present(target):
        if oracle.click_calls:
            return False
        if target != 'campaign-menu/page/back':
            return False
        present_calls[0] += 1
        return case != 'owner-lost' or present_calls[0] < 3

    def enabled(target):
        if target != 'campaign-menu/page/back':
            return False
        calls[0] += 1
        return case == 'settles' and calls[0] > 1

    oracle.observation_target_present, oracle.enabled = present, enabled
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep'):
        if case == 'settles':
            assert adapter._click_main('GOTO_MAIN', None).semantic_id == 'campaign-menu/page/back'
            assert oracle.click_calls == ['campaign-menu/page/back']
        else:
            with pytest.raises(SemanticGateClosed, match='no reviewed page target'):
                adapter._click_main('GOTO_MAIN', None)
            assert oracle.click_calls == []
