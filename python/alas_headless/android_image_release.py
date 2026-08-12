"""Content-addressed, fail-closed Android image foundation release manifests."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .android_foundation_audit import AUDIT_SCHEMA
from .android_image_policy import AndroidImagePolicy


RELEASE_SCHEMA = "alas-headless.android-image-foundation-release/v1"
TARGET_ABIS = ("x86_64", "arm64-v8a")
OCI_IDENTITY_SCHEMA = "alas-headless.oci-image-identity/v1"
OCI_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def hash_file(path: Path) -> Mapping[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"path": str(Path(path).resolve()), "bytes": size, "sha256": digest.hexdigest()}


def apk_abis(path: Path) -> frozenset[str]:
    with zipfile.ZipFile(path) as archive:
        return frozenset(
            name.split("/", 2)[1]
            for name in archive.namelist()
            if name.startswith("lib/") and name.count("/") >= 2
        )


def load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object: {0}".format(path))
    return value


def target_record(
    abi: str,
    contract_apk: Optional[Path],
    angle_apk: Optional[Path],
    image_artifact: Optional[Path],
    contract_evidence: Mapping[str, Optional[Mapping[str, Any]]],
    foundation_audit: Optional[Mapping[str, Any]],
    update_evidence: Optional[Mapping[str, Any]],
    image_identity: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    blockers = []
    contract = None
    if contract_apk is None:
        blockers.append("contract-artifact-missing")
    else:
        contract = dict(hash_file(contract_apk))
        observed = apk_abis(contract_apk)
        contract["observed_abis"] = sorted(observed)
        if observed != frozenset((abi,)):
            blockers.append("contract-artifact-abi-mismatch")

    angle = None
    if angle_apk is None:
        blockers.append("angle-artifact-missing")
    else:
        angle = dict(hash_file(angle_apk))
        observed_angle_abis = apk_abis(angle_apk)
        angle["observed_abis"] = sorted(observed_angle_abis)
        if observed_angle_abis != frozenset((abi,)):
            blockers.append("angle-artifact-abi-mismatch")

    image = None
    if image_artifact is not None and image_identity is not None:
        blockers.append("image-identity-ambiguous")
    elif image_artifact is not None:
        image = hash_file(image_artifact)
        image["kind"] = "file"
    elif image_identity is not None:
        image = dict(image_identity)
        image["kind"] = "oci"
        digest = str(image_identity.get("manifest_digest", ""))
        expected_architecture = "arm64" if abi == "arm64-v8a" else "amd64"
        if image_identity.get("schema") != OCI_IDENTITY_SCHEMA:
            blockers.append("image-identity-schema-mismatch")
        if OCI_DIGEST.fullmatch(digest) is None:
            blockers.append("image-identity-digest-invalid")
        if image_identity.get("architecture") != expected_architecture:
            blockers.append("image-identity-abi-mismatch")
        if image_identity.get("immutable") is not True:
            blockers.append("image-identity-not-immutable")
    else:
        blockers.append("image-artifact-missing")

    contracts: Dict[str, Any] = {}
    for gate in ("gles-contract", "unity-contract", "observer-contract"):
        evidence = contract_evidence.get(gate)
        if evidence is None:
            blockers.append("{0}-evidence-missing".format(gate))
            contracts[gate] = None
            continue
        summary = {
            "schema": evidence.get("schema"),
            "outcome": evidence.get("outcome"),
            "abi": evidence.get("abi"),
        }
        contracts[gate] = summary
        if evidence.get("outcome") != "pass":
            blockers.append("{0}-evidence-not-pass".format(gate))
        if evidence.get("game_installed") is not False or evidence.get("alas_workload_used") is not False:
            blockers.append("{0}-evidence-scope-invalid".format(gate))
        evidence_abi = str(evidence.get("abi", ""))
        if evidence_abi and abi not in evidence_abi.split(","):
            blockers.append("{0}-evidence-abi-mismatch".format(gate))
        if (
            gate == "unity-contract"
            and contract is not None
            and evidence.get("apk_sha256") != contract.get("sha256")
        ):
            blockers.append("unity-contract-evidence-artifact-mismatch")
        if (
            angle is not None
            and evidence.get("angle_apk_sha256")
            and evidence.get("angle_apk_sha256") != angle.get("sha256")
        ):
            blockers.append("{0}-evidence-angle-mismatch".format(gate))

    audit_summary = None
    if foundation_audit is None:
        blockers.append("foundation-audit-missing")
    else:
        identity = foundation_audit.get("identity", {})
        audit_summary = {
            "schema": foundation_audit.get("schema"),
            "outcome": foundation_audit.get("outcome"),
            "policy_sha256": foundation_audit.get("policy_sha256"),
            "identity": identity,
        }
        if foundation_audit.get("schema") != AUDIT_SCHEMA or foundation_audit.get("outcome") != "pass":
            blockers.append("foundation-audit-not-pass")
        if abi not in str(identity.get("abi_list", "")).split(","):
            blockers.append("foundation-audit-abi-mismatch")
        if foundation_audit.get("game_installed") is not False or foundation_audit.get("alas_workload_used") is not False:
            blockers.append("foundation-audit-scope-invalid")

    update_summary = None
    if update_evidence is None:
        blockers.append("update-qualification-missing")
    else:
        phases = update_evidence.get("phases", [])
        passed = {
            phase.get("name")
            for phase in phases
            if isinstance(phase, dict) and phase.get("outcome") == "pass"
        }
        update_summary = {
            "schema": update_evidence.get("schema"),
            "outcome": update_evidence.get("outcome"),
            "passed_phases": sorted(item for item in passed if isinstance(item, str)),
        }
        required = {
            "wrong-signer-negative",
            "single-apk-upgrade",
            "split-apk-upgrade",
            "resource-process-resume",
            "resource-low-space-negative",
            "resource-android-restart-resume",
            "resource-pointer-rollback",
        }
        if update_evidence.get("outcome") != "pass" or not required.issubset(passed):
            blockers.append("update-qualification-not-pass")
        if update_evidence.get("game_installed") is not False or update_evidence.get("alas_workload_used") is not False:
            blockers.append("update-qualification-scope-invalid")
        split_paths = " ".join(
            str(path)
            for phase in phases
            if isinstance(phase, dict) and phase.get("name") == "split-apk-upgrade"
            for path in phase.get("details", {}).get("paths", [])
        )
        split_token = "split_config.{0}.apk".format(abi.replace("-", "_"))
        if split_token not in split_paths:
            blockers.append("update-qualification-abi-mismatch")

    return {
        "abi": abi,
        "outcome": "platform-and-update-qualified" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "contract_artifact": contract,
        "angle_artifact": angle,
        "image_artifact": image,
        "contract_evidence": contracts,
        "foundation_audit": audit_summary,
        "update_qualification": update_summary,
    }


def build_release_manifest(
    policy: AndroidImagePolicy,
    source: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    if set(targets) != set(TARGET_ABIS):
        raise ValueError("release manifest requires exactly x86_64 and arm64-v8a targets")
    normalized_targets: Dict[str, Dict[str, Any]] = {
        abi: dict(targets[abi]) for abi in TARGET_ABIS
    }
    for abi, record in normalized_targets.items():
        target_blockers = list(record.get("blockers", []))
        audit = record.get("foundation_audit")
        if isinstance(audit, Mapping) and audit.get("policy_sha256") != policy.sha256:
            target_blockers.append("foundation-audit-policy-mismatch")
        record["blockers"] = sorted(set(target_blockers))
        record["outcome"] = (
            "platform-and-update-qualified" if not target_blockers else "blocked"
        )
    blockers = [
        "{0}:{1}".format(abi, blocker)
        for abi in TARGET_ABIS
        for blocker in normalized_targets[abi].get("blockers", [])
    ]
    if source.get("dirty") is not False:
        blockers.append("source:dirty-worktree")
    return {
        "schema": RELEASE_SCHEMA,
        "policy_sha256": policy.sha256,
        "source": dict(source),
        "targets": normalized_targets,
        "game_delivery": "external-install",
        "game_artifact_included": False,
        "alas_workload_qualified": False,
        "promotion": {
            "ceiling": "platform-and-update-qualified",
            "outcome": "pass" if not blockers else "blocked",
            "blockers": sorted(blockers),
        },
    }
