"""Supply-chain evidence for self-maintained Android image artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from .android_image_source import AndroidImageSourceLock


PROVENANCE_SCHEMA = "alas-headless.android-image-build-provenance/v1"
REPRODUCIBILITY_SCHEMA = "alas-headless.android-image-reproducibility/v1"
FORBIDDEN_GAME_TOKENS = ("com.bilibili.azurlane", "azurlane")
ABIS = ("x86_64", "arm64-v8a")


class AndroidImageSupplyChainError(ValueError):
    """Raised when release inputs do not prove their identity or license surface."""


def hash_file(path: Path) -> Mapping[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {
        "path": str(Path(path).resolve()),
        "bytes": size,
        "sha256": digest.hexdigest(),
    }


def _nonempty(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise AndroidImageSupplyChainError("{0} must be a non-empty file: {1}".format(label, path))


def _parse_named_paths(values: Iterable[str]) -> Sequence[Tuple[str, Path]]:
    parsed = []
    observed = set()
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name) is None:
            raise AndroidImageSupplyChainError("artifact must use name=path: {0}".format(value))
        if name in observed:
            raise AndroidImageSupplyChainError("duplicate artifact name: {0}".format(name))
        observed.add(name)
        parsed.append((name, Path(raw_path)))
    if not {"system.img", "vendor.img"}.issubset(observed):
        raise AndroidImageSupplyChainError("system.img and vendor.img artifacts are mandatory")
    return parsed


def create_build_provenance(
    source_lock: AndroidImageSourceLock,
    resolved_manifest: Path,
    abi: str,
    lunch: str,
    product_out: str,
    build_fingerprint: str,
    security_patch: str,
    artifacts: Iterable[str],
    sbom: Path,
    notices: Sequence[Path],
    installed_files: Path,
    host_preflight: Mapping[str, Any],
) -> Mapping[str, Any]:
    if abi not in ABIS:
        raise AndroidImageSupplyChainError("unsupported ABI: {0}".format(abi))
    expected_product = next(
        item for item in source_lock.document["products"] if item["abi"] == abi
    )
    if lunch != expected_product["lunch"] or product_out != expected_product["product_out"]:
        raise AndroidImageSupplyChainError("lunch/product_out do not match the source lock")
    _nonempty(resolved_manifest, "resolved manifest")
    if "<manifest" not in resolved_manifest.read_text(encoding="utf-8", errors="replace"):
        raise AndroidImageSupplyChainError("resolved manifest is not a repo manifest XML")
    _nonempty(sbom, "SBOM")
    sbom_value = json.loads(sbom.read_text(encoding="utf-8"))
    if not isinstance(sbom_value, Mapping) or sbom_value.get("spdxVersion") != "SPDX-2.3":
        raise AndroidImageSupplyChainError("SBOM must be AOSP SPDX 2.3 JSON")
    if not notices:
        raise AndroidImageSupplyChainError("at least one product NOTICE artifact is mandatory")
    for notice in notices:
        _nonempty(notice, "NOTICE")
    _nonempty(installed_files, "installed-files inventory")
    inventory = installed_files.read_text(encoding="utf-8", errors="replace").lower()
    forbidden = sorted(token for token in FORBIDDEN_GAME_TOKENS if token in inventory)
    if forbidden:
        raise AndroidImageSupplyChainError(
            "game artifact detected in installed-files inventory: {0}".format(",".join(forbidden))
        )
    if host_preflight.get("outcome") != "pass":
        raise AndroidImageSupplyChainError("build host preflight did not pass")
    if host_preflight.get("source_lock_sha256") != source_lock.sha256:
        raise AndroidImageSupplyChainError("build host preflight source lock mismatch")
    if not build_fingerprint.strip():
        raise AndroidImageSupplyChainError("build fingerprint is mandatory")
    if re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", security_patch) is None:
        raise AndroidImageSupplyChainError("security patch must use YYYY-MM-DD")

    artifact_records: Dict[str, Mapping[str, Any]] = {}
    for name, path in _parse_named_paths(artifacts):
        _nonempty(path, "build artifact")
        artifact_records[name] = hash_file(path)
    return {
        "schema": PROVENANCE_SCHEMA,
        "source_lock_sha256": source_lock.sha256,
        "resolved_manifest": hash_file(resolved_manifest),
        "target": {"abi": abi, "lunch": lunch, "product_out": product_out},
        "build_identity": {
            "fingerprint": build_fingerprint.strip(),
            "security_patch": security_patch,
        },
        "artifacts": artifact_records,
        "sbom": dict(hash_file(sbom), format="SPDX-2.3"),
        "notices": [hash_file(path) for path in notices],
        "installed_files": hash_file(installed_files),
        "host_preflight": dict(host_preflight),
        "game_delivery": "external-install",
        "game_artifact_included": False,
        "alas_workload_used": False,
    }


def compare_build_provenance(first: Mapping[str, Any], second: Mapping[str, Any]) -> Mapping[str, Any]:
    blockers = []
    for index, value in enumerate((first, second), 1):
        if value.get("schema") != PROVENANCE_SCHEMA:
            blockers.append("build-{0}-schema-mismatch".format(index))
        if value.get("game_artifact_included") is not False or value.get("alas_workload_used") is not False:
            blockers.append("build-{0}-scope-invalid".format(index))
    for key in ("source_lock_sha256", "resolved_manifest", "target"):
        left = first.get(key)
        right = second.get(key)
        if key == "resolved_manifest":
            left = left.get("sha256") if isinstance(left, Mapping) else None
            right = right.get("sha256") if isinstance(right, Mapping) else None
        if left != right:
            blockers.append("{0}-mismatch".format(key.replace("_", "-")))
    first_artifacts = first.get("artifacts", {})
    second_artifacts = second.get("artifacts", {})
    if not isinstance(first_artifacts, Mapping) or not isinstance(second_artifacts, Mapping):
        blockers.append("artifact-map-invalid")
    elif set(first_artifacts) != set(second_artifacts):
        blockers.append("artifact-set-mismatch")
    else:
        for name in first_artifacts:
            left = first_artifacts[name]
            right = second_artifacts[name]
            if not isinstance(left, Mapping) or not isinstance(right, Mapping) or (
                left.get("sha256") != right.get("sha256")
            ):
                blockers.append("artifact-digest-mismatch:{0}".format(name))
    return {
        "schema": REPRODUCIBILITY_SCHEMA,
        "outcome": "pass" if not blockers else "blocked",
        "blockers": sorted(blockers),
        "source_lock_sha256": first.get("source_lock_sha256"),
        "target": first.get("target"),
        "alas_workload_used": False,
    }
