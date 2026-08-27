#!/usr/bin/env python3
"""Probe an ARM64 Redroid host for the Azur Lane runtime requirements."""

from __future__ import annotations

import json

from alas_headless.redroid_arm64_host import probe_running_host


def main() -> int:
    evidence = probe_running_host()
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
