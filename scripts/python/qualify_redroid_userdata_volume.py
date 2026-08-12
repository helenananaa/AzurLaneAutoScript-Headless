#!/usr/bin/env python3
"""Qualify a Redroid host userdata volume probe without claiming Android FBE."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from alas_headless.android_userdata_volume import qualify_userdata_volume


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    value = json.loads(args.probe.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        parser.error("--probe must contain a JSON object")
    result = qualify_userdata_volume(value)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
