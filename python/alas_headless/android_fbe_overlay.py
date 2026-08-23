"""Validation for the local Redroid native-FBE build overlay."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .android_image_source import AndroidImageSourceLock


OVERLAY_SCHEMA = "alas-headless.redroid-native-fbe-overlay/v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_FILES = {"fstab.redroid", "init.alas-fbe.rc", "product.mk"}


class AndroidFbeOverlayError(ValueError):
    """Raised when the FBE overlay is incomplete, mutable, or overclaims."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_fbe_overlay(
    root: Path, source_lock: AndroidImageSourceLock | None = None
) -> Mapping[str, Any]:
    root = Path(root)
    lock_path = root / "overlay-lock.json"
    value = json.loads(lock_path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("schema") != OVERLAY_SCHEMA:
        raise AndroidFbeOverlayError("overlay lock schema mismatch")
    files = value.get("files")
    if not isinstance(files, Mapping) or set(files) != EXPECTED_FILES:
        raise AndroidFbeOverlayError("overlay file set must be exact")
    records = {}
    for name in sorted(EXPECTED_FILES):
        expected = str(files.get(name, ""))
        if SHA256.fullmatch(expected) is None:
            raise AndroidFbeOverlayError("invalid locked SHA-256 for {0}".format(name))
        path = root / name
        observed = _sha256(path)
        if observed != expected:
            raise AndroidFbeOverlayError("overlay digest mismatch for {0}".format(name))
        records[name] = {"bytes": path.stat().st_size, "sha256": observed}

    fstab = (root / "fstab.redroid").read_text(encoding="utf-8")
    required_fstab = (
        "/dev/block/alas_metadata", "/metadata", "formattable",
        "/dev/block/alas_userdata", "/data", "fileencryption=aes-256-xts:aes-256-cts",
        "keydirectory=/metadata/vold/metadata_encryption", "latemount",
    )
    if not all(token in fstab for token in required_fstab):
        raise AndroidFbeOverlayError("fstab does not implement the dual-volume FBE contract")
    if "encryptable=" in fstab or "forceencrypt=" in fstab:
        raise AndroidFbeOverlayError("legacy full-disk encryption flags are forbidden")

    init = (root / "init.alas-fbe.rc").read_text(encoding="utf-8")
    for token in (
        "on early-fs", "start vold", "mount_all /vendor/etc/fstab.redroid --early",
        "on late-fs", "mount_all /vendor/etc/fstab.redroid --late",
    ):
        if token not in init:
            raise AndroidFbeOverlayError("init mount ordering is incomplete")

    product = (root / "product.mk").read_text(encoding="utf-8")
    for destination in (
        "$(TARGET_COPY_OUT_VENDOR)/etc/fstab.redroid",
        "$(TARGET_COPY_OUT_VENDOR)/etc/init/init.alas-fbe.rc",
    ):
        if destination not in product:
            raise AndroidFbeOverlayError("product copy contract is incomplete")
    combined = "\n".join((fstab, init, product)).lower()
    if "azurlane" in combined or "com.bilibili" in combined:
        raise AndroidFbeOverlayError("game artifacts are forbidden in the overlay")
    if "ro.crypto." in combined:
        raise AndroidFbeOverlayError("crypto properties must be runtime results, not forced")
    if value.get("game_artifact_allowed") is not False:
        raise AndroidFbeOverlayError("overlay must keep game delivery external")
    if value.get("android_fbe_runtime_evidence_required") is not True:
        raise AndroidFbeOverlayError("Android FBE runtime evidence must remain mandatory")
    if value.get("direct_boot_runtime_evidence_required") is not True:
        raise AndroidFbeOverlayError("Direct Boot runtime evidence must remain mandatory")
    basis = value.get("upstream_basis", {})
    if not isinstance(basis, Mapping):
        raise AndroidFbeOverlayError("upstream basis must be an object")
    if source_lock is not None:
        platform = source_lock.document["platform"]
        device = next(
            item for item in source_lock.document["redroid"]["projects"]
            if item["name"] == "device_redroid"
        )
        if basis.get("aosp_goldfish_revision") != platform.get("revision"):
            raise AndroidFbeOverlayError("overlay AOSP revision differs from source lock")
        if basis.get("redroid_device_commit") != device.get("commit"):
            raise AndroidFbeOverlayError("overlay Redroid commit differs from source lock")

    return {
        "schema": "alas-headless.redroid-native-fbe-overlay-validation/v1",
        "outcome": "pass",
        "overlay_schema": OVERLAY_SCHEMA,
        "files": records,
        "upstream_basis": dict(basis),
        "source_lock_sha256": source_lock.sha256 if source_lock is not None else None,
        "block_devices": dict(value.get("block_devices", {})),
        "game_artifact_included": False,
        "android_fbe_proven": False,
        "direct_boot_proven": False,
    }
