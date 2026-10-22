"""The selected-row semantic branch retains ALAS' own input timers."""
import ast
from contextlib import nullcontext
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method, source


class NativeGameStuckError(RuntimeError):
    pass


def native_owner(ready_at, unproven=False):
    clock = [100.0]
    timer_class = next(n for n in ast.parse(source('module/base/timer.py')).body
                       if isinstance(n, ast.ClassDef) and n.name == 'Timer')
    timer_namespace = {'time': lambda: clock[0], 'sleep': Mock()}
    exec(compile(ast.Module(body=[timer_class], type_ignores=[]), 'native-timer', 'exec'), timer_namespace)
    timer = timer_namespace['Timer']
    advice = SimpleNamespace(name='COMMISSION_ADVICE')
    start = SimpleNamespace(name='COMMISSION_START')
    inputs = []
    started = [False]
    adapter = SimpleNamespace(
        commission_selection_active=lambda: True,
        appear=lambda button: clock[0] < ready_at if button is advice else clock[0] >= ready_at,
        close_started_commission_detail=Mock(),
        commission_start_proof=lambda: SimpleNamespace(name='reviewed commission',
            before_duration_seconds=7200, after_duration_seconds=7199, after_status_sprite='tag_ongoing'))
    def confirmed():
        if started[0] and unproven:
            raise SemanticGateClosed('start result remains unproven')
        return started[0]
    adapter.commission_start_confirmed = confirmed
    def click(button):
        inputs.append((button.name, clock[0]))
        if button is start: started[0] = True
    ticks = iter(100.0 + .7 * n for n in range(1, 30))
    device = SimpleNamespace(semantic_adapter=adapter, stuck_record_add=Mock(),
                             screenshot=lambda: clock.__setitem__(0, next(ticks)), click=click)
    owner = SimpleNamespace(device=device, interval_timer={}, ensure_button=lambda b: b,
        handle_popup_confirm=Mock(return_value=False), ui_ensure=Mock())
    for name in ('appear', 'interval_clear'):
        setattr(owner, name, partial(method('module/base/base.py', 'ModuleBase', name,
            Timer=timer), owner))
    run = method('module/commission/commission.py', 'RewardCommission', '_commission_start_click',
        Timer=timer, COMMISSION_ADVICE=advice, COMMISSION_START=start, page_commission='commission',
        GameStuckError=NativeGameStuckError)
    return owner, adapter, inputs, partial(run, owner, SimpleNamespace())


@pytest.mark.parametrize('ready_at,expected_recommends', [(102, 1), (109, 2)])
def test_native_timer_avoids_rapid_recommend_repeats_without_delaying_ready_start(ready_at, expected_recommends):
    owner, adapter, inputs, run = native_owner(ready_at)
    assert run() is True
    recommends = [at for name, at in inputs if name == 'COMMISSION_ADVICE']
    starts = [at for name, at in inputs if name == 'COMMISSION_START']
    assert len(recommends) == expected_recommends
    assert all(after - before > 7 for before, after in zip(recommends, recommends[1:]))
    assert len(starts) == 1 and ready_at <= starts[0] < ready_at + .7
    assert owner.interval_timer['COMMISSION_ADVICE'].limit == 7
    assert owner.interval_timer['COMMISSION_START'].limit == 7
    adapter.close_started_commission_detail.assert_called_once()
    owner.ui_ensure.assert_called_once_with('commission')


def test_unproven_native_start_is_not_repeated_or_reported_success():
    owner, adapter, inputs, run = native_owner(102, unproven=True)
    with pytest.raises(SemanticGateClosed, match='remains unproven'): run()
    assert [name for name, _ in inputs].count('COMMISSION_START') == 1
    adapter.close_started_commission_detail.assert_not_called()
    owner.ui_ensure.assert_not_called()


def test_selected_recommend_no_progress_uses_original_three_attempt_recovery():
    owner, adapter, inputs, run = native_owner(999)
    with pytest.raises(NativeGameStuckError, match='commission list flashing bug'):
        run()
    assert [name for name, _ in inputs] == ['COMMISSION_ADVICE'] * 3
    adapter.close_started_commission_detail.assert_not_called()
    owner.ui_ensure.assert_not_called()


def test_recommend_recovery_is_handled_by_original_scheduler():
    from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable

    owner, adapter, inputs, commission = native_owner(999)
    owner.device.sleep = Mock()
    owner.device.package = 'com.bilibili.azurlane'
    config = SimpleNamespace(task_call=Mock())
    host = SimpleNamespace(device=owner.device, config=config,
                           commission=commission, save_error_log=Mock())
    unrelated_error = type('UnrelatedNativeError', (Exception,), {})
    run = method('alas.py', 'AzurLaneAutoScript', 'run',
                 semantic_task_scope=lambda *_: nullcontext(),
                 TaskEnd=unrelated_error, TaskCapabilityUnavailable=TaskCapabilityUnavailable,
                 GameNotRunningError=unrelated_error,
                 GameStuckError=NativeGameStuckError, GameTooManyClickError=unrelated_error)
    assert run(host, 'commission') is False
    assert [name for name, _ in inputs] == ['COMMISSION_ADVICE'] * 3
    config.task_call.assert_called_once_with('Restart')
    owner.device.sleep.assert_called_once_with(10)
    host.save_error_log.assert_called_once()
    adapter.close_started_commission_detail.assert_not_called()
