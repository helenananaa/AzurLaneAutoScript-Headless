"""Per-change, workload-independent gates for Android image slimming."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence, Set

from .android_foundation_audit import AUDIT_SCHEMA
from .android_image_supply_chain import PROVENANCE_SCHEMA


SLIMMING_SCHEMA = "alas-headless.android-image-slimming-change/v1"
GATES = ("gles-contract", "unity-contract", "observer-contract")


class AndroidImageSlimmingError(ValueError):
    pass


def inventory(path: Path) -> Set[str]:
    values = {
        line.strip()
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not values:
        raise AndroidImageSlimmingError("installed-files inventory must not be empty")
    return values


def _payload_bytes(provenance: Mapping[str, Any]) -> int:
    artifacts = provenance.get("artifacts", {})
    if not isinstance(artifacts, Mapping):
        return 0
    total = 0
    for name in ("system.img", "vendor.img"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            return 0
        total += int(record.get("bytes", 0))
    return total


def qualify_slimming_change(
    change: Mapping[str, Any],
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    baseline_inventory: Path,
    candidate_inventory: Path,
    audit: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
    update: Mapping[str, Any],
    rollback: Mapping[str, Any],
) -> Mapping[str, Any]:
    blockers = []
    change_id = str(change.get("change_id", ""))
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", change_id) is None:
        blockers.append("change-id-invalid")
    if not str(change.get("hypothesis", "")).strip():
        blockers.append("hypothesis-missing")
    if change.get("alas_workload_required") is not False:
        blockers.append("workload-scope-invalid")
    allowed_removed = change.get("allowed_removed_files")
    if not isinstance(allowed_removed, Sequence) or isinstance(allowed_removed, (str, bytes)):
        allowed_removed = []
        blockers.append("allowed-removals-invalid")
    allowed_removed = {str(item) for item in allowed_removed}

    base_files = inventory(baseline_inventory)
    candidate_files = inventory(candidate_inventory)
    removed = base_files - candidate_files
    added = candidate_files - base_files
    if not removed:
        blockers.append("no-files-removed")
    unexpected = removed - allowed_removed
    if unexpected:
        blockers.append("unexpected-files-removed")
    unused_allowlist = allowed_removed - removed
    if unused_allowlist:
        blockers.append("declared-removal-not-observed")

    for name, value in (("baseline", baseline), ("candidate", candidate)):
        if value.get("schema") != PROVENANCE_SCHEMA:
            blockers.append("{0}-provenance-schema-mismatch".format(name))
        if value.get("game_artifact_included") is not False or value.get("alas_workload_used") is not False:
            blockers.append("{0}-scope-invalid".format(name))
    base_target = baseline.get("target", {})
    candidate_target = candidate.get("target", {})
    abi = candidate_target.get("abi") if isinstance(candidate_target, Mapping) else None
    if base_target != candidate_target:
        blockers.append("target-mismatch")
    if baseline.get("source_lock_sha256") != candidate.get("source_lock_sha256"):
        blockers.append("source-lock-mismatch")
    base_bytes = _payload_bytes(baseline)
    candidate_bytes = _payload_bytes(candidate)
    if base_bytes <= 0 or candidate_bytes <= 0 or candidate_bytes >= base_bytes:
        blockers.append("payload-size-not-reduced")

    identity = audit.get("identity", {})
    if audit.get("schema") != AUDIT_SCHEMA or audit.get("outcome") != "pass":
        blockers.append("foundation-audit-not-pass")
    if abi not in str(identity.get("abi_list", "")).split(","):
        blockers.append("foundation-audit-abi-mismatch")
    if audit.get("game_installed") is not False or audit.get("alas_workload_used") is not False:
        blockers.append("foundation-audit-scope-invalid")
    for gate in GATES:
        evidence = contracts.get(gate)
        if not isinstance(evidence, Mapping) or evidence.get("outcome") != "pass":
            blockers.append("{0}-not-pass".format(gate))
        elif evidence.get("game_installed") is not False or evidence.get("alas_workload_used") is not False:
            blockers.append("{0}-scope-invalid".format(gate))
    if update.get("outcome") != "pass" or update.get("game_installed") is not False or update.get("alas_workload_used") is not False:
        blockers.append("update-qualification-not-pass")
    if rollback.get("outcome") != "pass" or rollback.get("game_installed") is not False or rollback.get("alas_workload_used") is not False:
        blockers.append("image-rollback-not-pass")

    return {
        "schema": SLIMMING_SCHEMA,
        "change_id": change_id,
        "abi": abi,
        "source_lock_sha256": candidate.get("source_lock_sha256"),
        "removed_files": sorted(removed),
        "added_files": sorted(added),
        "baseline_payload_bytes": base_bytes,
        "candidate_payload_bytes": candidate_bytes,
        "saved_payload_bytes": base_bytes - candidate_bytes,
        "outcome": "pass" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "alas_workload_used": False,
    }
