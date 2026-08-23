#!/usr/bin/env python3
"""Qualify repeated Redroid container restarts with immutable image and /data."""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from alas_headless.android_update_lab import AdbClient, AndroidUpdateLabError


SCHEMA = "alas-headless.redroid-restart-qualification/v1"


def remote_inspect(ssh: Path, target: str, container: str) -> Mapping[str, Any]:
    completed = subprocess.run(
        [str(ssh), "-o", "BatchMode=yes", target, "docker", "inspect", container],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise AndroidUpdateLabError("remote Redroid inspect failed")
    value = json.loads(completed.stdout)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise AndroidUpdateLabError("remote Redroid inspect returned an invalid document")
    return value[0]


def reconnect(adb_path: Path, adb: AdbClient, serial: str, timeout: float) -> None:
    subprocess.run(
        [str(adb_path), "disconnect", serial],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        subprocess.run(
            [str(adb_path), "connect", serial],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        state = adb.run(("get-state",), timeout_seconds=10, check=False)
        if state.stdout.strip() == "device":
            return
        time.sleep(1)
    raise AndroidUpdateLabError("ADB TCP transport did not reconnect")


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--ssh", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    if args.rounds < 1 or args.rounds > 20:
        parser.error("--rounds must be between 1 and 20")
    if not args.adb.is_file() or not args.ssh.is_file():
        parser.error("--adb and --ssh must be files")

    adb = AdbClient(args.adb, args.serial)
    adb.wait_boot()
    initial = remote_inspect(args.ssh, args.target, args.container)
    descriptor = initial.get("ImageManifestDescriptor", {})
    digest = descriptor.get("digest") if isinstance(descriptor, dict) else None
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise AndroidUpdateLabError("Redroid container is not bound to a manifest digest")
    if initial.get("Image") != digest:
        raise AndroidUpdateLabError("Redroid image ID and manifest digest differ")

    sentinel = secrets.token_hex(24)
    sentinel_path = "/data/local/tmp/alas-foundation-restart-sentinel"
    adb.shell(("printf %s {0} > {1}".format(sentinel, sentinel_path),))
    rounds = []
    for index in range(1, args.rounds + 1):
        firstboot_before = adb.shell(("getprop", "ro.runtime.firstboot")).stdout.strip()
        started = time.monotonic()
        completed = subprocess.run(
            [
                str(args.ssh), "-o", "BatchMode=yes", args.target,
                "docker", "restart", args.container,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise AndroidUpdateLabError("Redroid restart command failed")
        reconnect(args.adb, adb, args.serial, 120)
        adb.wait_boot(300)
        elapsed = round(time.monotonic() - started, 3)
        firstboot_after = adb.shell(("getprop", "ro.runtime.firstboot")).stdout.strip()
        observed_sentinel = adb.shell(("cat", sentinel_path)).stdout.strip()
        current = remote_inspect(args.ssh, args.target, args.container)
        current_descriptor = current.get("ImageManifestDescriptor", {})
        current_digest = (
            current_descriptor.get("digest")
            if isinstance(current_descriptor, dict)
            else None
        )
        if firstboot_after == firstboot_before:
            raise AndroidUpdateLabError("Redroid firstboot identity did not change")
        if observed_sentinel != sentinel:
            raise AndroidUpdateLabError("Redroid /data sentinel was not preserved")
        if current_digest != digest:
            raise AndroidUpdateLabError("Redroid image digest changed across restart")
        rounds.append(
            {
                "round": index,
                "restart_to_android_ready_seconds": elapsed,
                "firstboot_before": firstboot_before,
                "firstboot_after": firstboot_after,
                "manifest_digest": current_digest,
                "data_sentinel_preserved": True,
            }
        )

    adb.shell(("rm", "-f", sentinel_path))
    cleanup = adb.shell(("test", "!", "-e", sentinel_path), check=False)
    if cleanup.returncode != 0:
        raise AndroidUpdateLabError("Redroid restart sentinel cleanup failed")

    document = {
        "schema": SCHEMA,
        "outcome": "pass",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "serial": args.serial,
        "target": args.target,
        "container": args.container,
        "manifest_digest": digest,
        "rounds": rounds,
        "sentinel_cleaned": True,
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
