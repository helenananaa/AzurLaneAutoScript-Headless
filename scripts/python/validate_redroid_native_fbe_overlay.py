#!/usr/bin/env python3
"""Validate and optionally record the locked Redroid native-FBE overlay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.android_fbe_overlay import validate_fbe_overlay
from alas_headless.android_image_source import AndroidImageSourceLock


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--source-lock", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    source_lock = AndroidImageSourceLock.from_path(args.source_lock) if args.source_lock else None
    result = validate_fbe_overlay(args.overlay, source_lock)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("--output must not already exist")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
