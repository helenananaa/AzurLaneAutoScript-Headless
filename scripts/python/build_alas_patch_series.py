#!/usr/bin/env python3
"""Build the canonical ALAS integration patch from an ordered manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alas-headless.alas-patch-series/v1"
LOCK_SCHEMA = "alas-headless.alas-upstream-lock/v1"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TOP_LEVEL_KEYS = frozenset(("schema", "upstream_commit", "members"))
MEMBER_KEYS = frozenset(("order", "path", "sha256"))


class AlasPatchSeriesError(RuntimeError):
    """The patch series is malformed or cannot be built deterministically."""


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    ) + "\n"


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AlasPatchSeriesError(label + " is not readable canonical JSON") from exc
    if not isinstance(value, dict):
        raise AlasPatchSeriesError(label + " root must be an object")
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _member_path(root: Path, value: Any) -> Tuple[str, Path]:
    if not isinstance(value, str) or not value:
        raise AlasPatchSeriesError("patch member path is missing")
    if "\\" in value:
        raise AlasPatchSeriesError("patch member path must use POSIX separators")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise AlasPatchSeriesError("patch member path is unsafe")
    if pure.suffix != ".patch" or pure.parts[:2] != ("integration", "alas"):
        raise AlasPatchSeriesError("patch member path is outside integration/alas")
    root_resolved = root.resolve()
    resolved = root.joinpath(*pure.parts).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise AlasPatchSeriesError("patch member path escapes repository root") from exc
    return pure.as_posix(), resolved


def validate_manifest(
    manifest_path: Path,
    *,
    root: Path = ROOT,
) -> Tuple[str, Tuple[Tuple[int, str, str, Path, bytes], ...]]:
    document = _read_json(manifest_path, "patch series manifest")
    if set(document) != TOP_LEVEL_KEYS or document.get("schema") != SCHEMA:
        raise AlasPatchSeriesError("patch series manifest schema is unsupported")
    upstream_commit = document.get("upstream_commit")
    if (
        not isinstance(upstream_commit, str)
        or COMMIT_PATTERN.fullmatch(upstream_commit) is None
    ):
        raise AlasPatchSeriesError("patch series upstream commit is malformed")

    lock = _read_json(
        root / "integration" / "alas" / "upstream-lock.json",
        "upstream lock",
    )
    if set(lock) != {"schema", "commit"} or lock.get("schema") != LOCK_SCHEMA:
        raise AlasPatchSeriesError("upstream lock schema is unsupported")
    if lock.get("commit") != upstream_commit:
        raise AlasPatchSeriesError("patch series upstream commit differs from lock")

    raw_members = document.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise AlasPatchSeriesError("patch series must contain at least one member")
    members = []
    seen_paths = set()
    for expected_order, member in enumerate(raw_members, start=1):
        if not isinstance(member, dict) or set(member) != MEMBER_KEYS:
            raise AlasPatchSeriesError("patch series member shape is invalid")
        order = member.get("order")
        if isinstance(order, bool) or order != expected_order:
            raise AlasPatchSeriesError("patch series order must be consecutive")
        path_text, path = _member_path(root, member.get("path"))
        if path_text in seen_paths:
            raise AlasPatchSeriesError("patch series member path is duplicated")
        seen_paths.add(path_text)
        expected_sha256 = member.get("sha256")
        if (
            not isinstance(expected_sha256, str)
            or SHA256_PATTERN.fullmatch(expected_sha256) is None
        ):
            raise AlasPatchSeriesError("patch member SHA-256 is malformed")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise AlasPatchSeriesError("patch series member cannot be read") from exc
        if not data or not data.endswith(b"\n") or b"\r\n" in data:
            raise AlasPatchSeriesError("patch member must be non-empty LF-terminated bytes")
        if _sha256(data) != expected_sha256:
            raise AlasPatchSeriesError("patch member SHA-256 changed")
        members.append((order, path_text, expected_sha256, path, data))
    return upstream_commit, tuple(members)


def build_patch_series(
    manifest_path: Path,
    output_path: Path,
    *,
    root: Path = ROOT,
) -> Mapping[str, Any]:
    upstream_commit, members = validate_manifest(manifest_path, root=root)
    output = output_path.resolve()
    if output.exists():
        raise AlasPatchSeriesError("patch series output already exists")
    if output in {member[3].resolve() for member in members}:
        raise AlasPatchSeriesError("patch series output cannot overwrite a member")
    combined = b"".join(member[4] for member in members)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(combined)
    except OSError as exc:
        raise AlasPatchSeriesError("patch series output cannot be written") from exc
    return {
        "schema": "alas-headless.alas-patch-series-build/v1",
        "upstream_commit": upstream_commit,
        "member_count": len(members),
        "members": [member[1] for member in members],
        "byte_count": len(combined),
        "combined_sha256": _sha256(combined),
    }


def parse_args(argv: Sequence[str] = ()) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "series" / "series.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(list(argv) if argv else None)


def main(argv: Sequence[str] = ()) -> int:
    arguments = parse_args(argv)
    result = build_patch_series(arguments.manifest, arguments.output)
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
