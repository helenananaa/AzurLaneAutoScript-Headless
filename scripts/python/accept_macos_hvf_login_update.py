#!/usr/bin/env python3
"""Accept one exact typed CN login-update prompt on a Mac/HVF AVD."""

from __future__ import annotations

import argparse
import json
import sys
import time
import types
from pathlib import Path
from typing import Sequence


_source_package = Path(__file__).resolve().parents[2] / "python" / "alas_headless"
if _source_package.is_dir() and "alas_headless" not in sys.modules:
    package = types.ModuleType("alas_headless")
    package.__path__ = [str(_source_package)]
    package.__package__ = "alas_headless"
    sys.modules["alas_headless"] = package

from alas_headless.oracle.contracts import OracleFingerprint
from alas_headless.oracle.errors import SemanticGateClosed
from alas_headless.oracle.transport import AdbObserverBridge
from alas_headless.semantic_oracle import SemanticOracle


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--adb-server-port", type=int, default=5037)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument(
        "--component",
        default="com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
    )
    parser.add_argument("--allow-update-download", action="store_true")
    args = parser.parse_args(list(argv) if argv else None)
    if not args.allow_update_download:
        parser.error("one explicit --allow-update-download grant is required")

    bridge = AdbObserverBridge(
        args.serial,
        args.package,
        adb=args.adb,
        adb_server_port=args.adb_server_port,
        command_timeout_seconds=15.0,
    )
    try:
        bridge.open()
        initial = bridge.request("GET /v1/snapshot\n")
        fingerprint = OracleFingerprint(
            package=args.package,
            component=args.component,
            driver_revision=str(initial.get("driver_revision", "")),
            width=int(initial.get("width", 0)),
            height=int(initial.get("height", 0)),
            peer_uid=int(initial.get("peer_uid", -1)),
            expected_pid=bridge.pid,
        )

        def foreground_component() -> str:
            activities = bridge._run(("shell", "dumpsys", "activity", "activities"))
            match = bridge._FOREGROUND_PATTERN.search(activities)
            return match.group(1) if match is not None else ""

        def tap(x: int, y: int) -> None:
            bridge._run(("shell", "input", "tap", str(x), str(y)))

        oracle = SemanticOracle(
            bridge.request,
            foreground_component,
            tap,
            fingerprint,
        )
        if not oracle.login_update_download_available():
            raise SemanticGateClosed("exact login update download prompt is absent")
        receipt = oracle.click("login/update/download")
        deadline = time.monotonic() + 20.0
        update_started = False
        while time.monotonic() < deadline:
            if oracle.login_update_in_progress():
                update_started = True
                break
            time.sleep(0.5)
        if not update_started:
            raise SemanticGateClosed("login update did not enter typed progress state")
        output = {
            "schema": "alas-headless.macos-hvf-login-update-admission/v1",
            "outcome": "pass",
            "semantic_id": receipt.semantic_id,
            "generation": receipt.generation,
            "path": receipt.path,
            "input_dispatch_count": oracle.input_dispatch_count,
            "update_started": True,
            "observer_forward_removed": True,
        }
    finally:
        bridge.close()
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
