"""Qualify selected Shipyard state and original non-strengthenable branch; no purchases."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root',type=Path,required=True)
    parser.add_argument('--serial',required=True)
    parser.add_argument('--driver-revision',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();alas=args.alas_root.resolve()
    if output.exists():raise FileExistsError(output)
    sys.path[:0]=[str(ROOT/'python'),str(alas)];os.chdir(alas)
    os.environ.update(ALAS_SEMANTIC_MODE='1',ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from alas import AzurLaneAutoScript
    from module.shipyard.ui import ShipyardUI
    from module.ui.page import page_shipyard,page_main
    from alas_headless.runtime import bind_semantic_session,reset_semantic_session
    from alas_headless.semantic_sources import semantic_source_hashes
    app=AzurLaneAutoScript('semantic_e2e');app.config.override(Emulator_Serial=args.serial)
    session=app.device.semantic_adapter;result=dict(passed=False,reads=[],source_sha256=semantic_source_hashes(ROOT))
    token=bind_semantic_session(session)
    try:
        a=session.open();o=a.oracle;host=ShipyardUI(app.config,app.device)
        result['runtime']=dataclasses.asdict(o.fingerprint)
        for iteration in range(2):
            host.ui_ensure(page_shipyard)
            ui=o.read_ui_state()
            toggles=sorted([t for t in ui.toggles if '/bottom_panel/ships/bg/content/ship_tpl' in t.path
                           and t.active_in_hierarchy and t.active_and_enabled and t.bounds is not None],key=lambda t:t.bounds.left)
            selected=[i+1 for i,t in enumerate(toggles) if t.checked]
            if len(selected)!=1:raise ValueError('selected ship is ambiguous')
            host._shipyard_focus_index=selected[0]
            app.device.screenshot()
            state=session.shipyard_state(selected[0])
            item=dict(state=dataclasses.asdict(state),cannot_strengthen=host._shipyard_cannot_strengthen())
            if iteration:
                before=o.input_dispatch_count;prior=a._shipyard_entry_receipt
                repeated=a._click_mapped('RESHMENU_GOTO_SHIPYARD','research-menu/shipyard')
                item['repeat_reused']=prior is not None and repeated is prior
                item['repeat_inputs']=o.input_dispatch_count-before
            result['reads'].append(item)
            host.ui_ensure(page_main)
            item['home']=o.main_page_visible()
        result['main_ui']=dataclasses.asdict(o.read_ui_state())
        result['passed']=all(x['cannot_strengthen'] and x['home'] for x in result['reads']) and result['reads'][1]['repeat_reused'] and result['reads'][1]['repeat_inputs']==0
    except Exception as exc:
        result['error']=str(exc);result['traceback']=traceback.format_exc()
    finally:
        reset_semantic_session(token);session.close();output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASSED',result['passed'])
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
