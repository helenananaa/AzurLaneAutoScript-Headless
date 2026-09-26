"""Check original Research navigation and queue reads without starting projects."""

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
    parser.add_argument('--recovery-only', action='store_true')
    parser.add_argument('--start-from-shop', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    alas = args.alas_root.resolve()
    sys.path[:0] = [str(ROOT / 'python'), str(alas)]
    os.chdir(alas)
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from alas import AzurLaneAutoScript
    from module.research.research import RewardResearch
    from module.ui.page import page_research, page_main, page_shop
    from alas_headless.runtime import bind_semantic_session, reset_semantic_session
    from alas_headless.semantic_sources import semantic_source_hashes

    app = AzurLaneAutoScript('semantic_e2e')
    app.config.override(Emulator_Serial=args.serial)
    session = app.device.semantic_adapter
    token = bind_semantic_session(session)
    result = dict(passed=False, source_sha256=semantic_source_hashes(ROOT))
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    try:
        adapter = session.open()
        oracle = adapter.oracle
        result['runtime'] = dataclasses.asdict(oracle.fingerprint)
        result['initial_ui'] = dataclasses.asdict(oracle.read_ui_state())
        result['actions'] = []
        original_click = oracle.click
        def record_click(semantic_id):
            receipt = original_click(semantic_id)
            result['actions'].append(dataclasses.asdict(receipt))
            save()
            return receipt
        oracle.click = record_click
        host = RewardResearch(app.config, app.device)
        if oracle.enabled('login/enter'):
            from module.handler.login import LoginHandler
            LoginHandler(app.config, app.device).handle_app_login()
            result['login_recovery_performed'] = True
        if args.start_from_shop:
            host.ui_ensure(page_shop)
            result['shop_before_main'] = oracle.recommendation_shop_visible()
            save()
        host.ui_ensure(page_main)
        result['before'] = dataclasses.asdict(oracle.read_ui_state())
        if args.recovery_only:
            result['home'] = oracle.main_page_visible()
            result['progress_notice_absent'] = not oracle.exists('research/progress/confirm')
            result['passed'] = result['home'] and result['progress_notice_absent']
            print('PASSED', result['passed'])
            return 0 if result['passed'] else 1
        adapter.begin_research()
        host.ui_ensure(page_research)
        result['projects'] = [dataclasses.asdict(p) for p in oracle.research_projects()]
        prior = adapter._research_context.navigation_receipts.get('research-menu/research')
        count = oracle.input_dispatch_count
        repeated = adapter._click_mapped('RESHMENU_GOTO_RESEARCH', 'research-menu/research')
        result['repeat_reused'] = prior is not None and repeated is prior
        result['repeat_inputs'] = oracle.input_dispatch_count - count
        save()
        host.queue_enter()
        result['queue'] = dataclasses.asdict(oracle.research_queue_state())
        host.queue_quit()
        # RewardResearch.run releases this scope in its finally block before
        # a caller navigates home; keep the diagnostic lifecycle identical.
        adapter.end_research()
        save()
        host.ui_ensure(page_main)
        result['home'] = oracle.main_page_visible()
        result['after'] = dataclasses.asdict(oracle.read_ui_state())
        result['passed'] = result['home'] and result['repeat_reused'] and result['repeat_inputs'] == 0
    except BaseException as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    finally:
        reset_semantic_session(token)
        session.close()
        save()
    print('PASSED', result['passed'])
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
