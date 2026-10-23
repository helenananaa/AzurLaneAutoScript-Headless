"""Exact, account-free identity documents for macOS/HVF qualification."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from .runtime_artifacts import RuntimeLock, canonical_json_bytes, resource_set_id


IDENTITY_SCHEMA = "alas-headless.macos-hvf-runtime-identity/v1"
PROVISION_PROFILE_SCHEMA = "alas-headless.macos-hvf-provision-profile/v1"
RESOURCE_MANIFEST_SCHEMA = "alas-headless.platform-resource-scope/v1"
ANGLE_PATCHSET_SCHEMA = "alas-headless.angle-patchset-manifest/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_document_bytes(value: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(value)


def write_canonical_document(path: Path, value: Mapping[str, Any]) -> str:
    path = Path(path)
    if path.exists():
        raise ValueError("identity output must not already exist")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_document_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def angle_patchset_manifest(repo_root: Path) -> Mapping[str, Any]:
    repo_root = Path(repo_root).resolve()
    roots = (
        repo_root / "patches" / "angle",
        repo_root / "patches" / "angle-g3",
        repo_root / "overlays" / "angle-g3",
    )
    entries = []
    for root in roots:
        if not root.is_dir():
            raise ValueError("ANGLE patchset root is missing")
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            entries.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
    if not entries:
        raise ValueError("ANGLE patchset is empty")
    return {"schema": ANGLE_PATCHSET_SCHEMA, "entries": entries}


def build_provision_profile(
    *,
    avd_name: str,
    avd_config_sha256: str,
    sdk_root: str,
    system_image_relative_path: str,
    system_image_sha256: str,
    emulator_version: str,
    acceleration: str,
    console_port: int,
    adb_server_port: int,
    android_fingerprint: str,
    api_level: int,
    abi: str,
) -> Mapping[str, Any]:
    return {
        "schema": PROVISION_PROFILE_SCHEMA,
        "avd_name": avd_name,
        "avd_config_sha256": avd_config_sha256,
        "sdk_root": sdk_root,
        "system_image_relative_path": system_image_relative_path,
        "system_image_sha256": system_image_sha256,
        "emulator_version": emulator_version,
        "acceleration": acceleration,
        "console_port": console_port,
        "adb_server_port": adb_server_port,
        "android_fingerprint": android_fingerprint,
        "api_level": api_level,
        "abi": abi,
        "snapshots": "disabled-for-qualification",
        "logical_display": "1280x720@240",
    }


def build_platform_resource_manifest(
    package: str, version_name: str, version_code: int
) -> Mapping[str, Any]:
    return {
        "schema": RESOURCE_MANIFEST_SCHEMA,
        "claim_scope": "none-platform-lifecycle-only",
        "package": package,
        "version_name": version_name,
        "version_code": version_code,
        "shared_public_paths": [],
    }


def _required_text(value: Mapping[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        raise ValueError("macOS HVF identity field is missing: {0}".format(name))
    return item.strip()


def _required_sha256(value: Mapping[str, Any], name: str) -> str:
    item = _required_text(value, name).lower()
    if _SHA256.fullmatch(item) is None:
        raise ValueError("macOS HVF identity hash is malformed: {0}".format(name))
    return item


def _git(repo_root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repo_root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_runtime_lock(
    *,
    repo_root: Path,
    identity: Mapping[str, Any],
    provision_profile: Path,
    resource_manifest: Path,
    angle_patchset_sha256: str,
) -> RuntimeLock:
    repo_root = Path(repo_root).resolve()
    if identity.get("schema") != IDENTITY_SCHEMA or identity.get("outcome") != "pass":
        raise ValueError("macOS HVF identity receipt is not a pass")
    if _required_text(identity, "platform") != "darwin":
        raise ValueError("macOS HVF identity platform mismatch")
    if _required_text(identity, "machine") not in ("arm64", "aarch64"):
        raise ValueError("macOS HVF identity machine mismatch")
    if _required_text(identity, "android_abi") != "arm64-v8a":
        raise ValueError("macOS HVF identity Android ABI mismatch")
    if _required_text(identity, "game_abi") != "arm64-v8a":
        raise ValueError("macOS HVF identity game ABI mismatch")
    if file_sha256(provision_profile) != _required_sha256(
        identity, "provision_profile_sha256"
    ):
        raise ValueError("macOS HVF provision profile receipt mismatch")
    if file_sha256(resource_manifest) != _required_sha256(
        identity, "resource_manifest_sha256"
    ):
        raise ValueError("macOS HVF resource manifest receipt mismatch")
    if _SHA256.fullmatch(angle_patchset_sha256) is None:
        raise ValueError("ANGLE patchset hash is malformed")

    core_commit = _git(repo_root, "rev-parse", "HEAD")
    if _COMMIT.fullmatch(core_commit) is None:
        raise ValueError("repository HEAD is not a full commit")
    upstream = json.loads(
        (repo_root / "integration/alas/upstream-lock.json").read_text(encoding="utf-8")
    )
    upstream_commit = str(upstream.get("commit", ""))
    if _COMMIT.fullmatch(upstream_commit) is None:
        raise ValueError("ALAS upstream lock commit is malformed")
    angle_revision = (repo_root / "ANGLE_REVISION").read_text(encoding="utf-8").strip()
    if _COMMIT.fullmatch(angle_revision) is None:
        raise ValueError("ANGLE revision is malformed")
    api_level = identity.get("api_level")
    game_version_code = identity.get("game_version_code")
    if isinstance(api_level, bool) or not isinstance(api_level, int):
        raise ValueError("macOS HVF identity API level is malformed")
    if isinstance(game_version_code, bool) or not isinstance(game_version_code, int):
        raise ValueError("macOS HVF identity game version code is malformed")
    game_version_name = _required_text(identity, "game_version_name")
    resource_hash = _required_sha256(identity, "resource_manifest_sha256")
    value = {
        "schema": "alas-headless.runtime-lock/v1",
        "core": {
            "core_commit": core_commit,
            "alas_upstream_commit": upstream_commit,
            "alas_patch_sha256": file_sha256(
                repo_root / "integration/alas/0001-semantic-oracle-hooks.patch"
            ),
            "alas_patch_series_manifest_sha256": file_sha256(
                repo_root / "integration/alas/series/series.json"
            ),
        },
        "angle": {
            "revision": angle_revision,
            "patchset_sha256": angle_patchset_sha256,
            "abi": "arm64-v8a",
            "apk_sha256": _required_sha256(identity, "angle_apk_sha256"),
            "observer_schema": "alas-headless.observer/v1",
        },
        "android": {
            "backend": "macos-hvf",
            "build_fingerprint": _required_text(identity, "android_fingerprint"),
            "api_level": api_level,
            "abi": "arm64-v8a",
            "system_image_sha256": _required_sha256(identity, "system_image_sha256"),
            "provision_profile_sha256": _required_sha256(
                identity, "provision_profile_sha256"
            ),
        },
        "game": {
            "package": _required_text(identity, "package"),
            "region": "cn",
            "version_name": game_version_name,
            "version_code": game_version_code,
            "abi": "arm64-v8a",
            "base_apk_sha256": _required_sha256(identity, "game_base_apk_sha256"),
            "libil2cpp_sha256": _required_sha256(identity, "game_libil2cpp_sha256"),
        },
        "resources": {
            "resource_set_id": resource_set_id("cn", game_version_name, resource_hash),
            "resource_epoch": 1,
            "manifest_sha256": resource_hash,
            "shared_public_paths": [],
        },
        "userdata": {"generation": 1, "account_scope": "per-instance"},
    }
    return RuntimeLock.from_mapping(value)


def runtime_lock_plain(lock: RuntimeLock) -> Mapping[str, Any]:
    return json.loads(canonical_json_bytes(lock.document).decode("utf-8"))


__all__ = [
    "ANGLE_PATCHSET_SCHEMA",
    "IDENTITY_SCHEMA",
    "PROVISION_PROFILE_SCHEMA",
    "RESOURCE_MANIFEST_SCHEMA",
    "angle_patchset_manifest",
    "build_platform_resource_manifest",
    "build_provision_profile",
    "build_runtime_lock",
    "canonical_document_bytes",
    "file_sha256",
    "runtime_lock_plain",
    "write_canonical_document",
]

