#!/usr/bin/env python3
"""Probe an x86 Redroid qualification host for FBE and recovery readiness."""

from __future__ import annotations

import json

from alas_headless.redroid_x86_host import probe_running_host


def main() -> int:
    evidence = probe_running_host()
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
