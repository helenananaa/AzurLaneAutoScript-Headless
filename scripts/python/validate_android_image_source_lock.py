#!/usr/bin/env python3
"""Validate and identify the immutable Redroid/AOSP source lock."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from alas_headless.android_image_source import AndroidImageSourceLock


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-lock", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    lock = AndroidImageSourceLock.from_path(args.source_lock)
    print(lock.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
