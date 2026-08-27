#!/usr/bin/env python3
"""Install, prepare, and activate one formal KVM live deployment."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alas_headless.kvm_live_cutover import (
    DEFAULT_CUTOVER_LOCK,
    KvmLiveCutoverError,
    activate_live_cutover,
    install_systemd_unit,
    load_cutover_context,
    prepare_live_cutover,
    resolve_user_identity,
    write_recovery_plan,
)


def _deployment(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--runtime-config", required=True, type=Path)
    parser.add_argument("--unit", required=True)


def _mutating(parser: argparse.ArgumentParser) -> None:
    _deployment(parser)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--phase-marker", required=True, type=Path)
    parser.add_argument("--cutover-lock", type=Path, default=DEFAULT_CUTOVER_LOCK)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser("install-unit")
    _mutating(install)
    install.add_argument("--run-as-user", required=True)
    install.add_argument("--run-script", required=True, type=Path)
    install.add_argument("--alas-python", required=True, type=Path)
    install.add_argument("--unit-directory", required=True, type=Path)
    install.add_argument("--timeout-stop-seconds", type=int, default=90)

    prepare = commands.add_parser("prepare")
    _mutating(prepare)
    prepare.add_argument("--unit-receipt", required=True, type=Path)
    prepare.add_argument("--previous-unit", required=True)
    prepare.add_argument("--previous-unit-archive", required=True, type=Path)
    prepare.add_argument("--snapshot-path", required=True, type=Path)
    prepare.add_argument("--snapshot-timeout-seconds", type=float, default=7200.0)

    activate = commands.add_parser("activate")
    _mutating(activate)
    activate.add_argument("--unit-receipt", required=True, type=Path)
    activate.add_argument("--prepare-receipt", required=True, type=Path)
    activate.add_argument("--adb-timeout-seconds", type=float, default=180.0)
    recovery = commands.add_parser("recovery-plan")
    _deployment(recovery)
    recovery.add_argument("--previous-unit", required=True)
    recovery.add_argument("--prepare-receipt", required=True, type=Path)
    recovery.add_argument("--activation-receipt", type=Path)
    recovery.add_argument("--phase-marker", required=True, type=Path)
    recovery.add_argument("--receipt", required=True, type=Path)
    return parser


def _require_root() -> None:
    if os.name != "posix" or os.geteuid() != 0:
        raise KvmLiveCutoverError(
            "formal cutover management requires root for systemd, listener PID, and complete /proc inspection"
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command != "recovery-plan":
            _require_root()
        context = load_cutover_context(
            args.domain, args.profile, args.release_id, args.runtime_config
        )
        if args.command == "install-unit":
            identity = resolve_user_identity(args.run_as_user)
            install_systemd_unit(
                context,
                args.unit,
                identity,
                args.run_script,
                args.alas_python,
                args.unit_directory,
                args.receipt,
                timeout_stop_seconds=args.timeout_stop_seconds,
                cutover_lock_path=args.cutover_lock,
                phase_marker_path=args.phase_marker,
            )
        elif args.command == "prepare":
            prepare_live_cutover(
                context,
                args.unit,
                args.unit_receipt,
                args.snapshot_path,
                args.receipt,
                previous_unit=args.previous_unit,
                previous_unit_archive_path=args.previous_unit_archive,
                copy_timeout_seconds=args.snapshot_timeout_seconds,
                cutover_lock_path=args.cutover_lock,
                phase_marker_path=args.phase_marker,
            )
        elif args.command == "activate":
            activate_live_cutover(
                context,
                args.unit,
                args.unit_receipt,
                args.prepare_receipt,
                args.receipt,
                adb_timeout_seconds=args.adb_timeout_seconds,
                cutover_lock_path=args.cutover_lock,
                phase_marker_path=args.phase_marker,
            )
        else:
            write_recovery_plan(
                context,
                args.unit,
                args.previous_unit,
                args.prepare_receipt,
                args.receipt,
                phase_marker_path=args.phase_marker,
                activation_receipt_path=args.activation_receipt,
            )
    except Exception as exc:
        print(f"KVM live cutover error: {exc}", file=sys.stderr)
        return 1
    print(os.fspath(args.receipt.resolve(strict=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
