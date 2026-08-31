#!/usr/bin/env python3
"""Verify that Redroid partition images contain the latest built runtime libs."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "alas-headless.redroid-partition-runtime-components/v1"
ELF_MACHINES = {"x86_64": 62, "arm64-v8a": 183}


def digest(path: Path) -> Mapping[str, Any]:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": value.hexdigest()}


def elf_machine(path: Path) -> int:
    header = path.read_bytes()[:20]
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise ValueError(f"runtime component is not ELF: {path}")
    if header[4] != 2 or header[5] != 1:
        raise ValueError(f"runtime component must be ELF64 little-endian: {path}")
    return struct.unpack_from("<H", header, 18)[0]


def unique_component(root: Path, candidates: Sequence[str], name: str) -> Path:
    matches = [root / candidate for candidate in candidates if (root / candidate).is_file()]
    if len(matches) != 1:
        raise ValueError(
            f"{name} must resolve to exactly one partition path; found {len(matches)}"
        )
    return matches[0]


def verify(
    system_root: Path,
    vendor_root: Path,
    expected_libegl: Path,
    expected_pastel: Path,
    abi: str,
    source_lock_sha256: str,
) -> Mapping[str, Any]:
    if abi not in ELF_MACHINES:
        raise ValueError("unsupported ABI: " + abi)
    if len(source_lock_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in source_lock_sha256
    ):
        raise ValueError("source lock SHA-256 must be lowercase hexadecimal")
    for path in (system_root, vendor_root):
        if not path.is_dir():
            raise ValueError("partition root is unavailable: " + str(path))
    for path in (expected_libegl, expected_pastel):
        if not path.is_file():
            raise ValueError("expected product component is unavailable: " + str(path))

    packaged = {
        "libEGL.so": unique_component(
            system_root,
            ("system/lib64/libEGL.so", "lib64/libEGL.so"),
            "libEGL.so",
        ),
        "vulkan.pastel.so": unique_component(
            vendor_root,
            ("lib64/hw/vulkan.pastel.so", "vendor/lib64/hw/vulkan.pastel.so"),
            "vulkan.pastel.so",
        ),
    }
    expected = {
        "libEGL.so": expected_libegl,
        "vulkan.pastel.so": expected_pastel,
    }
    components = {}
    blockers = []
    for name in sorted(expected):
        expected_identity = dict(digest(expected[name]))
        packaged_identity = dict(digest(packaged[name]))
        expected_machine = elf_machine(expected[name])
        packaged_machine = elf_machine(packaged[name])
        matches = expected_identity == packaged_identity
        machine_matches = (
            expected_machine == ELF_MACHINES[abi]
            and packaged_machine == ELF_MACHINES[abi]
        )
        if not matches:
            blockers.append(name + "-partition-image-stale")
        if not machine_matches:
            blockers.append(name + "-abi-mismatch")
        components[name] = {
            "expected_product_output": {
                "path": str(expected[name].resolve()),
                **expected_identity,
                "elf_machine": expected_machine,
            },
            "packaged_partition": {
                "path": str(packaged[name].resolve()),
                **packaged_identity,
                "elf_machine": packaged_machine,
            },
            "content_matches": matches,
            "abi_matches": machine_matches,
        }

    # This suffix is the reviewed AOSP loader change that prevents packaged
    # ANGLE from colliding with the already-loaded system ANGLE namespace.
    if b"_alasx.so" not in expected_libegl.read_bytes():
        blockers.append("libEGL.so-private-loader-suffix-missing")

    return {
        "schema": SCHEMA,
        "outcome": "pass" if not blockers else "blocked",
        "abi": abi,
        "source_lock_sha256": source_lock_sha256,
        "components": components,
        "blockers": sorted(blockers),
        "alas_workload_used": False,
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-root", required=True, type=Path)
    parser.add_argument("--vendor-root", required=True, type=Path)
    parser.add_argument("--expected-libegl", required=True, type=Path)
    parser.add_argument("--expected-pastel", required=True, type=Path)
    parser.add_argument("--abi", required=True, choices=tuple(ELF_MACHINES))
    parser.add_argument("--source-lock-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    try:
        value = verify(
            args.system_root,
            args.vendor_root,
            args.expected_libegl,
            args.expected_pastel,
            args.abi,
            args.source_lock_sha256,
        )
    except ValueError as exc:
        value = {
            "schema": SCHEMA,
            "outcome": "blocked",
            "abi": args.abi,
            "source_lock_sha256": args.source_lock_sha256,
            "components": {},
            "blockers": [str(exc)],
            "alas_workload_used": False,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0 if value["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
