"""Exercise the original ALAS FleetLock switch on an already entered map."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    sys.path[:0] = [str(ROOT / "python"), str(args.alas_root.resolve())]
    os.chdir(args.alas_root)
    os.environ.update(ALAS_SEMANTIC_MODE="1", ALAS_SEMANTIC_ADB="F:/platform-tools/adb.exe",
                      ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision)
    from module.handler.fast_forward import FastForwardHandler
    from alas_headless import SemanticGateClosed
    host = FastForwardHandler(args.seed_config, task="Main")
    host.config.override(Emulator_Serial=args.serial)
    session = host.device.semantic_adapter
    adapter = session.open()
    actions = []
    original = adapter.oracle._tap
    def tap(x, y):
        if len(actions) >= 3:
            raise SemanticGateClosed("FleetLock validation exceeded three switch inputs")
        actions.append([x, y])
        original(x, y)
    adapter.oracle._tap = tap
    result = {"schema": "alas-headless.fleet-lock-live/v1", "passed": False,
              "serial": args.serial, "stage": args.stage, "actions": actions}
    try:
        adapter.begin_campaign_pre_sortie(args.stage)
        entry = adapter.oracle.campaign_map_entry_state()
        result["map_generation"] = entry.generation
        result["pid"] = adapter.oracle.fingerprint.expected_pid
        result["initial"] = adapter.oracle.campaign_fleet_lock_selected()
        result["cases"] = []
        for desired in (True, False, True):
            host.config.override(Campaign_UseFleetLock=desired)
            host.device.screenshot()
            changed = host.handle_map_fleet_lock()
            observed = adapter.oracle.campaign_fleet_lock_selected()
            if observed is not desired:
                raise SemanticGateClosed("original FleetLock switch did not reach its postcondition")
            result["cases"].append(dict(desired=desired, changed=changed, observed=observed))
        result["passed"] = True
    finally:
        adapter.end_campaign_pre_sortie()
        session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
