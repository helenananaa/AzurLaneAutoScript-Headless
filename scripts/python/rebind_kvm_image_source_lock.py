#!/usr/bin/env python3
"""Rebind a KVM AOSP tree from one exact uncommitted patch set to another."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


def _load_source_lock_class():
    path = Path(__file__).resolve().parents[2] / "python" / "alas_headless" / (
        "android_kvm_source.py"
    )
    spec = importlib.util.spec_from_file_location("_android_kvm_source_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load KVM source lock contract: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.KvmImageSourceLock


KvmImageSourceLock = _load_source_lock_class()


SCHEMA = "alas-headless.kvm-source-lock-rebind/v1"


class KvmSourceRebindError(RuntimeError):
    pass


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _patch_identity(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            document["project_patches"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _git(project: Path, *arguments: str, env: Mapping[str, str] | None = None) -> str:
    return subprocess.check_output(
        ["git", "-C", str(project), *arguments],
        text=True,
        encoding="utf-8",
        env=env,
    ).strip()


def _run_git(project: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(project), *arguments], check=True)


def _load_old_lock(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise KvmSourceRebindError("old source lock must be an object")
    if value.get("schema") != "alas-headless.kvm-image-source-lock/v1":
        raise KvmSourceRebindError("old source lock schema differs")
    if value.get("backend") != "kvm":
        raise KvmSourceRebindError("old source lock backend differs")
    patches = value.get("project_patches")
    if not isinstance(patches, list) or not patches:
        raise KvmSourceRebindError("old source lock patch set is empty")
    return value


def _patch_map(document: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for raw in document["project_patches"]:
        if not isinstance(raw, Mapping):
            raise KvmSourceRebindError("project patch must be an object")
        project = str(raw.get("project", ""))
        digest = str(raw.get("sha256", ""))
        if not project or project in result:
            raise KvmSourceRebindError("project patches must target unique projects")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise KvmSourceRebindError("project patch digest is malformed")
        result[project] = raw
    return result


def _resolve_patch(
    spec: Mapping[str, Any], repository: Path, history: Path
) -> Path:
    expected = str(spec["sha256"])
    candidates = (
        repository / str(spec["path"]),
        history / (expected + ".patch"),
    )
    for candidate in candidates:
        if candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest() == expected:
            return candidate.resolve()
    raise KvmSourceRebindError(
        "patch payload is unavailable or has the wrong digest: " + str(spec["path"])
    )


def _touched_paths(project: Path, patch: Path) -> set[str]:
    output = _git(project, "apply", "--numstat", str(patch))
    paths = {
        line.split("\t", 2)[-1]
        for line in output.splitlines()
        if line.strip()
    }
    if not paths:
        raise KvmSourceRebindError("patch touches no paths: " + str(patch))
    return paths


def _tree_from_patch(project: Path, patch: Path | None, temporary_root: Path) -> str:
    descriptor, raw_index = tempfile.mkstemp(prefix="kvm-rebind-index-", dir=temporary_root)
    os.close(descriptor)
    index = Path(raw_index)
    index.unlink()
    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = str(index)
    try:
        _git(project, "read-tree", "HEAD", env=environment)
        if patch is not None:
            subprocess.run(
                ["git", "-C", str(project), "apply", "--cached", str(patch)],
                check=True,
                env=environment,
            )
        return _git(project, "write-tree", env=environment)
    finally:
        index.unlink(missing_ok=True)


def _working_tree(project: Path, paths: set[str], temporary_root: Path) -> str:
    descriptor, raw_index = tempfile.mkstemp(prefix="kvm-rebind-work-", dir=temporary_root)
    os.close(descriptor)
    index = Path(raw_index)
    index.unlink()
    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = str(index)
    try:
        _git(project, "read-tree", "HEAD", env=environment)
        subprocess.run(
            ["git", "-C", str(project), "add", "-A", "--", *sorted(paths)],
            check=True,
            env=environment,
        )
        return _git(project, "write-tree", env=environment)
    finally:
        index.unlink(missing_ok=True)


def _dirty_paths(project: Path) -> set[str]:
    tracked = _git(project, "diff", "--name-only", "HEAD").splitlines()
    untracked = _git(project, "ls-files", "--others", "--exclude-standard").splitlines()
    return {path for path in tracked + untracked if path}


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-source-lock", required=True, type=Path)
    parser.add_argument("--new-source-lock", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--history-root", required=True, type=Path)
    parser.add_argument("--source-marker", required=True, type=Path)
    parser.add_argument("--sync-marker", required=True, type=Path)
    parser.add_argument("--project-patch-marker", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    old = _load_old_lock(args.old_source_lock)
    new_lock = KvmImageSourceLock.from_path(args.new_source_lock)
    new = new_lock.document
    if old["platform"] != new["platform"]:
        raise KvmSourceRebindError("platform identity changed during patch rebind")
    old_sha = _canonical_sha256(old)
    marker_expectations = {
        args.source_marker: old_sha,
        args.sync_marker: old_sha,
        args.project_patch_marker: _patch_identity(old),
    }
    for marker, expected in marker_expectations.items():
        if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != expected:
            raise KvmSourceRebindError("existing KVM marker differs: " + str(marker))

    old_specs = _patch_map(old)
    new_specs = _patch_map(new)
    projects = sorted(set(old_specs) | set(new_specs))
    resolved: dict[str, tuple[Path | None, Path | None]] = {}
    temporary_root = args.output.parent

    # Preflight every project and both patch sets before mutating the first path.
    for project_name in projects:
        project = args.source_root / project_name
        if not project.is_dir():
            raise KvmSourceRebindError("AOSP project is unavailable: " + project_name)
        old_patch = (
            _resolve_patch(old_specs[project_name], args.repo_root, args.history_root)
            if project_name in old_specs
            else None
        )
        new_patch = (
            _resolve_patch(new_specs[project_name], args.repo_root, args.history_root)
            if project_name in new_specs
            else None
        )
        old_paths = _touched_paths(project, old_patch) if old_patch else set()
        dirty = _dirty_paths(project)
        if dirty - old_paths:
            raise KvmSourceRebindError(
                "project has changes outside the old patch: " + project_name
            )
        expected_old = _tree_from_patch(project, old_patch, temporary_root)
        actual = (
            _working_tree(project, old_paths, temporary_root)
            if old_paths
            else _git(project, "rev-parse", "HEAD^{tree}")
        )
        if actual != expected_old:
            raise KvmSourceRebindError(
                "project worktree is not the exact old patch: " + project_name
            )
        _tree_from_patch(project, new_patch, temporary_root)
        resolved[project_name] = (old_patch, new_patch)

    transitions: list[dict[str, Any]] = []
    try:
        for project_name in projects:
            project = args.source_root / project_name
            old_patch, new_patch = resolved[project_name]
            old_digest = old_specs.get(project_name, {}).get("sha256")
            new_digest = new_specs.get(project_name, {}).get("sha256")
            transition = {
                "project": project_name,
                "old_patch_sha256": old_digest,
                "new_patch_sha256": new_digest,
                "old_reversed": False,
                "new_applied": False,
            }
            transitions.append(transition)
            if old_digest == new_digest:
                continue
            if old_patch is not None:
                _run_git(project, "apply", "--reverse", str(old_patch))
                transition["old_reversed"] = True
            if new_patch is not None:
                _run_git(project, "apply", str(new_patch))
                transition["new_applied"] = True

        for transition in transitions:
            project_name = str(transition["project"])
            project = args.source_root / project_name
            new_patch = resolved[project_name][1]
            new_paths = _touched_paths(project, new_patch) if new_patch else set()
            dirty = _dirty_paths(project)
            if dirty - new_paths:
                raise KvmSourceRebindError(
                    "project has changes outside the new patch: " + project_name
                )
            expected = _tree_from_patch(project, new_patch, temporary_root)
            actual = (
                _working_tree(project, new_paths, temporary_root)
                if new_paths
                else _git(project, "rev-parse", "HEAD^{tree}")
            )
            if actual != expected:
                raise KvmSourceRebindError(
                    "project worktree is not the exact new patch: " + project_name
                )
    except BaseException:
        for transition in reversed(transitions):
            project_name = str(transition["project"])
            project = args.source_root / project_name
            old_patch, new_patch = resolved[project_name]
            if transition["new_applied"] and new_patch is not None:
                _run_git(project, "apply", "--reverse", str(new_patch))
            if transition["old_reversed"] and old_patch is not None:
                _run_git(project, "apply", str(old_patch))
        raise

    evidence = {
        "schema": SCHEMA,
        "outcome": "pass",
        "old_source_lock_sha256": old_sha,
        "new_source_lock_sha256": new_lock.sha256,
        "platform": dict(new["platform"]),
        "projects": transitions,
        "source_content_changed": True,
        "alas_workload_used": False,
    }
    _atomic_text(args.project_patch_marker, _patch_identity(new) + "\n")
    _atomic_text(args.sync_marker, new_lock.sha256 + "\n")
    _atomic_text(args.source_marker, new_lock.sha256 + "\n")
    _atomic_text(
        args.output, json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
