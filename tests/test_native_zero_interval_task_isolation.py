"""Original scheduler must yield unavailable zero-interval tasks locally."""
from tests.alas_test_source import patched_alas_root
import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticUnmapped
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from alas_headless.oracle.errors import SemanticInputBlocked, SemanticTargetNotActionable
from tests.test_opsi_native_camera_view import native


def methods():
    from module.config.config import AzurLaneConfig, TaskEnd
    from module.config.deep import deep_get, deep_set
    import module.exception as exceptions
    source = patched_alas_root() / 'alas.py'
    scope = dict(vars(exceptions), TaskEnd=TaskEnd, TaskCapabilityUnavailable=TaskCapabilityUnavailable,
                 AzurLaneConfig=AzurLaneConfig,
                 semantic_task_scope=semantic_task_scope, logger=Mock(), datetime=datetime,
                 timedelta=timedelta, deep_get=deep_get, deep_set=deep_set,
                 del_cached_property=Mock(), validate_alas_when_task_queue_empty=lambda x: x,
                 handle_notify=Mock(), inflection=__import__('inflection'))
    tree = ast.parse(source.read_text(encoding='utf-8'))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and n.name in ('run', 'get_next_task', 'wait_until', 'loop')]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
    return scope


def harness(future=False, interval=0):
    import module.config.config as native_config
    from module.config.config import AzurLaneConfig, Function
    from module.config.config_manual import ManualConfig
    from module.config.deep import deep_set
    now = datetime.now().replace(microsecond=0)
    # Other fixtures import a retained baseline tree first. Compile the exact
    # installed queue methods, keeping original dependencies and config model.
    source = patched_alas_root() / 'module/config/config.py'
    config_scope = dict(vars(native_config))
    nodes = [n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
             if isinstance(n, ast.FunctionDef) and n.name in ('get_next_task', 'get_next', 'task_switched')]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), config_scope)
    cls = type('InstalledNativeConfig', (AzurLaneConfig,), {n.name: config_scope[n.name] for n in nodes})
    cfg = cls.__new__(cls)
    cfg.auto_update = False
    cfg.bound = {}
    cfg.modified = {}
    cfg.data = {name: {'Scheduler': {'Enable': True, 'Command': name, 'NextRun': when,
                                    'FailureInterval': interval}}
                for name, when in (('OpsiExplore', now + timedelta(minutes=27) if future else now - timedelta(seconds=1)),
                                   ('Minigame', now - timedelta(seconds=1)))}
    cfg.data['Alas'] = {'Optimization': {'TaskHoardingDuration': 0}}
    cfg.SCHEDULER_PRIORITY = ManualConfig.SCHEDULER_PRIORITY
    cfg.task = Function(cfg.data['OpsiExplore'])
    cfg.Scheduler_NextRun = cfg.task.next_run
    cfg.Scheduler_FailureInterval = interval
    cfg.Optimization_WhenTaskQueueEmpty = 'stay_there'
    cfg.start_watching = Mock()
    cfg.should_reload = Mock(return_value=False)
    def update():
        for path, value in cfg.modified.items():
            deep_set(cfg.data, keys=path, value=value)
        cfg.Scheduler_NextRun = cfg.data[cfg.task.command]['Scheduler']['NextRun']
        cfg.modified.clear()
    cfg.update = update
    cfg.load = Mock()
    def bind(task):
        cfg.task = task
        cfg.Scheduler_NextRun = task.next_run
        cfg.Scheduler_FailureInterval = cfg.data[task.command]['Scheduler']['FailureInterval']
    cfg.bind = bind
    scope = methods()
    host = SimpleNamespace(config=cfg, _semantic_unavailable_tasks=set(), stop_event=None,
        is_first_task=False, failure_record={}, config_name='offline',
        checker=SimpleNamespace(wait_until_available=Mock(), is_recovered=lambda: False),
        device=SimpleNamespace(semantic_adapter=SimpleNamespace(discard_task_state=Mock(), trace=None),
                               screenshot=Mock(), release_during_wait=Mock(),
                               stuck_record_clear=Mock(), click_record_clear=Mock()),
        opsi_explore=Mock(side_effect=AlasSemanticUnmapped('controlled pre-cooldown gap')),
        minigame=Mock())
    cfg._semantic_unavailable_tasks = host._semantic_unavailable_tasks
    for name in ('run', 'get_next_task', 'wait_until'):
        setattr(host, name, lambda *a, _method=scope[name], **kw: _method(host, *a, **kw))
    return host, cfg, scope, now


@pytest.mark.parametrize('interval', [0, '0', '0-0'])
def test_zero_interval_unavailable_task_yields_original_priority_and_inner_switch(native, interval):
    host, cfg, _, now = harness(interval=interval)
    cfg.data['OpsiExplore']['Scheduler']['UpstreamNote'] = 'additive metadata'
    assert host.run('opsi_explore') is None
    assert host._semantic_unavailable_tasks == {'OpsiExplore'}
    assert cfg.data['OpsiExplore']['Scheduler']['NextRun'] <= datetime.now()
    assert cfg.get_next().command == 'Minigame'
    cfg.task = cfg.get_next()
    # A native task's own switch check must share the same admission filter.
    assert cfg.task_switched() is False
    host.device.screenshot.assert_called_once()


@pytest.mark.parametrize('future, interval', [(True, 0), (False, 15)])
def test_future_or_positive_failure_policy_needs_no_admission_filter(native, future, interval):
    host, cfg, _, _ = harness(future=future, interval=interval)
    assert host.run('opsi_explore') is None
    assert host._semantic_unavailable_tasks == set()
    assert cfg.get_next().command == 'Minigame'


@pytest.mark.parametrize('error', [SemanticInputBlocked('os/map/camera-swipe', 10, ('loading',)),
    SemanticTargetNotActionable('dorm/feed', 10)])
@pytest.mark.parametrize('interval', [0, 15])
def test_classified_no_input_refusal_uses_native_delay_and_keeps_next_task(native, error, interval):
    host, cfg, _, now = harness(interval=interval)
    cfg.data['OpsiExplore']['Scheduler']['FutureMetadata'] = {'schema': 2}
    host.opsi_explore.side_effect = error
    before_run = datetime.now().replace(microsecond=0)
    assert host.run('opsi_explore') is None
    assert host.device.semantic_adapter.last_task_outcome['outcome'] == 'input-unavailable'
    assert cfg.data['OpsiExplore']['Scheduler']['Enable'] is True
    next_run = cfg.data['OpsiExplore']['Scheduler']['NextRun']
    if interval > 0:
        assert next_run > now
    else:
        # Zero delay is immediate even when native run() crosses a second.
        assert before_run <= next_run <= datetime.now()
    next_task = cfg.get_next()
    assert next_task.command == 'Minigame'
    cfg.bind(next_task)
    assert host.run('minigame') is True
    host.minigame.assert_called_once()
    assert host.failure_record == {}


def test_healthy_zero_interval_task_keeps_original_continuous_priority(native):
    host, cfg, _, _ = harness()
    host.opsi_explore.side_effect = None
    assert host.run('opsi_explore') is True
    assert host._semantic_unavailable_tasks == set()
    assert cfg.get_next().command == 'OpsiExplore'


def test_other_task_native_positive_deferral_reopens_prior_unavailable_task(native, monkeypatch):
    import sys
    host, cfg, scope, now = harness(interval=15)
    host._semantic_unavailable_tasks.add('OpsiExplore')
    stopped = False
    def positive_deferral():
        nonlocal stopped
        assert cfg.task_switched() is False
        stopped = True
        raise AlasSemanticUnmapped('different task local gap')
    host.minigame.side_effect = positive_deferral
    host.stop_event = SimpleNamespace(is_set=lambda: stopped)
    monkeypatch.setitem(sys.modules, 'module.base.resource', SimpleNamespace(release_resources=Mock()))
    scope['loop'](host)
    assert cfg.data['Minigame']['Scheduler']['NextRun'] > now
    assert host._semantic_unavailable_tasks == set()
    assert cfg.get_next().command == 'OpsiExplore'


def test_all_unavailable_is_distinct_from_no_enabled_tasks(native):
    from module.exception import RequestHumanTakeover
    host, cfg, _, _ = harness()
    host._semantic_unavailable_tasks.update(('OpsiExplore', 'Minigame'))
    assert cfg.get_next() is None
    for row in cfg.data.values():
        if 'Scheduler' in row:
            row['Scheduler']['Enable'] = False
    with pytest.raises(RequestHumanTakeover):
        cfg.get_next()


@pytest.mark.parametrize('reload', [False, True])
def test_native_wait_clock_or_config_change_reopens_task_admission(native, reload):
    host, cfg, scope, now = harness()
    host._semantic_unavailable_tasks.add('OpsiExplore')
    cfg.should_reload.return_value = reload
    ticks = iter([now, now + timedelta(seconds=10)])
    scope['datetime'] = SimpleNamespace(now=lambda: next(ticks))
    scope['time'] = SimpleNamespace(sleep=Mock())
    assert host.wait_until(now + timedelta(seconds=1)) is (not reload)
    scope['time'].sleep.assert_called_once_with(5)
    assert host._semantic_unavailable_tasks == (set() if reload else {'OpsiExplore'})


def test_all_unavailable_uses_original_wait_and_reenters(native, monkeypatch):
    import sys
    host, cfg, _, _ = harness()
    host._semantic_unavailable_tasks.update(('OpsiExplore', 'Minigame'))
    def native_wait(future):
        assert isinstance(future, datetime)
        return True
    host.wait_until = Mock(side_effect=native_wait)
    monkeypatch.setitem(sys.modules, 'module.base.resource', SimpleNamespace(release_resources=Mock()))
    assert host.get_next_task() == 'OpsiExplore'
    host.wait_until.assert_called_once()


@pytest.mark.parametrize('waiting_task', [False, True])
def test_native_loop_other_task_result_reopens_previously_unavailable_task(native, monkeypatch, waiting_task):
    import sys
    host, cfg, scope, now = harness()
    if waiting_task:
        cfg.data['Minigame']['Scheduler']['NextRun'] = now + timedelta(minutes=1)
        host.wait_until = Mock(return_value=True)
    host._semantic_unavailable_tasks.add('OpsiExplore')
    stopped = False
    def finish():
        nonlocal stopped
        assert cfg.task_switched() is False
        stopped = True
    host.minigame.side_effect = finish
    host.stop_event = SimpleNamespace(is_set=lambda: stopped)
    monkeypatch.setitem(sys.modules, 'module.base.resource', SimpleNamespace(release_resources=Mock()))
    scope['loop'](host)
    host.minigame.assert_called_once()
    assert host._semantic_unavailable_tasks == set()
    assert cfg.get_next().command == 'OpsiExplore'
