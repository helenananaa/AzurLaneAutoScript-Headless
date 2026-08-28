"""Deterministic single-platform OCI archives for Redroid root filesystems."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


OCI_BUILD_SCHEMA = "alas-headless.redroid-oci-build/v1"
ARCHITECTURES = {"x86_64": "amd64", "arm64-v8a": "arm64"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AndroidImageOciError(ValueError):
    pass


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _write_blob(layout: Path, value: bytes) -> tuple[str, int]:
    digest = digest_bytes(value)
    target = layout / "blobs" / "sha256" / digest
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(value)
    return digest, len(value)


def _archive_layout(layout: Path, output: Path) -> None:
    with tarfile.open(output, "w", format=tarfile.USTAR_FORMAT) as archive:
        for path in sorted(layout.rglob("*"), key=lambda item: item.relative_to(layout).as_posix()):
            relative = path.relative_to(layout).as_posix()
            info = archive.gettarinfo(str(path), arcname=relative)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            info.mode = 0o755 if path.is_dir() else 0o644
            if path.is_file():
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                archive.addfile(info)


def _root_level_absolute_symlinks(members: list[tarfile.TarInfo]) -> list[str]:
    incompatible: list[str] = []
    for member in members:
        name = member.name
        while name.startswith("./"):
            name = name[2:]
        name = name.rstrip("/")
        if (
            member.issym()
            and name
            and "/" not in name
            and member.linkname.startswith("/")
        ):
            incompatible.append("{0} -> {1}".format(name, member.linkname))
    return sorted(incompatible)


def create_redroid_oci_archive(
    rootfs_layer: Path,
    abi: str,
    source_lock_sha256: str,
    build_fingerprint: str,
    source_date_epoch: int,
    output: Path,
) -> Mapping[str, Any]:
    if abi not in ARCHITECTURES:
        raise AndroidImageOciError("unsupported ABI: {0}".format(abi))
    if SHA256.fullmatch(source_lock_sha256) is None:
        raise AndroidImageOciError("source lock SHA-256 is invalid")
    if not build_fingerprint.strip():
        raise AndroidImageOciError("build fingerprint is mandatory")
    if source_date_epoch <= 0:
        raise AndroidImageOciError("SOURCE_DATE_EPOCH must be positive")
    if not rootfs_layer.is_file() or rootfs_layer.stat().st_size <= 0:
        raise AndroidImageOciError("rootfs layer must be a non-empty tar")
    if output.exists():
        raise AndroidImageOciError("output must not already exist")
    try:
        with tarfile.open(rootfs_layer, "r") as archive:
            members = archive.getmembers()
            if not members:
                raise AndroidImageOciError("rootfs layer tar is empty")
            incompatible_symlinks = _root_level_absolute_symlinks(members)
            if incompatible_symlinks:
                raise AndroidImageOciError(
                    "rootfs layer contains containerd-incompatible root-level "
                    "absolute symlink(s): {0}".format(", ".join(incompatible_symlinks))
                )
    except tarfile.TarError as error:
        raise AndroidImageOciError("rootfs layer is not a valid uncompressed tar") from error

    architecture = ARCHITECTURES[abi]
    image_name = "docker.io/alasheadless/redroid-{0}:latest".format(
        abi.replace("_", "-").replace("-v8a", "")
    )
    created = datetime.fromtimestamp(source_date_epoch, timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    layer_digest, layer_size = digest_file(rootfs_layer)
    layout = output.parent / (".{0}.layout".format(output.name))
    if layout.exists():
        raise AndroidImageOciError("temporary OCI layout already exists")
    try:
        (layout / "blobs" / "sha256").mkdir(parents=True)
        layer_target = layout / "blobs" / "sha256" / layer_digest
        shutil.copyfile(rootfs_layer, layer_target)
        config = {
            "architecture": architecture,
            "config": {
                "Entrypoint": ["/init", "androidboot.hardware=redroid"],
                "Labels": {
                    "io.github.alas-headless.abi": abi,
                    "io.github.alas-headless.build-fingerprint": build_fingerprint,
                    "io.github.alas-headless.game-delivery": "external-install",
                    "io.github.alas-headless.source-lock-sha256": source_lock_sha256,
                },
            },
            "created": created,
            "history": [{"created": created, "created_by": "alas-headless deterministic Redroid packager"}],
            "os": "linux",
            "rootfs": {"diff_ids": ["sha256:" + layer_digest], "type": "layers"},
        }
        config_digest, config_size = _write_blob(layout, canonical(config))
        manifest = {
            "config": {
                "digest": "sha256:" + config_digest,
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "size": config_size,
            },
            "layers": [{
                "digest": "sha256:" + layer_digest,
                "mediaType": "application/vnd.oci.image.layer.v1.tar",
                "size": layer_size,
            }],
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "schemaVersion": 2,
        }
        manifest_digest, manifest_size = _write_blob(layout, canonical(manifest))
        index = {
            "manifests": [{
                "annotations": {
                    "io.containerd.image.name": image_name,
                    "org.opencontainers.image.ref.name": image_name,
                },
                "digest": "sha256:" + manifest_digest,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "platform": {"architecture": architecture, "os": "linux"},
                "size": manifest_size,
            }],
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "schemaVersion": 2,
        }
        (layout / "index.json").write_bytes(canonical(index))
        (layout / "oci-layout").write_bytes(canonical({"imageLayoutVersion": "1.0.0"}))
        output.parent.mkdir(parents=True, exist_ok=True)
        _archive_layout(layout, output)
        archive_digest, archive_size = digest_file(output)
    finally:
        if layout.exists():
            shutil.rmtree(layout)
    return {
        "schema": OCI_BUILD_SCHEMA,
        "abi": abi,
        "architecture": architecture,
        "source_lock_sha256": source_lock_sha256,
        "source_date_epoch": source_date_epoch,
        "build_fingerprint": build_fingerprint,
        "image_name": image_name,
        "manifest_digest": "sha256:" + manifest_digest,
        "layer_digest": "sha256:" + layer_digest,
        "archive": {"path": str(output.resolve()), "bytes": archive_size, "sha256": archive_digest},
        "game_delivery": "external-install",
        "game_artifact_included": False,
        "alas_workload_used": False,
    }
