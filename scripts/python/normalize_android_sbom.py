#!/usr/bin/env python3
"""Normalize the official AOSP SPDX creation time to the locked build epoch."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Sequence


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--source-date-epoch", required=True, type=int)
    args = parser.parse_args(list(argv) if argv else None)
    value = json.loads(args.sbom.read_text(encoding="utf-8"))
    if value.get("spdxVersion") != "SPDX-2.3":
        raise ValueError("AOSP SBOM must be SPDX-2.3")
    creation = value.get("creationInfo")
    if not isinstance(creation, dict) or not isinstance(creation.get("created"), str):
        raise ValueError("AOSP SBOM creationInfo.created is mandatory")
    creation["created"] = datetime.datetime.fromtimestamp(
        args.source_date_epoch, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = json.dumps(value, indent=4, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=args.sbom.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, args.sbom)
    print(args.sbom)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
