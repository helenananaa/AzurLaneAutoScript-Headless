#!/usr/bin/env python3
"""Audit protected Android capabilities and collect a no-ALAS idle baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from alas_headless.android_foundation_audit import AUDIT_SCHEMA
from alas_headless.android_foundation_audit import audit_capabilities
from alas_headless.android_foundation_audit import collect_identity
from alas_headless.android_foundation_audit import collect_idle_metrics
from alas_headless.android_image_policy import AndroidImagePolicy
from alas_headless.android_update_lab import AdbClient


def load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object: {0}".format(path))
    return value


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--update-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample-seconds", type=float, default=60.0)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")

    policy = AndroidImagePolicy.from_mapping(load_json(args.policy))
    update_evidence = load_json(args.update_evidence)
    adb = AdbClient(args.adb, args.serial)
    adb.wait_boot()
    capabilities = audit_capabilities(adb, update_evidence)
    outcome = "pass" if all(
        value.get("outcome") == "pass" for value in capabilities.values()
    ) else "fail"
    document = {
        "schema": AUDIT_SCHEMA,
        "outcome": outcome,
        "serial": args.serial,
        "policy_sha256": policy.sha256,
        "identity": collect_identity(adb),
        "capabilities": capabilities,
        "idle_metrics": collect_idle_metrics(adb, args.sample_seconds),
        "game_installed": False,
        "alas_workload_used": False,
        "promotion_claim": "foundation-audit-only",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0 if outcome == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
