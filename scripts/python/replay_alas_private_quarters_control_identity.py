"""Replay the original ALAS click watchdog with concrete PrivateQuarters controls."""
import argparse
import ast
import collections
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--alas-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.alas_root / 'module/device/device.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'click_record_check')
    class TooManyClicks(Exception):
        pass
    scope = dict(collections=collections, GameTooManyClickError=TooManyClicks,
                 show_function_call=lambda: None, logger=SimpleNamespace(warning=lambda *a: None))
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
    check = scope['click_record_check']
    def rejected(history):
        record = collections.deque(history, maxlen=20)
        device = SimpleNamespace(click_record=record, click_record_clear=record.clear)
        try:
            check(device)
        except TooManyClicks:
            return True
        return False
    dialogue = ['PRIVATE_QUARTERS_ROOM_SAFE_CLICK_AREA'] * 7
    old = dialogue + ['PRIVATE_QUARTERS_ROOM_BACK'] * 6
    distinct = dialogue + ['PRIVATE_QUARTERS_ROOM_BACK@ik'] * 4 + ['PRIVATE_QUARTERS_ROOM_BACK@watch', 'PRIVATE_QUARTERS_ROOM_BACK@base']
    result = dict(old_alias_collision_rejected=rejected(old), distinct_views_allowed=not rejected(distinct),
                  repeated_same_control_rejected=rejected(['PRIVATE_QUARTERS_ROOM_BACK@ik'] * 12),
                  two_control_loop_rejected=rejected(dialogue + ['PRIVATE_QUARTERS_ROOM_BACK@ik'] * 6),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    result['passed'] = all(result[k] for k in result if k != 'source_sha256')
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
