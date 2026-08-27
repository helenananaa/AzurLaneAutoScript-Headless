"""Backend-owned Android build-domain contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping


BUILD_DOMAIN_SCHEMA = "alas-headless.android-build-domain/v3"
BUILD_DOMAIN_BACKENDS = ("kvm", "redroid")
PATH_FIELDS = (
    "source_root",
    "repo_metadata_root",
    "output_root",
    "ccache_root",
    "build_home",
    "temp_root",
    "runtime_root",
    "archive_root",
    "evidence_root",
    "apk_archive",
)


class AndroidBuildDomainError(ValueError):
    """Raised when a backend build domain is malformed or overlaps unsafely."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AndroidBuildDomainError(f"{name} must be an object")
    return value


def _path(value: Any, name: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.startswith("/"):
        raise AndroidBuildDomainError(f"{name} must be an absolute POSIX path")
    path = PurePosixPath(value)
    if path == PurePosixPath("/"):
        raise AndroidBuildDomainError(f"{name} must not be the filesystem root")
    if ".." in path.parts or str(path) != value.rstrip("/"):
        raise AndroidBuildDomainError(f"{name} must be normalized")
    return path


def _overlaps(first: PurePosixPath, second: PurePosixPath) -> bool:
    return first == second or first in second.parents or second in first.parents


def _under(path: PurePosixPath, root: str) -> bool:
    parent = PurePosixPath(root)
    return path == parent or parent in path.parents


def _require_owned_path(backend: str, name: str, path: PurePosixPath) -> None:
    domain_root = f"/srv/android-build/{backend}"
    if not _under(path, domain_root):
        raise AndroidBuildDomainError(
            f"paths.{name} must stay under {domain_root}"
        )


@dataclass(frozen=True)
class AndroidBuildDomain:
    document: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        expected_backend: str | None = None,
    ) -> "AndroidBuildDomain":
        if not isinstance(value, Mapping):
            raise AndroidBuildDomainError("build domain must be an object")
        document = json.loads(json.dumps(value))
        if set(document) != {"schema", "backend", "paths"}:
            raise AndroidBuildDomainError("build domain fields differ")
        if document.get("schema") != BUILD_DOMAIN_SCHEMA:
            raise AndroidBuildDomainError("build domain schema mismatch")

        backend = document.get("backend")
        if backend not in BUILD_DOMAIN_BACKENDS:
            raise AndroidBuildDomainError("build domain backend must be kvm or redroid")
        if expected_backend is not None and backend != expected_backend:
            raise AndroidBuildDomainError(
                f"build domain backend must be {expected_backend}"
            )

        paths = _mapping(document.get("paths"), "paths")
        if set(paths) != set(PATH_FIELDS):
            raise AndroidBuildDomainError("build domain path fields differ")
        parsed_paths = {
            name: _path(paths[name], f"paths.{name}") for name in PATH_FIELDS
        }
        for name, path in parsed_paths.items():
            _require_owned_path(str(backend), name, path)
        path_items = list(parsed_paths.items())
        for index, (first_name, first_path) in enumerate(path_items):
            for second_name, second_path in path_items[index + 1 :]:
                if _overlaps(first_path, second_path):
                    raise AndroidBuildDomainError(
                        "build domain paths must not overlap: "
                        f"{first_name}, {second_name}"
                    )

        canonical = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return cls(
            document=MappingProxyType(document),
            sha256=hashlib.sha256(canonical).hexdigest(),
        )

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        expected_backend: str | None = None,
    ) -> "AndroidBuildDomain":
        return cls.from_mapping(
            json.loads(path.read_text(encoding="utf-8")),
            expected_backend=expected_backend,
        )

    def path(self, name: str) -> str:
        if name not in PATH_FIELDS:
            raise KeyError(name)
        return str(self.document["paths"][name])

def require_isolated_domain_pair(
    first: AndroidBuildDomain, second: AndroidBuildDomain
) -> None:
    """Require every Redroid and KVM mutable path to be disjoint."""

    backends = {first.document["backend"], second.document["backend"]}
    if backends != set(BUILD_DOMAIN_BACKENDS):
        raise AndroidBuildDomainError(
            "domain pair must contain exactly redroid and kvm"
        )
    first_owned = {
        f"paths.{name}": PurePosixPath(first.path(name)) for name in PATH_FIELDS
    }
    second_owned = {
        f"paths.{name}": PurePosixPath(second.path(name)) for name in PATH_FIELDS
    }
    for first_name, first_path in first_owned.items():
        for second_name, second_path in second_owned.items():
            if _overlaps(first_path, second_path):
                raise AndroidBuildDomainError(
                    "backend domains must not overlap: "
                    f"{first.document['backend']}.{first_name}, "
                    f"{second.document['backend']}.{second_name}"
                )
