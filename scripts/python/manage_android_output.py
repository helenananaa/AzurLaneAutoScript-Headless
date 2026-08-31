#!/usr/bin/env python3
"""Initialize, archive, evict, or restore one backend-owned output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _imports():
    try:
        from alas_headless.android_build_domain import AndroidBuildDomain
        from alas_headless.android_build_domain_migration import (
            archive_output,
            initialize_owner_root,
            require_output_buildable,
            restore_output,
        )
    except ModuleNotFoundError:
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / "python"))
        from alas_headless.android_build_domain import AndroidBuildDomain
        from alas_headless.android_build_domain_migration import (
            archive_output,
            initialize_owner_root,
            require_output_buildable,
            restore_output,
        )
    return (
        AndroidBuildDomain,
        initialize_owner_root,
        archive_output,
        restore_output,
        require_output_buildable,
    )


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain", required=True, type=Path)
    parser.add_argument("--backend", required=True, choices=("kvm", "redroid"))


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("initialize-owner")
    _common(initialize)
    initialize.add_argument("--root-kind", required=True, choices=("output", "archive"))
    initialize.add_argument("--adopt-existing", action="store_true")
    archive = commands.add_parser("archive")
    _common(archive)
    archive.add_argument("--snapshot-id", required=True)
    archive.add_argument(
        "--evict",
        action="store_true",
        help="after full manifest/hash verification, leave only owner and cold receipt",
    )
    restore = commands.add_parser("restore")
    _common(restore)
    restore.add_argument("--peer-domain", required=True, type=Path)
    restore.add_argument("--snapshot-id", required=True)
    assert_buildable = commands.add_parser("assert-buildable")
    _common(assert_buildable)
    assert_buildable.add_argument("--peer-domain", required=True, type=Path)
    args = parser.parse_args()

    (
        domain_class,
        initialize_owner,
        archive_one,
        restore_one,
        require_available,
    ) = _imports()
    domain = domain_class.from_path(args.domain, expected_backend=args.backend)
    if args.command == "initialize-owner":
        result = initialize_owner(
            domain,
            backend=args.backend,
            root_kind=args.root_kind,
            adopt_existing=args.adopt_existing,
        )
    elif args.command == "archive":
        result = archive_one(
            domain,
            backend=args.backend,
            snapshot_id=args.snapshot_id,
            evict=args.evict,
        )
    elif args.command == "restore":
        peer_backend = "redroid" if args.backend == "kvm" else "kvm"
        peer_domain = domain_class.from_path(
            args.peer_domain, expected_backend=peer_backend
        )
        result = restore_one(
            domain,
            peer_domain,
            backend=args.backend,
            snapshot_id=args.snapshot_id,
        )
    else:
        peer_backend = "redroid" if args.backend == "kvm" else "kvm"
        peer_domain = domain_class.from_path(
            args.peer_domain, expected_backend=peer_backend
        )
        result = require_available(
            domain,
            peer_domain,
            backend=args.backend,
            for_build=True,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
