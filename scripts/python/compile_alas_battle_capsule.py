#!/usr/bin/env python3
"""Compile a verified battle trace into an account-free W0 capsule."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless.battle_capsule import compile_battle_capsule  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_directory", type=Path)
    parser.add_argument("semantic_replay", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bucket-seconds", type=float, default=1.0)
    args = parser.parse_args()
    capsule = compile_battle_capsule(
        args.capture_directory, args.semantic_replay,
        bucket_seconds=args.bucket_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(capsule, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"passed": True, "output": str(args.output),
                      "steps": len(capsule["steps"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
