#!/usr/bin/env python3
"""Verify Main/Main2/Main3 shared configuration without device input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alas_headless.alas_main_shared_config_replay import verify_main_shared_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_main_shared_config(args.alas_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
