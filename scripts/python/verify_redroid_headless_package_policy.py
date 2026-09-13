#!/usr/bin/env python3
"""Verify the x86_64 Redroid headless package boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence


SCHEMA = "alas-headless.redroid-headless-package-policy/v1"

REQUIRED_MODULES = frozenset({
    "ContactsProvider",
    "DocumentsUI",
    "DownloadProvider",
    "ExternalStorageProvider",
    "KeyChain",
    "LatinIME",
    "Launcher3QuickStep",
    "PackageInstaller",
    "Settings",
    "SettingsIntelligence",
    "StorageManager",
    "SystemUI",
    "com.android.conscrypt",
    "com.android.i18n",
    "com.android.media",
    "com.android.mediaprovider",
    "com.android.permission",
    "com.android.resolv",
    "com.android.wifi",
    "webview",
})

REMOVED_MODULES = frozenset({
    "BluetoothMidiService",
    "android.hardware.bluetooth@1.1-service.sim",
    "BasicDreams",
    "BookmarkProvider",
    "Browser2",
    "BuiltInPrintService",
    "Calendar",
    "CalendarProvider",
    "Camera2",
    "CameraExtensionsProxy",
    "Contacts",
    "DeskClock",
    "DeviceAsWebcam",
    "EasterEgg",
    "Gallery2",
    "LiveWallpapersPicker",
    "MtpService",
    "Music",
    "MusicFX",
    "PhotoTable",
    "PrintRecommendationService",
    "PrintSpooler",
    "QuickSearchBox",
    "Traceur",
    "vr",
})


def verify(inventory: Path) -> dict[str, object]:
    blockers: list[str] = []
    modules: set[str] = set()
    payload = b""
    try:
        payload = inventory.read_bytes()
        modules = {
            line.strip()
            for line in payload.decode("utf-8").splitlines()
            if line.strip()
        }
    except (FileNotFoundError, OSError, UnicodeDecodeError) as error:
        blockers.append("package-inventory-unreadable:{0}".format(type(error).__name__))

    missing = sorted(REQUIRED_MODULES - modules)
    present = sorted(REMOVED_MODULES & modules)
    if missing:
        blockers.append("required-modules-missing")
    if present:
        blockers.append("removed-modules-present")

    return {
        "schema": SCHEMA,
        "outcome": "pass" if not blockers else "fail",
        "abi": "x86_64",
        "inventory": {
            "path": str(inventory.resolve()),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest() if payload else "",
            "module_count": len(modules),
        },
        "required_modules": sorted(REQUIRED_MODULES),
        "missing_required_modules": missing,
        "removed_modules": sorted(REMOVED_MODULES),
        "forbidden_modules_present": present,
        "blockers": blockers,
        "alas_workload_used": False,
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    result = verify(args.inventory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
