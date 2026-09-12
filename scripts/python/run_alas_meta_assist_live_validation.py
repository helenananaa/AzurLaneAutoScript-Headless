"""Run the original META assist task with a bounded grant and durable observations."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import traceback
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alas-root', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--driver-revision', required=True)
    p.add_argument('--budget', type=int, default=3)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not 1 <= args.budget <= 3:
        p.error('budget must be 1..3')
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    alas = args.alas_root.resolve()
    config = json.loads((alas/'config/semantic_e2e.json').read_text(encoding='utf-8'))
    config['Alas']['Emulator']['Serial'] = args.serial
    config['Alas']['Error'].update(HandleError=False, SaveError=False)
    for group in config.values():
        if isinstance(group, dict) and 'Scheduler' in group:
            group['Scheduler']['Enable'] = False
    config['OpsiAshAssist']['OpsiAshAssist']['Tier'] = 15
    name = '_codex_meta_assist_' + uuid.uuid4().hex
    profile = alas/'config'/(name+'.json')
    profile.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.path[:0] = [str(ROOT/'python'), str(alas)]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
                      ALAS_SEMANTIC_META_ASSIST_BUDGET=str(args.budget))
    os.chdir(alas)
    from alas import AzurLaneAutoScript
    from module.os_ash.meta import AshBeaconAssist
    from alas_headless.semantic_sources import semantic_source_hashes
    from alas_headless import SemanticGateClosed
    instance = AzurLaneAutoScript(name)
    instance.config.init_task('OpsiAshAssist')
    session = instance.device.semantic_adapter
    result = dict(schema='alas-headless.meta-assist-live/v1', passed=False,
                  source_sha256=semantic_source_hashes(ROOT), budget=args.budget,
                  serial=args.serial, attacks=[], profile=str(profile))
    def save():
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    original = AshBeaconAssist._make_an_attack
    def read_assist():
        for attempt in range(5):
            try:
                return dataclasses.asdict(session.meta_assist_state())
            except SemanticGateClosed as exc:
                if str(exc) != 'META assist snapshots are not coherent' or attempt == 4:
                    raise
                time.sleep(.25)
    def observed_attack(host):
        item = {'before':read_assist()}
        result['attacks'].append(item)
        save()
        value = original(host)
        host.device.screenshot()
        item['after'] = read_assist()
        save()
        return value
    AshBeaconAssist._make_an_attack = observed_attack
    try:
        result['task_result'] = instance.run('opsi_ash_assist')
        adapter = session.open()
        result['grant_remaining'] = adapter._action_ledger.remaining('meta.assist')
        result['owner_released'] = not adapter._meta_assist_active
        result['final_state'] = dataclasses.asdict(adapter.oracle.read_state())
        result['passed'] = bool(result['task_result'] is True and result['attacks']
            and all(a.get('after',{}).get('remaining_attempts') == a['before']['remaining_attempts']-1 for a in result['attacks'])
            and result['attacks'][-1]['after']['remaining_attempts'] == 0
            and result['owner_released'])
    except (Exception, SystemExit) as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    finally:
        AshBeaconAssist._make_an_attack = original
        save()
        session.close()
    print('passed',result['passed'], 'attacks',len(result['attacks']))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
