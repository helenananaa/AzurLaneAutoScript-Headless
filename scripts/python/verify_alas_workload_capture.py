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

from alas_headless.workload_capture import verify_workload_capture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args()
    cases = [verify_workload_capture(path) for path in args.directories]
    result = {
        "schema": "alas-headless.live-workload-verification-batch/v1",
        "passed": all(case["passed"] for case in cases),
        "cases": cases,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
