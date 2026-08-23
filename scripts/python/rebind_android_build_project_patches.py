#!/usr/bin/env python3
"""Rebind an existing AOSP tree to newly content-addressed project patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Mapping, Sequence

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


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-source-lock", required=True, type=Path)
    parser.add_argument("--new-source-lock", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--resume-marker", required=True, type=Path)
    parser.add_argument("--project-patch-marker", required=True, type=Path)
    parser.add_argument("--resolved-manifest", required=True, type=Path)
    parser.add_argument("--apply-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    old = json.loads(args.old_source_lock.read_text(encoding="utf-8"))
    new_lock = AndroidImageSourceLock.from_path(args.new_source_lock)
    new = dict(new_lock.document)
    old_sha256 = canonical_sha256(old)
    if args.resume_marker.read_text(encoding="utf-8").strip() != old_sha256:
        raise ValueError("resume marker does not match old source lock")
    if old.get("project_patches") is not None:
        raise ValueError("old source lock already has project_patches")
    comparable = dict(new)
    patches = comparable.pop("project_patches")
    if old != comparable:
        raise ValueError("source identity changed outside project_patches")

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
        if git(project, "status", "--porcelain"):
            raise ValueError("project is dirty before rebind: " + item["project"])
        forward = subprocess.run(
            ["git", "-C", str(project), "apply", "--check", str(patch)], check=False
        ).returncode == 0
        if forward:
            subprocess.run(
                ["git", "-C", str(project), "apply", "--index", str(patch)], check=True
            )
            subprocess.run(
                ["git", "-C", str(project), "commit", "-m", item["commit_message"]],
                check=True, env=env,
            )
            action = "applied"
        else:
            reverse = subprocess.run(
                ["git", "-C", str(project), "apply", "--reverse", "--check", str(patch)],
                check=False,
            ).returncode == 0
            with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as handle:
                index_path = Path(handle.name)
            index_path.unlink()
            index_env = dict(os.environ)
            index_env["GIT_INDEX_FILE"] = str(index_path)
            try:
                subprocess.run(
                    ["git", "-C", str(project), "read-tree", "HEAD^"],
                    check=True, env=index_env,
                )
                subprocess.run(
                    ["git", "-C", str(project), "apply", "--cached", str(patch)],
                    check=True, env=index_env,
                )
                patched_tree = git(project, "write-tree", env=index_env)
            finally:
                index_path.unlink(missing_ok=True)
            if not reverse or patched_tree != git(project, "rev-parse", "HEAD^{tree}"):
                raise ValueError("project patch is neither applicable nor exact HEAD: " + item["project"])
            metadata = git(project, "show", "-s", "--format=%an%n%ae%n%at%n%ct%n%s").splitlines()
            expected = [
                build["git_identity"]["name"], build["git_identity"]["email"],
                str(build["source_date_epoch"]), str(build["source_date_epoch"]),
                item["commit_message"],
            ]
            if metadata != expected:
                raise ValueError("existing project patch commit identity differs")
            action = "verified-existing"
        project_results.append({
            "project": item["project"], "patch_sha256": item["sha256"],
            "action": action, "head": git(project, "rev-parse", "HEAD"),
            "tree": git(project, "rev-parse", "HEAD^{tree}"),
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
        "projects": project_results, "source_content_changed": True,
        "alas_workload_used": False,
    }
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
