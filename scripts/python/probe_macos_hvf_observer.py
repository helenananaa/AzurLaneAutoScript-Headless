#!/usr/bin/env python3
"""Read one typed observer frame through a temporary, cleaned ADB forward."""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from typing import Sequence


_source_package = Path(__file__).resolve().parents[2] / "python" / "alas_headless"
if _source_package.is_dir() and "alas_headless" not in sys.modules:
    package = types.ModuleType("alas_headless")
    package.__path__ = [str(_source_package)]
    package.__package__ = "alas_headless"
    sys.modules["alas_headless"] = package

from alas_headless.oracle.transport import AdbObserverBridge, request_observer_state


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--adb-server-port", type=int, default=5037)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    args = parser.parse_args(list(argv) if argv else None)

    bridge = AdbObserverBridge(
        args.serial,
        args.package,
        adb=args.adb,
        adb_server_port=args.adb_server_port,
        command_timeout_seconds=15.0,
    )
    try:
        bridge.open()
        snapshot, buttons, atomic = request_observer_state(bridge.request)
        ui = bridge.request("GET /v1/ui\n")
        output = {
            "schema": "alas-headless.macos-hvf-observer-probe/v1",
            "atomic": atomic,
            "protocol_schema": snapshot.get("protocol_schema"),
            "status": snapshot.get("status"),
            "package": snapshot.get("package"),
            "pid": snapshot.get("pid"),
            "generation": snapshot.get("generation"),
            "age_ms": snapshot.get("age_ms"),
            "main_thread": snapshot.get("main_thread"),
            "driver_revision": snapshot.get("driver_revision"),
            "button_count": buttons.get("button_count"),
            "button_truncated": buttons.get("truncated"),
            "button_paths": sorted(
                {
                    str(item.get("path"))
                    for item in buttons.get("buttons", [])
                    if isinstance(item, dict) and item.get("path")
                }
            )[:32],
            "button_targets": [
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "active_in_hierarchy": item.get("active_in_hierarchy"),
                    "active_and_enabled": item.get("active_and_enabled"),
                    "interactable": item.get("interactable"),
                    "raycast_top": item.get("raycast_top"),
                    "adb_point": item.get("adb_point"),
                }
                for item in buttons.get("buttons", [])
                if isinstance(item, dict)
            ][:32],
            "dialog_texts": [
                {
                    "path": str(item.get("path")),
                    "text": str(item.get("text")),
                }
                for item in ui.get("texts", [])
                if isinstance(item, dict)
                and "DialogPanel/" in str(item.get("path", ""))
            ][:16],
            "update_status_texts": [
                {
                    "path": str(item.get("path")),
                    "text": str(item.get("text")),
                }
                for item in ui.get("texts", [])
                if isinstance(item, dict)
                and "UpdatePanel/" in str(item.get("path", ""))
            ][:16],
            "ui_generation": ui.get("generation"),
            "ui_truncated": bool(
                ui.get("text_truncated") or ui.get("image_truncated")
            ),
        }
    finally:
        bridge.close()
    output["observer_forward_removed"] = True
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
