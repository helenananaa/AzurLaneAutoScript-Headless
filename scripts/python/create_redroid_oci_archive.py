#!/usr/bin/env python3
"""Create a deterministic OCI archive from a deterministic Redroid rootfs tar."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Sequence


def load_packager():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "python" / "alas_headless" / "android_image_oci.py"
    )
    spec = importlib.util.spec_from_file_location("alas_headless_android_image_oci", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load standalone Android OCI packager")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_redroid_oci_archive


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rootfs-layer", required=True, type=Path)
    parser.add_argument("--abi", required=True, choices=("x86_64", "arm64-v8a"))
    parser.add_argument("--source-lock-sha256", required=True)
    parser.add_argument("--build-fingerprint", required=True)
    parser.add_argument("--source-date-epoch", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--identity-output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.identity_output.exists():
        parser.error("--identity-output must not already exist")
    result = load_packager()(
        args.rootfs_layer, args.abi, args.source_lock_sha256,
        args.build_fingerprint, args.source_date_epoch, args.output,
    )
    args.identity_output.parent.mkdir(parents=True, exist_ok=True)
    args.identity_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.identity_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
