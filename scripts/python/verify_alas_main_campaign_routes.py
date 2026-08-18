#!/usr/bin/env python3
"""Verify all pinned Main/Main2/Main3 routes without device input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alas_headless.alas_campaign_route_config_replay import verify_main_campaign_routes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_main_campaign_routes(args.alas_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
