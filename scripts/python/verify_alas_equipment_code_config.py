#!/usr/bin/env python3
"""Verify EquipmentCode configuration from a patched ALAS tree."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless.alas_equipment_code_config_replay import verify_equipment_code_config


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


def verify_clean_upstream(upstream: Path) -> dict[str, object]:
    upstream = upstream.resolve()
    commit = json.loads(LOCK.read_text(encoding="utf-8"))["commit"]
    if _git(upstream, "rev-parse", "HEAD").lower() != commit:
        raise RuntimeError("EquipmentCode replay upstream commit drifted")
    if _git(upstream, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("EquipmentCode replay upstream must be clean")
    parent = Path(tempfile.mkdtemp(prefix="alas-equipment-code-verify-", dir=str(upstream.parent)))
    disposable = parent / "worktree"
    result_path = parent / "result.json"
    registered = False
    try:
        _git(upstream, "worktree", "add", "--detach", str(disposable), commit)
        registered = True
        _git(disposable, "apply", "--", str(PATCH.resolve()))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "python")))
        code = (
            "import json,sys; from pathlib import Path; "
            "from alas_headless.alas_equipment_code_config_replay import verify_equipment_code_config; "
            "Path(sys.argv[2]).write_text(json.dumps(verify_equipment_code_config(Path(sys.argv[1]))), encoding='utf-8')"
        )
        subprocess.run(
            (sys.executable, "-c", code, str(disposable), str(result_path)),
            check=True,
            env=environment,
            timeout=120,
        )
        return json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        if registered:
            _git(upstream, "worktree", "remove", "--force", str(disposable))
        shutil.rmtree(parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--alas-root", type=Path)
    source.add_argument("--upstream", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = (
        verify_clean_upstream(arguments.upstream)
        if arguments.upstream is not None
        else verify_equipment_code_config(arguments.alas_root)
    )
    text = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
