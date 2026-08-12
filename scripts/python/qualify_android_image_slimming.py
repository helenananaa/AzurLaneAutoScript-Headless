#!/usr/bin/env python3
"""Qualify exactly one Android image slimming change without ALAS workload data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.android_image_slimming import qualify_slimming_change


def load(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object: {0}".format(path))
    return value


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    for name in ("change", "baseline-provenance", "candidate-provenance", "audit", "gles", "unity", "observer", "update", "rollback"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--baseline-inventory", required=True, type=Path)
    parser.add_argument("--candidate-inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    result = qualify_slimming_change(
        load(args.change), load(args.baseline_provenance), load(args.candidate_provenance),
        args.baseline_inventory, args.candidate_inventory, load(args.audit),
        {"gles-contract": load(args.gles), "unity-contract": load(args.unity),
         "observer-contract": load(args.observer)},
        load(args.update), load(args.rollback),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
