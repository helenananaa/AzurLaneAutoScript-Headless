"""Current-config Gems qualification keeps task, replacement and return evidence."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.python.run_alas_configured_task_live import (
    return_main_after_native_task, trace_gems_replacements,
)


@pytest.mark.parametrize('outcome', [False, None, 1])
def test_failed_or_non_native_success_never_adds_return_input(outcome):
    app, session, result = Mock(), Mock(), {'return': outcome}
    return_main_after_native_task(app, session, outcome, result)
    app.goto_main.assert_not_called()
    session.open.assert_not_called()
    assert 'main_return' not in result


def test_native_return_records_ending_before_separate_navigation():
    oracle = SimpleNamespace(read_state=lambda: SimpleNamespace(snapshot={'pid': 7}, generation=12),
                             main_page_visible=lambda: False)
    session = SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle))
    result = {'return': True, 'task_outcome': {'task': 'gems_farming', 'outcome': 'returned'}}
    def navigate():
        assert result['main_return']['before'] == dict(pid=7, generation=12, main_visible=False)
        assert result['main_return']['returned'] is False
    app = SimpleNamespace(goto_main=Mock(side_effect=navigate))
    return_main_after_native_task(app, session, True, result)
    assert result['return'] is True and result['task_outcome']['task'] == 'gems_farming'
    assert result['main_return']['returned'] is True
    app.goto_main.assert_called_once_with()


def test_navigation_failure_preserves_original_task_and_no_retry():
    oracle = SimpleNamespace(read_state=lambda: SimpleNamespace(snapshot={'pid': 7}, generation=12),
                             main_page_visible=lambda: False)
    session = SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle))
    app = SimpleNamespace(goto_main=Mock(side_effect=RuntimeError('unsettled')))
    result = {'return': True}
    with pytest.raises(RuntimeError, match='unsettled'):
        return_main_after_native_task(app, session, True, result)
    assert result['return'] is True and not result['main_return']['returned']
    app.goto_main.assert_called_once_with()


def test_replacement_observation_preserves_native_values_and_exception():
    candidate = {'id': 12, 'emotion': 119}
    session = SimpleNamespace(gems_farming_candidates=Mock(return_value=[candidate]),
        gems_farming_confirm_candidate_selection=Mock(side_effect=ValueError('preinput rejected')))
    result = {}
    trace_gems_replacements(session, result)
    assert session.gems_farming_candidates('flagship') == [candidate]
    with pytest.raises(ValueError, match='preinput rejected'):
        session.gems_farming_confirm_candidate_selection('flagship', candidate)
    calls = result['gems_replacement_calls']
    assert len(calls) == 2 and calls[0]['returned'] and calls[0]['result'] == [candidate]
    assert calls[1]['arguments'] == ['flagship', candidate] and not calls[1]['returned']
    assert calls[1]['error']['type'] == 'ValueError'


def test_unrelated_session_without_replacement_ports_is_unchanged():
    result = {}
    trace_gems_replacements(SimpleNamespace(), result)
    assert result == {'gems_replacement_calls': []}
