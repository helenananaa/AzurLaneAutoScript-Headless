"""A previous queue read cannot replace unavailable current scheduling state."""
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('error', ['identity changed', 'generation gap', 'truncated queue'])
def test_queue_timer_does_not_reuse_a_previous_success_after_current_failure(error):
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_research()
    assert adapter.research_queue_remaining_seconds() == 0

    def unavailable():
        raise SemanticGateClosed(error)

    oracle.research_queue_state = unavailable
    with pytest.raises(SemanticGateClosed, match=error):
        adapter.research_queue_remaining_seconds()
    assert not oracle.click_calls


def test_queue_timer_and_capacity_use_the_latest_successful_observation():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_research()
    assert adapter.research_queue_empty_slots() == 5
    current = SimpleNamespace(empty_slots=3, first_remaining_seconds=1234)
    oracle.research_queue_value = current
    assert adapter.research_queue_state() is current
    assert adapter.research_queue_empty_slots() == 3
    assert adapter.research_queue_remaining_seconds() == 1234
    assert not oracle.click_calls
