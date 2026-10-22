"""Bounded original Campaign HP observation and withdrawal qualification."""

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
    parser.add_argument('--stage', default='10-2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--original-withdraw', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    sys.path[:0] = [str(ROOT / 'python'), str(args.alas_root.resolve())]
    os.chdir(args.alas_root)
    os.environ.update(ALAS_SEMANTIC_MODE='1',
        ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
        ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET='1',
        ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET='1',
        ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET='6',
        ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET='0')
    from module.campaign.run import CampaignRun
    from module.handler.fast_forward import to_map_file_name
    from module.ui.page import page_campaign
    from module.exception import CampaignEnd
    from verify_campaign_formations_live import confirm_withdrawal_when_ready

    runner = CampaignRun('semantic_e2e', task='Main')
    runner.config.override(Emulator_Serial=args.serial, Campaign_Name=args.stage,
        Campaign_Event='campaign_main', Campaign_Mode='normal', Campaign_UseClearMode=True,
        Campaign_UseAutoSearch=False, Campaign_Use2xBook=False, Fleet_Fleet1=2,
        Fleet_Fleet2=1, Fleet_FleetOrder='fleet1_mob_fleet2_boss', Submarine_Fleet=0,
        Submarine_Mode='do_not_use', HpControl_UseEmergencyRepair=False,
        HpControl_UseLowHpRetreat=False, HpControl_UseHpBalance=False)
    runner.load_campaign(to_map_file_name(args.stage))
    host = runner.campaign
    session = host.device.semantic_adapter
    adapter = session.open()
    oracle = adapter.oracle
    result = dict(schema='alas-headless.campaign-hp-live/v1', passed=False,
                  stage=args.stage, serial=args.serial, combat_budget=0)
    entered = False
    try:
        session.begin_campaign_pre_sortie(args.stage)
        host.device.screenshot()
        host.ui_ensure(page_campaign)
        host.ensure_campaign_ui(args.stage, mode='normal', skip_first_screenshot=False)
        result['oil_before'] = oracle.campaign_oil()
        host.enter_map(host.ENTRANCE, mode='normal', skip_first_screenshot=False)
        result['sortie'] = dataclasses.asdict(adapter.confirm_campaign_sortie())
        entered = True
        host.device.screenshot()
        result['fingerprint'] = dataclasses.asdict(oracle.fingerprint)
        result['map_buttons'] = dataclasses.asdict(oracle.read_state())
        result['map_ui'] = dataclasses.asdict(oracle.read_ui_state())
        result['hp'] = host.hp_get()
        result['hp_has_ship'] = host.hp_has_ship
        if args.original_withdraw:
            try:
                host.withdraw(skip_first_screenshot=False)
            except CampaignEnd as exc:
                result['campaign_end'] = str(exc)
            else:
                raise AssertionError('original withdrawal did not raise CampaignEnd')
            host.device.screenshot()
            if not oracle.campaign_page_is_normal():
                raise AssertionError('withdrawal did not restore chapter page')
            entered = False
        result['passed'] = True
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if entered:
            try:
                oracle.open_campaign_withdraw_confirmation()
                confirm_withdrawal_when_ready(oracle)
                time.sleep(2)
                result['cleanup_chapter'] = oracle.campaign_page_is_normal()
            except Exception as exc:
                result['passed'] = False
                result['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
        try:
            result['oil_after'] = oracle.campaign_oil()
        except Exception as exc:
            result['final_observation_error'] = str(exc)
        session.end_campaign_pre_sortie()
        session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('map_buttons', 'map_ui', 'sortie')}, ensure_ascii=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
