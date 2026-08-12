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
PROVENANCE_SCHEMA = "alas-headless.android-image-build-provenance/v1"
REPRODUCIBILITY_SCHEMA = "alas-headless.android-image-reproducibility/v1"
ROLLBACK_SCHEMA = "alas-headless.redroid-image-rollback/v1"
OCI_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def valid_hashed_file(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and SHA256.fullmatch(str(value.get("sha256", ""))) is not None
        and int(value.get("bytes", 0)) > 0
    )


def evidence_file(value: Mapping[str, Any], blocker: str, blockers: list[str]) -> Any:
    identity = value.get("_evidence_file")
    if not valid_hashed_file(identity):
        blockers.append(blocker)
        return None
    return dict(identity)


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
    build_provenance: Optional[Mapping[str, Any]] = None,
    reproducibility_evidence: Optional[Mapping[str, Any]] = None,
    rollback_evidence: Optional[Mapping[str, Any]] = None,
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
        image["evidence_file"] = evidence_file(
            image_identity, "image-identity-evidence-file-invalid", blockers
        )
        image.pop("_evidence_file", None)
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
        if OCI_DIGEST.fullmatch(str(image_identity.get("platform_manifest_digest", ""))) is None:
            blockers.append("image-identity-platform-digest-invalid")
        descriptor = image_identity.get("platform_descriptor")
        platform_value = descriptor.get("platform", {}) if isinstance(descriptor, Mapping) else {}
        if (
            not isinstance(platform_value, Mapping)
            or platform_value.get("architecture") != expected_architecture
            or platform_value.get("os") != "linux"
        ):
            blockers.append("image-identity-platform-descriptor-invalid")
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
            "evidence_file": evidence_file(
                evidence, "{0}-evidence-file-invalid".format(gate), blockers
            ),
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
            "evidence_file": evidence_file(
                foundation_audit, "foundation-audit-evidence-file-invalid", blockers
            ),
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
            "evidence_file": evidence_file(
                update_evidence, "update-qualification-evidence-file-invalid", blockers
            ),
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

    provenance_summary = None
    if build_provenance is None:
        blockers.append("build-provenance-missing")
    else:
        provenance_summary = {
            "schema": build_provenance.get("schema"),
            "source_lock_sha256": build_provenance.get("source_lock_sha256"),
            "target": build_provenance.get("target"),
            "build_identity": build_provenance.get("build_identity"),
            "artifacts": build_provenance.get("artifacts"),
            "sbom": build_provenance.get("sbom"),
            "notices": build_provenance.get("notices"),
            "evidence_file": evidence_file(
                build_provenance, "build-provenance-evidence-file-invalid", blockers
            ),
        }
        target = build_provenance.get("target", {})
        if build_provenance.get("schema") != PROVENANCE_SCHEMA:
            blockers.append("build-provenance-schema-mismatch")
        if not isinstance(target, Mapping) or target.get("abi") != abi:
            blockers.append("build-provenance-abi-mismatch")
        if build_provenance.get("game_artifact_included") is not False or build_provenance.get("alas_workload_used") is not False:
            blockers.append("build-provenance-scope-invalid")
        artifacts = build_provenance.get("artifacts", {})
        if not isinstance(artifacts, Mapping) or not all(
            valid_hashed_file(artifacts.get(name)) for name in ("system.img", "vendor.img")
        ):
            blockers.append("build-provenance-artifacts-invalid")
        if not valid_hashed_file(build_provenance.get("resolved_manifest")):
            blockers.append("build-provenance-resolved-manifest-invalid")
        sbom = build_provenance.get("sbom")
        if not valid_hashed_file(sbom) or sbom.get("format") != "SPDX-2.3":
            blockers.append("build-provenance-sbom-invalid")
        notices = build_provenance.get("notices")
        if not isinstance(notices, list) or not notices or not all(valid_hashed_file(item) for item in notices):
            blockers.append("build-provenance-notices-invalid")
        if not valid_hashed_file(build_provenance.get("installed_files")):
            blockers.append("build-provenance-inventory-invalid")
        host_preflight = build_provenance.get("host_preflight")
        if not isinstance(host_preflight, Mapping) or host_preflight.get("outcome") != "pass":
            blockers.append("build-provenance-host-preflight-invalid")

    reproducibility_summary = None
    if reproducibility_evidence is None:
        blockers.append("reproducibility-evidence-missing")
    else:
        reproducibility_summary = dict(reproducibility_evidence)
        reproducibility_summary["evidence_file"] = evidence_file(
            reproducibility_evidence, "reproducibility-evidence-file-invalid", blockers
        )
        reproducibility_summary.pop("_evidence_file", None)
        target = reproducibility_evidence.get("target", {})
        if reproducibility_evidence.get("schema") != REPRODUCIBILITY_SCHEMA or reproducibility_evidence.get("outcome") != "pass":
            blockers.append("reproducibility-evidence-not-pass")
        if not isinstance(target, Mapping) or target.get("abi") != abi:
            blockers.append("reproducibility-evidence-abi-mismatch")
        if reproducibility_evidence.get("alas_workload_used") is not False:
            blockers.append("reproducibility-evidence-scope-invalid")
        if build_provenance is not None and (
            reproducibility_evidence.get("source_lock_sha256")
            != build_provenance.get("source_lock_sha256")
        ):
            blockers.append("reproducibility-evidence-source-lock-mismatch")

    rollback_summary = None
    if rollback_evidence is None:
        blockers.append("image-rollback-evidence-missing")
    else:
        rollback_summary = dict(rollback_evidence)
        rollback_summary["evidence_file"] = evidence_file(
            rollback_evidence, "image-rollback-evidence-file-invalid", blockers
        )
        rollback_summary.pop("_evidence_file", None)
        previous = str(rollback_evidence.get("previous_image_digest", ""))
        candidate = str(rollback_evidence.get("candidate_image_digest", ""))
        if rollback_evidence.get("schema") != ROLLBACK_SCHEMA or rollback_evidence.get("outcome") != "pass":
            blockers.append("image-rollback-evidence-not-pass")
        if rollback_evidence.get("abi") != abi:
            blockers.append("image-rollback-evidence-abi-mismatch")
        if OCI_DIGEST.fullmatch(previous) is None or OCI_DIGEST.fullmatch(candidate) is None or previous == candidate:
            blockers.append("image-rollback-digest-invalid")
        if rollback_evidence.get("candidate_userdata_preserved") is not True or rollback_evidence.get("rollback_snapshot_restored") is not True:
            blockers.append("image-rollback-userdata-not-proven")
        previous_fingerprint = str(rollback_evidence.get("previous_fingerprint_before", ""))
        candidate_fingerprint = str(rollback_evidence.get("candidate_fingerprint", ""))
        if not previous_fingerprint or not candidate_fingerprint or previous_fingerprint == candidate_fingerprint:
            blockers.append("image-rollback-candidate-identity-not-proven")
        if rollback_evidence.get("previous_fingerprint_after") != previous_fingerprint:
            blockers.append("image-rollback-previous-identity-not-restored")
        previous_api = str(rollback_evidence.get("previous_api_before", ""))
        if not previous_api or rollback_evidence.get("previous_api_after") != previous_api:
            blockers.append("image-rollback-previous-api-not-restored")
        if not str(rollback_evidence.get("candidate_api", "")):
            blockers.append("image-rollback-candidate-api-not-proven")
        if rollback_evidence.get("lab_cleaned") is not True:
            blockers.append("image-rollback-lab-not-cleaned")
        if rollback_evidence.get("game_installed") is not False or rollback_evidence.get("alas_workload_used") is not False:
            blockers.append("image-rollback-scope-invalid")
        if image_identity is not None and candidate != image_identity.get("manifest_digest"):
            blockers.append("image-rollback-candidate-mismatch")
        if image_artifact is not None:
            blockers.append("image-rollback-candidate-unbound")

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
        "build_provenance": provenance_summary,
        "reproducibility": reproducibility_summary,
        "image_rollback": rollback_summary,
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
        provenance = record.get("build_provenance")
        if not isinstance(provenance, Mapping) or provenance.get("source_lock_sha256") != source.get("source_lock_sha256"):
            target_blockers.append("build-provenance-source-lock-mismatch")
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
    if re.fullmatch(r"[0-9a-f]{64}", str(source.get("source_lock_sha256", ""))) is None:
        blockers.append("source:source-lock-missing")
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
