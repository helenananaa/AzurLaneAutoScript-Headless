"""Observe the original ALAS scheduler using a copied CN semantic strategy."""

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

from run_alas_configured_task_live import parse_action_budgets

ROOT = Path(__file__).resolve().parents[2]


def prepare_config(seed, campaign_run_limit):
    config = copy.deepcopy(seed)
    config['Alas']['Error'].update(HandleError=False, SaveError=False, OnePushConfig='')
    overrides = {}
    if campaign_run_limit is not None:
        # Hard has its own native daily quota and no StopCondition group.
        for task in ('Main', 'Event', 'EventSp'):
            if config.get(task, {}).get('Scheduler', {}).get('Enable'):
                previous = config[task]['StopCondition']['RunCount']
                config[task]['StopCondition']['RunCount'] = campaign_run_limit
                overrides[task] = {'original': previous, 'qualification': campaign_run_limit}
    return config, overrides


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', required=True, type=Path)
    parser.add_argument('--seed-config', required=True)
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--max-tasks', required=True, type=int)
    parser.add_argument('--campaign-run-limit', type=int)
    parser.add_argument('--budget', action='append', default=[])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.max_tasks < 1 or (args.campaign_run_limit is not None and args.campaign_run_limit < 1):
        parser.error('task and optional campaign limits must be positive')
    sys.path.insert(0, str(ROOT / 'python'))
    try:
        budgets = parse_action_budgets(args.budget)
    except ValueError as exc:
        parser.error(str(exc))
    alas_root, output = args.alas_root.resolve(), args.output.resolve()
    if output.exists():
        parser.error(f'output already exists: {output}')
    seed_path = alas_root / 'config' / (args.seed_config + '.json')
    seed_raw = seed_path.read_bytes()
    config, overrides = prepare_config(json.loads(seed_raw), args.campaign_run_limit)
    name = '_codex_scheduler_' + uuid.uuid4().hex
    temporary = alas_root / 'config' / (name + '.json')
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
                      ALAS_SEMANTIC_ADB='adb', **budgets)
    sys.path[:0] = [str(ROOT / 'python'), str(alas_root)]
    os.chdir(alas_root)
    result = {'schema': 'alas-headless.original-scheduler-live/v1',
              'scope': 'original ALAS.loop selection, execution and scheduling; copied strategy',
              'seed_config': args.seed_config, 'seed_sha256': hashlib.sha256(seed_raw).hexdigest(),
              'serial': config['Alas']['Emulator']['Serial'], 'budgets': args.budget,
              'campaign_run_overrides': overrides, 'max_tasks': args.max_tasks,
              'tasks': [], 'terminal': False, 'passed': False}
    started = time.monotonic()
    session = None

    def save():
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    try:
        from alas import AzurLaneAutoScript
        app = AzurLaneAutoScript(name)
        app.stop_event = threading.Event()
        original_run = app.run
        current = None
        oracle = None
        last_observed_state = None
        instrumented = []

        def bind_runtime():
            nonlocal session, oracle
            session = app.device.semantic_adapter
            oracle = session.open().oracle
            if any(existing is oracle for existing in instrumented):
                return
            instrumented.append(oracle)
            original_appear = session.appear
            def appear(button):
                try:
                    return original_appear(button)
                except Exception:
                    if current is not None:
                        try:
                            current['failed_presence'] = {
                                'name': getattr(button, 'name', str(button)),
                                'state': dataclasses.asdict(session.open()._frame_or_live_observation_oracle().read_state()),
                            }
                        except Exception as exc:
                            current['failed_presence_record_error'] = str(exc)
                    raise
            session.appear = appear
            original_state, original_tap, original_click = oracle.read_state, oracle._tap, oracle.click

            def state(*values, **options):
                nonlocal last_observed_state
                observed = original_state(*values, **options)
                last_observed_state = observed
                return observed

            def tap(*values, **options):
                value = original_tap(*values, **options)
                if current is not None:
                    current['native_taps'].append({'point': list(values), 'returned': True})
                return value

            def click(target):
                receipt = original_click(target)
                if current is not None:
                    current['actions'].append(dataclasses.asdict(receipt))
                return receipt

            oracle.read_state, oracle._tap, oracle.click = state, tap, click

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
            last_observed_state = None
            save()
            try:
                try:
                    bind_runtime()
                    current['runtime_bound'] = True
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
                saved = json.loads(temporary.read_text(encoding='utf-8'))
                current['final_task_config'] = saved.get(scheduled)
                if current['return'] is not True:
                    try:
                        frame_oracle = session.open()._frame_or_live_observation_oracle()
                        current['failure_leased_frame'] = dataclasses.asdict(frame_oracle.read_state())
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
                if current['return'] is False or len(result['tasks']) >= args.max_tasks:
                    app.stop_event.set()
                save()
                current = None

        app.run = run
        save()
        app.loop()
        result['passed'] = bool(result['tasks']) and all(
            task['terminal'] and task['return'] is True for task in result['tasks'])
    except BaseException as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc),
                           'traceback': traceback.format_exc()}
    finally:
        result['terminal'] = True
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if session is not None:
            try:
                session.close()
            except Exception as exc:
                result['cleanup_error'] = str(exc)
        result['final_config'] = json.loads(temporary.read_text(encoding='utf-8'))
        temporary.unlink()
        result['temporary_config_removed'] = True
        save()
    print(json.dumps({key: result[key] for key in ('terminal', 'passed', 'elapsed_seconds')}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
