#!/usr/bin/env python3
"""Verify that the installed x86_64 Redroid WebView contains no 32-bit ABI."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Sequence


SCHEMA = "alas-headless.redroid-webview-abi/v1"
REQUIRED_LIBRARY = "lib/x86_64/libwebviewchromium.so"
ALLOWED_NATIVE_PREFIX = "lib/x86_64/"


def verify(apk: Path) -> dict[str, object]:
    blockers: list[str] = []
    native_entries: list[str] = []
    native_uncompressed_bytes = 0
    try:
        with zipfile.ZipFile(apk) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            names = {item.filename for item in infos}
            native_entries = sorted(
                item.filename for item in infos if item.filename.startswith("lib/")
            )
            native_uncompressed_bytes = sum(
                item.file_size for item in infos if item.filename.startswith("lib/")
            )
    except (FileNotFoundError, OSError, zipfile.BadZipFile) as error:
        blockers.append("webview-apk-unreadable:{0}".format(type(error).__name__))
        names = set()

    if REQUIRED_LIBRARY not in names:
        blockers.append("x86_64-webview-library-missing")
    unexpected = [
        name for name in native_entries if not name.startswith(ALLOWED_NATIVE_PREFIX)
    ]
    if unexpected:
        blockers.append("non-x86_64-native-payload-present")

    digest = ""
    size = 0
    if apk.is_file():
        hasher = hashlib.sha256()
        with apk.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        size = apk.stat().st_size
    return {
        "schema": SCHEMA,
        "outcome": "pass" if not blockers else "fail",
        "abi": "x86_64",
        "apk": {
            "path": str(apk.resolve()),
            "bytes": size,
            "sha256": digest,
        },
        "required_library": REQUIRED_LIBRARY,
        "native_entries": native_entries,
        "native_uncompressed_bytes": native_uncompressed_bytes,
        "unexpected_native_entries": unexpected,
        "blockers": blockers,
        "alas_workload_used": False,
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    result = verify(args.apk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
