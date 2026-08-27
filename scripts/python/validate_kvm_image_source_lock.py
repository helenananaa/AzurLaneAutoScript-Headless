#!/usr/bin/env python3
"""Validate the KVM-owned clean AOSP source lock."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Sequence


def _load_contract_class():
    path = Path(__file__).resolve().parents[2] / "python" / "alas_headless" / (
        "android_kvm_source.py"
    )
    spec = importlib.util.spec_from_file_location("_android_kvm_source_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load KVM source lock contract: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.KvmImageSourceLock


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-lock", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    value = json.loads(args.source_lock.read_text(encoding="utf-8"))
    source_lock = _load_contract_class().from_mapping(value)
    print(source_lock.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
