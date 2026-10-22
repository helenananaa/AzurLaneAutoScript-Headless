"""Qualify original StrategyHandler on two typed fleet slots, without battle."""

import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def confirm_withdrawal_when_ready(oracle):
    from alas_headless import SemanticGateClosed
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if oracle.confirm_campaign_withdrawal_if_present():
                return
        except SemanticGateClosed as exc:
            # Both errors are raised before input while the dialog mounts.
            # An ambiguous input outcome or any other failure is not retried.
            if str(exc) not in ("campaign withdrawal dialog is ambiguous",
                                "campaign withdrawal confirmation is not actionable"):
                raise
        time.sleep(0.5)
    raise TimeoutError("campaign withdrawal dialog did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="F:/platform-tools/adb.exe")
    parser.add_argument("--stage", default="3-1")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    sys.path[:0] = [str(ROOT / "python"), str(args.alas_root.resolve())]
    os.chdir(args.alas_root)
    os.environ.update(ALAS_SEMANTIC_MODE="1", ALAS_SEMANTIC_ADB=args.adb,
        ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
        ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET="1",
        ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET="1",
        ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET="6",
        ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET="0")
    from module.campaign.run import CampaignRun
    from module.handler.fast_forward import to_map_file_name
    from module.ui.page import page_campaign
    from alas_headless import SemanticGateClosed

    runner = CampaignRun("semantic_e2e", task="Main")
    runner.config.override(Emulator_Serial=args.serial, Campaign_Name=args.stage,
        Campaign_Event="campaign_main", Campaign_Mode="normal", Campaign_UseClearMode=True,
        Campaign_UseAutoSearch=False, Campaign_Use2xBook=False, Fleet_Fleet1=2,
        Fleet_Fleet2=1, Fleet_FleetOrder="fleet1_mob_fleet2_boss", Submarine_Fleet=0,
        Submarine_Mode="do_not_use")
    runner.load_campaign(to_map_file_name(args.stage))
    host = runner.campaign
    session = host.device.semantic_adapter
    adapter = session.open()
    oracle = adapter.oracle
    result = {"schema": "alas-headless.campaign-formations-live/v1", "passed": False,
              "stage": args.stage, "serial": args.serial, "cases": [], "switches": [],
              "restored": [], "combat_budget": 0}
    originals = {}
    entered = False
    initial_index = None

    def select(index):
        # Test setup exercises the reviewed typed selector, not a map model.
        # ALAS's combat routing is covered separately; do not claim it here.
        if oracle.campaign_map_displayed_fleet_index() == index:
            return
        receipt = oracle.click_campaign_map_fleet_switch()
        result["switches"].append(dataclasses.asdict(receipt))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            host.device.screenshot()
            if oracle.campaign_map_displayed_fleet_index() == index:
                return
            time.sleep(0.5)
        raise SemanticGateClosed("formation setup fleet selection did not advance")

    def set_formation(index, desired):
        select(index)
        host.config.override(**{f"Fleet_Fleet{index}Formation": desired})
        setattr(host, f"fleet_{index}_formation_fixed", False)
        host.device.screenshot()
        changed = host.handle_strategy(index=index)
        observed = oracle.campaign_map_formation()
        if observed != desired:
            raise SemanticGateClosed("original strategy formation postcondition failed")
        return {"slot": index, "desired": desired, "observed": observed,
                "handler_changed": changed, "generation": oracle.read_state().generation}

    try:
        session.begin_campaign_pre_sortie(args.stage)
        host.device.screenshot()
        host.ui_ensure(page_campaign)
        host.ensure_campaign_ui(args.stage, mode="normal", skip_first_screenshot=False)
        result["oil_before"] = oracle.campaign_oil()
        host.enter_map(host.ENTRANCE, mode="normal", skip_first_screenshot=False)
        result["sortie"] = dataclasses.asdict(adapter.confirm_campaign_sortie())
        entered = True
        result["pid"] = oracle.fingerprint.expected_pid
        initial_index = oracle.campaign_map_displayed_fleet_index()
        for index, formation in ((1, "line_ahead"), (2, "diamond")):
            select(index)
            originals[index] = oracle.campaign_map_formation()
            if originals[index] not in ("line_ahead", "double_line", "diamond"):
                del originals[index]
                raise SemanticGateClosed("initial formation cannot be read for restoration")
            result["cases"].append(set_formation(index, formation))
        result["passed"] = True
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if entered:
            try:
                for index, original in originals.items():
                    result["restored"].append(set_formation(index, original))
                if initial_index is not None:
                    select(initial_index)
            except Exception as exc:
                result["passed"] = False
                result["restore_error"] = type(exc).__name__ + ": " + str(exc)
            try:
                oracle.open_campaign_withdraw_confirmation()
                confirm_withdrawal_when_ready(oracle)
                time.sleep(2)
                result["oil_after"] = oracle.campaign_oil()
            except Exception as exc:
                result["passed"] = False
                result["cleanup_error"] = type(exc).__name__ + ": " + str(exc)
        session.end_campaign_pre_sortie()
        session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
