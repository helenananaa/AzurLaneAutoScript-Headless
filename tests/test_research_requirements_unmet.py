"""A conditional card remains observable without authorizing its start."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.contracts import ResearchProjectStatus
from alas_headless.oracle.errors import SemanticResearchStatusUnavailable
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_unmet_condition_keeps_page_and_original_alas_status_contract(drift):
    backend, oracle, adapter = host(drift, 'research-requirements-unmet-r31.json')
    adapter.begin_research()
    projects = oracle.research_projects()
    assert len(projects) == 5
    conditional = [p for p in projects if p.status is ResearchProjectStatus.REQUIREMENTS_UNMET]
    assert len(conditional) == 1 and conditional[0].duration_seconds == 0
    assert adapter.appear('RESEARCH_CHECK') is True
    assert adapter.research_statuses() == ['detail'] * 5
    # Card visibility is not detail/start admission.
    assert not oracle.enabled('research/detail/start')
    assert not backend.taps


def test_unreviewed_card_does_not_hide_page_or_break_independent_task_scope():
    backend, oracle, adapter = host(fixture='research-requirements-unmet-r31.json')
    oracle._sleep = lambda _: None
    next(t for t in backend.ui['texts'] if '条件未达成' in t['text'])['text'] = 'unreviewed new condition'
    adapter.begin_research()
    assert adapter.appear('RESEARCH_CHECK') is True
    with pytest.raises(SemanticResearchStatusUnavailable): oracle.research_projects()
    session = SimpleNamespace(discard_task_state=Mock(), trace=None)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session, 'research'): adapter.research_projects()
    with semantic_task_scope(session, 'commission'):
        assert oracle.read_state().generation > 0
    assert session.last_task_outcome['outcome'] == 'returned'
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_actual_empty_queue_is_not_base_page_and_native_queue_quit_can_continue(drift):
    backend, oracle, adapter = host(drift, 'research-empty-queue-r32.json')
    adapter.begin_research()
    assert oracle.enabled('research/page/back')
    assert not oracle.research_page_visible()
    assert not adapter.appear('RESEARCH_CHECK')
    assert adapter.appear('QUEUE_CHECK')
    assert oracle.research_queue_state().entries == ()
    assert not backend.taps
