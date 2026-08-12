#!/usr/bin/env python3
"""Require locked ext4 superblock and root inode timestamps for Android images."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Sequence


INODE_TIME = re.compile(r"^\s*(c|a|m|cr)time:\s+0x([0-9a-f]+):", re.MULTILINE)


def command(*args: str) -> str:
    env = os.environ.copy()
    env.update({"LC_ALL": "C", "TZ": "UTC"})
    return subprocess.check_output(
        args, text=True, encoding="utf-8", stderr=subprocess.DEVNULL, env=env
    )


def inspect(image: Path, epoch: int) -> dict:
    superblock = command("dumpe2fs", "-h", str(image))
    inode = command("debugfs", "-R", "stat /", str(image))
    expected = datetime.datetime.fromtimestamp(
        epoch, tz=datetime.timezone.utc
    ).strftime("%a %b %d %H:%M:%S %Y")
    values = {}
    for label in ("Filesystem created", "Last write time"):
        match = re.search(r"^{0}:\s+(.+)$".format(re.escape(label)), superblock, re.MULTILINE)
        if match is None:
            raise ValueError("missing ext4 field {0}: {1}".format(label, image))
        values[label] = match.group(1).strip()
        if values[label] != expected:
            raise ValueError("ext4 {0} is not locked epoch: {1}".format(label, image))
    inode_values = {name: int(raw, 16) for name, raw in INODE_TIME.findall(inode)}
    if set(inode_values) != {"c", "a", "m", "cr"}:
        raise ValueError("root inode timestamps are incomplete: " + str(image))
    if any(value != epoch for value in inode_values.values()):
        raise ValueError("root inode timestamps are not locked epoch: " + str(image))
    return {
        "path": str(image.resolve()), "superblock": values,
        "root_inode_epoch": inode_values,
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", action="append", required=True, type=Path)
    parser.add_argument("--source-date-epoch", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    value = {
        "schema": "alas-headless.android-ext4-timestamps/v1",
        "outcome": "pass", "source_date_epoch": args.source_date_epoch,
        "images": [inspect(image, args.source_date_epoch) for image in args.image],
        "alas_workload_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
