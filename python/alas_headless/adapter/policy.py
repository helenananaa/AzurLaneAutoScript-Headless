"""Strict immutable run-policy/v1 parsing and identity binding."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .errors import RunPolicyError


RUN_POLICY_SCHEMA = "alas-headless.run-policy/v1"
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "upstream_alas_commit",
        "runtime_lock_sha256",
        "task_config_sha256",
        "grants",
        "deadline_seconds",
        "recovery_policy",
    }
)
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_MAXIMUM_POLICY_BYTES = 1_048_576
_MAXIMUM_INTEGER = 2_147_483_647


class RecoveryPolicy(str, Enum):
    QUALIFICATION_STOP = "qualification-stop"
    MANUAL_TAKEOVER = "manual-takeover"


@dataclass(frozen=True)
class RunPolicyIdentity:
    upstream_alas_commit: str
    runtime_lock_sha256: str
    task_config_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.upstream_alas_commit, str)
            or _COMMIT_PATTERN.fullmatch(self.upstream_alas_commit) is None
        ):
            raise RunPolicyError()
        for value in (self.runtime_lock_sha256, self.task_config_sha256):
            if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
                raise RunPolicyError()


@dataclass(frozen=True)
class RunPolicy:
    profile_id: str
    identity: RunPolicyIdentity
    grants: Mapping[str, int]
    deadline_seconds: int
    recovery_policy: RecoveryPolicy
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _TOKEN_PATTERN.fullmatch(self.profile_id) is None
        ):
            raise RunPolicyError()
        if not isinstance(self.identity, RunPolicyIdentity):
            raise RunPolicyError()
        if not isinstance(self.grants, Mapping):
            raise RunPolicyError()
        normalized: dict[str, int] = {}
        for capability, amount in self.grants.items():
            if (
                not isinstance(capability, str)
                or _TOKEN_PATTERN.fullmatch(capability) is None
                or isinstance(amount, bool)
                or not isinstance(amount, int)
                or amount < 0
                or amount > _MAXIMUM_INTEGER
            ):
                raise RunPolicyError()
            normalized[capability] = amount
        if not normalized:
            raise RunPolicyError()
        if (
            isinstance(self.deadline_seconds, bool)
            or not isinstance(self.deadline_seconds, int)
            or self.deadline_seconds < 0
            or self.deadline_seconds > _MAXIMUM_INTEGER
        ):
            raise RunPolicyError()
        if not isinstance(self.recovery_policy, RecoveryPolicy):
            raise RunPolicyError()
        object.__setattr__(
            self,
            "grants",
            MappingProxyType(dict(sorted(normalized.items()))),
        )
        object.__setattr__(
            self,
            "sha256",
            hashlib.sha256(_canonical_bytes(self.document())).hexdigest(),
        )

    @property
    def upstream_alas_commit(self) -> str:
        return self.identity.upstream_alas_commit

    @property
    def runtime_lock_sha256(self) -> str:
        return self.identity.runtime_lock_sha256

    @property
    def task_config_sha256(self) -> str:
        return self.identity.task_config_sha256

    @property
    def total_grants(self) -> int:
        return sum(self.grants.values())

    def document(self) -> Mapping[str, Any]:
        return {
            "schema": RUN_POLICY_SCHEMA,
            "profile_id": self.profile_id,
            "upstream_alas_commit": self.upstream_alas_commit,
            "runtime_lock_sha256": self.runtime_lock_sha256,
            "task_config_sha256": self.task_config_sha256,
            "grants": dict(self.grants),
            "deadline_seconds": self.deadline_seconds,
            "recovery_policy": self.recovery_policy.value,
        }

    def require_identity(self, expected: RunPolicyIdentity) -> None:
        if not isinstance(expected, RunPolicyIdentity) or self.identity != expected:
            raise RunPolicyError()


class _DuplicateField(ValueError):
    pass


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> Mapping[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise _DuplicateField(key)
        value[key] = child
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(value)


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunPolicyError() from exc


def canonical_run_policy_json(policy: RunPolicy) -> str:
    if not isinstance(policy, RunPolicy):
        raise TypeError("canonical run policy requires a RunPolicy")
    return _canonical_bytes(policy.document()).decode("utf-8") + "\n"


def _parse_document(
    document: Mapping[str, Any],
    expected_identity: RunPolicyIdentity | None,
) -> RunPolicy:
    if not isinstance(document, Mapping) or set(document) != _TOP_LEVEL_FIELDS:
        raise RunPolicyError()
    if document.get("schema") != RUN_POLICY_SCHEMA:
        raise RunPolicyError()
    profile_id = document.get("profile_id")
    if not isinstance(profile_id, str) or _TOKEN_PATTERN.fullmatch(profile_id) is None:
        raise RunPolicyError()
    identity = RunPolicyIdentity(
        upstream_alas_commit=document.get("upstream_alas_commit"),
        runtime_lock_sha256=document.get("runtime_lock_sha256"),
        task_config_sha256=document.get("task_config_sha256"),
    )
    if expected_identity is not None and identity != expected_identity:
        raise RunPolicyError()
    raw_grants = document.get("grants")
    if not isinstance(raw_grants, Mapping):
        raise RunPolicyError()
    deadline_seconds = document.get("deadline_seconds")
    raw_recovery = document.get("recovery_policy")
    try:
        recovery_policy = RecoveryPolicy(raw_recovery)
    except (TypeError, ValueError) as exc:
        raise RunPolicyError() from exc
    return RunPolicy(
        profile_id=profile_id,
        identity=identity,
        grants=raw_grants,
        deadline_seconds=deadline_seconds,
        recovery_policy=recovery_policy,
    )


def parse_run_policy(
    text: str,
    *,
    expected_identity: RunPolicyIdentity | None = None,
) -> RunPolicy:
    if not isinstance(text, str):
        raise TypeError("run policy source must be text")
    try:
        encoded_size = len(text.encode("utf-8"))
    except UnicodeError as exc:
        raise RunPolicyError() from exc
    if not text or encoded_size > _MAXIMUM_POLICY_BYTES:
        raise RunPolicyError()
    if expected_identity is not None and not isinstance(
        expected_identity, RunPolicyIdentity
    ):
        raise TypeError("expected policy identity is malformed")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, _DuplicateField, ValueError) as exc:
        raise RunPolicyError() from exc
    return _parse_document(document, expected_identity)


def load_run_policy(
    path: Path,
    *,
    expected_identity: RunPolicyIdentity | None = None,
) -> RunPolicy:
    if not isinstance(path, Path):
        raise TypeError("run policy path must be a Path")
    try:
        size = path.stat().st_size
        if size <= 0 or size > _MAXIMUM_POLICY_BYTES:
            raise RunPolicyError()
        text = path.read_text(encoding="utf-8")
    except RunPolicyError:
        raise
    except (OSError, UnicodeError) as exc:
        raise RunPolicyError() from exc
    return parse_run_policy(text, expected_identity=expected_identity)
