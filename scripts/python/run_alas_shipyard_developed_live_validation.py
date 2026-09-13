"""Observe developed ships through original ALAS navigation, without consuming blueprints."""

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
    parser.add_argument('--indices', type=int, nargs='+', required=True)
    parser.add_argument('--series', type=int)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--login', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    sys.path[:0] = [str(ROOT / 'python'), str(args.alas_root.resolve())]
    os.chdir(args.alas_root)
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from alas import AzurLaneAutoScript
    from module.shipyard.ui import ShipyardUI
    from module.handler.login import LoginHandler
    from module.ui.page import page_shipyard, page_main
    from alas_headless.runtime import bind_semantic_session, reset_semantic_session
    from alas_headless.semantic_sources import semantic_source_hashes

    app = AzurLaneAutoScript('semantic_e2e')
    app.config.override(Emulator_Serial=args.serial)
    session = app.device.semantic_adapter
    token = bind_semantic_session(session)
    result = dict(passed=False, reads=[], source_sha256=semantic_source_hashes(ROOT))
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        adapter = session.open()
        oracle = adapter.oracle
        result['selections'] = []
        result['navigation'] = []
        original_click = oracle.click
        def record_click(semantic_id):
            receipt = original_click(semantic_id)
            result['navigation'].append(dataclasses.asdict(receipt))
            save()
            return receipt
        oracle.click = record_click
        original_select = oracle.click_shipyard_ship
        def record_select(index):
            receipt = original_select(index)
            result['selections'].append(dataclasses.asdict(receipt))
            save()
            return receipt
        oracle.click_shipyard_ship = record_select
        host = ShipyardUI(app.config, app.device)
        result['runtime'] = dataclasses.asdict(oracle.fingerprint)
        if args.login or oracle.enabled('login/enter') or oracle.login_update_in_progress():
            LoginHandler(app.config, app.device).handle_app_login()
            result['login_recovery'] = True
        host.ui_ensure(page_shipyard)
        ui = oracle.read_ui_state()
        result['before_ui'] = dataclasses.asdict(ui)
        toggles = sorted((t for t in ui.toggles
            if '/bottom_panel/ships/bg/content/ship_tpl' in t.path
            and t.active_in_hierarchy and t.active_and_enabled and t.bounds is not None),
            key=lambda t: t.bounds.left)
        selected = [i + 1 for i, t in enumerate(toggles) if t.checked]
        if len(selected) != 1:
            raise ValueError('original selected ship is ambiguous')
        result['original_index'] = selected[0]
        if args.series is not None:
            result['original_series'] = oracle.shipyard_series()
        save()
        if args.series is not None:
            if not host._shipyard_set_series(args.series):
                raise ValueError('original ALAS rejected requested series')
            result['selected_series'] = oracle.shipyard_series()
            save()
        for index in args.indices:
            host.shipyard_bottom_navbar_ensure(left=index)
            app.device.screenshot()
            state = session.shipyard_state(index)
            result['reads'].append(dict(state=dataclasses.asdict(state),
                buttons=dataclasses.asdict(oracle.read_state()),
                ui=dataclasses.asdict(oracle.read_ui_state()),
                cannot_strengthen=host._shipyard_cannot_strengthen(),
                append=host._shipyard_get_append(),
                blueprint_count=host._shipyard_get_bp_count(index)))
            save()
        if args.series is not None:
            host._shipyard_set_series(result['original_series'])
            result['restored_series'] = oracle.shipyard_series()
        host.shipyard_bottom_navbar_ensure(left=selected[0])
        result['restored'] = dataclasses.asdict(session.shipyard_state(selected[0]))
        host.ui_ensure(page_main)
        result['home'] = oracle.main_page_visible()
        result['after_ui'] = dataclasses.asdict(oracle.read_ui_state())
        result['passed'] = result['home'] and len(result['reads']) == len(args.indices)
    except BaseException as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
        if session._frame_reader is not None:
            try:
                frame_oracle = session._frame_reader.oracle()
                result['failure_frame_state'] = dataclasses.asdict(frame_oracle.read_state())
                result['failure_frame_ui'] = dataclasses.asdict(frame_oracle.read_ui_state())
            except Exception as read_error:
                result['failure_frame_error'] = str(read_error)
        if 'oracle' in locals():
            try:
                result['failure_ui'] = dataclasses.asdict(oracle.read_ui_state())
                result['failure_state'] = dataclasses.asdict(oracle.read_state())
            except Exception as read_error:
                result['failure_read_error'] = str(read_error)
    finally:
        reset_semantic_session(token)
        session.close()
        save()
    print('PASSED', result['passed'])
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
