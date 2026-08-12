#!/usr/bin/env python3
"""Verify upstream refs against the immutable Android image source lock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.android_image_source import AndroidImageSourceLock
from alas_headless.android_image_source import verify_remote_refs


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-lock", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    value = verify_remote_refs(AndroidImageSourceLock.from_path(args.source_lock))
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("--output must not already exist")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if value["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
