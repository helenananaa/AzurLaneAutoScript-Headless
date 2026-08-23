#!/usr/bin/env python3
"""Create an honest dual-ABI Android image foundation release candidate manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Mapping, Optional, Sequence

from alas_headless.android_image_policy import AndroidImagePolicy
from alas_headless.android_image_release import TARGET_ABIS
from alas_headless.android_image_release import build_release_manifest
from alas_headless.android_image_release import hash_file
from alas_headless.android_image_release import load_json
from alas_headless.android_image_release import target_record
from alas_headless.android_image_source import AndroidImageSourceLock


def optional_json(path: Optional[Path]) -> Optional[Mapping[str, object]]:
    if path is None:
        return None
    value = dict(load_json(path))
    value["_evidence_file"] = hash_file(path)
    return value


def git_output(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("git identity command failed: {0}".format(" ".join(arguments)))
    return result.stdout.strip()


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--source-lock", required=True, type=Path)
    for prefix in ("x86-64", "arm64"):
        parser.add_argument("--{0}-contract-apk".format(prefix), type=Path)
        parser.add_argument("--{0}-angle-apk".format(prefix), type=Path)
        parser.add_argument("--{0}-image".format(prefix), type=Path)
        parser.add_argument("--{0}-image-identity".format(prefix), type=Path)
        parser.add_argument("--{0}-gles-evidence".format(prefix), type=Path)
        parser.add_argument("--{0}-unity-evidence".format(prefix), type=Path)
        parser.add_argument("--{0}-observer-evidence".format(prefix), type=Path)
        parser.add_argument("--{0}-audit".format(prefix), type=Path)
        parser.add_argument("--{0}-update-evidence".format(prefix), type=Path)
        parser.add_argument("--{0}-build-provenance".format(prefix), type=Path)
        parser.add_argument("--{0}-reproducibility-evidence".format(prefix), type=Path)
        parser.add_argument("--{0}-rollback-evidence".format(prefix), type=Path)
        parser.add_argument("--{0}-userdata-volume-evidence".format(prefix), type=Path)
        parser.add_argument("--{0}-fbe-volume-set-evidence".format(prefix), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-promotable", action="store_true")
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")

    policy = AndroidImagePolicy.from_mapping(load_json(args.policy))
    source_lock = AndroidImageSourceLock.from_path(args.source_lock)
    status = git_output(args.repo, "status", "--porcelain")
    source = {
        "commit": git_output(args.repo, "rev-parse", "HEAD"),
        "dirty": bool(status),
        "source_lock_sha256": source_lock.sha256,
    }
    targets = {
        "x86_64": target_record(
            "x86_64", args.x86_64_contract_apk, args.x86_64_angle_apk,
            args.x86_64_image,
            {
                "gles-contract": optional_json(args.x86_64_gles_evidence),
                "unity-contract": optional_json(args.x86_64_unity_evidence),
                "observer-contract": optional_json(args.x86_64_observer_evidence),
            },
            optional_json(args.x86_64_audit), optional_json(args.x86_64_update_evidence),
            optional_json(args.x86_64_image_identity),
            optional_json(args.x86_64_build_provenance),
            optional_json(args.x86_64_reproducibility_evidence),
            optional_json(args.x86_64_rollback_evidence),
            optional_json(args.x86_64_userdata_volume_evidence),
            optional_json(args.x86_64_fbe_volume_set_evidence),
        ),
        "arm64-v8a": target_record(
            "arm64-v8a", args.arm64_contract_apk, args.arm64_angle_apk,
            args.arm64_image,
            {
                "gles-contract": optional_json(args.arm64_gles_evidence),
                "unity-contract": optional_json(args.arm64_unity_evidence),
                "observer-contract": optional_json(args.arm64_observer_evidence),
            },
            optional_json(args.arm64_audit), optional_json(args.arm64_update_evidence),
            optional_json(args.arm64_image_identity),
            optional_json(args.arm64_build_provenance),
            optional_json(args.arm64_reproducibility_evidence),
            optional_json(args.arm64_rollback_evidence),
            optional_json(args.arm64_userdata_volume_evidence),
            optional_json(args.arm64_fbe_volume_set_evidence),
        ),
    }
    manifest = build_release_manifest(policy, source, targets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    if args.require_promotable and manifest["promotion"]["outcome"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
