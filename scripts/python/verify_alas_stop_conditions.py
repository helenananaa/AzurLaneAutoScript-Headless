#!/usr/bin/env python3
"""Write deterministic StopCondition evidence from an exact ALAS source tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alas_headless.alas_stop_condition_replay import verify_stop_conditions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_stop_conditions(args.alas_root)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
