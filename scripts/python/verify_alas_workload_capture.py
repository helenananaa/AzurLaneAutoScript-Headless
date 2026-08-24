#!/usr/bin/env python3
"""Verify one or more ALAS live-workload capture directories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless.workload_capture import (  # noqa: E402
    build_workload_verification_manifest,
    verify_workload_capture,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seal-legacy",
        action="store_true",
        help="add a hash manifest to an unsealed retained legacy capture",
    )
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args()
    sealed = []
    if args.seal_legacy:
        for directory in args.directories:
            manifest_path = directory.resolve() / "verification-manifest.json"
            if manifest_path.exists():
                parser.error(
                    "verification manifest already exists: " + str(manifest_path)
                )
            manifest = build_workload_verification_manifest(directory)
            with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            sealed.append(str(manifest_path))
    cases = [verify_workload_capture(path) for path in args.directories]
    result = {
        "schema": "alas-headless.live-workload-verification-batch/v1",
        "passed": all(case["passed"] for case in cases),
        "sealed": sealed,
        "cases": cases,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
