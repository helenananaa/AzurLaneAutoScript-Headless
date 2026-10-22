"""Observe the actual ButtonGO postcondition after an original ALAS entry.

This is a bounded qualification probe, not an alternative Campaign runner.
It allows one Go input and records whether that input only opens preparation
or starts official combat; it never guesses a postcondition or clicks twice.
"""

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
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--stage", default="12-4")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-result", type=Path,
                        help="Resume a prior zero-Go probe at its existing result; never repeat its first sortie")
    args = parser.parse_args()
    output = args.output.resolve()
    prior = json.loads(args.resume_result.read_text(encoding='utf-8')) if args.resume_result else None
    sys.path[:0] = [str(ROOT / "python"), str(args.alas_root.resolve())]
    os.chdir(args.alas_root)
    os.environ.update(ALAS_SEMANTIC_MODE="1", ALAS_SEMANTIC_ADB="F:/platform-tools/adb.exe",
        ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
        ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET="1",
        ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET="1",
        ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET="8",
        ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET="0")
    from module.campaign.run import CampaignRun
    from module.handler.fast_forward import to_map_file_name
    from module.ui.page import page_campaign
    from alas_headless import SemanticGateClosed, SemanticTargetMissing
    runner = CampaignRun("semantic_e2e", task="Main")
    runner.config.override(Emulator_Serial=args.serial, Campaign_Name=args.stage,
        Campaign_Event="campaign_main", Campaign_Mode="normal", Campaign_UseClearMode=True,
        Campaign_UseAutoSearch=True, Campaign_Use2xBook=False, Fleet_Fleet1=2,
        Fleet_Fleet2=1, Fleet_FleetOrder="fleet1_boss_fleet2_mob", Submarine_Fleet=0,
        Submarine_Mode="do_not_use")
    runner.load_campaign(to_map_file_name(args.stage))
    host = runner.campaign
    session = host.device.semantic_adapter
    adapter = session.open()
    oracle = adapter.oracle
    result = {"schema": "alas-headless.campaign-reentry-probe/v1", "passed": False,
              "serial": args.serial, "stage": args.stage, "go_input_count": 0}

    def wait_result():
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            try:
                if oracle.enabled("reward/campaign-total/exit"):
                    return
            except SemanticGateClosed as exc:
                if str(exc) != "observer snapshot is stale":
                    raise
            time.sleep(1)
        raise TimeoutError("official auto search did not reach result")

    try:
        session.begin_campaign_pre_sortie(args.stage)
        if prior is not None:
            if (prior.get('pid') != oracle.fingerprint.expected_pid or prior.get('stage') != args.stage
                    or prior.get('go_input_count') != 0 or not prior.get('sortie')
                    or not oracle.enabled('reward/campaign-total/exit')):
                raise SemanticGateClosed('prior probe does not identify this retained result')
            result['resumed_from'] = str(args.resume_result)
            result['sortie'] = prior['sortie']
            result['oil_before'] = prior['oil_before']
        else:
            host.device.screenshot()
            host.ui_ensure(page_campaign)
            host.ensure_campaign_ui(args.stage, mode="normal", skip_first_screenshot=False)
            result["oil_before"] = oracle.campaign_oil()
            host.enter_map(host.ENTRANCE, mode="normal", skip_first_screenshot=False)
            result["sortie"] = dataclasses.asdict(adapter.confirm_campaign_auto_search_started())
        result["pid"] = oracle.fingerprint.expected_pid
        wait_result()
        result["oil_at_result"] = oracle.campaign_oil()
        if not oracle.campaign_auto_search_reentry_available():
            raise SemanticGateClosed("typed ButtonGO is unavailable")
        receipt = oracle.click_campaign_auto_search_reentry()
        result["go_input_count"] = 1
        result["go_receipt"] = dataclasses.asdict(receipt)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if oracle.enabled("reward/campaign-total/exit"):
                time.sleep(0.5)
                continue
            preparation = oracle.campaign_preparation_state(args.stage)
            if preparation is not None and preparation.generation > receipt.generation:
                result["postcondition"] = preparation.kind + "-preparation"
                result["preparation"] = dataclasses.asdict(preparation)
                if preparation.kind == "map":
                    oracle.cancel_campaign_map_preparation(args.stage)
                else:
                    oracle.cancel_campaign_fleet_preparation(args.stage)
                break
            try:
                active = oracle.campaign_auto_search_active_state()
            except SemanticTargetMissing:
                active = None
            if (active is not None and active.generation > receipt.generation
                    and active.root_path.endswith(("CombatUIStandard(Clone)", "ChapterPreCombatUI(Clone)"))):
                result["postcondition"] = "official-auto-started"
                result["active"] = dataclasses.asdict(active)
                wait_result()
                oracle.click("reward/campaign-total/exit")
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("ButtonGO postcondition not proven")
        time.sleep(2)
        result["stage_page_after_cleanup"] = oracle.campaign_page_is_normal()
        result["oil_after"] = oracle.campaign_oil()
        result["passed"] = result["stage_page_after_cleanup"]
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        session.end_campaign_pre_sortie()
        session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
