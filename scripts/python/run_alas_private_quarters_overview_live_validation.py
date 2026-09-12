"""Qualify the original PrivateQuarters disabled-action branch and typed count."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', type=Path, required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
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
    config['PrivateQuarters']['PrivateQuarters'].update(
        BuyRoses=False, BuyCake=False, TargetInteract=False, TargetShip='new_jersey')
    name = '_codex_pq_' + uuid.uuid4().hex
    profile = alas/'config'/(name+'.json')
    profile.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.path[:0] = [str(ROOT/'python'), str(alas)]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    os.chdir(alas)
    from alas import AzurLaneAutoScript
    from module.private_quarters.private_quarters import PrivateQuarters
    from module.ui.ui import UI
    from module.ui.page import page_main
    from alas_headless.semantic_sources import semantic_source_hashes
    instance = AzurLaneAutoScript(name)
    instance.config.init_task('PrivateQuarters')
    session = instance.device.semantic_adapter
    result = dict(schema='alas-headless.private-quarters-overview-live/v1', passed=False,
                  config=name, source_sha256=semantic_source_hashes(ROOT))
    try:
        task = PrivateQuarters(instance.config, instance.device)
        task.run()
        instance.device.screenshot()
        result['original_count'] = task.status_get_daily_count()
        oracle = session.open().oracle
        result['overview'] = dataclasses.asdict(oracle.private_quarters_overview())
        result['state'] = dataclasses.asdict(oracle.read_state())
        result['scheduler'] = json.loads(profile.read_text(encoding='utf-8'))['PrivateQuarters']['Scheduler']
        UI(instance.config, instance.device).ui_ensure(page_main)
        result['home'] = oracle.main_page_visible()
        result['passed'] = result['home'] and result['original_count'] == result['overview']['remaining']
    except (Exception, SystemExit) as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    finally:
        session.close()
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASSED', result['passed'])
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
