"""Run the original ALAS scheduler with copied or persistent semantic state."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
import uuid

from run_alas_configured_task_live import parse_action_budgets, encode_receipt_value

ROOT = Path(__file__).resolve().parents[2]


def scheduler_receipt_payload(value):
    """Encode retained Guild diagnostics at publication, outside live reads."""
    published = dict(value)
    tasks = []
    for task in value.get('tasks', []):
        observation = task.get('guild_node_post_input_observation')
        if observation is not None:
            task = dict(task)
            task['guild_node_post_input_observation'] = encode_receipt_value(observation)
        tasks.append(task)
    published['tasks'] = tasks
    return published


def write_scheduler_receipt(path: Path, value) -> None:
    """Publish a complete receipt without truncating the currently readable one."""
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Reuse the existing live-trace Windows sharing-violation policy. Each
    # task owns one output; no build lock, run handshake or fsync is needed.
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                # Preserve both the last published receipt and the new full
                # temporary receipt for diagnosis instead of a partial JSON.
                raise
            time.sleep(.025)


def commission_start_ui_record(observed):
    """Retain relevant fields from a read ALAS already performed."""
    root = 'Overlay/UIMain/blur_panel/scrollItem/'
    return {
        'generation': observed.generation,
        'method_mask': observed.method_mask,
        'image_truncated': observed.image_truncated,
        'texts': [dict(path=t.path, text=t.text, truncated=t.truncated)
                  for t in observed.texts if t.active_in_hierarchy and t.active_and_enabled
                  and (root in t.path or '/UIOverlay/TipPanel' in t.path)],
        'images': [dict(path=i.path, sprite=i.sprite, color=i.color, truncated=i.truncated)
                   for i in observed.images if i.active_in_hierarchy and i.active_and_enabled
                   and root in i.path and any(part in i.path for part in
                       ('/iconState$', '/iconType$', '/btn/start', '/conditions/'))],
    }


def prepare_config(seed, campaign_run_limit):
    config = copy.deepcopy(seed)
    # HandleError owns native restart/recovery and must retain the seed policy.
    config['Alas']['Error'].update(SaveError=False, OnePushConfig='')
    overrides = {}
    if campaign_run_limit is not None:
        # ALAS campaign variants expose the same native RunCount contract.
        # Hard has a separate daily quota and no StopCondition group.
        for task, panel in config.items():
            if not isinstance(panel, dict) or not panel.get('Scheduler', {}).get('Enable'):
                continue
            stop_condition = panel.get('StopCondition')
            if isinstance(stop_condition, dict) and 'RunCount' in stop_condition:
                previous = stop_condition['RunCount']
                if type(previous) is not int or previous < 0:
                    continue  # Preserve malformed input for its native contract.
                bounded = min(previous, campaign_run_limit) if previous else campaign_run_limit
                stop_condition['RunCount'] = bounded
                overrides[task] = {'original': previous, 'qualification': bounded}
    return config, overrides


def prepare_run_config(alas_root, seed, campaign_run_limit, persistent_name=None):
    """Keep native timers and progress when resuming a named ALAS config."""
    name = persistent_name or '_codex_scheduler_' + uuid.uuid4().hex
    if Path(name).name != name or name in ('.', '..') or '/' in name or '\\' in name:
        raise ValueError('config name must be a name within the ALAS config directory')
    path = alas_root / 'config' / (name + '.json')
    resumed = bool(persistent_name and path.exists())
    source = json.loads(path.read_text(encoding='utf-8')) if resumed else seed
    config, overrides = prepare_config(source, campaign_run_limit)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return name, path, config, overrides, resumed


def should_stop(returned, task_count, max_tasks, continue_after_failure=False):
    return ((max_tasks is not None and task_count >= max_tasks)
            or (returned is False and not continue_after_failure))


def run_native_loop(app):
    """Recognize ALAS' normal stop exit while it is waiting for NextRun."""
    try:
        app.loop()
    except SystemExit as exc:
        if exc.code not in (None, 0) or not app.stop_event.is_set():
            raise
        return True
    return False


def watch_stop_file(path, stop_event, finished):
    """Translate an operator request into ALAS' existing cooperative stop."""
    while not finished.is_set() and not stop_event.is_set():
        if path.is_file():
            stop_event.set()
            return
        finished.wait(0.5)


def request_startup_restart(app, requested):
    """Explicit recovery uses native Restart selection and LoginHandler."""
    if requested:
        app.config.task_call('Restart')
        # Native loop normally skips its first scheduled Restart because it
        # assumes the client is ready. Explicit startup recovery needs it.
        app.is_first_task = False


def resume_startup_login(app, requested):
    """Let native LoginHandler resume an already-running updating client."""
    if requested:
        from module.handler.login import LoginHandler
        LoginHandler(app.config, device=app.device).handle_app_login()


def renew_native_task_grants(session):
    """Start one bounded native task allowance without widening its grants.

    Continuous service authorizes recurring ordinary task runs. Qualification
    keeps its original run-wide allowance. This is called only between native
    scheduled runs, never from a retry or observation/input handler.
    """
    from alas_headless.adapter.ledger import ActionLedger
    previous = session.action_ledger
    replacement = ActionLedger(profile=previous.profile, inventory=previous.inventory,
        grants=previous.initial_grants, recovery_policy=previous.recovery_policy,
        policy_sha256=previous.policy_sha256)
    report = replacement.require_preflight()
    adapter = session.open()
    previous.close()
    session.action_ledger = replacement
    session.capability_report = report
    adapter._action_ledger = replacement


def maybe_renew_native_task_grants(session, continuous, command, selected_command):
    if not continuous or command != selected_command:
        return False
    renew_native_task_grants(session)
    return True


class _RecordedAction:
    def __init__(self, receipt, input_count, action_index):
        self.receipt = receipt
        self.input_count = input_count
        self.action_index = action_index


def record_action_receipt(current, receipt, seen):
    """Record returned authority once; cached acknowledgement is not new input."""
    if current is None or receipt is None or any(
            getattr(previous, 'receipt', previous) is receipt for previous in seen):
        return
    try:
        from alas_headless.semantic_oracle import ActionReceipt
        if not isinstance(receipt, ActionReceipt):
            raise TypeError('click returned no typed ActionReceipt')
        encoded = dataclasses.asdict(receipt)
    except Exception as error:
        # A diagnostic cannot change the outcome of an already accepted input.
        current.setdefault('action_recording_errors', []).append(str(error))
        return
    input_count = len(current['native_taps']) if 'native_taps' in current else None
    if input_count is not None and receipt.policy_sha256 and receipt.capability_id:
        # ActionLedger adds authorization metadata with dataclasses.replace.
        # That copy describes the same dispatch only if no native input was
        # added and every input field is unchanged. Two real inputs, including
        # two at the same generation/target, remain separate records.
        for previous in reversed(seen):
            if (not isinstance(previous, _RecordedAction)
                    or previous.input_count != input_count
                    or previous.receipt.policy_sha256 is not None
                    or previous.receipt.capability_id is not None):
                continue
            raw = current['actions'][previous.action_index]
            if all(raw.get(key) == value for key, value in encoded.items()
                   if key not in ('policy_sha256', 'capability_id')):
                current['actions'][previous.action_index] = encoded
                seen.append(_RecordedAction(receipt, input_count, previous.action_index))
                return
    seen.append(_RecordedAction(receipt, input_count, len(current['actions'])))
    current['actions'].append(encoded)


def recorded_retirement(call, receipt_reader, current_record):
    """Retain each native dock transaction without attributing cached history."""
    def invoke(*values, **options):
        before = None
        baseline_known = False
        try:
            before = receipt_reader()
            baseline_known = True
        except Exception as exc:
            record = current_record()
            if record is not None:
                record.setdefault('retirement_recording_errors', []).append(str(exc))
        try:
            return call(*values, **options)
        finally:
            record = current_record()
            if record is not None:
                try:
                    after = receipt_reader()
                    if baseline_known and after is not None and after is not before:
                        record.setdefault('retirement_receipts', []).append(encode_receipt_value(after))
                except Exception as exc:
                    record.setdefault('retirement_recording_errors', []).append(str(exc))
    return invoke


def recorded_click(call, current_record, seen, *, session=None):
    """Observe the session click boundary, including frame-bound operations."""
    def click(*values, **options):
        try:
            receipt = call(*values, **options)
        except Exception as exc:
            # ALAS' error handler can take another screenshot before run()
            # returns. Retain this immutable frame before that diagnostic IO.
            # It may still precede a live fallback, so do not call it the exact
            # failed input frame or use it to authorize another action.
            record = current_record()
            if session is not None and record is not None:
                try:
                    button = values[0] if values else None
                    record['failed_click'] = {
                        'resource': button if isinstance(button, str) else getattr(button, 'name', None),
                        'error_type': type(exc).__name__,
                        'error': str(exc),
                        'retained_screenshot_before_error_handler': presence_failure_frame(session),
                    }
                except Exception as diagnostic_error:
                    record['failed_click_recording_error'] = str(diagnostic_error)
            raise
        record_action_receipt(current_record(), receipt, seen)
        return receipt
    return click


def presence_screenshot_record(frame, *, scope):
    """Encode a retained immutable frame only when a diagnostic needs it."""
    if frame is None:
        return None
    return {'scope': scope, 'frame': encode_receipt_value(frame)}


def presence_failure_frame(session):
    """Copy the retained screenshot for diagnostics without acquiring state.

    This historical frame is not proof of current input readiness, or proof
    that a live fallback used it. Keep it separate from later diagnostic reads.
    """
    clock = getattr(session, '_frame_clock', None)
    frame = getattr(clock, '_current', None)
    return presence_screenshot_record(frame,
        scope='last immutable ALAS screenshot at failure; diagnostic only')


def map_swipe_attempts(oracle, offset=0):
    """Copy already recorded inputs, including failed postconditions, without IO."""
    return encode_receipt_value(getattr(oracle, '_operation_siren_map_swipe_attempts', [])[offset:])


def presence_failure_owners(session):
    """Record only scalar owner metadata, before diagnostic frame reads."""
    adapter = getattr(session, 'adapter', None)
    if adapter is None:
        return None
    contexts = {}
    for name in ('_campaign_context', '_mission_context', '_commission_context',
                 '_dorm_context', '_research_context', '_build_context'):
        context = getattr(adapter, name, None)
        contexts[name] = None if context is None else {
            'type': type(context).__name__,
            'flow_kind': getattr(context, 'flow_kind', None),
        }
    return {
        'recorded_monotonic': time.monotonic(),
        'contexts': contexts,
        'flags': {name: getattr(adapter, name, None) for name in (
            '_operation_siren_combat_active', '_meta_beacon_active', '_meta_assist_active')},
        'login_active': getattr(getattr(adapter, '_login_flow', None), 'active', None),
        'deadlines': {name: getattr(adapter, name, None) for name in (
            '_main_guild_entry_until', '_guild_return_transition_until',
            '_commission_return_transition_until', '_main_dock_transition_until')},
    }


def request_startup_task(app, task):
    """Let native selection recover one owner, then restore normal priority."""
    if not task:
        return
    startup_priority = app.config.SCHEDULER_PRIORITY
    if not app.config.task_call(task, force_call=False):
        raise ValueError('startup recovery task is disabled')
    app.config.override(SCHEDULER_PRIORITY=task + ' > ' + startup_priority)
    native_run = app.run

    def resume_run(command, *values, **options):
        app.config.override(SCHEDULER_PRIORITY=startup_priority)
        app.run = native_run
        return native_run(command, *values, **options)

    app.run = resume_run


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', required=True, type=Path)
    parser.add_argument('--seed-config', required=True)
    parser.add_argument('--driver-revision', required=True)
    duration = parser.add_mutually_exclusive_group(required=True)
    duration.add_argument('--max-tasks', type=int)
    duration.add_argument('--continuous', action='store_true',
        help='Keep ALAS.loop running; explicit budgets apply to each native scheduled task run')
    parser.add_argument('--campaign-run-limit', type=int)
    parser.add_argument('--persistent-config',
                        help='Named config initialized once from the seed; retained for native resume')
    parser.add_argument('--continue-after-failure', action='store_true',
                        help='Let ALAS apply its native failure delay and select the next task')
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument('--restart-before-loop', action='store_true',
                        help='Request native Restart/login before resuming scheduled tasks')
    recovery.add_argument('--login-before-loop', action='store_true',
                         help='Resume native login on the running client before scheduled tasks')
    recovery.add_argument('--resume-task',
                         help='Prioritize one enabled native popup owner for startup recovery only')
    parser.add_argument('--budget', action='append', default=[])
    parser.add_argument('--stop-file', type=Path,
                        help='Request native cooperative stop when this file exists; never deletes the file')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    args.continue_after_failure = args.continuous or args.continue_after_failure
    if ((args.max_tasks is not None and args.max_tasks < 1)
            or (args.campaign_run_limit is not None and args.campaign_run_limit < 1)):
        parser.error('task and optional campaign limits must be positive')
    return parser, args


def main():
    parser, args = parse_args()
    sys.path.insert(0, str(ROOT / 'python'))
    try:
        budgets = parse_action_budgets(args.budget)
    except ValueError as exc:
        parser.error(str(exc))
    alas_root, output = args.alas_root.resolve(), args.output.resolve()
    stop_file = args.stop_file.resolve() if args.stop_file is not None else None
    if output.exists():
        parser.error(f'output already exists: {output}')
    seed_path = alas_root / 'config' / (args.seed_config + '.json')
    seed_raw = seed_path.read_bytes()
    try:
        name, temporary, config, overrides, resumed = prepare_run_config(
            alas_root, json.loads(seed_raw), args.campaign_run_limit, args.persistent_config)
    except ValueError as exc:
        parser.error(str(exc))
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
                      ALAS_SEMANTIC_ADB='adb', **budgets)
    sys.path[:0] = [str(ROOT / 'python'), str(alas_root)]
    os.chdir(alas_root)
    result = {'schema': 'alas-headless.original-scheduler-live/v1',
              'scope': 'original ALAS.loop selection, execution and scheduling; copied strategy',
              'seed_config': args.seed_config, 'seed_sha256': hashlib.sha256(seed_raw).hexdigest(),
              'serial': config['Alas']['Emulator']['Serial'], 'budgets': args.budget,
              'campaign_run_overrides': overrides, 'max_tasks': args.max_tasks,
              'continuous': args.continuous,
              'stop_file': str(stop_file) if stop_file is not None else None,
              'startup_restart_requested': args.restart_before_loop,
              'startup_login_requested': args.login_before_loop,
              'startup_resume_task': args.resume_task,
              'action_grant_scope': 'native_scheduled_task' if args.continuous else 'run',
              'run_config': name, 'persistent_config': bool(args.persistent_config),
              'resumed_config': resumed, 'continue_after_failure': args.continue_after_failure,
              'tasks': [], 'terminal': False, 'passed': False}
    started = time.monotonic()
    session = None
    stop_watcher_finished = threading.Event()
    stop_watcher = None

    def save():
        write_scheduler_receipt(output, scheduler_receipt_payload(result))

    try:
        from alas import AzurLaneAutoScript
        from alas import inflection
        app = AzurLaneAutoScript(name)
        app.stop_event = threading.Event()
        if stop_file is not None:
            stop_watcher = threading.Thread(
                target=watch_stop_file,
                args=(stop_file, app.stop_event, stop_watcher_finished),
                name='alas-operator-stop', daemon=True,
            )
            stop_watcher.start()
        original_run = app.run
        current = None
        oracle = None
        last_observed_state = None
        instrumented = []
        instrumented_sessions = []
        action_receipts_seen = []

        def bind_runtime():
            nonlocal session, oracle
            session = app.device.semantic_adapter
            if not any(existing is session for existing in instrumented_sessions):
                instrumented_sessions.append(session)
                session.click = recorded_click(session.click, lambda: current, action_receipts_seen, session=session)
                retirement = getattr(session, 'retire_ships_one_click', None)
                receipt_reader = getattr(session, 'retirement_receipt', None)
                if callable(retirement) and callable(receipt_reader):
                    session.retire_ships_one_click = recorded_retirement(
                        retirement, receipt_reader, lambda: current)
                port_repair = getattr(session, 'click_operation_siren_port_repair', None)
                if callable(port_repair):
                    session.click_operation_siren_port_repair = recorded_click(
                        port_repair, lambda: current, action_receipts_seen, session=session)
                original_appear = session.appear
                def appear(button):
                    # Holding this immutable object has no device-read or encoding
                    # cost. The session may refresh internally before it raises;
                    # preserve both points only on that failure path.
                    entry_frame = getattr(getattr(session, '_frame_clock', None), '_current', None)
                    try:
                        return original_appear(button)
                    except Exception as error:
                        if current is not None:
                            current['failed_presence'] = {
                                'name': getattr(button, 'name', str(button)),
                                'error_type': type(error).__name__,
                                'error_message': str(error),
                            }
                            try:
                                current['failed_presence']['retained_screenshot_at_session_entry'] = presence_screenshot_record(
                                    entry_frame, scope='frame at session.appear entry; may precede internal refresh; diagnostic only')
                            except Exception as exc:
                                current['failed_presence']['entry_screenshot_recording_error'] = str(exc)
                            try:
                                current['failed_presence']['retained_screenshot_before_diagnostic_reads'] = presence_failure_frame(session)
                            except Exception as exc:
                                current['failed_presence']['screenshot_recording_error'] = str(exc)
                            try:
                                current['failed_presence']['owners_before_diagnostic_reads'] = presence_failure_owners(session)
                            except Exception as exc:
                                current['failed_presence']['owner_recording_error'] = str(exc)
                            try:
                                frame_oracle = session.open()._frame_or_live_observation_oracle()
                                current['failed_presence']['state'] = encode_receipt_value(frame_oracle.read_state())
                                current['failed_presence']['ui'] = encode_receipt_value(frame_oracle.read_ui_state())
                            except Exception as exc:
                                current['failed_presence_record_error'] = str(exc)
                        raise
                session.appear = appear
                original_combat_presence = session.combat_is_executing

                def combat_presence():
                    entry_frame = getattr(getattr(session, '_frame_clock', None), '_current', None)
                    try:
                        return original_combat_presence()
                    except Exception as error:
                        if current is not None:
                            current['failed_combat_observation'] = {
                                'method': 'combat_is_executing',
                                'error_type': type(error).__name__,
                                'error_message': str(error),
                            }
                            try:
                                current['failed_combat_observation']['retained_screenshot_at_session_entry'] = presence_screenshot_record(
                                    entry_frame, scope='immutable combat probe entry before native error recovery; diagnostic only')
                            except Exception as exc:
                                current['failed_combat_observation']['recording_error'] = str(exc)
                        raise

                session.combat_is_executing = combat_presence
            oracle = session.open().oracle
            if any(existing is oracle for existing in instrumented):
                return
            instrumented.append(oracle)
            original_state, original_tap, original_click = oracle.read_state, oracle._tap, oracle.click
            original_ui = oracle.read_ui_state
            input_semantic_target = None
            guild_node_probe = False
            last_guild_ui = None
            commission_probe_owner = None

            def record_guild_node_observation(kind, observed):
                if guild_node_probe and current is not None and current['command'] == 'guild':
                    try:
                        current.setdefault('guild_node_post_input_observation', {
                            'scope': 'Existing native post-node reads; no additional observer request'
                        # The transport gives each read its own snapshot. Keep
                        # its reference here; recursive encoding between state
                        # and UI reads can itself break their coherence window.
                        })[kind] = observed
                    except Exception as exc:
                        current['guild_node_post_input_recording_error'] = str(exc)

            def state(*values, **options):
                nonlocal last_observed_state
                observed = original_state(*values, **options)
                last_observed_state = observed
                record_guild_node_observation('state', observed)
                return observed

            def ui(*values, **options):
                nonlocal last_guild_ui
                observed = original_ui(*values, **options)
                last_guild_ui = observed
                record_guild_node_observation('ui', observed)
                if current is not None and commission_probe_owner is current:
                    try:
                        recorded = commission_start_ui_record(observed)
                        probe = current['commission_start_observation']
                        probe.setdefault('first_post_input_ui', recorded)
                        probe['latest_post_input_ui'] = recorded
                        tips = probe.setdefault('observed_tips', [])
                        for text in recorded['texts']:
                            if '/UIOverlay/TipPanel' in text['path'] and text['text'] not in tips:
                                tips.append(text['text'])
                    except Exception as exc:
                        current['commission_start_recording_error'] = str(exc)
                return observed

            def tap(*values, **options):
                nonlocal guild_node_probe, commission_probe_owner
                # Preserve the already-read input frame for the observed
                # Commission reward-page drift. Encoding happens after input;
                # this diagnostic adds no observer read or admission gate.
                reward_frame = (last_observed_state
                                if current is not None
                                and current['command'] == 'commission'
                                and input_semantic_target in (
                                    'reward/commission/finish',
                                    'reward/ship-exp/close',
                                    'reward/award-info/close',
                                    'reward/award-info1/close') else None)
                guild_frame = (last_observed_state
                               if current is not None and current['command'] == 'guild'
                               and last_observed_state is not None
                               and any('/GuildEventPage(Clone)/missionlist/path/' in b.path
                                       and b.point is not None
                                       and b.bounds is not None
                                       and [int(round((b.bounds.left + b.bounds.right) / 2)),
                                            int(round((b.bounds.top + b.bounds.bottom) / 2))] == list(values)
                                       for b in last_observed_state.buttons) else None)
                value = original_tap(*values, **options)
                guild_node_probe = guild_frame is not None
                if current is not None and current['command'] == 'commission' and last_observed_state is not None:
                    starts = [b for b in last_observed_state.buttons
                              if b.path.endswith('Overlay/UIMain/blur_panel/scrollItem/maskDetail/detailPanel/btn')
                              and b.point is not None
                              and [int(round(b.point.x)), int(round(b.point.y))] == list(values)]
                    if len(starts) == 1:
                        try:
                            current['commission_start_observation'] = {
                                'scope': 'Existing pre-start and native post-start reads only; no extra request or input',
                                'input_generation': last_observed_state.generation,
                                'input_path': starts[0].path,
                                'pre_input_ui': commission_start_ui_record(last_guild_ui),
                            }
                            commission_probe_owner = current
                        except Exception as exc:
                            current['commission_start_recording_error'] = str(exc)
                if current is not None:
                    recorded = {'point': list(values), 'returned': True}
                    if reward_frame is not None or guild_frame is not None:
                        recorded['semantic_target'] = input_semantic_target
                        recorded['pre_input_state_scope'] = 'Existing final oracle read before tap; no additional observer request'
                        try:
                            recorded['pre_input_state'] = encode_receipt_value(
                                reward_frame if reward_frame is not None else guild_frame)
                        except Exception as exc:
                            # Diagnostic serialization cannot turn an accepted
                            # native input into a failed game operation.
                            recorded['pre_input_state_recording_error'] = str(exc)
                    current['native_taps'].append(recorded)
                return value

            def click(target):
                nonlocal input_semantic_target
                previous_target = input_semantic_target
                input_semantic_target = target
                try:
                    receipt = original_click(target)
                finally:
                    input_semantic_target = previous_target
                record_action_receipt(current, receipt, action_receipts_seen)
                return receipt

            oracle.read_state, oracle._tap, oracle.click = state, tap, click
            oracle.read_ui_state = ui
            original_guild_operations = oracle.guild_operations_state
            def guild_operations(*values, **options):
                observed = original_guild_operations(*values, **options)
                if current is not None and current['command'] == 'guild':
                    try:
                        current['guild_operations_observation'] = {
                            'scope': 'Existing Guild admission read; no extra observer request',
                            'operations': encode_receipt_value(observed),
                            'state': encode_receipt_value(last_observed_state),
                            'ui': encode_receipt_value(last_guild_ui),
                        }
                    except Exception as exc:
                        current['guild_operations_recording_error'] = str(exc)
                return observed
            oracle.guild_operations_state = guild_operations
            original_swipe = oracle._swipe
            if original_swipe is not None:
                def swipe(*values, **options):
                    frame = (last_observed_state if current is not None
                             and current['command'] == 'guild' else None)
                    value = original_swipe(*values, **options)
                    if frame is not None:
                        recorded = dict(points=list(values), returned=True,
                                        scope='Existing Guild input frame; no extra observer request')
                        try:
                            recorded['pre_input_state'] = encode_receipt_value(frame)
                        except Exception as exc:
                            recorded['recording_error'] = str(exc)
                        current.setdefault('native_swipes', []).append(recorded)
                    return value
                oracle._swipe = swipe

        def run(command, *values, **options):
            nonlocal current, last_observed_state
            # ALAS can call goto_main during an idle wait; retain that native
            # navigation separately from its selected scheduled tasks.
            scheduled = app.config.task.command
            current = {'selected_task': scheduled, 'command': command, 'actions': [],
                       'native_taps': [],
                       'return': None, 'started_at': time.time(), 'terminal': False}
            result['tasks'].append(current)
            task_started = time.monotonic()
            receipt_offsets = {}
            map_swipe_offset = 0
            last_observed_state = None
            action_receipts_seen.clear()
            save()
            try:
                try:
                    bind_runtime()
                    map_swipe_offset = len(getattr(oracle, '_operation_siren_map_swipe_attempts', []))
                    current['runtime_bound'] = True
                    if maybe_renew_native_task_grants(
                            session, args.continuous, command, inflection.underscore(scheduled)):
                        current['native_task_grants_renewed'] = True
                    ledger = getattr(session, 'action_ledger', None)
                    if ledger is not None:
                        current['starting_action_grants'] = {
                            key: ledger.remaining(key) for key in ledger.initial_grants}
                    for key in ('awaken_receipts', 'awaken_cost_observations',
                                'enhancement_receipts', 'daily_execution_receipts'):
                        reader = getattr(session, key, None)
                        if callable(reader):
                            receipt_offsets[key] = len(reader())
                except Exception as exc:
                    # Observation recording must not prevent original restart
                    # from restoring a runtime that cannot yet be observed.
                    current['recording_error'] = str(exc)
                current['return'] = original_run(command, *values, **options)
                return current['return']
            except BaseException as exc:
                current['exception'] = {'type': type(exc).__name__, 'message': str(exc),
                                        'traceback': traceback.format_exc()}
                app.stop_event.set()
                raise
            finally:
                current['terminal'] = True
                current['elapsed_seconds'] = round(time.monotonic() - task_started, 3)
                current['native_error'] = getattr(session, 'last_task_error', None)
                current['task_outcome'] = dict(getattr(session, 'last_task_outcome', {}))
                try:
                    current['opsi_map_swipe_attempts'] = map_swipe_attempts(oracle, map_swipe_offset)
                except Exception as exc:
                    current['map_swipe_recording_error'] = str(exc)
                try:
                    ledger = getattr(session, 'action_ledger', None)
                    if command == 'dorm':
                        current['dorm_feed_consumption_proofs'] = encode_receipt_value(
                            getattr(getattr(session, 'adapter', None), '_dorm_feed_consumption_proofs', []))
                    if ledger is not None:
                        current['remaining_action_grants'] = {
                            key: ledger.remaining(key) for key in ledger.initial_grants}
                    for key, offset in receipt_offsets.items():
                        current[key] = encode_receipt_value(getattr(session, key)()[offset:])
                except Exception as exc:
                    current['resource_recording_error'] = str(exc)
                saved = json.loads(temporary.read_text(encoding='utf-8'))
                current['final_task_config'] = saved.get(scheduled)
                if current['return'] is not True:
                    try:
                        frame_oracle = session.open()._frame_or_live_observation_oracle()
                        current['failure_leased_frame'] = encode_receipt_value(frame_oracle.read_state())
                    except Exception as exc:
                        current['failure_leased_frame_error'] = str(exc)
                    if last_observed_state is not None:
                        current['last_observed_state'] = dataclasses.asdict(last_observed_state)
                    try:
                        current['failure_observation'] = {
                            'scope': 'later read-only observation; not the failed input frame',
                            'state': dataclasses.asdict(oracle.read_state()),
                            'ui': dataclasses.asdict(oracle.read_ui_state()),
                            'foreground': oracle._foreground_component()}
                    except Exception as exc:
                        current['failure_observation_error'] = str(exc)
                if should_stop(current['return'], len(result['tasks']), args.max_tasks,
                               args.continue_after_failure):
                    app.stop_event.set()
                save()
                current = None

        app.run = run
        request_startup_task(app, args.resume_task)
        request_startup_restart(app, args.restart_before_loop)
        if args.login_before_loop:
            bind_runtime()
            resume_startup_login(app, True)
            result['startup_login_completed'] = True
        save()
        result['native_stop_exit'] = run_native_loop(app)
        result['passed'] = bool(result['tasks']) and all(
            task['terminal'] and task['return'] is True for task in result['tasks'])
    except BaseException as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc),
                           'traceback': traceback.format_exc()}
    finally:
        stop_watcher_finished.set()
        if stop_watcher is not None:
            stop_watcher.join(timeout=1)
        result['stop_file_requested'] = stop_file is not None and stop_file.is_file()
        result['terminal'] = True
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if session is not None:
            try:
                session.close()
            except Exception as exc:
                result['cleanup_error'] = str(exc)
        result['final_config'] = json.loads(temporary.read_text(encoding='utf-8'))
        if not args.persistent_config:
            temporary.unlink()
        result['temporary_config_removed'] = not bool(args.persistent_config)
        save()
    print(json.dumps({key: result[key] for key in ('terminal', 'passed', 'elapsed_seconds')}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
