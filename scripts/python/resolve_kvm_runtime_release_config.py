#!/usr/bin/env python3
"""Resolve a KVM runtime config only after verifying its immutable release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alas_headless.kvm_runtime_bundle import load_runtime_bundle_inputs
from alas_headless.kvm_runtime_bundle import verify_runtime_release
from alas_headless.runtime_backend_kvm import KvmBackend
from alas_headless.runtime_backends import backend_from_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--runtime-config", required=True, type=Path)
    args = parser.parse_args()
    try:
        inputs = load_runtime_bundle_inputs(args.domain, args.profile)
        verified = verify_runtime_release(inputs, args.release_id).resolve()
        value = json.loads(args.runtime_config.read_text(encoding="utf-8"))
        backend = backend_from_config(
            value,
            None,
            release_verifier=lambda selected: (
                verified
                if selected.resolve(strict=False) == verified
                else (_ for _ in ()).throw(
                    ValueError("runtime config selects a different release")
                )
            ),
        )
        if not isinstance(backend, KvmBackend):
            raise ValueError("runtime config backend must be kvm")
        backend._require_release_avd()
        config = backend.config
        result = {
            "runtime_release_root": str(verified),
            "emulator": str(config.emulator),
            "adb": str(config.adb),
            "sdk_root": str(config.sdk_root),
            "avd_home": str(config.avd_home),
            "avd_name": config.avd_name,
            "console_port": config.console_port,
            "adb_server_port": config.adb_server_port,
            "transport_serial": config.serial,
        }
    except Exception as exc:
        print(f"KVM runtime config error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
