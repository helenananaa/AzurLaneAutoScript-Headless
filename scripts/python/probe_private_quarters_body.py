"""Capture one reviewed body input and stop for typed postcondition inspection."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', type=Path, required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    flow = output.with_name(output.stem+'-flow.json')
    if output.exists() or flow.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    alas = args.alas_root.resolve()
    sys.path[:0] = [str(ROOT/'python'), str(alas)]
    os.chdir(alas)
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from module.private_quarters.private_quarters import PrivateQuarters
    from module.private_quarters.assets import PRIVATE_QUARTERS_ROOM_TARGET_CLICK_AREA
    import run_alas_private_quarters_room_probe as probe
    original = PrivateQuarters._pq_goto_room_exit
    def capture(host):
        oracle = host.device.semantic_adapter.open().oracle
        result = {'ui':dataclasses.asdict(oracle.read_ui_state())}
        try:
            result['physics'] = dataclasses.asdict(oracle.private_quarters_physics())
            host.device.screenshot()
            result['body_receipt'] = dataclasses.asdict(host.device.click(PRIVATE_QUARTERS_ROOM_TARGET_CLICK_AREA))
            time.sleep(2)
            result['after_state'] = dataclasses.asdict(oracle.read_state())
            result['after_ui'] = dataclasses.asdict(oracle.read_ui_state())
        except Exception as exc:
            result['body_error'] = str(exc)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if 'body_receipt' in result:
            raise SystemExit('diagnostic stop after one body input')
        return original(host)
    PrivateQuarters._pq_goto_room_exit = capture
    sys.argv = ['probe', '--alas-root', str(alas), '--serial', args.serial,
                '--driver-revision', args.driver_revision, '--output', str(flow)]
    try:
        return probe.main()
    finally:
        PrivateQuarters._pq_goto_room_exit = original


if __name__ == '__main__':
    raise SystemExit(main())
