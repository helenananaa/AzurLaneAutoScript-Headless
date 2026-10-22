"""Run two original ALAS Daily-page round trips without challenge input."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import traceback

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
    alas = args.alas_root.resolve()
    sys.path[:0] = [str(ROOT/'python'), str(alas)]
    os.chdir(alas)
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from alas import AzurLaneAutoScript
    from module.ui.ui import UI
    from module.ui.page import page_daily, page_main
    from alas_headless.semantic_sources import semantic_source_hashes
    app = AzurLaneAutoScript('semantic_e2e')
    app.config.override(Emulator_Serial=args.serial)
    session = app.device.semantic_adapter
    result = dict(passed=False, rounds=[], entries=[], source_sha256=semantic_source_hashes(ROOT))
    try:
        adapter = session.open()
        o = adapter.oracle
        result['runtime'] = dataclasses.asdict(o.fingerprint)
        original = o.click_campaign_daily_entrance
        def record():
            receipt = original()
            result['entries'].append(dataclasses.asdict(receipt))
            return receipt
        o.click_campaign_daily_entrance = record
        ui = UI(app.config, app.device)
        ui.ui_ensure(page_main)
        result['main_before'] = dataclasses.asdict(o.read_ui_state())
        for _ in range(2):
            before = len(result['entries'])
            ui.ui_ensure(page_daily)
            item = dict(state=dataclasses.asdict(o.read_state()), ui=dataclasses.asdict(o.read_ui_state()))
            dispatch_before = o.input_dispatch_count
            prior = adapter._daily_entry_receipt
            repeated = adapter._click_mapped('CAMPAIGN_MENU_GOTO_DAILY', 'campaign-menu/daily')
            item['explicit_repeat_reused_receipt'] = repeated is prior
            item['explicit_repeat_inputs'] = o.input_dispatch_count-dispatch_before
            item['actual_entries'] = len(result['entries'])-before
            ui.ui_ensure(page_main)
            item['home'] = o.main_page_visible()
            result['rounds'].append(item)
        result['main_after'] = dataclasses.asdict(o.read_ui_state())
        result['passed'] = all(x['home'] and x['actual_entries']==1
            and x['explicit_repeat_reused_receipt'] and x['explicit_repeat_inputs']==0 for x in result['rounds'])
    except Exception as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    finally:
        session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASSED',result['passed'])
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
