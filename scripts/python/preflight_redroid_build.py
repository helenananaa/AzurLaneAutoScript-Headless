#!/usr/bin/env python3
"""Fail-closed host resource preflight before a full Redroid/AOSP build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.android_image_source import AndroidImageSourceLock
from alas_headless.android_image_source import host_preflight


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-lock", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--require-non-root-device", action="store_true")
    parser.add_argument("--backing-free-bytes", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    evidence = host_preflight(
        AndroidImageSourceLock.from_path(args.source_lock), args.root,
        args.backing_free_bytes,
        args.evidence_root,
        args.require_non_root_device,
    )
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("--output must not already exist")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if evidence["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
