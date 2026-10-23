"""Immutable clean-AOSP source identity for the KVM image builder."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


SOURCE_LOCK_SCHEMA = "alas-headless.kvm-image-source-lock/v1"
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_PATCHES = {
    "frameworks/base": (
        "integration/runtime/aosp-patches/"
        "0001-protolog-deterministic-generation-hash.patch",
        "ALAS: make ProtoLog generation reproducible",
    ),
    "build/make": (
        "integration/runtime/aosp-patches/"
        "0002-build-image-source-date-epoch.patch",
        "ALAS: make images reproducible and trim KVM-only packages",
    ),
    "device/generic/goldfish": (
        "integration/runtime/aosp-patches/"
        "0003-alas-kvm-first-stage-product.patch",
        "ALAS: add the first-stage headless KVM product",
    ),
    "external/chromium-webview": (
        "integration/runtime/aosp-patches/"
        "0004-webview-x86_64-only-prebuilt.patch",
        "ALAS: strip the unused x86 WebView payload",
    ),
    "external/noto-fonts": (
        "integration/runtime/aosp-patches/"
        "0005-kvm-language-font-whitelist.patch",
        "ALAS: retain only required KVM language fonts",
    ),
}


class KvmImageSourceLockError(ValueError):
    pass


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KvmImageSourceLockError(f"{name} must be an object")
    return value


def _commit(value: Any, name: str) -> str:
    text = str(value or "")
    if GIT_COMMIT.fullmatch(text) is None:
        raise KvmImageSourceLockError(f"{name} must be a full Git commit")
    return text


@dataclass(frozen=True)
class KvmImageSourceLock:
    document: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "KvmImageSourceLock":
        if not isinstance(value, Mapping):
            raise KvmImageSourceLockError("KVM source lock must be an object")
        document = json.loads(json.dumps(value))
        if set(document) != {
            "schema",
            "backend",
            "platform",
            "project_patches",
        }:
            raise KvmImageSourceLockError("KVM source lock fields differ")
        if document.get("schema") != SOURCE_LOCK_SCHEMA:
            raise KvmImageSourceLockError("KVM source lock schema mismatch")
        if document.get("backend") != "kvm":
            raise KvmImageSourceLockError("KVM source lock backend must be kvm")

        platform = _mapping(document.get("platform"), "platform")
        if set(platform) != {"manifest_url", "revision", "tag_object", "commit"}:
            raise KvmImageSourceLockError("KVM platform source fields differ")
        if platform.get("manifest_url") != (
            "https://android.googlesource.com/platform/manifest"
        ):
            raise KvmImageSourceLockError("KVM platform manifest URL differs")
        if platform.get("revision") != "android-14.0.0_r75":
            raise KvmImageSourceLockError("KVM platform revision differs")
        tag_object = _commit(platform.get("tag_object"), "platform.tag_object")
        commit = _commit(platform.get("commit"), "platform.commit")
        if tag_object == commit:
            raise KvmImageSourceLockError("tag object and manifest commit must differ")

        patches = document.get("project_patches")
        if not isinstance(patches, list) or len(patches) != len(EXPECTED_PATCHES):
            raise KvmImageSourceLockError("KVM project patches differ")
        observed: set[str] = set()
        for item in patches:
            patch = _mapping(item, "project patch")
            if set(patch) != {"project", "path", "sha256", "commit_message"}:
                raise KvmImageSourceLockError("KVM project patch fields differ")
            project = str(patch.get("project", ""))
            if project not in EXPECTED_PATCHES or project in observed:
                raise KvmImageSourceLockError("KVM project patch target differs")
            observed.add(project)
            _, expected_message = EXPECTED_PATCHES[project]
            path = str(patch.get("path", ""))
            # Candidate builds may retain a separate patch payload. Content is
            # still pinned by its digest and verified against the source tree.
            if (not path.startswith("integration/runtime/") or not path.endswith(".patch")
                    or "\\" in path or ".." in path.split("/")
                    or Path(path).is_absolute()):
                raise KvmImageSourceLockError("KVM project patch path differs")
            if patch.get("commit_message") != expected_message:
                raise KvmImageSourceLockError("KVM project patch message differs")
            if SHA256.fullmatch(str(patch.get("sha256", ""))) is None:
                raise KvmImageSourceLockError("KVM project patch digest must be sha256")
        if observed != set(EXPECTED_PATCHES):
            raise KvmImageSourceLockError("KVM project patch set differs")

        canonical = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return cls(
            MappingProxyType(document), hashlib.sha256(canonical).hexdigest()
        )

    @classmethod
    def from_path(cls, path: Path) -> "KvmImageSourceLock":
        value = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_mapping(value)
