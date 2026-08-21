#!/usr/bin/env python3
"""Open and capture the typed Operation Siren mission list without claiming it."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    AdbObserverBridge,
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument(
        "--component",
        default="com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with AdbObserverBridge(args.serial, args.package) as bridge:
        oracle = SemanticOracle(
            bridge.request,
            bridge.foreground_component,
            bridge.tap,
            OracleFingerprint(
                package=args.package,
                component=args.component,
                driver_revision=args.driver_revision,
                expected_pid=bridge.pid,
            ),
        )

        def tap_exact(name: str, path_suffix: str) -> None:
            state = oracle.read_state()
            matches = tuple(
                button
                for button in state.buttons
                if button.name == name
                and button.path.endswith(path_suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.raycast_top is None
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
                and 0 <= button.point.x < oracle.fingerprint.width
                and 0 <= button.point.y < oracle.fingerprint.height
            )
            if len(matches) != 1:
                raise RuntimeError(name + " control is absent or ambiguous")
            point = matches[0].point
            assert point is not None
            bridge.tap(int(round(point.x)), int(round(point.y)))

        if not oracle.operation_siren_mission_list_visible():
            if oracle.operation_siren_globe_visible():
                tap_exact("back_button", "top/adapt/top_chapter/back_button")
            for _ in range(20):
                try:
                    oracle.operation_siren_state()
                    break
                except SemanticGateClosed:
                    time.sleep(0.25)
            else:
                raise RuntimeError("Operation Siren local map did not settle")

            state = oracle.read_state()
            if any("WorldPortUI(Clone)" in button.path for button in state.buttons):
                tap_exact(
                    "back_button",
                    "WorldPortUI(Clone)/blur_panel/adapt/top/title/back_button",
                )
                time.sleep(1.0)

            tap_exact(
                "information_button",
                "top/adapt/right_stage/btn_list/dock/information_button",
            )
            for _ in range(40):
                if oracle.operation_siren_mission_list_visible():
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Operation Siren mission list did not settle")

        state = oracle.read_state()
        ui = oracle.read_ui_state(check_foreground=False)
        row_root = "WorldInformationUI(Clone)/adapt/right_panel/main/viewport/content/"
        payload = {
            "schema": "alas-headless.operation-siren-mission-list-probe/v1",
            "serial": args.serial,
            "package": args.package,
            "pid": bridge.pid,
            "driver_revision": args.driver_revision,
            "generation": {"buttons": state.generation, "ui": ui.generation},
            "monthly_boss_difficulty": oracle.operation_siren_month_boss_difficulty(),
            "buttons": [
                button.raw
                for button in state.buttons
                if row_root in button.path
                or button.path.endswith("WorldInformationUI(Clone)/adapt/top/btn_back")
            ],
            "texts": [
                text.raw
                for text in ui.texts
                if row_root in text.path
                or text.path.endswith(
                    "WorldInformationUI(Clone)/adapt/right_panel/title/task_all"
                )
            ],
            "input_injected": True,
            "mission_action_injected": False,
            "passed": True,
        }
        oracle.click("os/mission-list/close")
        payload["mission_list_closed"] = True

    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
