#!/usr/bin/env python3
"""Verify the canonical ALAS patch in a disposable pinned worktree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    from .build_alas_patch_series import (
        AlasPatchSeriesError,
        check_generated_patch,
    )
except ImportError:  # Direct script execution.
    from build_alas_patch_series import (  # type: ignore[no-redef]
        AlasPatchSeriesError,
        check_generated_patch,
    )


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alas-headless.patch-tree-verification/v1"
UPSTREAM_LOCK_SCHEMA = "alas-headless.alas-upstream-lock/v1"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PATCH_HEADER_PATTERN = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
ALLOWED_PATCH_ROOTS = frozenset({"campaign", "module"})
CANONICAL_PATCH = ROOT / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
SERIES_MANIFEST = ROOT / "integration" / "alas" / "series" / "series.json"


class AlasPatchVerificationError(RuntimeError):
    """The pinned patch cannot be verified without weakening its boundary."""


def _require_authoritative_combined(patch: Path) -> None:
    if patch.resolve() != CANONICAL_PATCH.resolve():
        return
    try:
        check_generated_patch(SERIES_MANIFEST, CANONICAL_PATCH, root=ROOT)
    except AlasPatchSeriesError as exc:
        raise AlasPatchVerificationError(
            "canonical combined patch differs from authoritative series"
        ) from exc


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: int = 60,
) -> str:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AlasPatchVerificationError("patch verification command failed") from exc
    return completed.stdout.rstrip("\r\n")


def _git(repository: Path, *arguments: str, timeout_seconds: int = 60) -> str:
    return _run(
        ("git", "-C", str(repository), *arguments),
        timeout_seconds=timeout_seconds,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AlasPatchVerificationError("cannot hash integration patch") from exc
    return digest.hexdigest()


def pinned_upstream_commit(root: Path = ROOT) -> str:
    path = root / "integration" / "alas" / "upstream-lock.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AlasPatchVerificationError("cannot read pinned upstream lock") from exc
    if not isinstance(value, dict) or set(value) != {"schema", "commit"}:
        raise AlasPatchVerificationError("pinned upstream lock fields are not exact")
    if value["schema"] != UPSTREAM_LOCK_SCHEMA:
        raise AlasPatchVerificationError("pinned upstream lock schema is unsupported")
    commit = value["commit"]
    if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
        raise AlasPatchVerificationError("pinned upstream commit is malformed")
    return commit


def parse_patch_paths(patch: Path) -> tuple[str, ...]:
    try:
        lines = patch.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise AlasPatchVerificationError("cannot read integration patch") from exc
    paths = []
    for line in lines:
        if not line.startswith("diff --git "):
            continue
        match = PATCH_HEADER_PATTERN.fullmatch(line)
        if match is None or match.group(1) != match.group(2):
            raise AlasPatchVerificationError("integration patch header is malformed")
        raw_path = match.group(1)
        normalized = PurePosixPath(raw_path)
        if (
            normalized.is_absolute()
            or ".." in normalized.parts
            or not normalized.parts
            or normalized.parts[0] not in ALLOWED_PATCH_ROOTS
            or normalized.suffix != ".py"
        ):
            raise AlasPatchVerificationError("integration patch path is not allowlisted")
        paths.append(normalized.as_posix())
    if not paths:
        raise AlasPatchVerificationError("integration patch has no changed files")
    if len(paths) != len(set(paths)):
        raise AlasPatchVerificationError("integration patch has duplicate changed files")
    return tuple(paths)


def inspect_upstream(upstream: Path, *, expected_commit: str) -> None:
    if not upstream.is_dir() or not (upstream / ".git").exists():
        raise AlasPatchVerificationError("upstream is not a Git working tree")
    if COMMIT_PATTERN.fullmatch(expected_commit) is None:
        raise AlasPatchVerificationError("expected upstream commit is malformed")
    head = _git(upstream, "rev-parse", "HEAD").lower()
    if head != expected_commit:
        raise AlasPatchVerificationError("upstream HEAD does not match pinned commit")
    status = _git(upstream, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise AlasPatchVerificationError("upstream working tree must be clean")


def check_patch_applies(upstream: Path, patch: Path) -> None:
    try:
        subprocess.run(
            (
                "git",
                "-C",
                str(upstream),
                "apply",
                "--check",
                "--",
                str(patch.resolve()),
            ),
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AlasPatchVerificationError("integration patch does not apply cleanly") from exc


def _result_document(
    *,
    expected_commit: str,
    patch_sha256: str,
    changed_files: Sequence[str],
    plan_only: bool,
    patch_applied: bool,
    compiled_python_files: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "schema": SCHEMA,
        "upstream_commit": expected_commit,
        "patch_sha256": patch_sha256,
        "changed_files": list(changed_files),
        "plan_only": plan_only,
        "patch_applied": patch_applied,
        "compiled_python_files": list(compiled_python_files),
    }


def canonical_json(document: Mapping[str, Any]) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    ) + "\n"


def plan_patch_verification(
    upstream: Path,
    patch: Path,
    *,
    expected_commit: str,
) -> Mapping[str, Any]:
    changed_files = parse_patch_paths(patch)
    _require_authoritative_combined(patch)
    inspect_upstream(upstream, expected_commit=expected_commit)
    check_patch_applies(upstream, patch)
    return _result_document(
        expected_commit=expected_commit,
        patch_sha256=_sha256(patch),
        changed_files=changed_files,
        plan_only=True,
        patch_applied=False,
        compiled_python_files=(),
    )


def _compile_patched_files(worktree: Path, changed_files: Sequence[str]) -> None:
    targets = [str(worktree.joinpath(*PurePosixPath(path).parts)) for path in changed_files]
    _run(
        (sys.executable, "-m", "py_compile", *targets),
        cwd=worktree,
        timeout_seconds=120,
    )


def execute_patch_verification(
    upstream: Path,
    patch: Path,
    output: Path,
    *,
    expected_commit: str,
) -> Mapping[str, Any]:
    if output.exists():
        raise AlasPatchVerificationError("verification output directory already exists")
    changed_files = parse_patch_paths(patch)
    _require_authoritative_combined(patch)
    inspect_upstream(upstream, expected_commit=expected_commit)
    check_patch_applies(upstream, patch)
    patch_sha256 = _sha256(patch)
    temporary_parent = Path(
        tempfile.mkdtemp(prefix="alas-patch-verify-", dir=str(upstream.parent))
    )
    disposable = temporary_parent / "worktree"
    registered = False
    try:
        _git(upstream, "worktree", "add", "--detach", str(disposable), expected_commit)
        registered = True
        _git(disposable, "apply", "--", str(patch.resolve()))
        _compile_patched_files(disposable, changed_files)
        status = _git(disposable, "status", "--porcelain", "--untracked-files=all")
        changed_status_paths = []
        for line in status.splitlines():
            if len(line) <= 3:
                raise AlasPatchVerificationError("patched worktree status is malformed")
            path = line[3:].replace("\\", "/")
            parts = PurePosixPath(path).parts
            if "__pycache__" in parts or path.endswith(".pyc"):
                continue
            changed_status_paths.append(path)
        changed_status_paths = tuple(sorted(changed_status_paths))
        if changed_status_paths != tuple(sorted(changed_files)):
            raise AlasPatchVerificationError(
                "patched worktree file surface changed: {0}".format(
                    ",".join(changed_status_paths)
                )
            )
        document = _result_document(
            expected_commit=expected_commit,
            patch_sha256=patch_sha256,
            changed_files=changed_files,
            plan_only=False,
            patch_applied=True,
            compiled_python_files=changed_files,
        )
    finally:
        if registered:
            try:
                _git(upstream, "worktree", "remove", "--force", str(disposable))
            except AlasPatchVerificationError:
                _git(upstream, "worktree", "prune")
                raise
        shutil.rmtree(temporary_parent, ignore_errors=True)

    try:
        output.mkdir(parents=True, exist_ok=False)
        (output / "result.json").write_text(
            canonical_json(document),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise AlasPatchVerificationError("cannot write verification result") from exc
    return document


def parse_args(argv: Sequence[str] = ()) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--patch", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(list(argv) if argv else None)
    if arguments.execute and arguments.output is None:
        parser.error("--execute requires --output")
    if arguments.plan and arguments.output is not None:
        parser.error("--plan does not accept --output")
    return arguments


def main(argv: Sequence[str] = ()) -> int:
    arguments = parse_args(argv)
    expected_commit = pinned_upstream_commit()
    upstream = arguments.upstream.resolve()
    patch = arguments.patch.resolve()
    if arguments.plan:
        result = plan_patch_verification(
            upstream,
            patch,
            expected_commit=expected_commit,
        )
    else:
        output = arguments.output.resolve()
        result = execute_patch_verification(
            upstream,
            patch,
            output,
            expected_commit=expected_commit,
        )
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
