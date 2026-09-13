"""Qualify one original Daily batch-skip transaction using real counters."""
from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
KINDS = {
    'TacticalTraining': 'tactical_training', 'FierceAssault': 'fierce_assault',
    'EscortMission': 'escort_mission', 'AdvanceMission': 'advance_mission',
    'ModuleDevelopment': 'module_development', 'SupplyLineDisruption': 'supply_line_disruption',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', required=True, type=Path)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--kind', choices=KINDS, default='TacticalTraining')
    parser.add_argument('--stage', choices=('first', 'second', 'third'), default='first')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    alas = args.alas_root.resolve()
    seed = json.loads((alas / 'config/semantic_e2e.json').read_text(encoding='utf-8'))
    config = copy.deepcopy(seed)
    config['Alas']['Emulator']['Serial'] = args.serial
    config['Alas']['Error'].update(HandleError=False, SaveError=False)
    daily = config['Daily']['Daily']
    for kind in (*KINDS, 'EmergencyModuleDevelopment'):
        daily[kind] = 'skip'
    daily[args.kind] = args.stage
    if args.kind + 'Fleet' in daily:
        daily[args.kind + 'Fleet'] = 1
    daily['UseDailySkip'] = True
    config['Daily']['Scheduler']['Enable'] = True
    name = '_codex_daily_quick_' + uuid.uuid4().hex
    config_path = alas / 'config' / (name + '.json')
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sys.path[:0] = [str(ROOT / 'python'), str(alas)]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
                      ALAS_SEMANTIC_DAILY_EXECUTE_BUDGET='1')
    os.chdir(alas)
    from alas import AzurLaneAutoScript
    from module.daily.daily import Daily
    from module.exception import ScriptEnd
    from alas_headless.semantic_sources import semantic_source_hashes
    result = dict(schema='alas-headless.daily-quick-live/v1', passed=False,
                  kind=KINDS[args.kind], stage=args.stage, serial=args.serial,
                  driver_revision=args.driver_revision, transactions=[])
    result['source_sha256'] = {**semantic_source_hashes(ROOT),
        'daily': hashlib.sha256((alas / 'module/daily/daily.py').read_bytes()).hexdigest(),
        'runner': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    result['upstream_lock'] = json.loads((ROOT / 'integration/alas/upstream-lock.json').read_text(encoding='utf-8'))
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    instance = AzurLaneAutoScript(name)
    instance.config.init_task('Daily')
    session = instance.device.semantic_adapter
    original = Daily.daily_execute
    def observed_execute(host, remain, stage, fleet):
        oracle = session.open().oracle
        kind = oracle.daily_current_kind()
        before = oracle.daily_remaining_for_kind(kind)
        if kind != result['kind'] or remain != before:
            raise AssertionError('original Daily intent differs from typed observation')
        item = dict(kind=kind, before=before, stage=stage, fleet=fleet)
        result['transactions'].append(item)
        save()
        value = original(host, remain, stage, fleet)
        host.device.screenshot()
        item['after'] = oracle.daily_remaining_for_kind(kind)
        item['original_result'] = value
        return value
    Daily.daily_execute = observed_execute
    try:
        def reject_normal_battle():
            raise ScriptEnd('This qualification requires an unlocked batch-skip control')
        session.click_daily_precombat_start = reject_normal_battle
        adapter = session.open()
        result['runtime_before'] = dataclasses.asdict(adapter.oracle.fingerprint)
        result['before_ui'] = dataclasses.asdict(adapter.oracle.read_ui_state())
        save()
        result['task_result'] = instance.run('daily')
        result['receipts'] = [dataclasses.asdict(r) for r in adapter.daily_execution_receipts()]
        result['grant_remaining'] = adapter._action_ledger.remaining('daily.execute')
        result['scheduler_after'] = json.loads(config_path.read_text(encoding='utf-8'))['Daily']['Scheduler']
        result['after_ui'] = dataclasses.asdict(adapter.oracle.read_ui_state())
        result['passed'] = bool(result['task_result'] is True
            and len(result['receipts']) == len(result['transactions']) == 1
            and result['receipts'][0]['semantic_id'].endswith('/quick/all')
            and result['transactions'][0]['before'] > 0
            and result['transactions'][0]['after'] == 0 and result['grant_remaining'] == 0)
    except (Exception, SystemExit) as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        result['traceback'] = traceback.format_exc()
        result['receipts'] = [dataclasses.asdict(r) for r in session.open().daily_execution_receipts()]
    finally:
        Daily.daily_execute = original
        session.close()
        config_path.unlink(missing_ok=True)
        result['temporary_config_removed'] = not config_path.exists()
        save()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
