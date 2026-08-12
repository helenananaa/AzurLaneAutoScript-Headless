#!/usr/bin/env python3
"""Capture deterministic Redroid post-patch Git state for resume validation."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence

from alas_headless.android_image_source import AndroidImageSourceLock


SCHEMA = "alas-headless.redroid-post-patch-state/v1"
PROJECT_LINE = re.compile(r"^process project: (\S+)$")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-lock", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--resolved-manifest", required=True, type=Path)
    parser.add_argument("--apply-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    lock = AndroidImageSourceLock.from_path(args.source_lock)
    affected = sorted({
        match.group(1)
        for line in args.apply_log.read_text(encoding="utf-8").splitlines()
        if (match := PROJECT_LINE.fullmatch(line)) is not None
    })
    if not affected:
        raise ValueError("apply log contains no affected projects")
    revisions = {
        item.get("path", item.get("name")): item.get("revision")
        for item in ET.parse(args.resolved_manifest).getroot().findall("project")
    }
    projects = []
    for path in affected:
        project = args.source_root / path
        upstream = revisions.get(path)
        if not upstream:
            raise ValueError("affected project is absent from resolved manifest: " + path)
        if git(project, "status", "--porcelain"):
            raise ValueError("affected project is dirty: " + path)
        head = git(project, "rev-parse", "HEAD")
        if head == upstream:
            raise ValueError("Redroid patch state was reset to upstream: " + path)
        if subprocess.run(
            ["git", "-C", str(project), "merge-base", "--is-ancestor", upstream, head],
            check=False,
        ).returncode != 0:
            raise ValueError("post-patch HEAD is not based on resolved revision: " + path)
        projects.append({
            "path": path,
            "upstream_revision": upstream,
            "head": head,
            "tree": git(project, "rev-parse", "HEAD^{tree}"),
        })
    value = {
        "schema": SCHEMA,
        "outcome": "pass",
        "source_lock_sha256": lock.sha256,
        "projects": projects,
        "alas_workload_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
