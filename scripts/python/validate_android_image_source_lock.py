#!/usr/bin/env python3
"""Validate and identify the immutable Redroid/AOSP source lock."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from typing import Sequence


def _load_contract_class():
    path = Path(__file__).resolve().parents[2] / "python" / "alas_headless" / (
        "android_image_source.py"
    )
    spec = importlib.util.spec_from_file_location("_android_image_source_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Android source lock contract: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.AndroidImageSourceLock


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-lock", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    lock = _load_contract_class().from_path(args.source_lock)
    print(lock.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
