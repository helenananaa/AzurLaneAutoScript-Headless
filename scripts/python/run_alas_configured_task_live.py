"""Run one original ALAS task with a copied semantic config and typed receipt."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import uuid
from collections.abc import Mapping


ROOT = Path(__file__).resolve().parents[2]


def encode_receipt_value(value):
    """Copy immutable typed evidence without deepcopying mapping proxies."""
    if dataclasses.is_dataclass(value):
        return {field.name: encode_receipt_value(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {key: encode_receipt_value(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode_receipt_value(child) for child in value]
    return value


def parse_action_budgets(items):
    from alas_headless.adapter.legacy_environment import LEGACY_BOOLEAN_GRANTS, LEGACY_BUDGET_GRANTS

    values = {}
    for item in items:
        key, separator, value = item.partition('=')
        if (not separator or not value.isdecimal()
                or key not in LEGACY_BUDGET_GRANTS and key not in LEGACY_BOOLEAN_GRANTS):
            raise ValueError(f'unknown or invalid action budget: {item}')
        if key in LEGACY_BOOLEAN_GRANTS and value not in ('0', '1'):
            raise ValueError(f'boolean action grant requires 0 or 1: {item}')
        values[key] = value
    return values


def encode_navigation_intent(values):
    """Retain typed observation arguments without losing their structure."""
    return [dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value for value in values]


def prepare_config(seed, task, run_limit):
    config = copy.deepcopy(seed)
    if task not in config or not config[task].get('Scheduler', {}).get('Enable'):
        raise ValueError(f'task is not enabled in imported config: {task}')
    override = None
    if run_limit is not None:
        stop_condition = config[task].get('StopCondition')
        if run_limit < 1 or not isinstance(stop_condition, dict) or 'RunCount' not in stop_condition:
            raise ValueError('--run-limit requires a positive count and a task with StopCondition.RunCount; '
                             'Hard uses its native daily quota')
        override = {'original': stop_condition['RunCount'], 'qualification': run_limit}
        stop_condition['RunCount'] = run_limit
    # Retain ALAS recovery policy: HandleError also controls app stop/start.
    # Error screenshots and outgoing notifications are not qualification data.
    config['Alas']['Error'].update(SaveError=False, OnePushConfig='')
    return config, override


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', required=True, type=Path)
    parser.add_argument('--seed-config', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--expected-surface', choices=(
        'main', 'reward', 'commission', 'mission', 'research', 'tactical', 'meowfficer', 'shop', 'munitions', 'meta', 'meta-sync', 'os', 'globe', 'opsi', 'campaign', 'game-room', 'fushun-prepare', 'exercise', 'dorm', 'dock', 'daily', 'campaign-menu', 'build-queue', 'shipyard',
    ), default='main')
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--budget', action='append', default=[], metavar='ENV=COUNT')
    parser.add_argument('--run-limit', type=int,
                        help='Bound original campaign runs in this temporary qualification config')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / 'python'))
    try:
        budget_values = parse_action_budgets(args.budget)
    except ValueError as exc:
        parser.error(str(exc))
    output = args.output.resolve()
    if output.exists():
        parser.error(f'output already exists: {output}')
    alas_root = args.alas_root.resolve()
    source = alas_root / 'config' / (args.seed_config + '.json')
    try:
        config, run_limit_override = prepare_config(
            json.loads(source.read_text(encoding='utf-8')), args.task, args.run_limit)
    except ValueError as exc:
        parser.error(str(exc))
    serial = config['Alas']['Emulator']['Serial']
    name = '_codex_configured_' + uuid.uuid4().hex
    temporary = alas_root / 'config' / (name + '.json')
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.environ.update(ALAS_SEMANTIC_MODE='1',
                      ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
                      ALAS_SEMANTIC_ADB='adb')
    os.environ.update(budget_values)
    sys.path[:0] = [str(ROOT / 'python'), str(alas_root)]
    os.chdir(alas_root)
    result = {'schema': 'alas-headless.configured-task-live/v1', 'task': args.task,
              'seed_config': args.seed_config, 'serial': serial,
              'driver_revision': args.driver_revision, 'budgets': args.budget,
              'passed': False, 'actions': []}
    if run_limit_override is not None:
        result['run_limit_override'] = run_limit_override
    started = time.monotonic()
    session = None
    last_observed_state = None
    try:
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function
        app = AzurLaneAutoScript(name)
        app.config.task = name_to_function(args.task)
        app.config.bind(args.task)
        session = app.device.semantic_adapter
        result['policy_grants'] = dict(getattr(session, 'policy_grants', {}))
        oracle = session.open().oracle
        original_appear = session.appear
        def record_presence(button):
            try:
                return original_appear(button)
            except Exception:
                result['failed_presence'] = {'name': getattr(button, 'name', str(button))}
                try:
                    frame_oracle = session.open()._frame_or_live_observation_oracle()
                    result['failed_presence']['state'] = encode_receipt_value(frame_oracle.read_state())
                    result['failed_presence']['ui'] = encode_receipt_value(frame_oracle.read_ui_state())
                except Exception as exc:
                    result['failed_presence']['record_error'] = str(exc)
                raise
        session.appear = record_presence
        original_read_state = oracle.read_state
        def record_state(*values, **options):
            nonlocal last_observed_state
            observed = original_read_state(*values, **options)
            last_observed_state = observed
            return observed
        oracle.read_state = record_state
        state = oracle.read_state()
        result['before'] = {'pid': state.snapshot['pid'], 'generation': state.generation,
                            'main_visible': oracle.main_page_visible()}
        original = oracle.click

        def record(target):
            try:
                receipt = original(target)
            except Exception:
                result['failed_target'] = target
                try:
                    state = oracle.read_state()
                    result['failed_observation'] = {
                        'generation': state.generation,
                        'main_visible': oracle.main_page_visible(),
                        'reward_back': oracle.exists('reward/page/back'),
                        'blockers': [rule.blocker_id for rule in oracle._blocking_rules(
                            state, 'ui/absence-probe')],
                    }
                except Exception as observation_error:
                    result['failed_observation_error'] = {
                        'type': type(observation_error).__name__,
                        'message': str(observation_error),
                    }
                raise
            result['actions'].append(dataclasses.asdict(receipt))
            result.pop('failed_target', None)
            result.pop('failed_observation', None)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return receipt

        original_map_swipe = getattr(oracle,'operation_siren_map_swipe',None)
        if callable(original_map_swipe):
            def retain_map_swipe(*values,**options):
                try:return original_map_swipe(*values,**options)
                finally:
                    result['map_swipe_attempts']=list(getattr(oracle,'_operation_siren_map_swipe_attempts',[]))
                    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            oracle.operation_siren_map_swipe=retain_map_swipe
        oracle.click = record
        def record_meta_detail_action(method):
            def invoke():
                before_count = oracle.input_dispatch_count
                try:
                    receipt = method()
                except Exception as exc:
                    result['failed_meta_action'] = {
                        'method': method.__name__, 'message': str(exc),
                        'input_dispatch_count_delta': oracle.input_dispatch_count - before_count,
                    }
                    if method.__name__ == 'click_meta_dossier_auto_start':
                        result['failed_meta_action']['transition_observations'] = getattr(
                            oracle, 'last_meta_dossier_auto_transition', [])
                    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                    raise
                result['actions'].append(dataclasses.asdict(receipt))
                if method.__name__ == 'click_meta_dossier_auto_confirm':
                    result['meta_dossier_auto_costs'] = oracle.last_meta_dossier_auto_costs
                if method.__name__ == 'click_meta_dossier_auto_result_confirm':
                    result['meta_dossier_auto_result'] = oracle.last_meta_dossier_auto_result
                result.pop('failed_meta_action', None)
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                return receipt
            return invoke
        for method_name in ('click_meta_current_start', 'click_meta_current_reward',
                            'click_meta_dossier_create', 'click_meta_dossier_auto_start',
                            'click_meta_dossier_auto_confirm',
                            'click_meta_dossier_auto_result_confirm', 'click_meta_dossier_reward',
                            'click_meta_dossier_start', 'click_meta_home'):
            method = getattr(oracle, method_name, None)
            if callable(method):
                setattr(oracle, method_name, record_meta_detail_action(method))
        original_meta_sync_claim = getattr(oracle, 'click_meta_character_sync_rewards', None)
        if callable(original_meta_sync_claim):
            def record_meta_sync_claim():
                receipt = original_meta_sync_claim()
                result['actions'].append(dataclasses.asdict(receipt))
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                return receipt
            oracle.click_meta_character_sync_rewards = record_meta_sync_claim
        original_meta_assist_state = getattr(oracle, 'meta_assist_state', None)
        if callable(original_meta_assist_state):
            result['meta_assist_observations'] = []
            def record_meta_assist_state():
                value = original_meta_assist_state()
                result['meta_assist_observations'].append(dataclasses.asdict(value))
                result['meta_assist_observations'] = result['meta_assist_observations'][-64:]
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                return value
            oracle.meta_assist_state = record_meta_assist_state
        original_shop_items = getattr(oracle, 'general_shop_items', None)
        if callable(original_shop_items):
            result['shop_inventory_observations'] = []
            def record_shop_items():
                values = original_shop_items()
                result['shop_inventory_observations'].append(
                    [dataclasses.asdict(value) for value in values])
                result['shop_inventory_observations'] = result['shop_inventory_observations'][-16:]
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                return values
            oracle.general_shop_items = record_shop_items
        result['prompt_routing_observations'] = []
        for method_name in ('observation_prompt_kind',
                            'operation_siren_exit_prompt_visible',
                            'minigame_ticket_prompt_visible'):
            original_reader = getattr(oracle, method_name, None)
            if not callable(original_reader):
                continue

            def record_prompt(*values, _reader=original_reader,
                              _name=method_name, **options):
                value = _reader(*values, **options)
                result['prompt_routing_observations'].append({
                    'method': _name, 'value': value,
                    'elapsed_seconds': round(time.monotonic() - started, 3),
                })
                result['prompt_routing_observations'] = result['prompt_routing_observations'][-64:]
                return value

            setattr(oracle, method_name, record_prompt)
        original_fleet_reader = getattr(oracle, 'campaign_fleet_selection_state', None)
        if callable(original_fleet_reader):
            def record_fleet_state(*values, **options):
                state = original_fleet_reader(*values, **options)
                result['latest_campaign_fleet_state'] = dataclasses.asdict(state)
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                return state
            oracle.campaign_fleet_selection_state = record_fleet_state
        result['typed_navigation_actions'] = []
        for method_name in ('click_operation_siren_globe_port',
                            'click_operation_siren_action_point_open',
                            'click_operation_siren_action_point_item',
                            'click_operation_siren_action_point_control',
                            'click_operation_siren_port_repair',
                            'click_weekly_mission_progress_claim',
                            'click_mission_overflow_confirm',
                            'click_reward_resource',
                            'click_tactical_first_empty_slot',
                            'click_operation_siren_globe',
                            'click_daily_precombat_start',
                            'click_daily_precombat_back',
                            'click_meta_assist_sortie',
                            'click_meta_home',
                            'click_meta_dossier_sync_open',
                            'click_meta_dossier_sync_rewards',
                            'click_daily_battle_result',
                            'click_operation_siren_exit',
                            'click_new_year_challenge_prepare_control',
                            'click_new_year_challenge_entry',
                            'click_operation_siren_globe_map_zone',
                            'operation_siren_globe_unpin', 'operation_siren_globe_swipe',
                            'operation_siren_map_swipe',
                            'click_operation_siren_radar_guidepost',
                            'click_operation_siren_globe_map'):
            original_method = getattr(oracle, method_name, None)
            if not callable(original_method):
                continue

            def record_navigation(*values, _method=original_method,
                                  _name=method_name, **options):
                receipt = _method(*values, **options)
                result['typed_navigation_actions'].append({
                    'method': _name, 'intent': encode_navigation_intent(values),
                    'receipt': dataclasses.asdict(receipt),
                })
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                return receipt

            setattr(oracle, method_name, record_navigation)
        result['globe_drag_proofs'] = []
        result['globe_blocker_observations'] = []
        original_blocking_rules = getattr(oracle, '_blocking_rules', None)
        def record_blocking_rules(state, semantic_id):
            rules = original_blocking_rules(state, semantic_id)
            if rules and semantic_id == 'os/globe/map':
                result['globe_blocker_observations'].append({
                    'generation':state.generation,
                    'blockers':[rule.blocker_id for rule in rules],
                })
            return rules
        if callable(original_blocking_rules):
            oracle._blocking_rules = record_blocking_rules
        original_globe_proof = getattr(oracle, 'operation_siren_globe_drag_proof', None)
        def record_globe_proof(start,end):
            generation,proof = original_globe_proof(start,end)
            result['globe_drag_proofs'].append({'generation':generation,'proof':proof})
            output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            return generation,proof
        if callable(original_globe_proof):
            oracle.operation_siren_globe_drag_proof = record_globe_proof
        result['globe_projection_observations'] = []
        original_projection = getattr(oracle, '_operation_siren_globe_map_projection_record', None)
        def record_projection(area_pos):
            ui, record = original_projection(area_pos)
            result['globe_projection_observations'].append({
                'generation':ui.generation, 'area_pos':list(area_pos), 'record':record,
            })
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            return ui, record
        if callable(original_projection):
            oracle._operation_siren_globe_map_projection_record = record_projection
        command = re.sub(r'(?<!^)(?=[A-Z])', '_', args.task).lower()
        if not hasattr(app, command):
            raise RuntimeError(f'original ALAS task command is absent: {command}')
        outcome = app.run(command)
        result['return'] = outcome
        current_oracle = session.open().oracle
        result['runtime_oracle_changed'] = current_oracle is not oracle
        oracle = current_oracle
        result['task_outcome'] = dict(session.last_task_outcome)
        result['native_error'] = getattr(session, 'last_task_error', None)
        completion_reader = getattr(session, 'last_campaign_auto_search_completion', None)
        if callable(completion_reader):
            completion = completion_reader()
            if completion is not None:
                result['campaign_completion'] = dataclasses.asdict(completion)
        after = oracle.read_state()
        result['after'] = {'pid': after.snapshot['pid'], 'generation': after.generation,
                           'main_visible': oracle.main_page_visible(),
                           'commission_back': oracle.exists('commission/page/back')}
        surface_targets = {
            'reward': 'reward/page/back',
            'commission': 'commission/page/back',
            'mission': 'task/page/back',
            'research': 'research/page/back',
            'tactical': 'tactical/page/back',
            'meowfficer': 'meowfficer/page/back',
        }
        if args.expected_surface in surface_targets:
            result['after']['expected_target'] = surface_targets[args.expected_surface]
            result['after']['expected_target_present'] = oracle.exists(
                surface_targets[args.expected_surface])
        result['scheduled_next_run'] = json.loads(temporary.read_text(encoding='utf-8'))[
            args.task]['Scheduler']['NextRun']
        if outcome is not True:
            arrived = False
        elif args.expected_surface == 'shipyard':
            result['after']['shipyard_visible'] = oracle.shipyard_page_visible()
            result['after']['shipyard_state'] = dataclasses.asdict(oracle.shipyard_selected_state())
            result['after']['shipyard_cannot_strengthen'] = oracle.shipyard_cannot_strengthen(
                result['after']['shipyard_state']['ship_index'])
            arrived = result['after']['shipyard_visible']
        elif args.expected_surface == 'main':
            arrived = result['after']['main_visible']
        elif args.expected_surface == 'reward':
            # Tactical can return while its accepted Back is still mounting
            # the reward sidebar. Prove the actual new actionable destination
            # with the existing read-only wait instead of accepting the first
            # transition frame or treating its temporary absence as failure.
            oracle.wait_for('reward/page/back', timeout_seconds=5.0,
                            minimum_generation=after.generation)
            result['after']['expected_target_present'] = True
            result['after']['reward_ready_generation'] = oracle.read_state().generation
            arrived = True
        elif args.expected_surface == 'shop':
            arrived = oracle.gift_pack_page_visible()
            result['after']['gift_pack_visible'] = arrived
        elif args.expected_surface == 'munitions':
            arrived = oracle.munitions_page_visible()
            result['after']['munitions_visible'] = arrived
        elif args.expected_surface == 'meta':
            arrived = oracle.meta_page_visible()
            result['after']['meta_visible'] = arrived
        elif args.expected_surface == 'meta-sync':
            points, eligible, collected = oracle.meta_character_sync_rewards()
            result['after']['meta_sync_rewards'] = {
                'points': points, 'eligible': eligible, 'collected': collected,
            }
            arrived = True  # The existing reader proves the complete reward page.
        elif args.expected_surface == 'exercise':
            arrived = oracle.exercise_page_visible()
            result['after']['exercise_visible'] = arrived
        elif args.expected_surface == 'daily':
            arrived = oracle.daily_page_visible()
            result['after']['daily_visible'] = arrived
        elif args.expected_surface == 'campaign-menu':
            arrived = oracle.campaign_menu_is_entry()
            result['after']['campaign_menu_visible'] = arrived
        elif args.expected_surface == 'build-queue':
            result['after']['build_queue_timers'] = list(oracle.build_queue_timers())
            arrived = True  # The reader proves the queue tab, capacity and timers.
        elif args.expected_surface == 'dorm':
            dorm = oracle.dorm_state()
            result['after']['dorm'] = dataclasses.asdict(dorm)
            arrived = True  # The reader proves the exact typed dorm summary.
        elif args.expected_surface == 'dock':
            dock_state, dock_ui = oracle._enhancement_dock_records()
            result['after']['dock_generation'] = dock_state.generation
            result['after']['dock_capacity'] = next(
                item.text for item in dock_ui.texts
                if item.path == 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/Text'
                and item.active_in_hierarchy and item.active_and_enabled
                and not item.truncated
            )
            arrived = True  # The reader proves capacity, filter and page identity.
        elif args.expected_surface == 'os':
            arrived = session.operation_siren_map_visible()
            result['after']['os_map_visible'] = arrived
        elif args.expected_surface == 'globe':
            arrived = oracle.operation_siren_globe_visible()
            result['after']['os_globe_visible'] = arrived
        elif args.expected_surface == 'opsi':
            map_visible = session.operation_siren_map_visible()
            globe_visible = False if map_visible else oracle.operation_siren_globe_visible()
            result['after'].update(os_map_visible=map_visible, os_globe_visible=globe_visible)
            arrived = map_visible or globe_visible
        elif args.expected_surface == 'campaign':
            arrived = oracle.campaign_page_is_normal()
            result['after']['campaign_stage_visible'] = arrived
        elif args.expected_surface == 'game-room':
            arrived = oracle.game_room_page_visible()
            result['after']['game_room_visible'] = arrived
        elif args.expected_surface == 'fushun-prepare':
            selected, owned = oracle.new_year_challenge_ticket_count()
            result['after'].update(fushun_ticket_selected=selected, fushun_ticket_owned=owned)
            arrived = True  # The reader proves the exact Fushun prepare controls.
        else:
            arrived = result['after']['expected_target_present']
        # ALAS owns its success decision: TaskEnd also returns True. The
        # scope's "raised" diagnostic must not override that native outcome.
        result['passed'] = outcome is True and arrived
    except BaseException as exc:
        result['passed'] = False
        result['error'] = {'type': type(exc).__name__, 'message': str(exc),
                           'traceback': traceback.format_exc()}
        if dataclasses.is_dataclass(last_observed_state):
            result['last_observed_state'] = dataclasses.asdict(last_observed_state)
        if session is not None:
            try:
                failure_oracle = session.open().oracle
                result['failure_observation'] = {
                    'scope':'read-only observation after failure; not the failed frame',
                    'state':dataclasses.asdict(failure_oracle.read_state()),
                    'ui':dataclasses.asdict(failure_oracle.read_ui_state()),
                    'foreground':failure_oracle._foreground_component(),
                }
            except Exception as observation_error:
                result['failure_observation_error'] = str(observation_error)
    finally:
        result['cleanup_errors'] = []
        try:
            result['final_task_config'] = json.loads(temporary.read_text(encoding='utf-8'))[args.task]
        except Exception as config_error:
            result['final_task_config_error'] = str(config_error)
        if session is not None:
            ledger = getattr(session, 'action_ledger', None)
            if ledger is not None:
                result['remaining_action_grants'] = {
                    key: ledger.remaining(key) for key in ledger.initial_grants
                }
            result.setdefault('task_outcome', dict(session.last_task_outcome))
            result.setdefault('native_error', getattr(session, 'last_task_error', None))
            # Preserve original ALAS dock recovery transactions before closing
            # the session, including failed tasks that already consumed items.
            for key, method_name in (
                ('enhancement_receipts', 'enhancement_receipts'),
                ('retirement_receipt', 'retirement_receipt'),
                ('awaken_receipts', 'awaken_receipts'),
                ('awaken_cost_observations', 'awaken_cost_observations'),
                ('daily_execution_receipts', 'daily_execution_receipts'),
            ):
                reader = getattr(session, method_name, None)
                if callable(reader):
                    try:
                        value = reader()
                        result[key] = ([dataclasses.asdict(item) for item in value]
                                       if isinstance(value, (tuple, list))
                                       else dataclasses.asdict(value) if value is not None else None)
                    except Exception as receipt_error:
                        result[key + '_error'] = str(receipt_error)
            try:
                session.close()
            except Exception as cleanup_error:
                result['cleanup_errors'].append({
                    'operation': 'session.close',
                    'type': type(cleanup_error).__name__, 'message': str(cleanup_error),
                })
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            result['cleanup_errors'].append({
                'operation': 'temporary_config.unlink',
                'type': type(cleanup_error).__name__, 'message': str(cleanup_error),
            })
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        result['temporary_config_removed'] = not temporary.exists()
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result.get(k) for k in ('task', 'passed', 'return', 'after', 'error', 'elapsed_seconds')},
                     ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
