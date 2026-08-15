#!/usr/bin/env python3
"""Verify OpsiStronghold is source-audited and blocked before headless work."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from alas_headless.alas_opsi_stronghold_source_audit import audit_opsi_stronghold_source, verify_opsi_stronghold_headless_gate
PATCH = ROOT / "integration/alas/0001-semantic-oracle-hooks.patch"; LOCK = ROOT / "integration/alas/upstream-lock.json"; AUDIT = ROOT / "integration/alas/opsi-stronghold-source-only-audit.json"

def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(("git", "-C", str(repository), *arguments), check=True, capture_output=True, text=True, encoding="utf-8", timeout=60).stdout.rstrip("\r\n")

def verify_clean_upstream(upstream: Path) -> dict[str, object]:
    upstream = upstream.resolve(); commit = json.loads(LOCK.read_text(encoding="utf-8"))["commit"]
    if _git(upstream, "rev-parse", "HEAD").lower() != commit: raise RuntimeError("Stronghold audit upstream commit drifted")
    if _git(upstream, "status", "--porcelain", "--untracked-files=all"): raise RuntimeError("Stronghold audit upstream must be clean")
    source = audit_opsi_stronghold_source(upstream, AUDIT); parent = Path(tempfile.mkdtemp(prefix="alas-stronghold-audit-", dir=str(upstream.parent))); worktree = parent / "worktree"; registered = False
    try:
        _git(upstream, "worktree", "add", "--detach", str(worktree), commit); registered = True; _git(worktree, "apply", "--", str(PATCH.resolve()))
        return {**source, **verify_opsi_stronghold_headless_gate(worktree)}
    finally:
        if registered: _git(upstream, "worktree", "remove", "--force", str(worktree))
        shutil.rmtree(parent, ignore_errors=True)

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--upstream", type=Path, required=True); args = parser.parse_args(); print(json.dumps(verify_clean_upstream(args.upstream), ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
