"""One typed New Jersey room visit, greeting and original ALAS room exit."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alas-root', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--driver-revision', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--resume-room', action='store_true', help='Resume from an observed room/dialogue; no overview start count')
    p.add_argument('--interact', action='store_true', help='Run original pq_interact three-loop routine')
    args = p.parse_args()
    if args.resume_room and not args.interact:
        p.error("--resume-room requires --interact")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    alas = args.alas_root.resolve()
    sys.path[:0] = [str(ROOT/'python'), str(alas)]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    os.chdir(alas)
    from alas import AzurLaneAutoScript
    from module.handler.login import LoginHandler
    from module.private_quarters.private_quarters import PrivateQuarters
    from alas_headless import SemanticGateClosed
    from alas_headless.semantic_sources import semantic_source_hashes
    instance = AzurLaneAutoScript('semantic_e2e')
    instance.config.override(Emulator_Serial=args.serial)
    session = instance.device.semantic_adapter
    result = dict(passed=False, schema='alas-headless.private-quarters-room-probe/v1',
                  source_sha256=semantic_source_hashes(ROOT), receipts=[])
    def wait(probe, seconds=60):
        end = time.monotonic()+seconds
        last = None
        while time.monotonic() < end:
            try:
                value = probe()
                if value:
                    return value
            except SemanticGateClosed as exc:
                last = exc
            time.sleep(.3)
        raise RuntimeError('typed state did not settle: '+str(last))
    try:
        o = session.open().oracle
        result['original_input_receipts'] = []
        original_click = o.click
        def record_click(semantic_id):
            receipt = original_click(semantic_id)
            result['original_input_receipts'].append(dataclasses.asdict(receipt))
            return receipt
        o.click = record_click
        result['resumed_room'] = args.resume_room
        if not args.resume_room:
            wait(lambda: o.main_page_visible() or o.exists('login/enter'), 90)
            if not o.main_page_visible():
                LoginHandler(instance.config,instance.device).handle_app_login()
            result['receipts'].append(dataclasses.asdict(o.click('main/live')))
            wait(lambda: o.enabled('dorm-menu/private-quarters'))
            result['receipts'].append(dataclasses.asdict(o.click('dorm-menu/private-quarters')))
            result['before'] = dataclasses.asdict(wait(o.private_quarters_overview))
            result['receipts'].append(dataclasses.asdict(o.click_private_quarters_new_jersey()))
        else:
            result['initial_room_state'] = dataclasses.asdict(o.read_state())
        wait(lambda: o.observation_target_present('private-quarters/dialogue/continue')
             or o.enabled('private-quarters/room/back'), 90)
        if o.observation_target_present('private-quarters/dialogue/continue'):
            time.sleep(3)
            result['receipts'].append(dataclasses.asdict(o.click_private_quarters_new_jersey_dialogue()))
        wait(lambda: o.enabled('private-quarters/room/back'), 90)
        result['room'] = dataclasses.asdict(o.read_state())
        task = PrivateQuarters(instance.config,instance.device)
        result['original_interact_requested'] = args.interact
        if args.interact:
            task.pq_interact()
            result['original_interact_completed'] = True
        else:
            task._pq_goto_room_exit()
        instance.device.screenshot()
        result['original_count'] = task.status_get_daily_count()
        result['after'] = dataclasses.asdict(o.private_quarters_overview())
        result['receipts'].append(dataclasses.asdict(o.click_private_quarters_home()))
        wait(o.main_page_visible)
        result['main'] = dataclasses.asdict(o.read_state())
        result['passed'] = (result['after']['remaining'] == result['original_count']
                            and (result['original_count'] == 0 if args.interact
                                 else result['before']['remaining'] == result['original_count']))
    except (Exception, SystemExit) as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    finally:
        session.close()
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASSED',result['passed'])
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
