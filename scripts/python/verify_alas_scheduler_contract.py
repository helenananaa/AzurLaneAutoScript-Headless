#!/usr/bin/env python3
"""Verify ALAS Scheduler contracts in a disposable patched source tree."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from alas_headless.alas_scheduler_replay import verify_scheduler_contract


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
LOCK = ROOT / "integration" / "alas" / "upstream-lock.json"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    return result.stdout.rstrip("\r\n")


def verify_clean_upstream(upstream: Path):
    upstream = upstream.resolve()
    commit = json.loads(LOCK.read_text(encoding="utf-8"))["commit"]
    if _git(upstream, "rev-parse", "HEAD").lower() != commit:
        raise RuntimeError("Scheduler replay upstream commit drifted")
    if _git(upstream, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("Scheduler replay upstream must be clean")
    temporary_parent = Path(
        tempfile.mkdtemp(prefix="alas-scheduler-verify-", dir=str(upstream.parent))
    )
    disposable = temporary_parent / "worktree"
    registered = False
    try:
        _git(upstream, "worktree", "add", "--detach", str(disposable), commit)
        registered = True
        _git(disposable, "apply", "--", str(PATCH.resolve()))
        return verify_scheduler_contract(disposable)
    finally:
        if registered:
            _git(upstream, "worktree", "remove", "--force", str(disposable))
        shutil.rmtree(temporary_parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--alas-root", type=Path)
    source.add_argument("--upstream", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = (
        verify_clean_upstream(args.upstream)
        if args.upstream is not None
        else verify_scheduler_contract(args.alas_root)
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

