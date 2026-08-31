"""Safe host preflight and output archive/restore for Android build domains.

The module deliberately owns no build logic.  It coordinates one explicitly
selected backend, validates that KVM and Redroid mutable state is disjoint, and
moves an inactive build output to or from its independently owned archive.
Destructive cleanup is confined to an exact, marked ``output_root``.  Operations
do not use advisory locks; stability is proven with activity probes and before/
after content manifests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from alas_headless.android_build_domain import (
    AndroidBuildDomain,
    require_isolated_domain_pair,
)


OWNER_SCHEMA = "alas-headless.android-build-domain-owner/v1"
SNAPSHOT_SCHEMA = "alas-headless.android-cold-output-snapshot/v1"
COLD_RECEIPT_SCHEMA = "alas-headless.android-cold-output-receipt/v1"
OWNER_MARKER = ".alas-android-build-domain-owner.json"
COLD_RECEIPT = ".alas-android-cold-output.json"
FILES_MANIFEST = "files.jsonl"
SNAPSHOT_MANIFEST = "snapshot-manifest.json"
SNAPSHOT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
ROOT_KINDS = {"output": "output_root", "archive": "archive_root"}
_STATE_NAMES = frozenset((OWNER_MARKER, COLD_RECEIPT))


class AndroidBuildDomainMigrationError(RuntimeError):
    """Raised when a host or output migration boundary is not proven."""


@dataclass(frozen=True)
class TreeManifest:
    entry_count: int
    file_count: int
    logical_bytes: int
    tree_sha256: str
    manifest_sha256: str


PathOverrides = Mapping[str, Path]
CopyTree = Callable[[Path, Path, frozenset[str]], None]
ActivityProbe = Callable[[Path], Sequence[str]]


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(_canonical_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _domain_path(
    domain: AndroidBuildDomain,
    kind: str,
    name: str,
    overrides: PathOverrides | None,
) -> Path:
    key = f"{kind}.{name}"
    if overrides is not None and key in overrides:
        return Path(overrides[key])
    if kind != "paths":
        raise AndroidBuildDomainMigrationError(f"unsupported domain field kind: {kind}")
    return Path(domain.path(name))


def _require_backend(domain: AndroidBuildDomain, backend: str) -> None:
    if backend not in ("kvm", "redroid"):
        raise AndroidBuildDomainMigrationError(
            "backend must be explicitly set to kvm or redroid"
        )
    if domain.document["backend"] != backend:
        raise AndroidBuildDomainMigrationError(
            f"domain belongs to {domain.document['backend']}, not {backend}"
        )


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve(strict=False)
    second = second.resolve(strict=False)
    return _is_within(first, second) or _is_within(second, first)


def _same_existing_object(first: Path, second: Path) -> bool:
    """Detect aliases such as bind mounts that lexical/realpath checks miss."""

    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _actual_domain_aliases(
    redroid: AndroidBuildDomain,
    kvm: AndroidBuildDomain,
    *,
    path_overrides: Mapping[str, PathOverrides] | None = None,
) -> list[Mapping[str, str]]:
    domains = {"redroid": redroid, "kvm": kvm}
    overrides = path_overrides or {}
    items = [
        (
            f"{backend}.{name}",
            _domain_path(domain, "paths", name, overrides.get(backend)),
        )
        for backend, domain in domains.items()
        for name in domain.document["paths"]
    ]
    aliases: list[Mapping[str, str]] = []
    for index, (first_name, first_path) in enumerate(items):
        for second_name, second_path in items[index + 1 :]:
            if _paths_overlap(first_path, second_path) or _same_existing_object(
                first_path, second_path
            ):
                aliases.append({"first": first_name, "second": second_name})
    return aliases


def require_actual_domain_pair_isolated(
    redroid: AndroidBuildDomain,
    kvm: AndroidBuildDomain,
    *,
    path_overrides: Mapping[str, PathOverrides] | None = None,
) -> None:
    """Reject existing path aliases, including same-inode bind mounts."""

    require_isolated_domain_pair(redroid, kvm)
    aliases = _actual_domain_aliases(
        redroid,
        kvm,
        path_overrides=path_overrides,
    )
    if aliases:
        first = aliases[0]
        raise AndroidBuildDomainMigrationError(
            "build-domain roots alias on this host: "
            f"{first['first']}, {first['second']}"
        )


def _require_narrow_root(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise AndroidBuildDomainMigrationError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=False)
    anchor = Path(resolved.anchor)
    if not resolved.anchor or resolved == anchor or len(resolved.parts) < 4:
        raise AndroidBuildDomainMigrationError(
            f"{label} is too broad for a managed root: {resolved}"
        )
    return resolved


def _require_backend_scoped_root(path: Path, backend: str, label: str) -> Path:
    resolved = _require_narrow_root(path, label)
    nearby_parts = resolved.parts[-3:]
    scoped = any(
        backend in re.split(r"[^a-z0-9]+", part.lower()) for part in nearby_parts
    )
    if not scoped:
        raise AndroidBuildDomainMigrationError(
            f"{label} must be backend-scoped near its leaf; refusing public parent: "
            f"{resolved}"
        )
    return resolved


def _owner_document(
    domain: AndroidBuildDomain, backend: str, root_kind: str
) -> Mapping[str, Any]:
    field = ROOT_KINDS[root_kind]
    canonical_root = domain.path(field)
    identity = {
        "backend": backend,
        "root_kind": root_kind,
        "canonical_root": canonical_root,
    }
    return {
        "schema": OWNER_SCHEMA,
        **identity,
        "domain_sha256": domain.sha256,
        "owner_sha256": hashlib.sha256(_canonical_bytes(identity)).hexdigest(),
    }


def initialize_owner_root(
    domain: AndroidBuildDomain,
    *,
    backend: str,
    root_kind: str,
    adopt_existing: bool = False,
    path_overrides: PathOverrides | None = None,
) -> Mapping[str, Any]:
    """Create an owner marker at one exact domain root.

    A non-empty existing directory is accepted only with ``adopt_existing``.
    The function never removes or rewrites payload data.
    """

    _require_backend(domain, backend)
    if root_kind not in ROOT_KINDS:
        raise AndroidBuildDomainMigrationError("root_kind must be output or archive")
    field = ROOT_KINDS[root_kind]
    root = _require_backend_scoped_root(
        _domain_path(domain, "paths", field, path_overrides), backend, field
    )
    expected = _owner_document(domain, backend, root_kind)
    marker = root / OWNER_MARKER
    if marker.exists():
        _require_owner(domain, backend, root_kind, root)
        return expected
    if root.exists():
        if not root.is_dir():
            raise AndroidBuildDomainMigrationError(f"{field} is not a directory")
        if any(root.iterdir()) and not adopt_existing:
            raise AndroidBuildDomainMigrationError(
                f"refusing to adopt non-empty {field} without --adopt-existing"
            )
    else:
        root.mkdir(parents=True)
    _atomic_json(marker, expected)
    return expected


def _require_owner(
    domain: AndroidBuildDomain,
    backend: str,
    root_kind: str,
    root: Path,
) -> Mapping[str, Any]:
    marker = root / OWNER_MARKER
    if not marker.is_file() or marker.is_symlink():
        raise AndroidBuildDomainMigrationError(
            f"{root_kind} root has no regular owner marker"
        )
    try:
        actual = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AndroidBuildDomainMigrationError("owner marker is unreadable") from exc
    expected = _owner_document(domain, backend, root_kind)
    if actual != expected:
        raise AndroidBuildDomainMigrationError(
            f"{root_kind} owner marker differs from the selected domain"
        )
    return actual


def _xattrs(path: Path, *, follow_symlinks: bool) -> list[Mapping[str, str]]:
    if not hasattr(os, "listxattr"):
        return []
    try:
        names = sorted(os.listxattr(path, follow_symlinks=follow_symlinks))
    except (OSError, TypeError, NotImplementedError):
        return []
    values = []
    for name in names:
        try:
            payload = os.getxattr(path, name, follow_symlinks=follow_symlinks)
        except (OSError, TypeError, NotImplementedError) as exc:
            raise AndroidBuildDomainMigrationError(
                f"cannot read xattr {name!r} from {path}"
            ) from exc
        values.append({"name": name, "sha256": hashlib.sha256(payload).hexdigest()})
    return values


def _file_sha256_stable(path: Path, before: os.stat_result) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat(follow_symlinks=False)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise AndroidBuildDomainMigrationError(f"file changed while hashing: {path}")
    return digest.hexdigest()


def _iter_tree_records(
    root: Path, *, skip_root_names: frozenset[str]
) -> Iterable[Mapping[str, Any]]:
    root = root.resolve()
    root_device = root.stat().st_dev
    for directory, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        directory_path = Path(directory)
        directory_names.sort()
        file_names.sort()
        if directory_path == root:
            directory_names[:] = [
                name for name in directory_names if name not in skip_root_names
            ]
            file_names = [name for name in file_names if name not in skip_root_names]

        traversed_directories = []
        for name in directory_names:
            path = directory_path / name
            relative = path.relative_to(root).as_posix()
            status = path.stat(follow_symlinks=False)
            if stat.S_ISLNK(status.st_mode):
                record: dict[str, Any] = {
                    "kind": "symlink",
                    "path": relative,
                    "target": os.readlink(path),
                    "mode": stat.S_IMODE(status.st_mode),
                    "mtime_ns": status.st_mtime_ns,
                }
                xattrs = _xattrs(path, follow_symlinks=False)
                if xattrs:
                    record["xattrs"] = xattrs
                yield record
                continue
            if not stat.S_ISDIR(status.st_mode):
                raise AndroidBuildDomainMigrationError(
                    f"unsupported output entry: {path}"
                )
            if status.st_dev != root_device:
                raise AndroidBuildDomainMigrationError(
                    f"nested filesystem is forbidden inside output_root: {path}"
                )
            traversed_directories.append(name)
            record = {
                "kind": "directory",
                "path": relative,
                "mode": stat.S_IMODE(status.st_mode),
            }
            xattrs = _xattrs(path, follow_symlinks=False)
            if xattrs:
                record["xattrs"] = xattrs
            yield record
        directory_names[:] = traversed_directories

        for name in file_names:
            path = directory_path / name
            relative = path.relative_to(root).as_posix()
            status = path.stat(follow_symlinks=False)
            if stat.S_ISLNK(status.st_mode):
                record = {
                    "kind": "symlink",
                    "path": relative,
                    "target": os.readlink(path),
                    "mode": stat.S_IMODE(status.st_mode),
                    "mtime_ns": status.st_mtime_ns,
                }
                xattrs = _xattrs(path, follow_symlinks=False)
                if xattrs:
                    record["xattrs"] = xattrs
                yield record
                continue
            if not stat.S_ISREG(status.st_mode):
                raise AndroidBuildDomainMigrationError(
                    f"special files are forbidden in inactive output: {path}"
                )
            record = {
                "kind": "file",
                "path": relative,
                "size": status.st_size,
                "mode": stat.S_IMODE(status.st_mode),
                "mtime_ns": status.st_mtime_ns,
                "sha256": _file_sha256_stable(path, status),
            }
            xattrs = _xattrs(path, follow_symlinks=False)
            if xattrs:
                record["xattrs"] = xattrs
            yield record


def write_tree_manifest(
    root: Path,
    output: Path,
    *,
    skip_root_names: frozenset[str] = frozenset(),
) -> TreeManifest:
    """Hash a tree into deterministic JSONL without following symlinks."""

    if not root.is_dir() or root.is_symlink():
        raise AndroidBuildDomainMigrationError(f"tree root is unavailable: {root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    entry_count = 0
    file_count = 0
    logical_bytes = 0
    with output.open("xb") as handle:
        for record in _iter_tree_records(root, skip_root_names=skip_root_names):
            line = _canonical_bytes(record) + b"\n"
            handle.write(line)
            digest.update(line)
            entry_count += 1
            if record["kind"] == "file":
                file_count += 1
                logical_bytes += int(record["size"])
        handle.flush()
        os.fsync(handle.fileno())
    return TreeManifest(
        entry_count=entry_count,
        file_count=file_count,
        logical_bytes=logical_bytes,
        tree_sha256=digest.hexdigest(),
        manifest_sha256=_sha256_file(output),
    )


def _same_tree(first: TreeManifest, second: TreeManifest) -> bool:
    return first == second


def _rsync_copy(source: Path, destination: Path, excludes: frozenset[str]) -> None:
    rsync = shutil.which("rsync")
    if rsync is None:
        raise AndroidBuildDomainMigrationError("rsync is required for output migration")
    destination.mkdir(parents=True, exist_ok=False)
    command = [
        rsync,
        "-aHAX",
        "--numeric-ids",
        "--sparse",
        "--protect-args",
    ]
    command.extend(f"--exclude=/{name}" for name in sorted(excludes))
    command.extend(("--", f"{source}/", f"{destination}/"))
    subprocess.run(command, check=True)


def active_output_users(root: Path) -> Sequence[str]:
    """Return Linux processes with an fd or mapping beneath ``root``."""

    if not sys.platform.startswith("linux") or not Path("/proc").is_dir():
        return ()
    root = root.resolve()
    owners: set[str] = set()
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        pid = process.name
        try:
            working_directory = Path(os.readlink(process / "cwd"))
        except OSError:
            working_directory = None
        if working_directory is not None and _is_within(working_directory, root):
            owners.add(f"pid={pid}:cwd")
        fd_root = process / "fd"
        try:
            descriptors = list(fd_root.iterdir())
        except OSError:
            descriptors = []
        for descriptor in descriptors:
            try:
                target = Path(os.readlink(descriptor).removesuffix(" (deleted)"))
            except OSError:
                continue
            if target.is_absolute() and _is_within(target, root):
                owners.add(f"pid={pid}:fd={descriptor.name}")
        try:
            mappings = (
                (process / "maps")
                .read_text(encoding="utf-8", errors="replace")
                .splitlines()
            )
        except OSError:
            mappings = []
        for line in mappings:
            fields = line.split(maxsplit=5)
            if len(fields) != 6 or not fields[5].startswith("/"):
                continue
            target = Path(fields[5].removesuffix(" (deleted)"))
            if _is_within(target, root):
                owners.add(f"pid={pid}:map")
                break
    return tuple(sorted(owners))


def _require_inactive(root: Path, probe: ActivityProbe) -> None:
    owners = tuple(probe(root))
    if owners:
        preview = ", ".join(owners[:8])
        raise AndroidBuildDomainMigrationError(
            f"output_root is active and cannot be migrated: {preview}"
        )


def _payload_names(root: Path) -> list[str]:
    return sorted(path.name for path in root.iterdir() if path.name not in _STATE_NAMES)


def _snapshot_manifest(path: Path) -> tuple[Mapping[str, Any], str]:
    manifest_path = path / SNAPSHOT_MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise AndroidBuildDomainMigrationError("cold snapshot is incomplete")
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AndroidBuildDomainMigrationError(
            "snapshot manifest is unreadable"
        ) from exc
    return value, _sha256_file(manifest_path)


def archive_output(
    domain: AndroidBuildDomain,
    *,
    backend: str,
    snapshot_id: str,
    evict: bool = False,
    path_overrides: PathOverrides | None = None,
    copier: CopyTree = _rsync_copy,
    activity_probe: ActivityProbe = active_output_users,
) -> Mapping[str, Any]:
    """Create a verified snapshot and optionally evict the output payload."""

    _require_backend(domain, backend)
    if SNAPSHOT_ID.fullmatch(snapshot_id) is None:
        raise AndroidBuildDomainMigrationError("snapshot_id contains unsafe characters")
    output_root = _require_backend_scoped_root(
        _domain_path(domain, "paths", "output_root", path_overrides),
        backend,
        "output_root",
    )
    archive_root = _require_backend_scoped_root(
        _domain_path(domain, "paths", "archive_root", path_overrides),
        backend,
        "archive_root",
    )
    if _paths_overlap(output_root, archive_root):
        raise AndroidBuildDomainMigrationError(
            "output_root and archive_root must not overlap"
        )
    with ExitStack() as stack:
        _require_owner(domain, backend, "output", output_root)
        _require_owner(domain, backend, "archive", archive_root)
        _require_inactive(output_root, activity_probe)
        if (output_root / COLD_RECEIPT).exists():
            raise AndroidBuildDomainMigrationError("output_root is already cold")
        if not _payload_names(output_root):
            raise AndroidBuildDomainMigrationError("output_root has no hot payload")

        snapshot = archive_root / "cold-output" / snapshot_id
        if snapshot.exists():
            raise AndroidBuildDomainMigrationError("snapshot_id already exists")
        snapshot.mkdir(parents=True)
        source_before_path = snapshot / ".source-before.jsonl"
        source_after_path = snapshot / ".source-after.jsonl"
        files_path = snapshot / FILES_MANIFEST
        source_before = write_tree_manifest(
            output_root, source_before_path, skip_root_names=_STATE_NAMES
        )
        payload = snapshot / "payload"
        copier(output_root, payload, _STATE_NAMES)
        archived = write_tree_manifest(payload, files_path)
        source_after = write_tree_manifest(
            output_root, source_after_path, skip_root_names=_STATE_NAMES
        )
        source_before_path.unlink()
        source_after_path.unlink()
        if not _same_tree(source_before, source_after):
            raise AndroidBuildDomainMigrationError(
                "output_root changed while it was being archived"
            )
        if not _same_tree(source_before, archived):
            raise AndroidBuildDomainMigrationError(
                "cold archive differs from output_root"
            )
        manifest: dict[str, Any] = {
            "schema": SNAPSHOT_SCHEMA,
            "backend": backend,
            "domain_sha256": domain.sha256,
            "snapshot_id": snapshot_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "canonical_output_root": domain.path("output_root"),
            "entry_count": archived.entry_count,
            "file_count": archived.file_count,
            "logical_bytes": archived.logical_bytes,
            "tree_sha256": archived.tree_sha256,
            "files_manifest_sha256": archived.manifest_sha256,
            "copy_contract": "rsync-aHAX-numeric-ids-sparse-or-equivalent",
            "complete": True,
        }
        _atomic_json(snapshot / SNAPSHOT_MANIFEST, manifest)
        snapshot_manifest_sha256 = _sha256_file(snapshot / SNAPSHOT_MANIFEST)

        if evict:
            _require_inactive(output_root, activity_probe)
            cold_receipt = {
                "schema": COLD_RECEIPT_SCHEMA,
                "backend": backend,
                "domain_sha256": domain.sha256,
                "snapshot_id": snapshot_id,
                "tree_sha256": archived.tree_sha256,
                "snapshot_manifest_sha256": snapshot_manifest_sha256,
            }
            _atomic_json(output_root / COLD_RECEIPT, cold_receipt)
            for child in tuple(output_root.iterdir()):
                if child.name in _STATE_NAMES:
                    continue
                if child.is_symlink() or child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
                else:
                    raise AndroidBuildDomainMigrationError(
                        f"refusing to evict special output entry: {child}"
                    )
            if _payload_names(output_root):
                raise AndroidBuildDomainMigrationError(
                    "output eviction did not reach a cold state"
                )
        return {
            **manifest,
            "snapshot_manifest_sha256": snapshot_manifest_sha256,
            "evicted": evict,
        }


def _require_snapshot(
    domain: AndroidBuildDomain,
    backend: str,
    snapshot: Path,
) -> tuple[Mapping[str, Any], str]:
    manifest, manifest_sha256 = _snapshot_manifest(snapshot)
    expected = {
        "schema": SNAPSHOT_SCHEMA,
        "backend": backend,
        "domain_sha256": domain.sha256,
        "snapshot_id": snapshot.name,
        "canonical_output_root": domain.path("output_root"),
        "complete": True,
    }
    for name, value in expected.items():
        if manifest.get(name) != value:
            raise AndroidBuildDomainMigrationError(
                f"snapshot manifest field differs: {name}"
            )
    files_path = snapshot / FILES_MANIFEST
    if _sha256_file(files_path) != manifest.get("files_manifest_sha256"):
        raise AndroidBuildDomainMigrationError("files manifest digest differs")
    payload_manifest_path = snapshot / ".payload-current.jsonl"
    try:
        current = write_tree_manifest(snapshot / "payload", payload_manifest_path)
    finally:
        payload_manifest_path.unlink(missing_ok=True)
    if (
        current.tree_sha256 != manifest.get("tree_sha256")
        or current.entry_count != manifest.get("entry_count")
        or current.file_count != manifest.get("file_count")
        or current.logical_bytes != manifest.get("logical_bytes")
        or current.manifest_sha256 != manifest.get("files_manifest_sha256")
    ):
        raise AndroidBuildDomainMigrationError("cold snapshot payload differs")
    return manifest, manifest_sha256


def require_output_buildable(
    domain: AndroidBuildDomain,
    peer_domain: AndroidBuildDomain,
    *,
    backend: str,
    for_build: bool = False,
    path_overrides: PathOverrides | None = None,
    peer_path_overrides: PathOverrides | None = None,
) -> Mapping[str, Any]:
    """Require independent output ownership and a buildable selected output."""

    _require_backend(domain, backend)
    peer_backend = "redroid" if backend == "kvm" else "kvm"
    _require_backend(peer_domain, peer_backend)
    require_isolated_domain_pair(domain, peer_domain)
    domains = {backend: domain, peer_backend: peer_domain}
    require_actual_domain_pair_isolated(
        domains["redroid"],
        domains["kvm"],
        path_overrides={
            backend: path_overrides or {},
            peer_backend: peer_path_overrides or {},
        },
    )
    output_root = _require_backend_scoped_root(
        _domain_path(domain, "paths", "output_root", path_overrides),
        backend,
        "output_root",
    )
    peer_output_root = _require_backend_scoped_root(
        _domain_path(
            peer_domain,
            "paths",
            "output_root",
            peer_path_overrides,
        ),
        peer_backend,
        "peer output_root",
    )
    if _paths_overlap(output_root, peer_output_root):
        raise AndroidBuildDomainMigrationError(
            "selected and peer output roots overlap after resolution"
        )
    _require_owner(domain, backend, "output", output_root)
    _require_owner(peer_domain, peer_backend, "output", peer_output_root)
    if for_build and (output_root / COLD_RECEIPT).exists():
        raise AndroidBuildDomainMigrationError(
            "selected output is cold; restore it before an incremental build"
        )
    return {
        "schema": "alas-headless.android-output-availability/v2",
        "backend": backend,
        "peer_backend": peer_backend,
        "domain_sha256": domain.sha256,
        "peer_domain_sha256": peer_domain.sha256,
        "peer_output_independent": True,
        "buildable": bool(for_build),
    }


def restore_output(
    domain: AndroidBuildDomain,
    peer_domain: AndroidBuildDomain,
    *,
    backend: str,
    snapshot_id: str,
    path_overrides: PathOverrides | None = None,
    peer_path_overrides: PathOverrides | None = None,
    copier: CopyTree = _rsync_copy,
    activity_probe: ActivityProbe = active_output_users,
) -> Mapping[str, Any]:
    """Restore one verified snapshot through a same-filesystem staging root."""

    _require_backend(domain, backend)
    if SNAPSHOT_ID.fullmatch(snapshot_id) is None:
        raise AndroidBuildDomainMigrationError("snapshot_id contains unsafe characters")
    output_root = _require_backend_scoped_root(
        _domain_path(domain, "paths", "output_root", path_overrides),
        backend,
        "output_root",
    )
    archive_root = _require_backend_scoped_root(
        _domain_path(domain, "paths", "archive_root", path_overrides),
        backend,
        "archive_root",
    )
    with ExitStack() as stack:
        require_output_buildable(
            domain,
            peer_domain,
            backend=backend,
            path_overrides=path_overrides,
            peer_path_overrides=peer_path_overrides,
        )
        _require_owner(domain, backend, "output", output_root)
        _require_owner(domain, backend, "archive", archive_root)
        _require_inactive(output_root, activity_probe)
        if _payload_names(output_root):
            raise AndroidBuildDomainMigrationError(
                "restore requires an empty, owner-marked output_root"
            )
        snapshot = archive_root / "cold-output" / snapshot_id
        manifest, manifest_sha256 = _require_snapshot(domain, backend, snapshot)
        cold_path = output_root / COLD_RECEIPT
        if cold_path.exists():
            try:
                cold = json.loads(cold_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise AndroidBuildDomainMigrationError(
                    "cold output receipt is unreadable"
                ) from exc
            expected_cold = {
                "schema": COLD_RECEIPT_SCHEMA,
                "backend": backend,
                "domain_sha256": domain.sha256,
                "snapshot_id": snapshot_id,
                "tree_sha256": manifest["tree_sha256"],
                "snapshot_manifest_sha256": manifest_sha256,
            }
            if cold != expected_cold:
                raise AndroidBuildDomainMigrationError(
                    "cold output receipt differs from selected snapshot"
                )

        parent = output_root.parent
        staging = (
            parent / f".{output_root.name}.restore-{snapshot_id}-{uuid.uuid4().hex}"
        )
        backup = parent / f".{output_root.name}.cold-{uuid.uuid4().hex}"
        if staging.exists() or backup.exists():
            raise AndroidBuildDomainMigrationError(
                "restore staging path already exists"
            )
        copier(snapshot / "payload", staging, frozenset())
        first_handle = tempfile.NamedTemporaryFile(
            dir=parent, prefix=".restore-manifest-", delete=False
        )
        first_path = Path(first_handle.name)
        first_handle.close()
        first_path.unlink()
        second_handle = tempfile.NamedTemporaryFile(
            dir=parent, prefix=".restore-verified-", delete=False
        )
        second_path = Path(second_handle.name)
        second_handle.close()
        second_path.unlink()
        try:
            restored = write_tree_manifest(staging, first_path)
            verified = write_tree_manifest(staging, second_path)
        finally:
            first_path.unlink(missing_ok=True)
            second_path.unlink(missing_ok=True)
        if (
            restored.tree_sha256 != manifest["tree_sha256"]
            or restored.entry_count != manifest["entry_count"]
            or restored.file_count != manifest["file_count"]
            or restored.logical_bytes != manifest["logical_bytes"]
        ):
            raise AndroidBuildDomainMigrationError("restored staging tree differs")
        if (
            verified.tree_sha256 != manifest["tree_sha256"]
            or verified.manifest_sha256 != manifest["files_manifest_sha256"]
        ):
            raise AndroidBuildDomainMigrationError(
                "restored staging verification differs"
            )

        moved_old = False
        moved_new = False
        try:
            output_root.rename(backup)
            moved_old = True
            staging.rename(output_root)
            moved_new = True
            _atomic_json(
                output_root / OWNER_MARKER, _owner_document(domain, backend, "output")
            )
        except Exception:
            if moved_new and output_root.exists():
                output_root.rename(staging)
            if moved_old and backup.exists():
                backup.rename(output_root)
            raise
        for child in tuple(backup.iterdir()):
            if child.name not in _STATE_NAMES:
                raise AndroidBuildDomainMigrationError(
                    f"unexpected entry in cold-root backup: {child}"
                )
            child.unlink()
        backup.rmdir()
        return {
            "schema": "alas-headless.android-output-restore/v2",
            "backend": backend,
            "domain_sha256": domain.sha256,
            "snapshot_id": snapshot_id,
            "tree_sha256": manifest["tree_sha256"],
            "snapshot_manifest_sha256": manifest_sha256,
            "restored": True,
        }


def _actual_paths(
    domain: AndroidBuildDomain, overrides: PathOverrides | None
) -> Mapping[str, Path]:
    return {
        name: _domain_path(domain, "paths", name, overrides).resolve(strict=False)
        for name in domain.document["paths"]
    }


def preflight_domain_pair(
    redroid: AndroidBuildDomain,
    kvm: AndroidBuildDomain,
    *,
    source_free_min_bytes: int,
    repo_filesystem_free_min_bytes: int,
    output_free_min_bytes: int = 0,
    require_owned_roots: bool = False,
    path_overrides: Mapping[str, PathOverrides] | None = None,
) -> Mapping[str, Any]:
    """Return a non-mutating host preflight for the two v3 domains."""

    require_isolated_domain_pair(redroid, kvm)
    domains = {"redroid": redroid, "kvm": kvm}
    overrides = path_overrides or {}
    actual = {
        backend: _actual_paths(domain, overrides.get(backend))
        for backend, domain in domains.items()
    }
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    for backend, domain in domains.items():
        selected = actual[backend]
        for name, path in selected.items():
            checks[f"{backend}.{name}.exists"] = path.is_dir() and not path.is_symlink()
        source = selected["source_root"]
        repo = selected["repo_metadata_root"]
        output = selected["output_root"]
        archive = selected["archive_root"]
        if source.is_dir():
            source_free = shutil.disk_usage(source).free
            details[f"{backend}.source_free_bytes"] = source_free
            checks[f"{backend}.source_free_floor"] = (
                source_free >= source_free_min_bytes
            )
        else:
            checks[f"{backend}.source_free_floor"] = False
        if repo.is_dir():
            repo_free = shutil.disk_usage(repo).free
            details[f"{backend}.repo_filesystem_free_bytes"] = repo_free
            checks[f"{backend}.repo_filesystem_free_floor"] = (
                repo_free >= repo_filesystem_free_min_bytes
            )
        else:
            checks[f"{backend}.repo_filesystem_free_floor"] = False
        if output.is_dir():
            output_free = shutil.disk_usage(output).free
            details[f"{backend}.output_free_bytes"] = output_free
            checks[f"{backend}.output_free_floor"] = (
                output_free >= output_free_min_bytes
            )
        else:
            checks[f"{backend}.output_free_floor"] = False
        if source.is_dir() and repo.is_dir():
            source_repo = source / ".repo"
            checks[f"{backend}.source_repo_binding"] = (
                source_repo.exists() and source_repo.resolve() == repo.resolve()
            )
        else:
            checks[f"{backend}.source_repo_binding"] = False
        if require_owned_roots and output.is_dir() and archive.is_dir():
            for root_kind, root in (("output", output), ("archive", archive)):
                try:
                    _require_owner(domain, backend, root_kind, root)
                except AndroidBuildDomainMigrationError:
                    checks[f"{backend}.{root_kind}_owned"] = False
                else:
                    checks[f"{backend}.{root_kind}_owned"] = True

    actual_aliases = _actual_domain_aliases(
        redroid,
        kvm,
        path_overrides=overrides,
    )
    if actual_aliases:
        details["actual_overlaps"] = actual_aliases
    checks["backend_actual_paths_disjoint"] = not actual_aliases
    blockers = sorted(name for name, passed in checks.items() if not passed)
    return {
        "schema": "alas-headless.android-build-domain-host-preflight/v3",
        "domains": {backend: domain.sha256 for backend, domain in domains.items()},
        "source_free_min_bytes": source_free_min_bytes,
        "repo_filesystem_free_min_bytes": repo_filesystem_free_min_bytes,
        "output_free_min_bytes": output_free_min_bytes,
        "checks": checks,
        "details": details,
        "outcome": "pass" if not blockers else "blocked",
        "blockers": blockers,
    }
