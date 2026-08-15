#!/usr/bin/env python3
"""Run the deterministic ALAS configuration interaction attack matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alas_headless.alas_configuration_attack_matrix import (
    verify_configuration_attack_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    arguments = parser.parse_args()
    print(
        json.dumps(
            verify_configuration_attack_matrix(arguments.alas_root),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
