#!/usr/bin/env python3
"""Verify Event/Event2/EventA-D/EventSp shared entry configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alas_headless.alas_event_shared_entry_replay import verify_event_shared_entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = verify_event_shared_entry(arguments.alas_root)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
