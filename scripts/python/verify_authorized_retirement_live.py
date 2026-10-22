"""One authorized existing-ALAS retirement transaction from its selection page."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', type=Path, required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--observer-apk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume-completion', type=Path,
                        help='Finish dialogs for the same already-submitted transaction; no new retirement')
    parser.add_argument('--observe-only', action='store_true')
    parser.add_argument('--quit-only', action='store_true',
                        help='Resume only original ui_back from an idle selection; zero retirement budget')
    parser.add_argument('--full-handler', action='store_true',
                        help='Execute original ALAS retirement handler including its ui_back return')
    args = parser.parse_args()
    import hashlib
    output = args.output.resolve()
    apk = args.observer_apk.resolve()
    prior = json.loads(args.resume_completion.read_text(encoding='utf-8')) if args.resume_completion else None
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / 'python'), str(args.alas_root.resolve())]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_ADB='F:/platform-tools/adb.exe',
        ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
        ALAS_SEMANTIC_RETIREMENT_BUDGET='0' if args.observe_only or args.quit_only or prior else '1')
    os.chdir(args.alas_root.resolve())
    from module.retire.retirement import Retirement
    h = Retirement('semantic_e2e', task='Main')
    h.config.override(Emulator_Serial=args.serial)
    result = {'schema': 'alas-headless.authorized-retirement-live/v1', 'passed': False,
        'serial': args.serial, 'observer_apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
        'transaction_budget': 0 if args.observe_only or args.quit_only or prior else 1,
        'premium_spending_authorized': False}
    def returned():
        result['returned_to_main'] = adapter.oracle.main_page_visible()
        result['returned_to_build'] = (adapter.oracle.enabled('build/page/back')
                                      and adapter.oracle.toggle_selected('build/nav/pools'))
        return result['returned_to_main'] or result['returned_to_build']
    try:
        if (h.config.Retirement_RetireMode != 'one_click_retire'
                or h.config.OneClickRetire_KeepLimitBreak != 'keep_limit_break'):
            raise RuntimeError('Existing retirement configuration differs from authorization')
        session = h.device.semantic_adapter
        adapter = session.open()
        result['before'] = dataclasses.asdict(adapter.oracle.retirement_selection_state())
        result['fingerprint'] = dataclasses.asdict(adapter.oracle.fingerprint)
        if prior is not None:
            from alas_headless.oracle.contracts import RetirementSelectionState, RetirementSettingsState, ActionReceipt, Point, Bounds
            stored = prior['receipt']
            if (prior['fingerprint']['expected_pid'] != adapter.oracle.fingerprint.expected_pid
                    or result['before']['capacity_used'] != stored['capacity_after']
                    or result['before']['selected_count'] != 0
                    or adapter.oracle._retirement_screen_kind() not in ('award', 'equipment', 'equipment-preserve-confirm')):
                raise RuntimeError('Prior submitted retirement does not match current pending dialogs')
            actions = [ActionReceipt(**dict(item, point=Point(**item['point']), bounds=Bounds(**item['bounds']))) for item in stored['actions']]
            settings = RetirementSettingsState(**dict(stored['settings'], priority=tuple(stored['settings']['priority'])))
            before = RetirementSelectionState(**prior['before'])
            receipt = adapter.oracle._finish_retirement_transaction(before, stored['retired_count'], settings, actions, 60)
            result['transaction_budget'] = 0
            result['resumed_completion_from'] = str(args.resume_completion)
            result['new_ship_retirement_submitted'] = False
            result['receipt'] = dataclasses.asdict(dataclasses.replace(receipt,
                policy_sha256=stored['policy_sha256'], capability_id=stored['capability_id']))
            h._retirement_quit()
            result['passed'] = returned()
            return
        if args.quit_only:
            result['transaction_budget'] = 0
            result['quit_only'] = True
            h._retirement_quit()
            result['passed'] = returned()
            return
        if args.observe_only:
            result['transaction_budget'] = 0
            result['readback_only'] = True
            result['passed'] = result['before']['selected_count'] == 0
            return
        result['full_handler'] = args.full_handler
        result['retired_count'] = h._retire_handler() if args.full_handler else h.retire_ships_one_click()
        result['receipt'] = dataclasses.asdict(adapter.retirement_receipt())
        if args.full_handler:
            return_proven = returned()
            result['dock_full_triggered'] = h.config.DOCK_FULL_TRIGGERED
        else:
            result['after'] = dataclasses.asdict(adapter.oracle.retirement_selection_state())
        result['passed'] = result['retired_count'] > 0
        if args.full_handler:
            result['passed'] = result['passed'] and return_proven and result['dock_full_triggered']
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        if 'adapter' in locals() and adapter.retirement_receipt() is not None:
            result['receipt'] = dataclasses.asdict(adapter.retirement_receipt())
        # Preserve completed input receipts even if final receipt construction
        # fails. Never retry a destructive transaction from this exception.
        tb = exc.__traceback__
        while tb:
            if tb.tb_frame.f_code.co_name == 'retire_ships_one_click':
                local = tb.tb_frame.f_locals
                if 'actions' in local:
                    result['partial_actions'] = [dataclasses.asdict(a) for a in local['actions']]
                    result['equipment_preserved_observed'] = local.get('equipment_preserved')
            tb = tb.tb_next
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=True))
        if 'device' in h.__dict__:
            h.device.semantic_adapter.close()


if __name__ == '__main__':
    main()
