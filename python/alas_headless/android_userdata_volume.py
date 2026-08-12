"""Fail-closed qualification for a Redroid host userdata block volume.

This contract deliberately stops at the host filesystem boundary.  An ext4
filesystem with the ``encrypt`` feature is necessary for fscrypt, but it is
not proof that Android mounted it with file-based encryption or that Direct
Boot works.
"""

from __future__ import annotations

from typing import Any, Mapping


PROBE_SCHEMA = "alas-headless.redroid-userdata-volume-probe/v1"
QUALIFICATION_SCHEMA = "alas-headless.redroid-userdata-volume-qualification/v1"
FORBIDDEN_MOUNTPOINTS = {"/", "/data", "/var/lib/redroid/data"}


def qualify_userdata_volume(probe: Mapping[str, Any]) -> Mapping[str, Any]:
    """Assess an isolated, newly created userdata volume probe."""
    blockers = []
    if probe.get("schema") != PROBE_SCHEMA:
        blockers.append("probe-schema-mismatch")
    if probe.get("scope") != "empty-lab-volume":
        blockers.append("scope-is-not-empty-lab-volume")
    if probe.get("created_new") is not True:
        blockers.append("volume-was-not-created-new")
    if probe.get("backing_file_existed_before") is not False:
        blockers.append("backing-file-preexisted")
    if probe.get("production_data_touched") is not False:
        blockers.append("production-data-may-have-been-touched")

    backing_file = str(probe.get("backing_file", ""))
    mountpoint = str(probe.get("mountpoint", ""))
    block_device = str(probe.get("block_device", ""))
    root_source = str(probe.get("root_source", ""))
    if not backing_file.startswith("/"):
        blockers.append("backing-file-is-not-absolute")
    if backing_file == "/var/lib/redroid/data" or backing_file.startswith(
        "/var/lib/redroid/data/"
    ):
        blockers.append("backing-file-overlaps-production-data")
    if not block_device.startswith("/dev/loop"):
        blockers.append("userdata-is-not-an-isolated-loop-block-device")
    if block_device == root_source:
        blockers.append("userdata-reuses-host-root-device")
    if not mountpoint.startswith("/") or mountpoint in FORBIDDEN_MOUNTPOINTS:
        blockers.append("unsafe-or-production-mountpoint")

    if probe.get("filesystem_type") != "ext4":
        blockers.append("filesystem-is-not-ext4")
    features = {str(item) for item in probe.get("filesystem_features", [])}
    if "encrypt" not in features:
        blockers.append("ext4-encrypt-feature-missing")
    if probe.get("mounted_read_write") is not True:
        blockers.append("volume-was-not-mounted-read-write")
    if probe.get("empty_before_mount") is not True:
        blockers.append("mountpoint-was-not-empty")
    if probe.get("android_fbe_claimed") is not False:
        blockers.append("host-volume-must-not-claim-android-fbe")

    return {
        "schema": QUALIFICATION_SCHEMA,
        "outcome": "pass" if not blockers else "fail",
        "ceiling": "host-volume-qualified",
        "android_fbe_proven": False,
        "direct_boot_proven": False,
        "blockers": blockers,
        "probe": dict(probe),
    }
