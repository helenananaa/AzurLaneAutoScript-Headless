#!/usr/bin/env python3
"""Validate one backend-owned Android build domain."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _load_contract_class():
    try:
        from alas_headless.android_build_domain import AndroidBuildDomain
    except ModuleNotFoundError:
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / "python"))
        from alas_headless.android_build_domain import AndroidBuildDomain
    return AndroidBuildDomain


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, type=Path)
    parser.add_argument("--expected-backend", choices=("kvm", "redroid"))
    args = parser.parse_args()
    domain = _load_contract_class().from_path(
        args.domain, expected_backend=args.expected_backend
    )
    print(domain.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
