"""Native port completion must wait for the confirmation it actually owns."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.oracle.errors import SemanticNavigationPending
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.test_alas_config_branch_compatibility import method
from tests.semantic_support.observer_fixtures import DRIVER_REVISION


def dock(mode='delayed-confirm'):
    frame = [-1]
    calls = []
    returned = [None]

    def screenshot():
        frame[0] += 1

    def enabled(target):
        if target == 'os/port/dock':
            return frame[0] == -1
        if target == 'os/port/supply':
            return (returned[0] is not None and mode != 'stalled-return'
                    and mode != 'unknown-return' and frame[0] >= returned[0] + 2)
        if target == 'os/port/dock/repair-all':
            return mode != 'unknown-return' or returned[0] is None
        if target == 'os/port/dock/back':
            return True
        return False

    def click(target):
        calls.append(target)
        if target == 'os/port/dock/back':
            returned[0] = frame[0]
        return SimpleNamespace(semantic_id=target, generation=frame[0])

    def cost():
        if mode == 'unsafe':
            raise SemanticGateClosed('game activity is not top-resumed')
        return 500 if mode not in ('stalled-entrance', 'info-result') and frame[0] in (4, 5) else None

    oracle = SimpleNamespace(enabled=enabled, click=click,
        read_state=lambda: SimpleNamespace(generation=frame[0]))
    adapter = SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle),
        operation_siren_port_repair_cost=cost,
        click_operation_siren_port_repair=Mock(return_value=object()))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,
        screenshot=screenshot, sleep=Mock()),
        info_bar_count=lambda: int(mode == 'info-result' and frame[0] >= 3))
    run = method('module/os_handler/port.py', 'PortHandler', 'port_dock_repair')
    return lambda: run(host), calls, adapter, frame


def test_retained_repair_button_does_not_finish_before_delayed_cost_confirmation():
    run, calls, adapter, frame = dock()
    run()
    assert calls == ['os/port/dock', 'os/port/dock/repair-all', 'os/port/dock/back']
    adapter.click_operation_siren_port_repair.assert_called_once_with(True)
    assert frame[0] >= 8


def test_native_info_result_remains_an_original_completion_decision():
    run, calls, adapter, _ = dock('info-result')
    run()
    assert calls.count('os/port/dock/repair-all') == 1
    adapter.click_operation_siren_port_repair.assert_not_called()


@pytest.mark.parametrize('mode,target', [
    ('stalled-entrance', 'os/port/dock/repair-all'),
    ('stalled-return', 'os/port/dock/back'),
])
def test_healthy_unsettled_source_keeps_one_input_and_defers_native_task(mode, target):
    run, calls, _, _ = dock(mode)
    session = AlasSemanticSession(serial='offline-test', driver_revision=DRIVER_REVISION)
    with pytest.raises(TaskCapabilityUnavailable) as pending:
        with semantic_task_scope(session, 'opsi_abyssal'):
            run()
    assert isinstance(pending.value.cause, SemanticNavigationPending)
    assert pending.value.cause.semantic_id == target
    assert calls.count(target) == 1
    assert session.last_task_outcome['outcome'] == 'navigation-pending'
    with semantic_task_scope(session, 'daily'):
        pass
    assert session.last_task_outcome['outcome'] == 'returned'


def test_foreground_failure_is_not_reclassified_as_healthy_navigation():
    run, calls, adapter, _ = dock('unsafe')
    with pytest.raises(SemanticGateClosed) as denied:
        run()
    assert not isinstance(denied.value, SemanticNavigationPending)
    assert calls == ['os/port/dock']
    adapter.click_operation_siren_port_repair.assert_not_called()


def test_unidentified_destination_keeps_original_failure():
    run, calls, _, _ = dock('unknown-return')
    with pytest.raises(RuntimeError, match='did not return to port') as denied:
        run()
    assert not isinstance(denied.value, SemanticNavigationPending)
    assert calls.count('os/port/dock/back') == 1


@pytest.mark.parametrize('healthy', [True, False])
def test_native_port_enter_timeout_is_local_only_with_proven_local_map(healthy):
    receipt = SimpleNamespace(semantic_id='os/port/enter', generation=10)
    oracle = SimpleNamespace(click=Mock(return_value=receipt), exists=lambda target: False,
        operation_siren_local_map_visible=lambda: healthy,
        read_state=lambda: SimpleNamespace(generation=12))
    adapter = SimpleNamespace(refresh_frame=Mock(), open=lambda: SimpleNamespace(oracle=oracle))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, sleep=Mock()))
    run = method('module/os_handler/port.py', 'PortHandler', 'port_enter')
    error = SemanticNavigationPending if healthy else RuntimeError
    with pytest.raises(error) as denied:
        run(host)
    assert isinstance(denied.value, SemanticNavigationPending) == healthy
    oracle.click.assert_called_once_with('os/port/enter')
