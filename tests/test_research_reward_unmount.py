from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('change', [None, 'stale', 'unknown-queue', 'unclaimed', 'covered'])
def test_duplicate_reward_close_requires_prior_receipt_and_fresh_queue(change):
    o = FakeOracle()
    o.observation_target_present = Mock(return_value=change == 'covered')
    o.read_state = Mock(return_value=SimpleNamespace(generation=10 if change == 'stale' else 11))
    o.research_queue_state = Mock(return_value=SimpleNamespace())
    if change == 'unknown-queue': o.research_queue_state.side_effect = SemanticGateClosed('unknown queue')
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_research()
    a._award_close_target = Mock(return_value=None)
    prior = SimpleNamespace(generation=10)
    a._research_context.reward_receipts = [] if change == 'unclaimed' else [object()]
    a._research_context.popup_close_receipts = [prior]
    if change:
        with pytest.raises(SemanticGateClosed): a._click_research('GET_ITEMS_RESEARCH_SAVE')
    else:
        assert a._click_research('GET_ITEMS_RESEARCH_SAVE') is prior
    assert not o.click_calls
