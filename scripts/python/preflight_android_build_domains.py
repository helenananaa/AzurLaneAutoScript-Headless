#!/usr/bin/env python3
"""Validate an isolated, lock-free KVM/Redroid domain pair on one build host."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def _imports():
    try:
        from alas_headless.android_build_domain import AndroidBuildDomain
        from alas_headless.android_build_domain_migration import preflight_domain_pair
    except ModuleNotFoundError:
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / "python"))
        from alas_headless.android_build_domain import AndroidBuildDomain
        from alas_headless.android_build_domain_migration import preflight_domain_pair
    return AndroidBuildDomain, preflight_domain_pair


def _gib(value: str | float | int) -> int:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("capacity floor must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("capacity floor must be non-negative")
    return int(parsed * 1024**3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redroid-domain", required=True, type=Path)
    parser.add_argument("--kvm-domain", required=True, type=Path)
    parser.add_argument("--source-free-min-gib", type=_gib, default=_gib(400))
    parser.add_argument(
        "--repo-filesystem-free-min-gib",
        type=_gib,
        required=True,
        help="explicit system/root-filesystem reserve after both private .repo trees",
    )
    parser.add_argument("--output-free-min-gib", type=_gib, default=0)
    parser.add_argument("--require-owned-roots", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    domain_class, preflight = _imports()
    redroid = domain_class.from_path(args.redroid_domain, expected_backend="redroid")
    kvm = domain_class.from_path(args.kvm_domain, expected_backend="kvm")
    result = preflight(
        redroid,
        kvm,
        source_free_min_bytes=args.source_free_min_gib,
        repo_filesystem_free_min_bytes=args.repo_filesystem_free_min_gib,
        output_free_min_bytes=args.output_free_min_gib,
        require_owned_roots=args.require_owned_roots,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        if args.output.exists():
            parser.error("--output must not already exist")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
