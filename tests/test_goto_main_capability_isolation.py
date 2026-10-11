"""A missing reviewed exit is local; invalid observations retain their error."""
import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.observer_fixtures import (
    DRIVER_REVISION, FakeBackend, make_button, make_buttons, make_oracle,
)


def unknown_page():
    backend = FakeBackend([])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    return backend, adapter


def test_missing_reviewed_exit_defers_only_current_task_then_allows_main_discovery():
    backend, adapter = unknown_page()
    session = AlasSemanticSession(serial='offline-test', driver_revision=DRIVER_REVISION)
    session.adapter = adapter
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'goto_main'):
            adapter.click('GOTO_MAIN')
    assert isinstance(caught.value.cause, AlasSemanticUnmapped)
    assert 'no reviewed page target' in str(caught.value.cause)
    assert session.last_task_outcome == {'task': 'goto_main', 'outcome': 'capability-unavailable'}
    assert backend.taps == []
    backend.buttons = make_buttons([
        make_button('battle', 'root/frame/right/1/battle'),
        make_button('formation', 'root/frame/right/1/formation'),
    ])
    with semantic_task_scope(session, 'reward'):
        assert adapter.oracle.main_page_visible()
    assert session.last_task_outcome == {'task': 'reward', 'outcome': 'returned'}
    assert session.last_task_error is None
    assert backend.taps == []


@pytest.mark.parametrize('case', ['stale', 'truncated', 'foreign-package', 'foreign-foreground'])
def test_invalid_runtime_cannot_be_reclassified_as_missing_exit(case):
    backend, adapter = unknown_page()
    if case == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif case == 'truncated':
        backend.buttons['truncated'] = True
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.foreground = 'unrelated.package/OtherActivity'
    with pytest.raises(SemanticGateClosed) as caught:
        adapter.click('GOTO_MAIN')
    assert not isinstance(caught.value, AlasSemanticUnmapped)
    assert backend.taps == []
