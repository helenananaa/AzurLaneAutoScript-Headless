#!/usr/bin/env python3
"""Rebind an existing AOSP tree to newly content-addressed project patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Mapping, Sequence

from alas_headless.android_build_domain import AndroidBuildDomain
from alas_headless.android_image_source import AndroidImageSourceLock


SCHEMA = "alas-headless.android-image-project-patch-rebind/v1"


def canonical_sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def git(project: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    return subprocess.check_output(
        ["git", "-C", str(project), *args], text=True, encoding="utf-8", env=env
    ).strip()


def dirty_project_paths(project: Path) -> set[str]:
    paths = {
        line for line in git(project, "diff", "--name-only", "HEAD").splitlines()
        if line
    }
    paths.update(
        line for line in git(
            project, "ls-files", "--others", "--exclude-standard"
        ).splitlines() if line
    )
    return paths


def exact_patch_commit(
    project: Path,
    patch: Path,
    expected_metadata: Sequence[str],
    temporary_root: Path,
) -> str | None:
    """Find the exact locked patch commit in the current HEAD ancestry."""
    for commit in git(project, "rev-list", "HEAD").splitlines():
        metadata = git(
            project,
            "show",
            "-s",
            "--format=%an%n%ae%n%at%n%ct%n%s",
            commit,
        ).splitlines()
        if metadata != list(expected_metadata):
            continue
        with tempfile.TemporaryDirectory(dir=temporary_root) as raw:
            temporary = Path(raw)
            index_path = temporary / "index"
            work_tree = temporary / "worktree"
            normalized_patch = temporary / "locked.patch"
            work_tree.mkdir()
            normalized_patch.write_bytes(patch.read_bytes().replace(b"\r\n", b"\n"))
            index_env = dict(os.environ)
            index_env["GIT_INDEX_FILE"] = str(index_path)
            index_env["GIT_WORK_TREE"] = str(work_tree)
            try:
                parent = git(project, "rev-parse", commit + "^")
                subprocess.run(
                    ["git", "-C", str(project), "read-tree", parent],
                    check=True,
                    env=index_env,
                )
                subprocess.run(
                    [
                        "git", "-C", str(project), "-c", "core.autocrlf=false",
                        "apply", "--cached", str(normalized_patch),
                    ],
                    check=True,
                    env=index_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                patched_tree = git(project, "write-tree", env=index_env)
            except subprocess.CalledProcessError:
                continue
        if patched_tree == git(project, "rev-parse", commit + "^{tree}"):
            return commit
    return None


def _require_within(path: Path, root: Path, name: str) -> None:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"{name} must stay inside Redroid evidence_root")


def _main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, type=Path)
    parser.add_argument("--old-source-lock", required=True, type=Path)
    parser.add_argument("--new-source-lock", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--resolved-manifest", required=True, type=Path)
    parser.add_argument("--apply-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv))
    domain = AndroidBuildDomain.from_path(args.domain, expected_backend="redroid")
    args.source_root = Path(domain.path("source_root"))
    args.resume_marker = args.source_root / ".alas-redroid-build-source-lock"
    args.project_patch_marker = args.source_root / ".alas-project-patches-applied"
    evidence_root = Path(domain.path("evidence_root"))
    _require_within(args.apply_log, evidence_root, "--apply-log")
    _require_within(args.output, evidence_root, "--output")
    if args.output.exists():
        parser.error("--output must not already exist")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    old = json.loads(args.old_source_lock.read_text(encoding="utf-8"))
    new_lock = AndroidImageSourceLock.from_path(args.new_source_lock)
    new = dict(new_lock.document)
    old_sha256 = canonical_sha256(old)
    if args.resume_marker.read_text(encoding="utf-8").strip() != old_sha256:
        raise ValueError("resume marker does not match old source lock")
    old_comparable = dict(old)
    old_patches = list(old_comparable.pop("project_patches", []))
    new_comparable = dict(new)
    patches = list(new_comparable.pop("project_patches"))
    if old_comparable != new_comparable:
        raise ValueError("source identity changed outside project_patches")
    for old_patch in old_patches:
        if old_patch not in patches:
            raise ValueError(
                "existing project patch removal or mutation is unsupported: "
                + str(old_patch.get("path"))
            )

    resolved = {
        (item.get("name"), item.get("path")): item.get("revision")
        for item in ET.parse(args.resolved_manifest).getroot().findall("project")
    }
    for item in new["redroid"]["projects"] + new["redroid"]["webview_projects"]:
        if resolved.get((item["name"], item["path"])) != item["commit"]:
            raise ValueError("resolved manifest differs from source lock: " + item["path"])

    build = new["build"]
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": build["git_identity"]["name"],
        "GIT_AUTHOR_EMAIL": build["git_identity"]["email"],
        "GIT_COMMITTER_NAME": build["git_identity"]["name"],
        "GIT_COMMITTER_EMAIL": build["git_identity"]["email"],
        "GIT_AUTHOR_DATE": "@{0} +0000".format(build["source_date_epoch"]),
        "GIT_COMMITTER_DATE": "@{0} +0000".format(build["source_date_epoch"]),
    })
    project_results = []
    repo_root = args.repo_root.resolve()
    for item in patches:
        patch = (repo_root / item["path"]).resolve()
        if repo_root not in patch.parents:
            raise ValueError("project patch escapes repository")
        payload = patch.read_bytes()
        if hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise ValueError("project patch digest mismatch: " + item["path"])
        project = args.source_root / item["project"]
        status = git(project, "status", "--porcelain")
        forward = subprocess.run(
            ["git", "-C", str(project), "apply", "--check", str(patch)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        if status:
            if item in old_patches:
                raise ValueError(
                    "existing patched project is dirty before rebind: "
                    + item["project"]
                )
            touched_paths = {
                line.split("\t", 2)[2]
                for line in git(project, "apply", "--numstat", str(patch)).splitlines()
                if line.count("\t") >= 2
            }
            dirty_paths = dirty_project_paths(project)
            if not dirty_paths or not dirty_paths.issubset(touched_paths):
                raise ValueError(
                    "dirty project contains paths outside the new patch: "
                    + item["project"]
                )

            def index_tree(apply_patch: bool) -> str:
                with tempfile.NamedTemporaryFile(
                    dir=args.output.parent, delete=False
                ) as handle:
                    index_path = Path(handle.name)
                index_path.unlink()
                index_env = dict(os.environ)
                index_env["GIT_INDEX_FILE"] = str(index_path)
                try:
                    subprocess.run(
                        ["git", "-C", str(project), "read-tree", "HEAD"],
                        check=True, env=index_env,
                    )
                    if apply_patch:
                        subprocess.run(
                            ["git", "-C", str(project), "apply", "--cached", str(patch)],
                            check=True, env=index_env,
                        )
                    else:
                        subprocess.run(
                            ["git", "-C", str(project), "add", "-A", "--", *sorted(touched_paths)],
                            check=True, env=index_env,
                        )
                    return git(project, "write-tree", env=index_env)
                finally:
                    index_path.unlink(missing_ok=True)

            if index_tree(True) != index_tree(False):
                raise ValueError(
                    "dirty project is not the exact new patch: " + item["project"]
                )
            subprocess.run(
                ["git", "-C", str(project), "add", "-A", "--", *sorted(touched_paths)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(project), "commit", "-m", item["commit_message"]],
                check=True, env=env,
            )
            action = "adopted-exact-worktree"
        elif forward:
            subprocess.run(
                ["git", "-C", str(project), "apply", "--index", str(patch)], check=True
            )
            subprocess.run(
                ["git", "-C", str(project), "commit", "-m", item["commit_message"]],
                check=True, env=env,
            )
            action = "applied"
        else:
            expected = [
                build["git_identity"]["name"], build["git_identity"]["email"],
                str(build["source_date_epoch"]), str(build["source_date_epoch"]),
                item["commit_message"],
            ]
            matched_commit = exact_patch_commit(
                project, patch, expected, args.output.parent
            )
            # A later locked patch in the same project may overlap this patch's
            # context, making a reverse apply against HEAD fail even though the
            # exact patch commit is still an active ancestor. Reconstructing
            # the commit tree from its parent is the stronger identity check.
            if matched_commit is None:
                raise ValueError(
                    "project patch is neither applicable nor an exact active ancestor: "
                    + item["project"]
                )
            action = "verified-existing"
        result_head = (
            matched_commit if action == "verified-existing"
            else git(project, "rev-parse", "HEAD")
        )
        project_results.append({
            "project": item["project"], "patch_sha256": item["sha256"],
            "action": action, "head": result_head,
            "tree": git(project, "rev-parse", result_head + "^{tree}"),
        })

    patch_identity = hashlib.sha256(json.dumps(
        patches, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    lines = args.apply_log.read_text(encoding="utf-8").splitlines()
    for result in project_results:
        line = "process project: " + result["project"]
        if line not in lines:
            lines.append(line)
    atomic_text(args.apply_log, "\n".join(lines) + "\n")
    atomic_text(args.project_patch_marker, patch_identity + "\n")
    atomic_text(args.resume_marker, new_lock.sha256 + "\n")
    evidence = {
        "schema": SCHEMA, "outcome": "pass",
        "old_source_lock_sha256": old_sha256,
        "new_source_lock_sha256": new_lock.sha256,
        "change_scope": "content-addressed-project-patches-only",
        "projects": project_results,
        "source_content_changed": any(
            item["action"] in {"applied", "adopted-exact-worktree"}
            for item in project_results
        ),
        "alas_workload_used": False,
    }
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


def main(argv: Sequence[str] = ()) -> int:
    raw_args = list(argv) if argv else sys.argv[1:]
    return _main(raw_args)


if __name__ == "__main__":
    raise SystemExit(main())
