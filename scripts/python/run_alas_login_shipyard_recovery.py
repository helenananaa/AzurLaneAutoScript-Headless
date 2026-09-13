"""Exercise original ALAS login recovery from a real shipyard page, without purchases."""
import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alas-root', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--driver-revision', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    alas = args.alas_root.resolve()
    sys.path[:0] = [str(ROOT/'python'), str(alas)]
    os.chdir(alas)
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from alas import AzurLaneAutoScript
    from module.shipyard.ui import ShipyardUI
    from module.handler.login import LoginHandler
    from module.ui.page import page_shipyard, page_main
    from alas_headless.semantic_sources import semantic_source_hashes
    app = AzurLaneAutoScript('semantic_e2e')
    app.config.override(Emulator_Serial=args.serial)
    session = app.device.semantic_adapter
    result = dict(passed=False, actions=[], source_sha256=semantic_source_hashes(ROOT),
                  scope='original LoginHandler from observed shipyard; no cold-start or purchases')
    result['source_sha256'].update({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in
        (Path(__file__),alas/'module/handler/login.py',alas/'module/ui/ui.py')})
    def save():
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        oracle = session.open().oracle
        result['runtime'] = dataclasses.asdict(oracle.fingerprint)
        original_click = session.click
        def click(button):
            receipt = original_click(button)
            result['actions'].append(dataclasses.asdict(receipt))
            save()
            return receipt
        session.click = click
        host = ShipyardUI(app.config,app.device)
        host.ui_ensure(page_shipyard)
        app.device.screenshot()
        result['before'] = dataclasses.asdict(oracle.read_state())
        result['shipyard_before'] = oracle.shipyard_page_visible()
        if not result['shipyard_before']:
            raise ValueError('shipyard precondition missing')
        save()
        LoginHandler(app.config,app.device).handle_app_login()
        result['login_handler_returned'] = True
        result['after_handler'] = dataclasses.asdict(oracle.read_state())
        save()
        host.ui_ensure(page_main)
        result['after'] = dataclasses.asdict(oracle.read_state())
        result['home'] = oracle.main_page_visible()
        result['passed'] = result['home'] and any(a['semantic_id']=='shipyard/page/back' for a in result['actions'])
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    finally:
        session.close()
        save()
    print('PASSED',result['passed'])
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
