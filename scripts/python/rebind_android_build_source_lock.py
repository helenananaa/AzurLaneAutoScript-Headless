#!/usr/bin/env python3
"""Rebind a synced source tree after an evidence-only lunch target correction."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Mapping, Sequence

from alas_headless.android_build_domain import AndroidBuildDomain
from alas_headless.android_image_source import AndroidImageSourceLock


SCHEMA = "alas-headless.android-image-source-lock-rebind/v1"
LEGACY_PRODUCTS = [
    {
        "abi": "x86_64",
        "lunch": "redroid_x86_64_only-userdebug",
        "product_out": "redroid_x86_64_only",
    },
    {
        "abi": "arm64-v8a",
        "lunch": "redroid_arm64_only-userdebug",
        "product_out": "redroid_arm64_only",
    },
]


def canonical_sha256(value: Mapping[str, object]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source lock must be an object")
    return value


def _require_within(path: Path, root: Path, name: str) -> None:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"{name} must stay inside Redroid evidence_root")


def _main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, type=Path)
    parser.add_argument("--old-source-lock", required=True, type=Path)
    parser.add_argument("--new-source-lock", required=True, type=Path)
    parser.add_argument("--resolved-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv))
    domain = AndroidBuildDomain.from_path(args.domain, expected_backend="redroid")
    source_root = Path(domain.path("source_root"))
    args.resume_marker = source_root / ".alas-redroid-build-source-lock"
    _require_within(args.output, Path(domain.path("evidence_root")), "--output")
    if args.output.exists():
        parser.error("--output must not already exist")

    old = load_object(args.old_source_lock)
    new_lock = AndroidImageSourceLock.from_path(args.new_source_lock)
    new = dict(new_lock.document)
    if old.get("products") != LEGACY_PRODUCTS:
        raise ValueError("old source lock is not the exact legacy lunch-target lock")
    old_without_products = dict(old)
    new_without_products = dict(new)
    old_without_products.pop("products", None)
    new_without_products.pop("products", None)
    if old_without_products != new_without_products:
        raise ValueError("source identity changed outside products")

    old_sha256 = canonical_sha256(old)
    if args.resume_marker.read_text(encoding="utf-8").strip() != old_sha256:
        raise ValueError("resume marker does not match old source lock")
    resolved = {
        (item.get("name"), item.get("path")): item.get("revision")
        for item in ET.parse(args.resolved_manifest).getroot().findall("project")
    }
    missing = []
    for project in new["redroid"]["projects"] + new["redroid"]["webview_projects"]:
        key = (project["name"], project["path"])
        if resolved.get(key) != project["commit"]:
            missing.append("{0}:{1}".format(*key))
    if missing:
        raise ValueError("resolved manifest differs from source lock: " + ",".join(missing))

    evidence = {
        "schema": SCHEMA,
        "outcome": "pass",
        "old_source_lock_sha256": old_sha256,
        "new_source_lock_sha256": new_lock.sha256,
        "change_scope": "products.lunch-release-segment-only",
        "resolved_projects_verified": len(
            new["redroid"]["projects"] + new["redroid"]["webview_projects"]
        ),
        "source_content_changed": False,
        "alas_workload_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=args.resume_marker.parent, delete=False
    ) as handle:
        handle.write(new_lock.sha256 + "\n")
        temporary = Path(handle.name)
    os.replace(temporary, args.resume_marker)
    print(args.output)
    return 0


def main(argv: Sequence[str] = ()) -> int:
    raw_args = list(argv) if argv else sys.argv[1:]
    return _main(raw_args)


if __name__ == "__main__":
    raise SystemExit(main())
