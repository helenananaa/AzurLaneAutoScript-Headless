#!/usr/bin/env python3
"""Record a bounded original-ALAS month-start run using a dedicated config.

The config remains on disk so a subsequent process can prove cursor recovery.
An exploration stop is explicitly partial; it is never a full-month pass.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', required=True, type=Path)
    parser.add_argument('--config', required=True)
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--mode', choices=('explore', 'samples'), default='explore')
    parser.add_argument('--sample-source-zone', type=int,
                        help='Run one explicit zone through the original explore loop; use a separate config.')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    alas = args.alas_root.resolve()
    sys.path[:0] = [str(ROOT / 'python'), str(alas)]
    os.chdir(alas)
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from alas import AzurLaneAutoScript
    from module.config.config import AzurLaneConfig, TaskEnd, name_to_function
    from module.campaign.os_run import OSCampaignRun
    from module.os.map import OSMap
    from module.os_handler.storage import StorageHandler
    from alas_headless.opsi_monthstart import SampleUse
    from alas_headless.semantic_oracle import SemanticOracle
    from alas_headless.semantic_sources import semantic_source_paths

    result = dict(schema='alas-headless.opsi-monthstart-live/v1', mode=args.mode,
                  driver_revision=args.driver_revision, visits=[], samples=[], inputs=[],
                  bounded_stop=False, full_month_qualified=False, passed=False)
    app = AzurLaneAutoScript(args.config)
    task = name_to_function('OpsiExplore')
    app.config.task = task
    app.config.bind(task)
    if args.sample_source_zone is not None:
        if args.mode != 'explore':
            parser.error('--sample-source-zone requires --mode explore')
        app.config.override(OS_EXPLORE_FILTER=str(args.sample_source_zone))
    result['explore_order'] = [int(v.strip()) for v in app.config.OS_EXPLORE_FILTER.split('>')]
    config_path = alas / 'config' / (args.config + '.json')
    result['config_before'] = json.loads(config_path.read_text(encoding='utf-8'))['OpsiExplore']
    start_zone = app.config.OpsiExplore_LastZone
    original_switch = AzurLaneConfig.check_task_switch
    original_goto = OSMap.globe_goto
    original_samples = StorageHandler.storage_sample_use_all
    original_click = SampleUse.click
    original_order = SemanticOracle.click_operation_siren_order
    paths = [ROOT / 'python/alas_headless/opsi_monthstart.py',
             *semantic_source_paths(ROOT),
             ROOT / 'integration/alas/0001-semantic-oracle-hooks.patch', Path(__file__).resolve()]
    def source_hashes():
        return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['source_sha256'] = source_hashes()
    def alas_source_hashes():
        relatives = ('module/os/map.py', 'module/os/globe_operation.py',
                     'module/os/tasks/explore.py', 'module/os_handler/storage.py')
        return {p: hashlib.sha256((alas / p).read_bytes()).hexdigest() for p in relatives}
    result['alas_source_sha256'] = alas_source_hashes()

    def record_visit(owner, zone, *a, **kw):
        value = original_goto(owner, zone, *a, **kw)
        result['visits'].append(dict(zone=owner.name_to_zone(zone).zone_id,
                                     entered=bool(value), stop_if_safe=kw.get('stop_if_safe', False)))
        return value

    def record_samples(owner):
        session = owner.device.semantic_adapter
        before = session.operation_siren_storage_state()
        value = original_samples(owner)
        after = session.operation_siren_storage_state()
        result['samples'].append(dict(before=asdict(before), after=asdict(after)))
        return value

    def record_click(context, oracle, name):
        index = len(result['inputs'])
        for label, value in [('buttons', oracle.read_state()), ('ui', oracle.read_ui_state())]:
            (output / f'input-{index:03d}-{label}.json').write_text(
                json.dumps(asdict(value), ensure_ascii=False, indent=2), encoding='utf-8')
        receipt = original_click(context, oracle, name)
        result['inputs'].append(asdict(receipt))
        return receipt

    def bounded_switch(config, *a, **kw):
        if config.OpsiExplore_LastZone != start_zone:
            result['bounded_stop'] = True
            raise TaskEnd
        return original_switch(config, *a, **kw)

    def record_order(oracle, kind):
        receipt = original_order(oracle, kind)
        result.setdefault('order_inputs', []).append(asdict(receipt))
        with (output / 'order-inputs.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(asdict(receipt), ensure_ascii=False) + '\n')
        return receipt

    started = time.monotonic()
    try:
        session = app.device.semantic_adapter
        session.refresh_frame()
        fingerprint = session.open().oracle.fingerprint
        result['runtime'] = dict(package=fingerprint.package, pid=fingerprint.expected_pid,
                                 component=fingerprint.component)
        with patch.object(OSMap, 'globe_goto', record_visit), \
             patch.object(StorageHandler, 'storage_sample_use_all', record_samples), \
             patch.object(SampleUse, 'click', record_click), \
             patch.object(SemanticOracle, 'click_operation_siren_order', record_order), \
             patch.object(AzurLaneConfig, 'check_task_switch', bounded_switch):
            if args.mode == 'samples':
                campaign = OSCampaignRun(config=app.config, device=app.device).load_campaign()
                campaign.tuning_sample_use()
                def count(state):
                    return sum(v['count'] for v in state['items'] if v['item_type'].startswith('SAMPLE_'))
                result['passed'] = any(count(v['before']) > count(v['after']) for v in result['samples'])
            else:
                result['task_result'] = app.run('opsi_explore')
                result['passed'] = bool(result['task_result'] and result['bounded_stop'])
        result['resources_after'] = asdict(session.open().oracle.operation_siren_state())
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        result['passed'] = False
    finally:
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        result['config_after'] = json.loads(config_path.read_text(encoding='utf-8'))['OpsiExplore']
        device = app.__dict__.get('device')
        session = getattr(device, '__dict__', {}).get('semantic_adapter')
        if session:
            session.close()
        result['source_changed_during_run'] = source_hashes() != result['source_sha256']
        result['alas_source_changed_during_run'] = alas_source_hashes() != result['alas_source_sha256']
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
