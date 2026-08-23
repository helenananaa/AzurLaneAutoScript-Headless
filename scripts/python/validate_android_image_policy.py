#!/usr/bin/env python3
"""Validate the no-ALAS-data Android image policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alas_headless.android_image_policy import AndroidImagePolicy


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True, type=Path)
    arguments = parser.parse_args(list(argv) if argv else None)
    value = json.loads(arguments.policy.read_text(encoding="utf-8"))
    policy = AndroidImagePolicy.from_mapping(value)
    print(
        json.dumps(
            {
                "schema": "alas-headless.android-image-policy-validation/v1",
                "policy_id": policy.document["policy_id"],
                "policy_sha256": policy.sha256,
                "targets": [
                    target["target_id"] for target in policy.document["architectures"]
                ],
                "valid": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
