"""An absent pre-input Guild dispatch control must not stop other native tasks."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.oracle.errors import (
    SemanticGateClosed, SemanticTargetMissing, SemanticInputTargetMissing,
    SemanticGuildFormationUnavailable,
)
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_image, make_ui


ROOT = 'OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)'
GO = ROOT + '/frame/bottom/go'


def formation_oracle(go_count):
    backend = FakeBackend([make_button('GuildMissionFormationPage(Clone)', ROOT, raycast_top=None)] +
                          [make_button('go', GO, raycast_top=None) for _ in range(go_count)])
    backend.ui = make_ui([], images=[make_image(GO, 'btn', {'left':620,'top':340,'right':660,'bottom':380})])
    return make_oracle(backend), backend


def task_session():
    return SimpleNamespace(discard_task_state=Mock(), trace=None)


def test_missing_dispatch_control_defers_guild_before_input_and_research_reads_continue():
    oracle, backend = formation_oracle(0)
    session = task_session()
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'guild'):
            oracle.click('guild/formation/go')
    assert isinstance(caught.value.cause, SemanticGuildFormationUnavailable)
    assert backend.taps == []
    assert session.last_task_outcome == {'task':'guild','outcome':'capability-unavailable'}
    with semantic_task_scope(session, 'research'):
        assert oracle.read_state().generation > 0
    assert session.last_task_outcome == {'task':'research','outcome':'returned'}


def test_present_unique_dispatch_control_remains_allowed():
    oracle, backend = formation_oracle(1)
    assert oracle.click('guild/formation/go').semantic_id == 'guild/formation/go'
    assert len(backend.taps) == 1


def test_ambiguous_dispatch_control_remains_fatal_without_input():
    oracle, backend = formation_oracle(2)
    with pytest.raises(SemanticGateClosed, match='ambiguous') as caught:
        with semantic_task_scope(task_session(), 'guild'):
            oracle.click('guild/formation/go')
    assert not isinstance(caught.value, SemanticGuildFormationUnavailable)
    assert backend.taps == []


def test_other_missing_guild_control_defers_before_input_without_formation_reclassification():
    oracle, backend = formation_oracle(0)
    session = task_session()
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'guild'):
            oracle.click('guild/dispatch/confirm')
    assert isinstance(caught.value.cause, SemanticInputTargetMissing)
    assert not isinstance(caught.value.cause, SemanticGuildFormationUnavailable)
    assert session.last_task_outcome == {'task': 'guild', 'outcome': 'input-unavailable'}
    assert backend.taps == []


def test_missing_dispatch_control_outside_guild_is_not_silently_deferred():
    oracle, backend = formation_oracle(0)
    with pytest.raises(SemanticGuildFormationUnavailable):
        with semantic_task_scope(task_session(), 'research'):
            oracle.click('guild/formation/go')
    assert backend.taps == []


def test_backend_failure_after_input_remains_fatal():
    oracle, backend = formation_oracle(1)
    failure = SemanticTargetMissing('backend input result is uncertain')
    backend.on_tap = Mock(side_effect=failure)
    session = task_session()
    with pytest.raises(SemanticTargetMissing) as caught:
        with semantic_task_scope(session, 'guild'):
            oracle.click('guild/formation/go')
    assert caught.value is failure
    assert len(backend.taps) == 1
    assert session.last_task_outcome['outcome'] == 'raised'


def test_wrong_activity_remains_fatal_before_missing_dispatch_classification():
    oracle, backend = formation_oracle(0)
    backend.foreground = 'other.package/.OtherActivity'
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(task_session(), 'guild'):
            oracle.click('guild/formation/go')
    assert not isinstance(caught.value, SemanticGuildFormationUnavailable)
    assert backend.taps == []
