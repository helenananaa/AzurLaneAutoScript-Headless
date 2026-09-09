"""Recover a retained settlement with original ALAS, without claiming a sortie."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alas-root', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--kind', choices=('settlement', 'urgent-notice'), default='settlement')
    args = p.parse_args()
    output = args.output.resolve()
    root = Path(__file__).resolve().parents[2]
    upstream = args.alas_root.resolve()
    sys.path[:0] = [str(root / 'python'), str(upstream)]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_ADB='F:/platform-tools/adb.exe',
        ALAS_SEMANTIC_DRIVER_REVISION='506b76f698b5089aaa29c4e7908b48edb8532a44',
        ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET='0', ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET='0')
    os.chdir(upstream)
    from module.campaign.run import CampaignRun
    runner = CampaignRun('semantic_e2e', task='Main')
    runner.config.override(Emulator_Serial=args.serial, Campaign_Name='10-2',
        Campaign_Event='campaign_main', Campaign_Mode='normal')
    runner.load_campaign('campaign_10_2')
    h = runner.campaign
    session = h.device.semantic_adapter
    a = session.open()
    o = a.oracle
    result = dict(schema='alas-headless.campaign-settlement-recovery/v1',
                  passed=False, claimed_completed_sorties=0, serial=args.serial, kind=args.kind)
    original = o.click
    receipts = []
    def record(target, *values, **keywords):
        receipt = original(target, *values, **keywords)
        receipts.append(dataclasses.asdict(receipt))
        return receipt
    o.click = record
    try:
        session.begin_campaign_pre_sortie('10-2')
        h.device.screenshot()
        result['fingerprint'] = dataclasses.asdict(o.fingerprint)
        if args.kind == 'urgent-notice':
            result['notice_before'] = o._campaign_urgent_notice_matches(o.read_state())
            if not result['notice_before']:
                raise RuntimeError('Expected urgent notice is absent')
            result['handled'] = h.handle_popup_single(name='CAMPAIGN_MAP', interval=0)
            h.device.screenshot()
            result['notice_after'] = o._campaign_urgent_notice_matches(o.read_state())
            result['map_after'] = o.campaign_is_in_map()
            result['passed'] = (result['handled'] and not result['notice_after']
                                and result['map_after'] and len(receipts) == 1)
            return
        result['settlement_before'] = o.enabled('reward/campaign-total/exit')
        if not result['settlement_before']:
            raise RuntimeError('Expected retained settlement is absent')
        result['chapter_probe_before'] = o.campaign_page_is_normal()
        h.ensure_auto_search_exit(skip_first_screenshot=False)
        result['chapter_after'] = o.campaign_page_is_normal()
        result['settlement_after'] = o.exists('reward/campaign-total/exit')
        result['oil_after'] = o.campaign_oil()
        result['passed'] = (not result['chapter_probe_before'] and result['chapter_after']
                            and not result['settlement_after'] and len(receipts) == 1)
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        result['receipts'] = receipts
        session.end_campaign_pre_sortie()
        session.close()
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
