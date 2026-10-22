"""Retain typed preparation observations without sending Android input."""

import argparse
import dataclasses
import json
import time
from pathlib import Path

from alas_headless import AdbObserverBridge, OracleFingerprint, SemanticOracle, SemanticGateClosed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-auto-menu", type=float, default=0,
                        help="Passive wait in seconds for the total-reward menu; sends no input")
    args = parser.parse_args()
    package = "com.bilibili.azurlane"
    with AdbObserverBridge(args.serial, package) as bridge:
        snapshot = bridge.request("GET /v1/state\n")["snapshot"]
        oracle = SemanticOracle(
            bridge.request, bridge.foreground_component, bridge.tap,
            OracleFingerprint(
                package=package,
                component=package + "/com.manjuu.azurlane.MainActivity",
                driver_revision=snapshot["driver_revision"], expected_pid=bridge.pid,
            ),
        )
        state = oracle.read_state()
        discarded_stale_samples = 0
        if args.wait_auto_menu:
            deadline = time.monotonic() + args.wait_auto_menu
            while not any("LevelStageTotalRewardPanel(Clone)/" in b.path for b in state.buttons):
                if time.monotonic() >= deadline:
                    raise TimeoutError("official auto-search menu did not appear")
                time.sleep(1)
                try:
                    state = oracle.read_state()
                except SemanticGateClosed as exc:
                    if str(exc) != "observer snapshot is stale":
                        raise
                    # A load transition can temporarily stop exports. Discard
                    # that sample; the same deadline still bounds observation.
                    discarded_stale_samples += 1
        ui = oracle.read_ui_state()
        fragments = ("/BottomExtra/LoopGroup/Loop/", "/Fixed/sp", "LevelStageView(Clone)/",
                     "LevelStageTotalRewardPanel(Clone)/")
        result = dict(
            schema="alas-headless.campaign-preparation-observation/v1",
            serial=args.serial, pid=bridge.pid, generation=state.generation,
            ui_generation=ui.generation, driver_revision=snapshot["driver_revision"],
            input_injected=False,
            discarded_stale_samples=discarded_stale_samples,
            buttons=[dataclasses.asdict(x) for x in state.buttons if any(f in x.path for f in fragments)],
            images=[dataclasses.asdict(x) for x in ui.images if any(f in x.path for f in fragments)],
            texts=[dataclasses.asdict(x) for x in ui.texts if any(f in x.path for f in fragments)],
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("serial", "pid", "generation", "ui_generation", "input_injected")}))


if __name__ == "__main__":
    main()
