#!/usr/bin/env python3
"""Validate the pinned KVM-owned image build profile."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Sequence


def _load_contract_class():
    path = Path(__file__).resolve().parents[2] / "python" / "alas_headless" / (
        "android_kvm_image.py"
    )
    spec = importlib.util.spec_from_file_location("_android_kvm_image_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load KVM image contract: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.KvmImageBuildProfile


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    profile = _load_contract_class().from_mapping(
        json.loads(args.profile.read_text(encoding="utf-8"))
    )
    print(profile.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
