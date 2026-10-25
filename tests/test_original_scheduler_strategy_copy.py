"""Scheduler qualification preserves task admission, order and runtime state."""

import copy
import importlib.util
from pathlib import Path
import sys
import pytest

scripts = Path(__file__).resolve().parents[1] / 'scripts' / 'python'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('scheduler_live', scripts / 'run_alas_configured_scheduler_live.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('code,requested', [(0, True), (None, True), (1, True), (0, False)])
def test_native_loop_stop_exit_preserves_real_failure_codes(code, requested):
    import threading
    from types import SimpleNamespace
    from unittest.mock import Mock

    stop = threading.Event()
    if requested:
        stop.set()
    app = SimpleNamespace(stop_event=stop, loop=Mock(side_effect=SystemExit(code)))
    if requested and code in (None, 0):
        assert module.run_native_loop(app) is True
    else:
        with pytest.raises(SystemExit) as caught:
            module.run_native_loop(app)
        assert caught.value.code == code
    app.loop.assert_called_once_with()


def test_operator_stop_file_requests_native_stop_and_preserves_request(tmp_path):
    import threading
    stop, finished = threading.Event(), threading.Event()
    request = tmp_path / 'operator.stop'
    watcher = threading.Thread(target=module.watch_stop_file, args=(request, stop, finished))
    watcher.start()
    try:
        assert not stop.wait(0.05)
        request.write_text('stop after the native safe boundary')
        assert stop.wait(2)
        assert request.is_file()
    finally:
        finished.set()
        watcher.join(timeout=2)
    assert not watcher.is_alive()


def test_stop_file_watcher_finishes_without_requesting_stop(tmp_path):
    import threading
    stop, finished = threading.Event(), threading.Event()
    finished.set()
    module.watch_stop_file(tmp_path / 'unused.stop', stop, finished)
    assert not stop.is_set()


def test_session_and_live_click_record_authority_once_without_replaying_cached_input():
    from alas_headless.semantic_oracle import ActionReceipt, Point, Bounds
    receipt = ActionReceipt('tactical/course/confirm', 10, Point(20, 20),
                            Bounds(10, 10, 30, 30), 'exact/Msgbox/confirm')
    record = {'actions': []}
    seen, actual_inputs = [], []
    def live_click(target):
        actual_inputs.append(target)
        module.record_action_receipt(record, receipt, seen)
        return receipt
    native_session_click = module.recorded_click(live_click, lambda: record, seen)
    assert native_session_click('live') is receipt
    assert len(record['actions']) == 1
    # Frame-bound input bypasses the live-click callback but still crosses
    # the same native Device/session boundary.
    frame_receipt = ActionReceipt('tactical/course/confirm', 11, receipt.point,
                                  receipt.bounds, receipt.path)
    frame_call = module.recorded_click(lambda target: frame_receipt, lambda: record, seen)
    assert frame_call('frame') is frame_receipt
    assert frame_call('cached-acknowledgement') is frame_receipt
    assert len(record['actions']) == 2
    assert [x['generation'] for x in record['actions']] == [10, 11]
    assert actual_inputs == ['live']


def test_diagnostic_receipt_failure_or_no_input_does_not_change_native_return():
    record, seen = {'actions': []}, []
    for value in (None, object()):
        call = module.recorded_click(lambda: value, lambda: record, seen)
        assert call() is value
    assert record['actions'] == []
    assert len(record['action_recording_errors']) == 1
    def refused():
        raise RuntimeError('actual input rejected')
    with pytest.raises(RuntimeError, match='actual input rejected'):
        module.recorded_click(refused, lambda: record, seen)()
    assert len(record['action_recording_errors']) == 1


def test_oracle_rebuild_keeps_one_session_failure_diagnostic():
    import ast
    from types import SimpleNamespace
    from unittest.mock import Mock
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle
    main = next(node for node in ast.parse(Path(module.__file__).read_text(encoding='utf8')).body
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    bind = next(node for node in ast.walk(main) if isinstance(node, ast.FunctionDef) and node.name == 'bind_runtime')
    harness = 'def fixture(app, current):\n    session = oracle = last_observed_state = None\n    instrumented, instrumented_sessions, action_receipts_seen = [], [], []\n'
    harness += '\n'.join('    ' + line for line in ast.unparse(bind).splitlines())
    harness += '\n    return bind_runtime\n'
    namespace = dict(module.__dict__)
    owners = Mock(return_value={})
    namespace.update(presence_failure_owners=owners, presence_failure_frame=lambda _: None)
    exec(compile(harness, '<actual runtime recording fixture>', 'exec'), namespace)
    native_appear = Mock(side_effect=RuntimeError('native observation refusal'))
    from alas_headless.semantic_oracle import ActionReceipt, Point, Bounds
    repair_receipt = ActionReceipt('os/port/dock/repair/confirm', 11, Point(20, 20),
                                  Bounds(10, 10, 30, 30), 'exact/repair/confirm')
    native_repair = Mock(return_value=repair_receipt)
    selected = SimpleNamespace(oracle=make_oracle(FakeBackend([])))
    session = SimpleNamespace(click=lambda _: None, appear=native_appear,
        click_operation_siren_port_repair=native_repair,
        combat_is_executing=lambda: False, open=lambda: selected,
        _frame_or_live_observation_oracle=lambda: selected.oracle)
    record = {'actions': []}
    bind_runtime = namespace['fixture'](SimpleNamespace(device=SimpleNamespace(semantic_adapter=session)), record)
    bind_runtime()
    selected.oracle = make_oracle(FakeBackend([]))
    bind_runtime()
    assert session.click_operation_siren_port_repair(True) is repair_receipt
    native_repair.assert_called_once_with(True)
    assert len(record['actions']) == 1
    assert record['actions'][0]['generation'] == 11
    with pytest.raises(RuntimeError, match='native observation refusal'):
        session.appear('LOGIN_CHECK')
    native_appear.assert_called_once_with('LOGIN_CHECK')
    owners.assert_called_once()


@pytest.mark.parametrize('requested', [False, True])
def test_explicit_startup_recovery_uses_native_restart_without_changing_default(requested):
    from types import SimpleNamespace
    calls = []
    app = SimpleNamespace(config=SimpleNamespace(task_call=calls.append), is_first_task=True)
    module.request_startup_restart(app, requested)
    assert calls == (['Restart'] if requested else [])
    assert app.is_first_task is (not requested)


def test_resuming_native_login_preserves_running_client_and_scheduler_state(monkeypatch):
    from types import SimpleNamespace
    calls = []
    app = SimpleNamespace(config=object(), device=object(), is_first_task=True)
    class LoginHandler:
        def __init__(self, config, device):
            assert config is app.config and device is app.device
        def handle_app_login(self):
            calls.append('native_login')
    monkeypatch.setitem(sys.modules, 'module.handler.login', SimpleNamespace(LoginHandler=LoginHandler))
    module.resume_startup_login(app, False)
    assert calls == []
    module.resume_startup_login(app, True)
    assert calls == ['native_login']
    assert app.is_first_task is True


def test_campaign_bound_keeps_enabled_tasks_timers_filters_and_device_binding():
    seed = {'Alas': {'Error': {'HandleError': True, 'SaveError': True, 'OnePushConfig': 'provider'},
                     'Emulator': {'Serial': 'discovered-device'}},
            'Main': {'Scheduler': {'Enable': True, 'NextRun': '2026-09-30 01:00:00'},
                     'StopCondition': {'RunCount': 0, 'OilLimit': 3000}},
            'Event': {'Scheduler': {'Enable': False}, 'StopCondition': {'RunCount': 9999}},
            'Hard': {'Scheduler': {'Enable': True}, 'Hard': {'Campaign': '12-4'}},
            'Research': {'Scheduler': {'Enable': True}, 'Research': {'Filter': 'source-filter'}}}
    before = copy.deepcopy(seed)
    config, overrides = module.prepare_config(seed, 1)
    assert seed == before
    assert config['Main']['Scheduler'] == seed['Main']['Scheduler']
    assert config['Main']['StopCondition']['OilLimit'] == 3000
    assert config['Event'] == seed['Event']
    assert config['Hard'] == seed['Hard']
    assert config['Research'] == seed['Research']
    assert config['Alas']['Emulator'] == seed['Alas']['Emulator']
    assert config['Alas']['Error']['HandleError'] is True
    assert config['Alas']['Error']['SaveError'] is False
    assert config['Alas']['Error']['OnePushConfig'] == ''
    assert overrides == {'Main': {'original': 0, 'qualification': 1}}


def test_unbounded_scheduler_preserves_original_campaign_policy():
    seed = {'Alas': {'Error': {}}, 'Main': {'Scheduler': {'Enable': True}, 'StopCondition': {'RunCount': 0}}}
    config, overrides = module.prepare_config(seed, None)
    assert config['Main'] == seed['Main']
    assert overrides == {}


@pytest.mark.parametrize('handle_error', [True, False])
def test_copied_scheduler_keeps_explicit_recovery_choice(handle_error):
    seed = {'Alas': {'Error': {'HandleError': handle_error}}}
    config, _ = module.prepare_config(seed, None)
    assert config['Alas']['Error']['HandleError'] is handle_error


def test_campaign_bound_follows_native_capability_for_additional_task_panels():
    seed = {'Alas': {'Error': {}},
            'Hard': {'Scheduler': {'Enable': True}},
            'Research': {'Scheduler': {'Enable': True}}}
    for task in ('Main2', 'Main3', 'Event2', 'EventA', 'FutureCampaign'):
        seed[task] = {'Scheduler': {'Enable': True}, 'StopCondition': {'RunCount': 0}}
    config, overrides = module.prepare_config(seed, 2)
    assert set(overrides) == {'Main2', 'Main3', 'Event2', 'EventA', 'FutureCampaign'}
    assert all(config[task]['StopCondition']['RunCount'] == 2 for task in overrides)
    assert all(seed[task]['StopCondition']['RunCount'] == 0 for task in overrides)
    assert config['Hard'] == seed['Hard']
    assert config['Research'] == seed['Research']


def test_persistent_resume_uses_native_saved_timers_and_progress(tmp_path):
    import json
    (tmp_path / 'config').mkdir()
    seed = {'Alas': {'Error': {'HandleError': True}},
            'Research': {'Scheduler': {'Enable': True, 'NextRun': '2026-10-04 08:00:00'}},
            'OpsiExplore': {'Storage': {'LastZone': 111}}}
    _, path, config, _, resumed = module.prepare_run_config(tmp_path, seed, None, 'continuous')
    assert not resumed
    config['Research']['Scheduler']['NextRun'] = '2026-10-04 11:15:00'
    config['OpsiExplore']['Storage']['LastZone'] = 121
    path.write_text(json.dumps(config), encoding='utf-8')
    _, retained, config, _, resumed = module.prepare_run_config(tmp_path, seed, None, 'continuous')
    assert resumed and retained == path
    assert config['Research']['Scheduler']['NextRun'] == '2026-10-04 11:15:00'
    assert config['OpsiExplore']['Storage']['LastZone'] == 121
    assert config['Alas']['Error']['HandleError'] is True
    assert seed['OpsiExplore']['Storage']['LastZone'] == 111


def test_continuous_mode_leaves_failed_task_delay_and_reselection_to_alas():
    assert module.should_stop(False, 1, 3)
    assert not module.should_stop(False, 1, 3, continue_after_failure=True)
    assert not module.should_stop(True, 2, 3, continue_after_failure=True)
    assert module.should_stop(False, 3, 3, continue_after_failure=True)


def test_continuous_mode_has_no_qualification_task_count_cutoff():
    assert not module.should_stop(True, 1000, None, continue_after_failure=True)
    assert not module.should_stop(None, 1000, None, continue_after_failure=True)
    assert not module.should_stop(False, 1000, None, continue_after_failure=True)
    assert module.should_stop(False, 1000, None)


def test_duration_selection_is_explicit_and_mutually_exclusive():
    base = ['--alas-root', 'root', '--seed-config', 'seed', '--driver-revision', 'revision',
            '--output', 'receipt.json']
    _, args = module.parse_args(base + ['--continuous'])
    assert args.continuous and args.max_tasks is None and args.continue_after_failure
    assert args.resume_task is None
    _, resumed = module.parse_args(base + ['--continuous', '--resume-task', 'Tactical'])
    assert resumed.resume_task == 'Tactical'
    with pytest.raises(SystemExit):
        module.parse_args(base + ['--continuous', '--resume-task', 'Tactical', '--login-before-loop'])
    _, args = module.parse_args(base + ['--max-tasks', '8'])
    assert not args.continuous and args.max_tasks == 8
    for options in ([], ['--continuous', '--max-tasks', '8'], ['--max-tasks', '0']):
        with pytest.raises(SystemExit):
            module.parse_args(base + options)


def test_native_task_renewal_keeps_each_task_bounded_and_purchase_denied():
    from types import SimpleNamespace
    from alas_headless.adapter import (ActionLedger, DEFAULT_CAPABILITY_INVENTORY,
        RecoveryPolicy, compatibility_profile, compatibility_policy_sha256)
    from alas_headless.adapter.errors import ActionLeaseError
    grants = {'commission.reward': 1, 'dorm.collect': 1, 'shop.purchase': 0}
    profile = compatibility_profile('continuous-native-task', grants)
    ledger = ActionLedger(profile=profile, inventory=DEFAULT_CAPABILITY_INVENTORY,
        grants=grants, recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
        policy_sha256=compatibility_policy_sha256(profile.profile_id, grants))
    adapter = SimpleNamespace(_action_ledger=ledger)
    session = SimpleNamespace(action_ledger=ledger, open=lambda: adapter)
    ledger.dispatch('commission.reward', lambda: 'accepted first task')
    with pytest.raises(ActionLeaseError):
        ledger.dispatch('commission.reward', lambda: 'duplicate')
    assert not module.maybe_renew_native_task_grants(session, False, 'commission', 'commission')
    assert not module.maybe_renew_native_task_grants(session, True, 'goto_main', 'commission')
    assert session.action_ledger is ledger and ledger.remaining('commission.reward') == 0
    # The continuous runner renews only at the next native task boundary.
    assert module.maybe_renew_native_task_grants(session, True, 'commission', 'commission')
    renewed = session.action_ledger
    assert renewed is adapter._action_ledger and renewed is not ledger
    assert renewed.remaining('commission.reward') == 1
    assert renewed.remaining('shop.purchase') == 0
    assert not ledger.allowed('commission.reward')
    with pytest.raises(ActionLeaseError):
        ledger.dispatch('dorm.collect', lambda: 'stale task reference')
    renewed.dispatch('commission.reward', lambda: 'accepted next task')
    with pytest.raises(ActionLeaseError):
        renewed.dispatch('commission.reward', lambda: 'duplicate next task')
    with pytest.raises(ActionLeaseError):
        renewed.dispatch('shop.purchase', lambda: 'purchase')


def test_resume_preserves_remaining_native_campaign_attempt(tmp_path):
    import json
    (tmp_path / 'config').mkdir()
    seed = {'Alas': {'Error': {}}, 'Main': {'Scheduler': {'Enable': True}, 'StopCondition': {'RunCount': 0}}}
    _, path, config, _, _ = module.prepare_run_config(tmp_path, seed, 2, 'continuous')
    config['Main']['StopCondition']['RunCount'] = 1
    path.write_text(json.dumps(config), encoding='utf-8')
    _, _, resumed, _, _ = module.prepare_run_config(tmp_path, seed, 2, 'continuous')
    assert resumed['Main']['StopCondition']['RunCount'] == 1


def test_qualification_bound_does_not_mask_invalid_native_count():
    for count in (True, -1, '2'):
        seed = {'Alas': {'Error': {}}, 'Main': {'Scheduler': {'Enable': True}, 'StopCondition': {'RunCount': count}}}
        config, overrides = module.prepare_config(seed, 2)
        assert config['Main']['StopCondition']['RunCount'] == count
        assert overrides == {}


def test_native_owner_recovery_restores_priority_before_first_execution():
    from types import SimpleNamespace
    from unittest.mock import Mock, call
    config = Mock(SCHEDULER_PRIORITY='Restart > Commission > Tactical')
    config.task_call.return_value = True
    original = Mock(return_value=True)
    app = SimpleNamespace(config=config, run=original)
    module.request_startup_task(app, 'Tactical')
    config.task_call.assert_called_once_with('Tactical', force_call=False)
    assert app.run('tactical', skip_first_screenshot=False) is True
    assert app.run is original
    assert config.override.call_args_list == [
        call(SCHEDULER_PRIORITY='Tactical > Restart > Commission > Tactical'),
        call(SCHEDULER_PRIORITY='Restart > Commission > Tactical')]
    original.assert_called_once_with('tactical', skip_first_screenshot=False)


def test_native_owner_recovery_cannot_enable_disabled_task():
    from types import SimpleNamespace
    from unittest.mock import Mock
    config = Mock(SCHEDULER_PRIORITY='Restart > Commission')
    config.task_call.return_value = False
    original = Mock()
    app = SimpleNamespace(config=config, run=original)
    with pytest.raises(ValueError):
        module.request_startup_task(app, 'Tactical')
    assert app.run is original
    config.override.assert_not_called()


def test_operator_deadline_requests_existing_stop_without_stop_file(monkeypatch):
    import threading
    from datetime import datetime, timezone
    from unittest.mock import Mock
    stop = threading.Event()
    clock = [1000.0]
    def wait(_interval):
        assert not stop.is_set()
        clock[0] = 1001.0
    finished = Mock(is_set=Mock(return_value=False), wait=wait)
    monkeypatch.setattr(module.time, "time", lambda: clock[0])
    record = {}
    module.watch_stop_file(None, stop, finished, datetime.fromtimestamp(1001, timezone.utc), record)
    assert stop.is_set() and record == dict(reason="deadline", requested_at=1001)


def test_finished_run_does_not_acquire_a_later_deadline_stop():
    import threading
    from datetime import datetime, timezone
    stop, finished = threading.Event(), threading.Event()
    finished.set()
    record = {}
    module.watch_stop_file(None, stop, finished, datetime.fromtimestamp(1, timezone.utc), record)
    assert not stop.is_set() and record == {}


@pytest.mark.parametrize("value", ["2026-10-25T15:45:00+08:00", "2026-10-25T07:45:00Z"])
def test_operator_deadline_has_explicit_timezone(value):
    assert module.parse_stop_at(value).timestamp() == 1792914300


@pytest.mark.parametrize("value", ["2026-10-25T15:45:00", "not-a-timestamp"])
def test_ambiguous_or_malformed_operator_deadline_is_rejected(value):
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        module.parse_stop_at(value)
