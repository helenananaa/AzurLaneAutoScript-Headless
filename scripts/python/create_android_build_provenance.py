#!/usr/bin/env python3
"""Create fail-closed source, SBOM, NOTICE, and artifact provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.android_image_source import AndroidImageSourceLock
from alas_headless.android_image_supply_chain import create_build_provenance


def load_object(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object: {0}".format(path))
    return value


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-lock", required=True, type=Path)
    parser.add_argument("--resolved-manifest", required=True, type=Path)
    parser.add_argument("--abi", required=True, choices=("x86_64", "arm64-v8a"))
    parser.add_argument("--lunch", required=True)
    parser.add_argument("--product-out", required=True)
    parser.add_argument("--build-fingerprint", required=True)
    parser.add_argument("--security-patch", required=True)
    parser.add_argument("--artifact", action="append", required=True)
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--notice", action="append", required=True, type=Path)
    parser.add_argument("--installed-files", required=True, type=Path)
    parser.add_argument("--host-preflight", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    value = create_build_provenance(
        AndroidImageSourceLock.from_path(args.source_lock), args.resolved_manifest,
        args.abi, args.lunch, args.product_out, args.build_fingerprint,
        args.security_patch, args.artifact, args.sbom, args.notice,
        args.installed_files, load_object(args.host_preflight),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
