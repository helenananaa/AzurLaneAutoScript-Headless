#!/usr/bin/env python3
"""Measure repeatable no-snapshot cold boots on a dedicated Android AVD."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Sequence

from alas_headless.android_update_lab import AdbClient, AndroidUpdateLabError


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--emulator", required=True, type=Path)
    parser.add_argument("--avd-home", required=True, type=Path)
    parser.add_argument("--avd-name", required=True)
    parser.add_argument("--console-port", required=True, type=int)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    if args.console_port % 2 or not (5554 <= args.console_port <= 5680):
        parser.error("--console-port must be an even emulator port")
    if not (1 <= args.rounds <= 10):
        parser.error("--rounds must be between 1 and 10")
    for path in (args.adb, args.emulator):
        if not path.is_file():
            parser.error("tool path is missing: {0}".format(path))
    avd_home = args.avd_home.resolve()
    if not (avd_home / (args.avd_name + ".avd") / "config.ini").is_file():
        parser.error("dedicated AVD config is missing")

    serial = "emulator-{0}".format(args.console_port)
    adb = AdbClient(args.adb, serial)
    sentinel = "/data/local/tmp/alas-image-foundation-cold-boot-sentinel"
    rounds = []

    def stop_existing() -> None:
        state = adb.run(["get-state"], timeout_seconds=5, check=False)
        if state.returncode == 0 and state.stdout == "device":
            avd_name = adb.run(["emu", "avd", "name"], timeout_seconds=10).stdout.splitlines()[0]
            if avd_name != args.avd_name:
                raise AndroidUpdateLabError("serial belongs to a different AVD")
            adb.run(["emu", "kill"], timeout_seconds=10, check=False)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if adb.run(["get-state"], timeout_seconds=5, check=False).returncode != 0:
                return
            time.sleep(0.5)
        raise AndroidUpdateLabError("existing emulator did not stop")

    stop_existing()
    environment = os.environ.copy()
    environment["ANDROID_AVD_HOME"] = str(avd_home)
    common = [
        "-avd", args.avd_name, "-port", str(args.console_port), "-no-window",
        "-no-audio", "-no-boot-anim", "-no-snapshot", "-gpu",
        "swiftshader_indirect", "-accel", "on", "-camera-back", "none",
        "-camera-front", "none", "-no-metrics",
    ]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = None
    try:
        for index in range(args.rounds):
            started = time.monotonic()
            process = subprocess.Popen(
                [str(args.emulator), *common],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            ready = adb.wait_boot(300)
            duration = round(time.monotonic() - started, 3)
            if index == 0:
                adb.shell(("touch", sentinel))
            sentinel_check = adb.shell(("ls", sentinel), check=False)
            if sentinel_check.returncode != 0:
                raise AndroidUpdateLabError("userdata sentinel did not survive cold boot")
            rounds.append(
                {
                    "round": index + 1,
                    "boot_seconds": duration,
                    "boot_completed": ready["boot_completed"],
                    "abi": adb.shell(("getprop", "ro.product.cpu.abilist")).stdout.strip(),
                    "fingerprint": adb.shell(("getprop", "ro.build.fingerprint")).stdout.strip(),
                    "userdata_sentinel": "present",
                }
            )
            adb.run(["emu", "kill"], timeout_seconds=10, check=False)
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            process = None
            stop_existing()
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    durations = [record["boot_seconds"] for record in rounds]
    document: Dict[str, Any] = {
        "schema": "alas-headless.android-cold-boot-qualification/v1",
        "outcome": "pass",
        "serial": serial,
        "avd_name": args.avd_name,
        "rounds": rounds,
        "median_boot_seconds": round(statistics.median(durations), 3),
        "min_boot_seconds": min(durations),
        "max_boot_seconds": max(durations),
        "snapshot_mode": "disabled",
        "userdata_wiped": False,
        "game_installed": False,
        "alas_workload_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
