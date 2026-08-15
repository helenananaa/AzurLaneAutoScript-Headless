#!/usr/bin/env python3
"""Write deterministic Meowfficer configuration evidence from pinned ALAS."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from alas_headless.alas_meowfficer_config_replay import verify_meowfficer_config
PATCH = ROOT / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
LOCK = ROOT / "integration" / "alas" / "upstream-lock.json"

def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(("git", "-C", str(repository), *arguments), check=True, capture_output=True, text=True, encoding="utf-8", timeout=60).stdout.rstrip("\r\n")

def verify_clean_upstream(upstream: Path) -> dict[str, object]:
    upstream = upstream.resolve(); commit = json.loads(LOCK.read_text(encoding="utf-8"))["commit"]
    if _git(upstream, "rev-parse", "HEAD").lower() != commit: raise RuntimeError("Meowfficer replay upstream commit drifted")
    if _git(upstream, "status", "--porcelain", "--untracked-files=all"): raise RuntimeError("Meowfficer replay upstream must be clean")
    parent = Path(tempfile.mkdtemp(prefix="alas-meowfficer-verify-", dir=str(upstream.parent))); worktree = parent / "worktree"; result = parent / "result.json"; registered = False
    try:
        _git(upstream, "worktree", "add", "--detach", str(worktree), commit); registered = True; _git(worktree, "apply", "--", str(PATCH.resolve()))
        environment = os.environ.copy(); environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "python")))
        code = "import json,sys; from pathlib import Path; from alas_headless.alas_meowfficer_config_replay import verify_meowfficer_config; Path(sys.argv[2]).write_text(json.dumps(verify_meowfficer_config(Path(sys.argv[1]))),encoding='utf-8')"
        subprocess.run((sys.executable, "-c", code, str(worktree), str(result)), check=True, env=environment, timeout=120)
        return json.loads(result.read_text(encoding="utf-8"))
    finally:
        if registered: _git(upstream, "worktree", "remove", "--force", str(worktree))
        shutil.rmtree(parent, ignore_errors=True)

def main() -> int:
    parser = argparse.ArgumentParser(); source = parser.add_mutually_exclusive_group(required=True); source.add_argument("--alas-root", type=Path); source.add_argument("--upstream", type=Path); parser.add_argument("--output", type=Path); args = parser.parse_args()
    result = verify_clean_upstream(args.upstream) if args.upstream else verify_meowfficer_config(args.alas_root); text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text, encoding="utf-8")
    print(text, end=""); return 0
if __name__ == "__main__": raise SystemExit(main())
