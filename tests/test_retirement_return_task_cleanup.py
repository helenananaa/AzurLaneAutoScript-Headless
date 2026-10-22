"""A completed task must not lend its retirement return intent to the next."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.observer_fixtures import DRIVER_REVISION


@pytest.mark.parametrize('outcome', ['returned', 'deferred', 'fatal'])
def test_retirement_return_intent_ends_with_owning_task(outcome):
    session = AlasSemanticSession(serial='offline-test', driver_revision=DRIVER_REVISION)
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    session.adapter = adapter
    # A normal dock can remain open, but is not a retirement selection page.
    oracle.read_state = Mock(return_value=SimpleNamespace(generation=11, buttons=(
        SimpleNamespace(path='UICamera/Canvas/UIMain/DockyardUI(Clone)/ordinary',
                        active_in_hierarchy=True),)))
    oracle.retirement_selection_visible = Mock(return_value=False)
    check = SimpleNamespace(name='IN_RETIREMENT_CHECK')

    def first_task():
        with semantic_task_scope(session, 'retirement'):
            session._retirement_return_receipt = SimpleNamespace(generation=10)
            # Existing same-task transition observation remains in effect.
            assert session.appear(check) is True
            if outcome == 'deferred':
                raise AlasSemanticActionDeferred('controlled unavailable input')
            if outcome == 'fatal':
                raise SemanticGateClosed('controlled invalid owner')

    if outcome == 'returned':
        first_task()
    else:
        expected = TaskCapabilityUnavailable if outcome == 'deferred' else SemanticGateClosed
        with pytest.raises(expected):
            first_task()
    with semantic_task_scope(session, 'goto_main'):
        assert session.appear(check) is False
        assert session._retirement_return_receipt is None
        oracle.retirement_selection_visible.assert_called_once_with()
        # A genuinely observed retirement selection still remains visible.
        oracle.retirement_selection_visible.return_value = True
        assert session.appear(check) is True
