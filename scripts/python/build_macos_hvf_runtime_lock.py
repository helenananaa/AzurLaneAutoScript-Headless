#!/usr/bin/env python3
"""Build an exact Mac/HVF runtime lock from an account-free identity receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.macos_hvf_identity import (
    angle_patchset_manifest,
    build_runtime_lock,
    runtime_lock_plain,
    write_canonical_document,
)


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--provision-profile", required=True, type=Path)
    parser.add_argument("--resource-manifest", required=True, type=Path)
    parser.add_argument("--angle-patchset-output", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists() or args.angle_patchset_output.exists():
        parser.error("runtime lock outputs must not already exist")
    patchset_sha256 = write_canonical_document(
        args.angle_patchset_output, angle_patchset_manifest(args.repo_root)
    )
    identity = json.loads(args.identity.read_text(encoding="utf-8"))
    lock = build_runtime_lock(
        repo_root=args.repo_root,
        identity=identity,
        provision_profile=args.provision_profile,
        resource_manifest=args.resource_manifest,
        angle_patchset_sha256=patchset_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(runtime_lock_plain(lock), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"runtime_lock_sha256": lock.sha256}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
