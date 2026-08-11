#!/usr/bin/env python3
"""Build a deterministic, source-only ALAS adapter baseline inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alas-headless.adapter-baseline/v1"
UPSTREAM_LOCK_SCHEMA = "alas-headless.alas-upstream-lock/v1"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SEMANTIC_ENV_PATTERN = re.compile(r"\bALAS_SEMANTIC_[A-Z0-9_]+\b")
WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
ISO_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
FORBIDDEN_VOLATILE_KEYS = frozenset(
    {
        "captured_at",
        "captured_at_utc",
        "created_at",
        "dirty",
        "git_status",
        "timestamp",
        "updated_at",
        "working_tree",
    }
)
TOP_LEVEL_KEYS = frozenset(
    {
        "schema",
        "core_commit",
        "upstream_alas_commit",
        "source_metrics",
        "integration_patch",
        "semantic_environment_variables",
        "public_adapter_methods",
        "combat_coverage",
        "artifact_sha256",
    }
)
COVERAGE_KEYS = frozenset(
    {
        "canonical_resources",
        "canonical_qualified_resources",
        "defensive_resources",
        "defensive_qualified_resources",
        "actions",
        "qualified_actions",
        "blockers",
        "qualified_blockers",
        "branch_review_complete",
        "blocker_review_complete",
        "fleet_stats_qualified",
        "production_ready",
    }
)


class AdapterBaselineError(RuntimeError):
    """The source inventory cannot be produced safely or deterministically."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AdapterBaselineError("cannot read required baseline source") from exc


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise AdapterBaselineError("baseline JSON is malformed") from exc
    if not isinstance(value, dict):
        raise AdapterBaselineError("baseline JSON root must be an object")
    return value


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdapterBaselineError("cannot inspect baseline Git repository") from exc
    return completed.stdout.strip()


def require_clean_repository(root: Path) -> str:
    commit = _git(root, "rev-parse", "HEAD").lower()
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise AdapterBaselineError("baseline Git commit is malformed")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise AdapterBaselineError("baseline Git repository must be clean")
    return commit


def tracked_source_paths(root: Path) -> tuple[Path, ...]:
    output = _git(root, "ls-files", "--", "*.py", "*.patch")
    paths = []
    for value in output.splitlines():
        normalized = PurePosixPath(value)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise AdapterBaselineError("tracked baseline path is unsafe")
        path = root.joinpath(*normalized.parts)
        if not path.is_file():
            raise AdapterBaselineError("tracked baseline source is missing")
        paths.append(path)
    if not paths:
        raise AdapterBaselineError("tracked baseline source set is empty")
    return tuple(sorted(paths, key=lambda item: item.relative_to(root).as_posix()))


def _parse_python(path: Path) -> tuple[str, ast.Module]:
    source = _read_text(path)
    try:
        tree = ast.parse(source, filename=path.name)
    except SyntaxError as exc:
        raise AdapterBaselineError("baseline Python source is malformed") from exc
    return source, tree


def _class_methods(tree: ast.Module, class_name: str) -> tuple[str, ...]:
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(matches) != 1:
        raise AdapterBaselineError("required adapter class is missing or duplicated")
    return tuple(
        sorted(
            node.name
            for node in matches[0].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        )
    )


def _method_count(tree: ast.Module) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and isinstance(getattr(node, "col_offset", None), int)
        and node.col_offset > 0
    )


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    matches = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            matches.append(node.value)
    if len(matches) != 1:
        raise AdapterBaselineError("required combat source constant is missing")
    try:
        return ast.literal_eval(matches[0])
    except (ValueError, TypeError) as exc:
        raise AdapterBaselineError("combat source constant is not literal") from exc


def _qualified_mapping(mapping: Mapping[str, Any]) -> bool:
    selectors = mapping.get("selectors")
    evidence = mapping.get("evidence_sha256")
    return (
        isinstance(selectors, list)
        and bool(selectors)
        and isinstance(evidence, str)
        and SHA256_PATTERN.fullmatch(evidence) is not None
    )


def _qualified_action(mapping: Mapping[str, Any]) -> bool:
    variants = mapping.get("variants")
    if isinstance(variants, list) and variants:
        return all(
            isinstance(variant, dict) and _qualified_mapping(variant)
            for variant in variants
        )
    return _qualified_mapping(mapping)


def _combat_coverage(root: Path) -> Mapping[str, Any]:
    manifest_path = root / "integration" / "alas" / "combat-observer-manifest.json"
    manifest = _read_json(manifest_path)
    state_replay_path = root / "python" / "alas_headless" / "alas_combat_state_replay.py"
    _, replay_tree = _parse_python(state_replay_path)
    canonical = _literal_assignment(replay_tree, "ALAS_COMBAT_REPLAY_RESOURCE_NAMES")
    if (
        not isinstance(canonical, tuple)
        or not canonical
        or any(not isinstance(name, str) or not name for name in canonical)
        or len(set(canonical)) != len(canonical)
    ):
        raise AdapterBaselineError("canonical combat resource surface is malformed")

    resources = manifest.get("resources")
    actions = manifest.get("actions")
    blockers = manifest.get("blockers")
    fleet_stats = manifest.get("fleet_stats")
    if not all(isinstance(items, list) for items in (resources, actions, blockers)):
        raise AdapterBaselineError("combat coverage lists are malformed")
    if any(
        not isinstance(item, dict)
        for items in (resources, actions, blockers)
        for item in items
    ):
        raise AdapterBaselineError("combat coverage entries are malformed")
    if not isinstance(fleet_stats, dict):
        raise AdapterBaselineError("combat fleet-stat coverage is malformed")

    resource_names = [item.get("resource_name") for item in resources]
    action_names = [item.get("action_name") for item in actions]
    blocker_names = [item.get("blocker_name") for item in blockers]
    for names in (resource_names, action_names, blocker_names):
        if any(not isinstance(name, str) or not name for name in names):
            raise AdapterBaselineError("combat coverage identity is malformed")
        if len(names) != len(set(names)):
            raise AdapterBaselineError("combat coverage identity is duplicated")
    if not set(canonical).issubset(resource_names):
        raise AdapterBaselineError("canonical combat coverage is incomplete")

    qualified_resources = {
        item["resource_name"] for item in resources if _qualified_mapping(item)
    }
    qualified_actions = sum(_qualified_action(item) for item in actions)
    qualified_blockers = sum(_qualified_mapping(item) for item in blockers)
    hp_images = fleet_stats.get("hp_images")
    level_texts = fleet_stats.get("level_texts")
    stats_evidence = fleet_stats.get("evidence_sha256")
    fleet_stats_qualified = (
        isinstance(hp_images, list)
        and len(hp_images) == 6
        and isinstance(level_texts, list)
        and len(level_texts) == 6
        and isinstance(stats_evidence, str)
        and SHA256_PATTERN.fullmatch(stats_evidence) is not None
    )
    branch_review_complete = manifest.get("branch_review_complete") is True
    blocker_review_complete = manifest.get("blocker_review_complete") is True
    production_ready = (
        len(qualified_resources) == len(resources)
        and qualified_actions == len(actions)
        and branch_review_complete
        and blocker_review_complete
        and bool(blockers)
        and qualified_blockers == len(blockers)
        and fleet_stats_qualified
    )
    return {
        "canonical_resources": len(canonical),
        "canonical_qualified_resources": len(set(canonical) & qualified_resources),
        "defensive_resources": len(resources),
        "defensive_qualified_resources": len(qualified_resources),
        "actions": len(actions),
        "qualified_actions": qualified_actions,
        "blockers": len(blockers),
        "qualified_blockers": qualified_blockers,
        "branch_review_complete": branch_review_complete,
        "blocker_review_complete": blocker_review_complete,
        "fleet_stats_qualified": fleet_stats_qualified,
        "production_ready": production_ready,
    }


def _patch_metrics(path: Path) -> Mapping[str, Any]:
    source = _read_text(path)
    changed_files = []
    for line in source.splitlines():
        if not line.startswith("diff --git a/"):
            continue
        parts = line.split()
        if len(parts) != 4 or not parts[2].startswith("a/") or not parts[3].startswith("b/"):
            raise AdapterBaselineError("integration patch header is malformed")
        old_path = parts[2][2:]
        new_path = parts[3][2:]
        if old_path != new_path or not old_path or old_path.startswith("/"):
            raise AdapterBaselineError("integration patch target is unsafe")
        changed_files.append(old_path)
    if not changed_files or len(changed_files) != len(set(changed_files)):
        raise AdapterBaselineError("integration patch file surface is malformed")
    return {
        "changed_file_count": len(changed_files),
        "line_count": len(source.splitlines()),
    }


def _semantic_environment_variables(paths: Iterable[Path]) -> tuple[str, ...]:
    names = set()
    for path in paths:
        names.update(SEMANTIC_ENV_PATTERN.findall(_read_text(path)))
    return tuple(sorted(names))


def _upstream_commit(root: Path) -> str:
    value = _read_json(root / "integration" / "alas" / "upstream-lock.json")
    if set(value) != {"schema", "commit"}:
        raise AdapterBaselineError("upstream lock fields are not exact")
    if value["schema"] != UPSTREAM_LOCK_SCHEMA:
        raise AdapterBaselineError("upstream lock schema is unsupported")
    commit = value["commit"]
    if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
        raise AdapterBaselineError("pinned upstream commit is malformed")
    return commit


def collect_baseline(
    root: Path,
    *,
    core_commit: str,
    tracked_paths: Sequence[Path] | None = None,
) -> Mapping[str, Any]:
    if COMMIT_PATTERN.fullmatch(core_commit) is None:
        raise AdapterBaselineError("core commit is malformed")
    adapter_path = root / "python" / "alas_headless" / "alas_adapter.py"
    oracle_path = root / "python" / "alas_headless" / "semantic_oracle.py"
    patch_path = root / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
    manifest_path = root / "integration" / "alas" / "combat-observer-manifest.json"
    adapter_source, adapter_tree = _parse_python(adapter_path)
    oracle_source, oracle_tree = _parse_python(oracle_path)
    sources = tuple(tracked_paths) if tracked_paths is not None else tracked_source_paths(root)
    document = {
        "schema": SCHEMA,
        "core_commit": core_commit,
        "upstream_alas_commit": _upstream_commit(root),
        "source_metrics": {
            "alas_adapter": {
                "line_count": len(adapter_source.splitlines()),
                "method_count": _method_count(adapter_tree),
            },
            "semantic_oracle": {
                "line_count": len(oracle_source.splitlines()),
                "method_count": _method_count(oracle_tree),
            },
        },
        "integration_patch": _patch_metrics(patch_path),
        "semantic_environment_variables": list(_semantic_environment_variables(sources)),
        "public_adapter_methods": {
            "AlasSemanticAdapter": list(_class_methods(adapter_tree, "AlasSemanticAdapter")),
            "AlasSemanticSession": list(_class_methods(adapter_tree, "AlasSemanticSession")),
        },
        "combat_coverage": _combat_coverage(root),
        "artifact_sha256": {
            "combat_observer_manifest": _sha256(manifest_path),
            "integration_patch": _sha256(patch_path),
        },
    }
    validate_baseline_document(document)
    return document


def _validate_nonvolatile(value: Any, *, key: str = "") -> None:
    if key.lower() in FORBIDDEN_VOLATILE_KEYS:
        raise AdapterBaselineError("baseline document contains volatile fields")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if not isinstance(child_key, str):
                raise AdapterBaselineError("baseline document key is malformed")
            _validate_nonvolatile(child_value, key=child_key)
    elif isinstance(value, list):
        for child in value:
            _validate_nonvolatile(child, key=key)
    elif isinstance(value, str):
        if WINDOWS_ABSOLUTE_PATTERN.match(value) or value.startswith(("/", "\\\\")):
            raise AdapterBaselineError("baseline document contains an absolute path")
        if ISO_TIMESTAMP_PATTERN.fullmatch(value):
            raise AdapterBaselineError("baseline document contains a timestamp")


def validate_baseline_document(document: Mapping[str, Any]) -> None:
    if not isinstance(document, dict) or set(document) != TOP_LEVEL_KEYS:
        raise AdapterBaselineError("baseline document fields are not exact")
    if document.get("schema") != SCHEMA:
        raise AdapterBaselineError("baseline document schema is unsupported")
    for field in ("core_commit", "upstream_alas_commit"):
        value = document.get(field)
        if not isinstance(value, str) or COMMIT_PATTERN.fullmatch(value) is None:
            raise AdapterBaselineError("baseline identity is malformed")
    coverage = document.get("combat_coverage")
    if not isinstance(coverage, dict) or set(coverage) != COVERAGE_KEYS:
        raise AdapterBaselineError("combat coverage fields are not exact")
    for qualified, total in (
        ("canonical_qualified_resources", "canonical_resources"),
        ("defensive_qualified_resources", "defensive_resources"),
        ("qualified_actions", "actions"),
        ("qualified_blockers", "blockers"),
    ):
        qualified_value = coverage.get(qualified)
        total_value = coverage.get(total)
        if (
            isinstance(qualified_value, bool)
            or not isinstance(qualified_value, int)
            or isinstance(total_value, bool)
            or not isinstance(total_value, int)
            or qualified_value < 0
            or total_value < 0
            or qualified_value > total_value
        ):
            raise AdapterBaselineError("combat coverage count is malformed")
    for field in (
        "branch_review_complete",
        "blocker_review_complete",
        "fleet_stats_qualified",
        "production_ready",
    ):
        if not isinstance(coverage.get(field), bool):
            raise AdapterBaselineError("combat coverage flag is malformed")
    _validate_nonvolatile(document)


def canonical_json(document: Mapping[str, Any]) -> str:
    validate_baseline_document(document)
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    ) + "\n"


def parse_args(argv: Sequence[str] = ()) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(list(argv) if argv else None)


def main(argv: Sequence[str] = ()) -> int:
    arguments = parse_args(argv)
    commit = require_clean_repository(ROOT)
    document = collect_baseline(ROOT, core_commit=commit)
    output = arguments.output.resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise AdapterBaselineError("baseline output must stay inside the repository") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(document), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
