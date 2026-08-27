#!/usr/bin/env python3
"""Publish, verify, switch, or roll back an immutable KVM runtime release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alas_headless.android_build_domain import AndroidBuildDomainError
from alas_headless.android_kvm_image import KvmImageBuildProfileError
from alas_headless.kvm_runtime_bundle import KvmRuntimeBundleError
from alas_headless.kvm_runtime_bundle import load_runtime_bundle_inputs
from alas_headless.kvm_runtime_bundle import publish_runtime_release
from alas_headless.kvm_runtime_bundle import switch_avd_runtime_release
from alas_headless.kvm_runtime_bundle import verify_runtime_release


def _contracts(parser: argparse.ArgumentParser, *, peer: bool = False) -> None:
    parser.add_argument("--domain", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    if peer:
        parser.add_argument("--peer-domain", required=True, type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    publish = commands.add_parser("publish")
    _contracts(publish, peer=True)

    verify = commands.add_parser("verify")
    _contracts(verify)

    for command in ("switch-avd", "rollback-avd"):
        avd = commands.add_parser(command)
        _contracts(avd)
        avd.add_argument("--avd-home", required=True, type=Path)
        avd.add_argument("--avd-name", required=True)
        avd.add_argument("--emulator-service", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        inputs = load_runtime_bundle_inputs(
            args.domain,
            args.profile,
            args.peer_domain if args.command == "publish" else None,
        )
        if args.command == "publish":
            result = publish_runtime_release(inputs, args.release_id)
            print(result)
            return 0
        if args.command == "verify":
            result = verify_runtime_release(inputs, args.release_id)
            print(result)
            return 0
        action = "rollback" if args.command == "rollback-avd" else "switch"
        result = switch_avd_runtime_release(
            inputs,
            args.release_id,
            args.avd_home,
            args.avd_name,
            args.emulator_service,
            action=action,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (
        AndroidBuildDomainError,
        KvmImageBuildProfileError,
        KvmRuntimeBundleError,
        OSError,
        ValueError,
    ) as exc:
        print(f"KVM runtime bundle error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
