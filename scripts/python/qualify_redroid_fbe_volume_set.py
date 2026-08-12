#!/usr/bin/env python3
"""Bind distinct Redroid host userdata and metadata volume qualifications."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from alas_headless.android_userdata_volume import qualify_fbe_volume_set


def load(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("qualification must be a JSON object: {0}".format(path))
    return value


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--userdata", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    result = qualify_fbe_volume_set(load(args.userdata), load(args.metadata))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
