"""ALAS owns refocus waits; an accepted input must never cause endless polling."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from alas_headless.oracle.errors import SemanticNavigationPending
from tests.test_alas_config_branch_compatibility import method


def case(observations, healthy=True):
    opened = SimpleNamespace(semantic_id='os/map/fleet-selector/open', generation=10)
    selected = SimpleNamespace(semantic_id='os/map/fleet-selector/1', generation=20)
    oracle = SimpleNamespace(operation_siren_local_map_visible=Mock(return_value=healthy),
                             read_state=Mock(return_value=SimpleNamespace(generation=30)))
    session = SimpleNamespace(
        operation_siren_current_fleet=Mock(return_value=1),
        operation_siren_fleet_selector_open=Mock(side_effect=observations),
        click_operation_siren_fleet_bar=Mock(return_value=opened),
        click_operation_siren_fleet_selector=Mock(return_value=selected),
        open=Mock(return_value=SimpleNamespace(oracle=oracle)),
        discard_task_state=Mock(),
        trace=None,
    )
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),
                           loop=Mock(side_effect=lambda **kwargs: iter((1, 2))))
    run = method('module/os/fleet.py', 'OSFleet', 'fleet_reset_view')
    return run, host, session, opened, selected


def test_normal_and_delayed_selector_edges_keep_one_input_each():
    run, host, session, _, _ = case([False, False, True, True, False])
    assert run(host) is True
    session.click_operation_siren_fleet_bar.assert_called_once_with()
    session.click_operation_siren_fleet_selector.assert_called_once_with(1)
    assert host.loop.call_count == 2
    for call in host.loop.call_args_list:
        assert call.kwargs == dict(skip_first=False, timeout=30)


def test_already_open_selector_skips_open_input():
    run, host, session, _, _ = case([True, False])
    assert run(host) is True
    session.click_operation_siren_fleet_bar.assert_not_called()
    session.click_operation_siren_fleet_selector.assert_called_once_with(1)


def test_open_timeout_retains_accepted_receipt_and_does_not_replay():
    run, host, session, opened, _ = case([False, False, False])
    with pytest.raises(SemanticNavigationPending, match='did not open') as caught:
        run(host)
    assert caught.value.receipt is opened and caught.value.generation == 30
    session.click_operation_siren_fleet_bar.assert_called_once_with()
    session.click_operation_siren_fleet_selector.assert_not_called()


def test_close_timeout_retains_selection_without_replay():
    run, host, session, _, selected = case([True, True, True])
    with pytest.raises(SemanticNavigationPending, match='did not close') as caught:
        run(host)
    assert caught.value.receipt is selected
    session.click_operation_siren_fleet_bar.assert_not_called()
    session.click_operation_siren_fleet_selector.assert_called_once_with(1)


def test_timeout_without_healthy_map_does_not_manufacture_reentry_proof():
    run, host, session, _, _ = case([False, False, False], healthy=False)
    with pytest.raises(SemanticGateClosed, match='owning map is unavailable') as caught:
        run(host)
    assert not isinstance(caught.value, SemanticNavigationPending)
    session.click_operation_siren_fleet_selector.assert_not_called()


def test_native_task_scope_localizes_timeout_and_unrelated_task_still_runs():
    run, host, session, _, _ = case([False, False, False])
    with pytest.raises(TaskCapabilityUnavailable, match='for OpsiDaemon'):
        with semantic_task_scope(session, 'OpsiDaemon'):
            run(host)
    assert session.last_task_outcome['outcome'] == 'navigation-pending'
    with semantic_task_scope(session, 'Commission'):
        pass
    assert session.last_task_outcome == dict(task='Commission', outcome='returned')


def test_nonsemantic_native_selector_is_unchanged():
    run, host, _, _, _ = case([])
    host.device.semantic_adapter = None
    host.fleet_selector = SimpleNamespace(get=Mock(return_value=2), open=Mock(), click=Mock())
    assert run(host) is True
    host.fleet_selector.open.assert_called_once_with()
    host.fleet_selector.click.assert_called_once_with(2)
    host.loop.assert_not_called()
