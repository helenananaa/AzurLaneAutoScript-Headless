"""Static policy for Android image work that does not require an ALAS workload."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Tuple


ANDROID_IMAGE_POLICY_SCHEMA = "alas-headless.android-image-policy/v2"
TOKEN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SUPPORTED_BACKENDS = frozenset(("kvm", "redroid", "arm64-qemu"))
SUPPORTED_ABIS = frozenset(("x86_64", "arm64-v8a"))

REQUIRED_UPDATE_PATHS = frozenset(
    ("package-replace", "split-package-replace", "in-app-resource-download")
)
REQUIRED_PROTECTED_CAPABILITIES = frozenset(
    (
        "android-framework",
        "art-runtime",
        "audio-framework",
        "dns",
        "download-provider",
        "external-app-storage",
        "hwui-egl",
        "input",
        "keystore",
        "logging-crash-evidence",
        "low-storage-signals",
        "network",
        "package-installer",
        "package-manager",
        "settings-provider",
        "surfaceflinger",
        "time-sync",
        "tls-ca-store",
        "user-storage-ready",
        "webview",
    )
)
REQUIRED_DEFERRED_OPTIMIZATIONS = frozenset(
    (
        "cpu-affinity",
        "cpuset",
        "governor",
        "instance-density",
        "null-refresh-rate",
        "pgo-with-alas-workload",
        "unity-worker-count",
        "vcpu-count",
    )
)
REQUIRED_QUALIFICATION_GATES = frozenset(
    (
        "cold-boot",
        "gles-contract",
        "observer-contract",
        "package-update-lab",
        "resource-update-lab",
        "restart-recovery",
        "rollback-drill",
        "source-lock",
        "unit-tests",
        "userdata-persistence",
        "unity-contract",
    )
)


class AndroidImagePolicyError(ValueError):
    pass


def _canonical_json_bytes(value: Any) -> bytes:
    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        return item

    return json.dumps(
        plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise AndroidImagePolicyError("policy field must be an object: {0}".format(key))
    return item


def _text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise AndroidImagePolicyError(
            "policy field must be non-empty text: {0}".format(key)
        )
    return item.strip()


def _exact_fields(value: Mapping[str, Any], section: str, expected: Iterable[str]) -> None:
    expected_set = set(expected)
    missing = sorted(expected_set - set(value))
    unknown = sorted(set(value) - expected_set)
    if missing or unknown:
        raise AndroidImagePolicyError(
            "policy section differs: {0} (missing={1}; unknown={2})".format(
                section, ",".join(missing), ",".join(unknown)
            )
        )


def _tokens(value: Mapping[str, Any], key: str) -> Tuple[str, ...]:
    items = value.get(key)
    if not isinstance(items, list) or not items:
        raise AndroidImagePolicyError("policy field must be a non-empty list: {0}".format(key))
    accepted = []
    for item in items:
        if not isinstance(item, str) or TOKEN_PATTERN.fullmatch(item) is None:
            raise AndroidImagePolicyError("policy list contains an invalid token: {0}".format(key))
        accepted.append(item)
    if len(set(accepted)) != len(accepted):
        raise AndroidImagePolicyError("policy list contains duplicates: {0}".format(key))
    return tuple(accepted)


@dataclass(frozen=True)
class AndroidImagePolicy:
    document: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AndroidImagePolicy":
        if not isinstance(value, dict):
            raise AndroidImagePolicyError("Android image policy must be a JSON object")
        _exact_fields(
            value,
            "root",
            (
                "schema",
                "policy_id",
                "game_delivery",
                "architectures",
                "protected_capabilities",
                "optimization_scope",
                "qualification",
            ),
        )
        if value.get("schema") != ANDROID_IMAGE_POLICY_SCHEMA:
            raise AndroidImagePolicyError("Android image policy schema mismatch")
        policy_id = _text(value, "policy_id")
        if TOKEN_PATTERN.fullmatch(policy_id) is None:
            raise AndroidImagePolicyError("policy_id must be a token")

        game = _mapping(value, "game_delivery")
        _exact_fields(
            game,
            "game_delivery",
            (
                "package",
                "mode",
                "supported_update_paths",
                "preserve_userdata",
                "public_release_allowed",
            ),
        )
        _text(game, "package")
        if game.get("mode") != "external-install":
            raise AndroidImagePolicyError("the game must remain external to the image")
        update_paths = frozenset(_tokens(game, "supported_update_paths"))
        if update_paths != REQUIRED_UPDATE_PATHS:
            raise AndroidImagePolicyError("game update paths do not match the required contract")
        if game.get("preserve_userdata") is not True:
            raise AndroidImagePolicyError("game updates must preserve per-instance userdata")
        if game.get("public_release_allowed") is not False:
            raise AndroidImagePolicyError("proprietary game artifacts cannot be public releases")

        architectures = value.get("architectures")
        if not isinstance(architectures, list) or not architectures:
            raise AndroidImagePolicyError("architectures must be a non-empty list")
        observed_abis = set()
        target_ids = set()
        for target in architectures:
            if not isinstance(target, dict):
                raise AndroidImagePolicyError("architecture targets must be objects")
            _exact_fields(target, "architecture", ("target_id", "abi", "backends"))
            target_id = _text(target, "target_id")
            if TOKEN_PATTERN.fullmatch(target_id) is None or target_id in target_ids:
                raise AndroidImagePolicyError("architecture target_id is invalid or duplicated")
            target_ids.add(target_id)
            abi = _text(target, "abi")
            if abi not in SUPPORTED_ABIS or abi in observed_abis:
                raise AndroidImagePolicyError("architecture ABI is unsupported or duplicated")
            observed_abis.add(abi)
            backends = frozenset(_tokens(target, "backends"))
            if not backends or not backends.issubset(SUPPORTED_BACKENDS):
                raise AndroidImagePolicyError("architecture contains an unsupported backend")
            if "arm64-qemu" in backends and abi != "arm64-v8a":
                raise AndroidImagePolicyError("arm64-qemu requires arm64-v8a")
        if observed_abis != set(SUPPORTED_ABIS):
            raise AndroidImagePolicyError("both x86_64 and arm64-v8a targets are required")

        protected = frozenset(_tokens(value, "protected_capabilities"))
        missing_protected = sorted(REQUIRED_PROTECTED_CAPABILITIES - protected)
        if missing_protected:
            raise AndroidImagePolicyError(
                "protected capabilities are missing: {0}".format(",".join(missing_protected))
            )

        scope = _mapping(value, "optimization_scope")
        _exact_fields(
            scope,
            "optimization_scope",
            ("allowed_without_alas_data", "deferred_until_alas_data"),
        )
        allowed = frozenset(_tokens(scope, "allowed_without_alas_data"))
        deferred = frozenset(_tokens(scope, "deferred_until_alas_data"))
        if allowed & deferred:
            raise AndroidImagePolicyError("allowed and deferred optimizations must be disjoint")
        missing_deferred = sorted(REQUIRED_DEFERRED_OPTIMIZATIONS - deferred)
        if missing_deferred:
            raise AndroidImagePolicyError(
                "workload-dependent optimizations are not deferred: {0}".format(
                    ",".join(missing_deferred)
                )
            )

        qualification = _mapping(value, "qualification")
        _exact_fields(qualification, "qualification", ("required_gates", "promotion_ceiling"))
        gates = frozenset(_tokens(qualification, "required_gates"))
        missing_gates = sorted(REQUIRED_QUALIFICATION_GATES - gates)
        if missing_gates:
            raise AndroidImagePolicyError(
                "qualification gates are missing: {0}".format(",".join(missing_gates))
            )
        if qualification.get("promotion_ceiling") != "platform-and-update-qualified":
            raise AndroidImagePolicyError(
                "promotion must stop before ALAS workload qualification"
            )

        plain = json.loads(_canonical_json_bytes(value).decode("utf-8"))
        digest = hashlib.sha256(_canonical_json_bytes(plain)).hexdigest()
        return cls(document=_freeze(plain), sha256=digest)
