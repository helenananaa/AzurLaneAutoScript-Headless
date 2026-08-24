"""Host-only authority and lifecycle for bounded live-validation workers.

The security boundary is deliberately narrow: a directly invoked runner or a
self-consistent environment/control file is not a worker.  A worker activates
only after reading a one-time message from an anonymous OS pipe inherited from
its real parent, and the parent sends that message only after assigning the
worker to a kill-on-close Windows Job Object.  Same-user arbitrary native code
can still duplicate handles or modify Python and is outside this boundary.

Nothing in this module understands game pages, navigation, or task flow.  The
Job Object contains the worker host process and children it starts while
active.  It never acquires handles to, or operates on, the game, emulator, or
pre-existing ADB server processes.
"""

from __future__ import annotations

import ctypes
import base64
import hashlib
import hmac
import json
import math
import os
import re
import signal
import stat
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple


MIN_TOTAL_DEADLINE_SECONDS = 120
MAX_TOTAL_DEADLINE_SECONDS = 1800
WORKER_CLEANUP_GRACE_SECONDS = 45.0
WORKER_FORCE_STOP_GRACE_SECONDS = 5.0
WORKER_CONTROL_SCHEMA = "alas-headless.runner-worker-control/v5"
WORKER_BINDING_SCHEMA = "alas-headless.runner-worker-binding/v2"
WORKER_ACTIVATION_SCHEMA = "ALASACT2"
WORKER_RESULT_SCHEMA = "alas-headless.runner-worker-result/v2"
WORKER_CLEANUP_SCHEMA = "alas-headless.runner-worker-cleanup/v2"
FORWARD_LEASE_SCHEMA = "alas-headless.runner-forward-lease/v2"
CONFIG_OWNERSHIP_SCHEMA = "alas-headless.runner-config-ownership/v1"
CONFIG_MARKER_SCHEMA = "alas-headless.eventsp-config-provenance/v2"
CONFIG_MARKER_FIELD = "_alas_headless_eventsp_provenance"
WORKER_TERMINAL_SCHEMA = "alas-headless.runner-worker-terminal/v1"
WORKER_ROLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_ROLE"
WORKER_CONTROL_ENV = "ALAS_EVENT_RUNNER_INTERNAL_CONTROL"
WORKER_ACTIVATION_HANDLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_ACTIVATION_HANDLE"
WORKER_CONTROL_HANDLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_CONTROL_HANDLE"
WORKER_CONFIG_HANDLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_CONFIG_HANDLE"
WORKER_RESULT_HANDLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_RESULT_HANDLE"
WORKER_CLEANUP_HANDLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_CLEANUP_HANDLE"
WORKER_LEASE_HANDLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_LEASE_HANDLE"
WORKER_SEED_HANDLE_ENV = "ALAS_EVENT_RUNNER_INTERNAL_SEED_HANDLE"
SEED_SOURCE_SCHEMA = "alas-headless.runner-seed-source/v1"

_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_PROCESS_IDENTITY = re.compile(r"^[0-9]+:[0-9]+$")
_LOCAL_FORWARD = re.compile(r"^tcp:([1-9][0-9]{0,4})$")
_REMOTE_FORWARD = re.compile(r"^localabstract:alas\.g3\.([1-9][0-9]*)$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_EXCEPTION_TYPES = frozenset(
    {
        "RunnerStopRequested",
        "SystemExit",
        "KeyboardInterrupt",
        "TimeoutError",
        "OSError",
        "RuntimeError",
        "ValueError",
        "TypeError",
        "AssertionError",
        "Exception",
        "BaseException",
    }
)
_ACTIVATION_MAGIC = WORKER_ACTIVATION_SCHEMA.encode("ascii")
_ACTIVATION_TOKEN_BYTES = 32
_ACTIVATION_DIGEST_BYTES = 32
ACTIVATION_RECORD_BYTES = (
    len(_ACTIVATION_MAGIC) + _ACTIVATION_TOKEN_BYTES + _ACTIVATION_DIGEST_BYTES
)
if ACTIVATION_RECORD_BYTES > 512:
    raise RuntimeError("runner activation capability exceeds its hard bound")
_MAX_CONTROL_BYTES = 512 * 1024
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_WORKER_RESULT_BYTES = 2 * 1024 * 1024
MAX_IMMUTABLE_ARTIFACT_BYTES = MAX_WORKER_RESULT_BYTES
MAX_TERMINAL_MESSAGE_CHARS = 2048
WORKER_PHASES = (
    "pre_init",
    "config_write",
    "alas_import",
    "alas_construct",
    "startup",
    "task_run",
    "post_run",
    "cleanup",
    "result_serialize",
)
WORKER_EXECUTION_STATES = ("not_started", "started", "unknown", "finished")
BOUND_RECORD_SCHEMA = "alas-headless.runner-bound-record/v1"
RECORD_RESULT = "worker-result/v1"
RECORD_CLEANUP = "worker-cleanup/v1"
RECORD_TERMINAL = "worker-terminal/v1"
RECORD_FORWARD_LEASE = "forward-lease/v1"
RECORD_WORKER_CONTROL = "worker-control/v1"
_RECORD_PURPOSES = frozenset(
    (
        RECORD_RESULT,
        RECORD_CLEANUP,
        RECORD_TERMINAL,
        RECORD_FORWARD_LEASE,
        RECORD_WORKER_CONTROL,
    )
)
_WORKER_BUDGET_FIELDS = frozenset(
    {
        "stage_entry",
        "fleet_mutation",
        "sortie",
        "combat",
        "grid_click",
        "viewport_swipe",
        "camera_positioning",
        "recovery_total",
    }
)


class RunnerStopRequested(BaseException):
    """Cooperative main-thread unwind requested by the parent supervisor."""


def _strict_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " is malformed")
    return value


def _strict_positive_int(value: Any, label: str) -> int:
    result = _strict_nonnegative_int(value, label)
    if result == 0:
        raise ValueError(label + " is malformed")
    return result


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def bind_record(
    control: "WorkerControl", purpose: str, payload: Mapping[str, Any]
) -> Mapping[str, Any]:
    return _bind_record_to_binding(control.binding, purpose, payload)


def _bind_record_to_binding(
    binding: "RunBinding", purpose: str, payload: Mapping[str, Any]
) -> Mapping[str, Any]:
    if purpose not in _RECORD_PURPOSES:
        raise ValueError("runner record purpose is unsupported")
    if not isinstance(payload, Mapping):
        raise ValueError("runner record payload is malformed")
    return {
        "schema": BOUND_RECORD_SCHEMA,
        "purpose": purpose,
        "binding_digest": binding_digest(binding),
        "payload": dict(payload),
    }


def verify_bound_record(
    control: "WorkerControl", purpose: str, value: Mapping[str, Any]
) -> Mapping[str, Any]:
    return _verify_bound_record_for_binding(control.binding, purpose, value)


def _verify_bound_record_for_binding(
    binding: "RunBinding", purpose: str, value: Mapping[str, Any]
) -> Mapping[str, Any]:
    expected = {"schema", "purpose", "binding_digest", "payload"}
    if (
        purpose not in _RECORD_PURPOSES
        or not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("schema") != BOUND_RECORD_SCHEMA
        or value.get("purpose") != purpose
        or value.get("binding_digest") != binding_digest(binding)
        or not isinstance(value.get("payload"), Mapping)
    ):
        raise ValueError("runner bound record is malformed or belongs to another run")
    return dict(value["payload"])


def validate_config_basename(run_id: str, basename: Any) -> str:
    """Accept only the single ASCII spelling reserved for this run."""

    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("worker run id is malformed")
    expected = "_codex_event_live_eventsp_" + run_id + ".json"
    if not isinstance(basename, str):
        raise ValueError("worker config basename is malformed")
    try:
        basename.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("worker config basename must be ASCII") from exc
    if (
        basename != expected
        or basename.casefold() != expected
        or any(separator in basename for separator in ("/", "\\", ":"))
        or basename.endswith((".", " "))
    ):
        raise ValueError("worker config basename is not the exact run-owned name")
    return basename


@dataclass(frozen=True)
class FileIdentity:
    volume_serial: int
    file_id: int

    def __post_init__(self) -> None:
        _strict_nonnegative_int(self.volume_serial, "file volume serial")
        _strict_positive_int(self.file_id, "file identity")

    def to_mapping(self) -> Mapping[str, int]:
        return {"volume_serial": self.volume_serial, "file_id": self.file_id}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FileIdentity":
        if not isinstance(value, Mapping) or set(value) != {
            "volume_serial",
            "file_id",
        }:
            raise ValueError("file identity is malformed")
        return cls(
            volume_serial=value.get("volume_serial"),
            file_id=value.get("file_id"),
        )


@dataclass(frozen=True)
class ConfigFileState:
    exists: bool
    identity: Optional[FileIdentity]
    attributes: Optional[int]
    link_count: Optional[int]
    size: Optional[int]
    is_directory: bool
    is_reparse_point: bool
    marker_verified: bool
    marker_error: Optional[str] = None

    def __post_init__(self) -> None:
        for label, value in (
            ("exists", self.exists),
            ("directory", self.is_directory),
            ("reparse", self.is_reparse_point),
            ("marker verified", self.marker_verified),
        ):
            if not isinstance(value, bool):
                raise ValueError("config state {0} flag is malformed".format(label))
        if not self.exists:
            if (
                any(
                    value is not None
                    for value in (
                        self.identity,
                        self.attributes,
                        self.link_count,
                        self.size,
                        self.marker_error,
                    )
                )
                or self.is_directory
                or self.is_reparse_point
                or self.marker_verified
            ):
                raise ValueError("absent config state contains file metadata")
            return
        if not isinstance(self.identity, FileIdentity):
            raise ValueError("config state identity is malformed")
        _strict_nonnegative_int(self.attributes, "config attributes")
        _strict_positive_int(self.link_count, "config link count")
        _strict_nonnegative_int(self.size, "config size")
        if self.marker_verified == (self.marker_error is not None):
            raise ValueError("config marker state is inconsistent")
        if self.marker_error is not None and (
            not isinstance(self.marker_error, str) or not self.marker_error
        ):
            raise ValueError("config marker error is malformed")

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "exists": self.exists,
            "identity": self.identity.to_mapping() if self.identity else None,
            "attributes": self.attributes,
            "link_count": self.link_count,
            "size": self.size,
            "is_directory": self.is_directory,
            "is_reparse_point": self.is_reparse_point,
            "marker_verified": self.marker_verified,
            "marker_error": self.marker_error,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConfigFileState":
        expected = {
            "exists",
            "identity",
            "attributes",
            "link_count",
            "size",
            "is_directory",
            "is_reparse_point",
            "marker_verified",
            "marker_error",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("config state is malformed")
        identity_value = value.get("identity")
        return cls(
            exists=value.get("exists"),
            identity=(
                FileIdentity.from_mapping(identity_value)
                if identity_value is not None
                else None
            ),
            attributes=value.get("attributes"),
            link_count=value.get("link_count"),
            size=value.get("size"),
            is_directory=value.get("is_directory"),
            is_reparse_point=value.get("is_reparse_point"),
            marker_verified=value.get("marker_verified"),
            marker_error=value.get("marker_error"),
        )


@dataclass(frozen=True, order=True)
class ForwardRecord:
    serial: str
    local: str
    remote: str

    def __post_init__(self) -> None:
        if not isinstance(self.serial, str) or not self.serial.strip():
            raise ValueError("forward serial is missing")
        if not isinstance(self.local, str):
            raise ValueError("forward local endpoint is not an exact TCP port")
        local_match = _LOCAL_FORWARD.fullmatch(self.local)
        if local_match is None or int(local_match.group(1)) > 65535:
            raise ValueError("forward local endpoint is not an exact TCP port")
        if not isinstance(self.remote, str) or not self.remote.strip():
            raise ValueError("forward remote endpoint is missing")

    @property
    def port(self) -> int:
        match = _LOCAL_FORWARD.fullmatch(self.local)
        assert match is not None
        return int(match.group(1))

    def to_mapping(self) -> Mapping[str, Any]:
        return {"serial": self.serial, "local": self.local, "remote": self.remote}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ForwardRecord":
        if not isinstance(value, Mapping):
            raise ValueError("forward record is malformed")
        return cls(value.get("serial"), value.get("local"), value.get("remote"))


@dataclass(frozen=True)
class RunBinding:
    run_id: str
    token_digest: str
    task: str
    stage: str
    event: str
    deadline_seconds: int
    parent_pid: int
    parent_identity: str
    worker_pid: int
    config_path: Path
    control_path: Path
    result_path: Path
    cleanup_path: Path
    lease_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or _RUN_ID.fullmatch(self.run_id) is None:
            raise ValueError("worker run id is malformed")
        if (
            not isinstance(self.token_digest, str)
            or _SHA256_HEX.fullmatch(self.token_digest) is None
        ):
            raise ValueError("worker token digest is malformed")
        if (
            self.task != "EventSp"
            or not isinstance(self.stage, str)
            or self.stage.strip().lower() != "sp"
        ):
            raise ValueError("worker task/stage binding is unsupported")
        if not isinstance(self.event, str) or not self.event.strip():
            raise ValueError("worker event binding is missing")
        validate_total_deadline(self.deadline_seconds)
        for label, value in (
            ("parent", self.parent_pid),
            ("worker", self.worker_pid),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("worker {0} PID is invalid".format(label))
        if (
            not isinstance(self.parent_identity, str)
            or _PROCESS_IDENTITY.fullmatch(self.parent_identity) is None
        ):
            raise ValueError("worker parent identity is malformed")
        paths = (
            self.config_path,
            self.control_path,
            self.result_path,
            self.cleanup_path,
            self.lease_path,
        )
        if any(not isinstance(path, Path) or not path.is_absolute() for path in paths):
            raise ValueError("worker paths must be absolute")
        if len({str(path) for path in paths}) != len(paths):
            raise ValueError("worker paths must be distinct")
        validate_config_basename(self.run_id, self.config_path.name)

    @property
    def config_name(self) -> str:
        return self.config_path.stem

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "schema": WORKER_BINDING_SCHEMA,
            "run_id": self.run_id,
            "token_digest": self.token_digest,
            "task": self.task,
            "stage": self.stage,
            "event": self.event,
            "deadline_seconds": self.deadline_seconds,
            "parent_pid": self.parent_pid,
            "parent_identity": self.parent_identity,
            "worker_pid": self.worker_pid,
            "config_path": str(self.config_path),
            "control_path": str(self.control_path),
            "result_path": str(self.result_path),
            "cleanup_path": str(self.cleanup_path),
            "lease_path": str(self.lease_path),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RunBinding":
        expected = {
            "schema",
            "run_id",
            "token_digest",
            "task",
            "stage",
            "event",
            "deadline_seconds",
            "parent_pid",
            "parent_identity",
            "worker_pid",
            "config_path",
            "control_path",
            "result_path",
            "cleanup_path",
            "lease_path",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != WORKER_BINDING_SCHEMA
        ):
            raise ValueError("worker binding schema is unsupported")
        for path_field in (
            "config_path",
            "control_path",
            "result_path",
            "cleanup_path",
            "lease_path",
        ):
            if not isinstance(value.get(path_field), str) or not value[path_field]:
                raise ValueError("worker binding path is malformed")
        return cls(
            run_id=value.get("run_id"),
            token_digest=value.get("token_digest"),
            task=value.get("task"),
            stage=value.get("stage"),
            event=value.get("event"),
            deadline_seconds=value.get("deadline_seconds"),
            parent_pid=value.get("parent_pid"),
            parent_identity=value.get("parent_identity"),
            worker_pid=value.get("worker_pid"),
            config_path=Path(value.get("config_path", "")),
            control_path=Path(value.get("control_path", "")),
            result_path=Path(value.get("result_path", "")),
            cleanup_path=Path(value.get("cleanup_path", "")),
            lease_path=Path(value.get("lease_path", "")),
        )


def binding_digest(binding: RunBinding) -> str:
    if not isinstance(binding, RunBinding):
        raise ValueError("worker binding is malformed")
    return _sha256_hex(_canonical_bytes(binding.to_mapping()))


def _config_control_core(
    binding: RunBinding,
    *,
    config_root: Path,
    root_identity: FileIdentity,
    initial_identity: FileIdentity,
    control_identity: FileIdentity,
) -> Mapping[str, Any]:
    return {
        "schema": "alas-headless.runner-config-control-core/v1",
        "binding_digest": binding_digest(binding),
        "config_root": str(config_root),
        "config_path": str(binding.config_path),
        "config_basename": binding.config_path.name,
        "control_path": str(binding.control_path),
        "result_path": str(binding.result_path),
        "cleanup_path": str(binding.cleanup_path),
        "forward_lease_path": str(binding.lease_path),
        "root_identity": root_identity.to_mapping(),
        "initial_identity": initial_identity.to_mapping(),
        "control_identity": control_identity.to_mapping(),
        "marker_schema": CONFIG_MARKER_SCHEMA,
    }


def _validate_activation_token(token: bytes) -> bytes:
    if not isinstance(token, bytes) or len(token) != _ACTIVATION_TOKEN_BYTES:
        raise ValueError("worker activation token is malformed")
    return token


def expected_config_marker(
    binding: RunBinding, control_core_digest: str
) -> Mapping[str, Any]:
    if (
        not isinstance(control_core_digest, str)
        or _SHA256_HEX.fullmatch(control_core_digest) is None
    ):
        raise ValueError("config control digest is malformed")
    return {
        "schema": CONFIG_MARKER_SCHEMA,
        "run_id": binding.run_id,
        "task": binding.task,
        "stage": binding.stage,
        "event": binding.event,
        "config_basename": binding.config_path.name,
        "control_digest": control_core_digest,
    }


@dataclass(frozen=True)
class ConfigOwnership:
    config_root: Path
    root_identity: FileIdentity
    initial_identity: FileIdentity
    control_identity: FileIdentity
    binding_digest: str
    control_core_digest: str
    marker_schema: str
    marker_digest: str
    def __post_init__(self) -> None:
        if not isinstance(self.config_root, Path) or not self.config_root.is_absolute():
            raise ValueError("config ownership root must be absolute")
        if any(
            not isinstance(item, FileIdentity)
            for item in (
                self.root_identity,
                self.initial_identity,
                self.control_identity,
            )
        ):
            raise ValueError("config ownership identity is malformed")
        for label, value in (
            ("binding", self.binding_digest),
            ("control", self.control_core_digest),
            ("marker", self.marker_digest),
        ):
            if not isinstance(value, str) or _SHA256_HEX.fullmatch(value) is None:
                raise ValueError(
                    "config ownership {0} digest is malformed".format(label)
                )
        if self.marker_schema != CONFIG_MARKER_SCHEMA:
            raise ValueError("config ownership marker schema is unsupported")

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "schema": CONFIG_OWNERSHIP_SCHEMA,
            "config_root": str(self.config_root),
            "root_identity": self.root_identity.to_mapping(),
            "initial_identity": self.initial_identity.to_mapping(),
            "control_identity": self.control_identity.to_mapping(),
            "binding_digest": self.binding_digest,
            "control_core_digest": self.control_core_digest,
            "marker_schema": self.marker_schema,
            "marker_digest": self.marker_digest,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConfigOwnership":
        expected = {
            "schema",
            "config_root",
            "root_identity",
            "initial_identity",
            "control_identity",
            "binding_digest",
            "control_core_digest",
            "marker_schema",
            "marker_digest",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != CONFIG_OWNERSHIP_SCHEMA
            or not isinstance(value.get("config_root"), str)
        ):
            raise ValueError("config ownership is malformed")
        return cls(
            config_root=Path(value["config_root"]),
            root_identity=FileIdentity.from_mapping(value.get("root_identity")),
            initial_identity=FileIdentity.from_mapping(value.get("initial_identity")),
            control_identity=FileIdentity.from_mapping(value.get("control_identity")),
            binding_digest=value.get("binding_digest"),
            control_core_digest=value.get("control_core_digest"),
            marker_schema=value.get("marker_schema"),
            marker_digest=value.get("marker_digest"),
        )


def build_config_ownership(
    binding: RunBinding,
    *,
    config_root: Path,
    root_identity: FileIdentity,
    initial_identity: FileIdentity,
    control_identity: FileIdentity,
) -> ConfigOwnership:
    if config_root != binding.config_path.parent:
        raise ValueError("config ownership root/path binding changed")
    validate_config_basename(binding.run_id, binding.config_path.name)
    core = _config_control_core(
        binding,
        config_root=config_root,
        root_identity=root_identity,
        initial_identity=initial_identity,
        control_identity=control_identity,
    )
    control_core_digest = _sha256_hex(_canonical_bytes(core))
    marker = expected_config_marker(binding, control_core_digest)
    ownership = ConfigOwnership(
        config_root=config_root,
        root_identity=root_identity,
        initial_identity=initial_identity,
        control_identity=control_identity,
        binding_digest=binding_digest(binding),
        control_core_digest=control_core_digest,
        marker_schema=CONFIG_MARKER_SCHEMA,
        marker_digest=_sha256_hex(_canonical_bytes(marker)),
    )
    return ownership


def validate_config_ownership(binding: RunBinding, ownership: ConfigOwnership) -> None:
    if ownership.config_root != binding.config_path.parent:
        raise ValueError("config ownership root/path binding changed")
    validate_config_basename(binding.run_id, binding.config_path.name)
    core = _config_control_core(
        binding,
        config_root=ownership.config_root,
        root_identity=ownership.root_identity,
        initial_identity=ownership.initial_identity,
        control_identity=ownership.control_identity,
    )
    if ownership.binding_digest != binding_digest(
        binding
    ) or ownership.control_core_digest != _sha256_hex(_canonical_bytes(core)):
        raise ValueError("config ownership digest binding changed")
    marker = expected_config_marker(binding, ownership.control_core_digest)
    if ownership.marker_digest != _sha256_hex(_canonical_bytes(marker)):
        raise ValueError("config ownership marker digest changed")


def insert_config_marker(
    payload: Mapping[str, Any], binding: RunBinding, ownership: ConfigOwnership
) -> dict[str, Any]:
    """Insert only under ALAS's pinned preserved storage value."""

    validate_config_ownership(binding, ownership)
    if not isinstance(payload, dict):
        raise ValueError("ALAS config payload must be a mutable object")
    event_sp = payload.get("EventSp")
    storage_group = event_sp.get("Storage") if isinstance(event_sp, dict) else None
    storage = storage_group.get("Storage") if isinstance(storage_group, dict) else None
    if not isinstance(storage, dict):
        raise ValueError("EventSp preserved storage field is unavailable")
    if CONFIG_MARKER_FIELD in storage:
        raise ValueError("EventSp provenance marker already exists")
    marker = expected_config_marker(binding, ownership.control_core_digest)
    if _sha256_hex(_canonical_bytes(marker)) != ownership.marker_digest:
        raise ValueError("EventSp provenance marker digest changed")
    storage[CONFIG_MARKER_FIELD] = marker
    return payload


def validate_config_marker(
    payload: Mapping[str, Any], binding: RunBinding, ownership: ConfigOwnership
) -> None:
    validate_config_ownership(binding, ownership)
    event_sp = payload.get("EventSp") if isinstance(payload, Mapping) else None
    storage_group = event_sp.get("Storage") if isinstance(event_sp, Mapping) else None
    storage = (
        storage_group.get("Storage") if isinstance(storage_group, Mapping) else None
    )
    marker = storage.get(CONFIG_MARKER_FIELD) if isinstance(storage, Mapping) else None
    expected = expected_config_marker(binding, ownership.control_core_digest)
    if not isinstance(marker, Mapping) or set(marker) != set(expected):
        raise ValueError("EventSp provenance marker is missing or malformed")
    if dict(marker) != dict(expected):
        raise ValueError("EventSp provenance marker binding changed")
    if _sha256_hex(_canonical_bytes(dict(marker))) != ownership.marker_digest:
        raise ValueError("EventSp provenance marker digest changed")


@dataclass(frozen=True)
class WorkerHandles:
    control: int
    config: int
    result: int
    cleanup: int
    lease: int
    seed: int

    def __post_init__(self) -> None:
        values = (
            self.control,
            self.config,
            self.result,
            self.cleanup,
            self.lease,
            self.seed,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in values
        ):
            raise ValueError("worker inherited output handle is invalid")
        if len(set(values)) != len(values):
            raise ValueError("worker inherited output handles must be distinct")

    def to_mapping(self) -> Mapping[str, int]:
        return {
            "control": self.control,
            "config": self.config,
            "result": self.result,
            "cleanup": self.cleanup,
            "lease": self.lease,
            "seed": self.seed,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkerHandles":
        if not isinstance(value, Mapping) or set(value) != {
            "control",
            "config",
            "result",
            "cleanup",
            "lease",
            "seed",
        }:
            raise ValueError("worker handle binding is malformed")
        return cls(
            control=value.get("control"),
            config=value.get("config"),
            result=value.get("result"),
            cleanup=value.get("cleanup"),
            lease=value.get("lease"),
            seed=value.get("seed"),
        )


@dataclass(frozen=True)
class SeedSource:
    capability: str
    seed_name: str
    path: Path
    root_path: Path
    root_identity: FileIdentity
    identity: FileIdentity
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability, str)
            or not self.capability
            or not isinstance(self.seed_name, str)
            or not self.seed_name
        ):
            raise ValueError("worker seed capability is malformed")
        if (
            not isinstance(self.path, Path)
            or not self.path.is_absolute()
            or not isinstance(self.root_path, Path)
            or not self.root_path.is_absolute()
            or self.path.parent != self.root_path
        ):
            raise ValueError("worker seed path binding is malformed")
        if not isinstance(self.root_identity, FileIdentity) or not isinstance(
            self.identity, FileIdentity
        ):
            raise ValueError("worker seed identity is malformed")
        if (
            isinstance(self.size, bool)
            or not isinstance(self.size, int)
            or self.size <= 0
        ):
            raise ValueError("worker seed size is malformed")
        if (
            not isinstance(self.sha256, str)
            or _SHA256_HEX.fullmatch(self.sha256) is None
        ):
            raise ValueError("worker seed digest is malformed")

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "schema": SEED_SOURCE_SCHEMA,
            "capability": self.capability,
            "seed_name": self.seed_name,
            "path": str(self.path),
            "root_path": str(self.root_path),
            "root_identity": self.root_identity.to_mapping(),
            "identity": self.identity.to_mapping(),
            "size": self.size,
            "sha256": self.sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SeedSource":
        expected = {
            "schema",
            "capability",
            "seed_name",
            "path",
            "root_path",
            "root_identity",
            "identity",
            "size",
            "sha256",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != SEED_SOURCE_SCHEMA
            or not isinstance(value.get("path"), str)
            or not isinstance(value.get("root_path"), str)
        ):
            raise ValueError("worker seed source schema is unsupported")
        return cls(
            capability=value.get("capability"),
            seed_name=value.get("seed_name"),
            path=Path(value["path"]),
            root_path=Path(value["root_path"]),
            root_identity=FileIdentity.from_mapping(value.get("root_identity")),
            identity=FileIdentity.from_mapping(value.get("identity")),
            size=value.get("size"),
            sha256=value.get("sha256"),
        )


@dataclass(frozen=True)
class WorkerControl:
    binding: RunBinding
    config_ownership: ConfigOwnership
    seed_source: SeedSource
    serial: str
    verified_game_pid: int
    starting_forwards: Tuple[ForwardRecord, ...]
    handles: WorkerHandles
    materialization_control: Mapping[str, Any] = field(default_factory=dict)
    execution_budgets: Mapping[str, int] = field(default_factory=dict)
    _activation_verified: bool = field(
        default=False, init=False, compare=False, repr=False
    )
    _activation_token: bytes | None = field(
        default=None, init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.config_ownership, ConfigOwnership):
            raise ValueError("worker config ownership is malformed")
        if not isinstance(self.seed_source, SeedSource):
            raise ValueError("worker seed source is malformed")
        if (
            self.seed_source.root_path != self.binding.config_path.parent
            or self.config_ownership.config_root != self.binding.config_path.parent
        ):
            raise ValueError("worker seed/config root binding changed")
        if self.seed_source.root_identity != self.config_ownership.root_identity:
            raise ValueError("worker seed/config root identity changed")
        validate_config_ownership(self.binding, self.config_ownership)
        if not isinstance(self.serial, str) or not self.serial.strip():
            raise ValueError("worker serial is missing")
        if (
            isinstance(self.verified_game_pid, bool)
            or not isinstance(self.verified_game_pid, int)
            or self.verified_game_pid <= 0
        ):
            raise ValueError("worker game PID is not verified")
        if tuple(sorted(set(self.starting_forwards))) != self.starting_forwards:
            raise ValueError("worker starting forward inventory is not canonical")
        if not isinstance(self.materialization_control, Mapping):
            raise ValueError("worker materialization control is malformed")
        materialization = strict_json_mapping_bytes(
            canonical_json_bytes(self.materialization_control),
            maximum=_MAX_CONTROL_BYTES,
            label="worker materialization control",
        )
        if not materialization:
            raise ValueError("worker materialization control is missing")
        expected_materialization_binding = {
            "run_id": self.binding.run_id,
            "task": self.binding.task,
            "stage": self.binding.stage,
            "event": self.binding.event,
            "deadline_seconds": self.binding.deadline_seconds,
            "parent_pid": self.binding.parent_pid,
            "alas_root": str(self.binding.config_path.parent.parent),
        }
        if any(
            materialization.get(field) != expected
            for field, expected in expected_materialization_binding.items()
        ):
            raise ValueError("worker materialization binding changed")
        if (
            not isinstance(materialization.get("schema"), str)
            or not isinstance(materialization.get("proof"), Mapping)
        ):
            raise ValueError("worker materialization proof is malformed")
        if (
            not isinstance(self.execution_budgets, Mapping)
            or set(self.execution_budgets) != _WORKER_BUDGET_FIELDS
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in self.execution_budgets.values()
            )
        ):
            raise ValueError("worker execution budgets are malformed")
        object.__setattr__(self, "materialization_control", materialization)
        object.__setattr__(self, "execution_budgets", dict(self.execution_budgets))
        validate_worker_control_root(self)

    def _body_mapping(self) -> Mapping[str, Any]:
        return {
            "schema": WORKER_CONTROL_SCHEMA,
            "binding": self.binding.to_mapping(),
            "config_ownership": self.config_ownership.to_mapping(),
            "seed_source": self.seed_source.to_mapping(),
            "serial": self.serial,
            "verified_game_pid": self.verified_game_pid,
            "starting_forwards": [item.to_mapping() for item in self.starting_forwards],
            "handles": self.handles.to_mapping(),
            "materialization_control": dict(self.materialization_control),
            "execution_budgets": dict(self.execution_budgets),
        }

    def to_mapping(self) -> Mapping[str, Any]:
        """Return a canonical record bound to this run's public identity."""

        validate_worker_control_root(self)
        return _bind_record_to_binding(
            self.binding, RECORD_WORKER_CONTROL, self._body_mapping()
        )

    @property
    def activation_verified(self) -> bool:
        return self._activation_verified

    @property
    def activation_token(self) -> bytes:
        if self._activation_token is None:
            raise RuntimeError("worker control has no activation secret")
        return self._activation_token

    def bind_activation_token(self, token: bytes, *, verified: bool) -> None:
        token = _validate_activation_token(token)
        token_digest = hashlib.sha256(token).hexdigest()
        if not hmac.compare_digest(token_digest, self.binding.token_digest):
            raise RuntimeError("worker activation token digest changed")
        validate_config_ownership(self.binding, self.config_ownership)
        object.__setattr__(self, "_activation_token", token)
        if verified:
            object.__setattr__(self, "_activation_verified", True)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any], *, activation_token: bytes | None = None
    ) -> "WorkerControl":
        """Verify public run binding before constructing the control object."""

        if activation_token is None:
            raise ValueError("worker activation token is required")
        if not isinstance(value, Mapping) or not isinstance(value.get("payload"), Mapping):
            raise ValueError("worker control record is malformed")
        candidate_binding = RunBinding.from_mapping(value["payload"].get("binding"))
        body = _verify_bound_record_for_binding(
            candidate_binding, RECORD_WORKER_CONTROL, value
        )
        if not hmac.compare_digest(
            hashlib.sha256(_validate_activation_token(activation_token)).hexdigest(),
            candidate_binding.token_digest,
        ):
            raise ValueError("worker activation token does not match this run")
        return cls._from_body_mapping(body)

    @classmethod
    def _from_body_mapping(cls, value: Mapping[str, Any]) -> "WorkerControl":
        expected = {
            "schema",
            "binding",
            "config_ownership",
            "seed_source",
            "serial",
            "verified_game_pid",
            "starting_forwards",
            "handles",
            "materialization_control",
            "execution_budgets",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != WORKER_CONTROL_SCHEMA
        ):
            raise ValueError("worker control schema is unsupported")
        forwards = value.get("starting_forwards")
        if not isinstance(forwards, list):
            raise ValueError("worker starting forward inventory is malformed")
        return cls(
            binding=RunBinding.from_mapping(value.get("binding")),
            config_ownership=ConfigOwnership.from_mapping(
                value.get("config_ownership")
            ),
            seed_source=SeedSource.from_mapping(value.get("seed_source")),
            serial=value.get("serial"),
            verified_game_pid=value.get("verified_game_pid"),
            starting_forwards=tuple(
                sorted(ForwardRecord.from_mapping(item) for item in forwards)
            ),
            handles=WorkerHandles.from_mapping(value.get("handles")),
            materialization_control=value.get("materialization_control"),
            execution_budgets=value.get("execution_budgets"),
        )


def sanitize_terminal_text(
    value: Any, *, maximum: int = MAX_TERMINAL_MESSAGE_CHARS
) -> str:
    try:
        text = str(value)
    except BaseException:
        text = "<unprintable>"
    text = "".join(character if character >= " " else " " for character in text)
    return text[:maximum]


def safe_exception_type(exc: BaseException) -> str:
    """Collapse exception classes onto a fixed public allowlist."""

    for exception_class, public_name in (
        (RunnerStopRequested, "RunnerStopRequested"),
        (SystemExit, "SystemExit"),
        (KeyboardInterrupt, "KeyboardInterrupt"),
        (TimeoutError, "TimeoutError"),
        (OSError, "OSError"),
        (RuntimeError, "RuntimeError"),
        (ValueError, "ValueError"),
        (TypeError, "TypeError"),
        (AssertionError, "AssertionError"),
        (Exception, "Exception"),
    ):
        if isinstance(exc, exception_class):
            return public_name
    return "BaseException"


def exception_traceback_digest(exc: BaseException, purpose: str) -> str:
    """Hash exception diagnostics without exposing their body."""

    if not isinstance(purpose, str) or not re.fullmatch(
        r"[a-z0-9_.:-]{1,128}", purpose
    ):
        raise ValueError("exception digest purpose is malformed")
    try:
        body = str(exc)
    except BaseException:
        body = "<unprintable>"
    material = (
        b"alas-headless.public-exception/v1\0"
        + purpose.encode("ascii")
        + b"\0"
        + safe_exception_type(exc).encode("ascii")
        + b"\0"
        + body.encode("utf-8", errors="replace")
    )
    return hashlib.sha256(material).hexdigest()


def public_exception_descriptor(exc: BaseException, purpose: str) -> Mapping[str, str]:
    return {
        "type": safe_exception_type(exc),
        "message_digest": exception_traceback_digest(exc, purpose + ":message"),
        "traceback_digest": exception_traceback_digest(exc, purpose + ":traceback"),
    }


def secret_free_exception_label(exc: BaseException, purpose: str) -> str:
    descriptor = public_exception_descriptor(exc, purpose)
    return "{0}:{1}:sha256:{2}".format(
        purpose, descriptor["type"], descriptor["traceback_digest"]
    )


def _secret_representations(token: bytes) -> tuple[str, ...]:
    token = _validate_activation_token(token)
    values = {token.hex(), token.hex().upper()}
    for encoder in (base64.b64encode, base64.urlsafe_b64encode):
        encoded = encoder(token).decode("ascii")
        values.add(encoded)
        values.add(encoded.rstrip("="))
    try:
        decoded = token.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        decoded = ""
    if decoded:
        values.add(decoded)
    return tuple(sorted(values, key=len, reverse=True))


def redact_secret_representations(value: Any, token: bytes) -> Any:
    """Recursively redact every direct public representation of a run token."""

    representations = _secret_representations(token)

    def redact(item: Any) -> Any:
        if isinstance(item, str):
            result = item
            for representation in representations:
                result = result.replace(representation, "[redacted-secret]")
            return result
        if isinstance(item, bytes):
            if any(rep.encode("utf-8") in item for rep in representations):
                return "[redacted-secret]"
            return item
        if isinstance(item, Mapping):
            result: dict[Any, Any] = {}
            for key, nested in item.items():
                redacted_key = redact(key)
                if redacted_key in result:
                    raise ValueError("secret redaction produced a duplicate key")
                result[redacted_key] = redact(nested)
            return result
        if isinstance(item, list):
            return [redact(nested) for nested in item]
        if isinstance(item, tuple):
            return tuple(redact(nested) for nested in item)
        return item

    return redact(value)


def ensure_secret_free_payload(value: Any, token: bytes) -> Any:
    redacted = redact_secret_representations(value, token)
    if redacted != value:
        raise RuntimeError("public payload contained a private runner capability")
    return value


def normalize_exit_code(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(min(value, 2147483647), -2147483648)
    return None


def normalize_system_exit_code(value: Any) -> int:
    """Normalize SystemExit using Python's process-exit convention."""

    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(min(value, 2147483647), -2147483648)
    return 1


@dataclass(frozen=True)
class WorkerTerminal:
    terminal_kind: str
    phase: str
    execution_state: str
    classification: str
    passed: bool
    capability_promotion: bool
    exit_code: Optional[int]
    exception_type: str
    message: str
    traceback_digest: Optional[str]
    cleanup_status: str
    cleanup_digest: Optional[str]

    def __post_init__(self) -> None:
        if self.terminal_kind not in ("fatal", "stop_requested"):
            raise ValueError("worker terminal kind is unsupported")
        if self.phase not in WORKER_PHASES:
            raise ValueError("worker terminal phase is unsupported")
        if self.execution_state not in WORKER_EXECUTION_STATES:
            raise ValueError("worker terminal execution state is unsupported")
        if (
            not isinstance(self.classification, str)
            or not self.classification.startswith("runner.worker_")
            or len(self.classification) > 128
        ):
            raise ValueError("worker terminal classification is malformed")
        if self.passed is not False or self.capability_promotion is not False:
            raise ValueError("worker terminal cannot claim success or promotion")
        if self.exit_code is not None and (
            isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)
        ):
            raise ValueError("worker terminal exit code is malformed")
        if self.exception_type not in PUBLIC_EXCEPTION_TYPES:
            raise ValueError("worker terminal exception type is malformed")
        if (
            not isinstance(self.message, str)
            or len(self.message) > MAX_TERMINAL_MESSAGE_CHARS
        ):
            raise ValueError("worker terminal message is malformed")
        if self.traceback_digest is not None and (
            not isinstance(self.traceback_digest, str)
            or _SHA256_HEX.fullmatch(self.traceback_digest) is None
        ):
            raise ValueError("worker terminal traceback digest is malformed")
        if self.cleanup_status not in ("complete", "failed", "missing", "unknown"):
            raise ValueError("worker terminal cleanup status is malformed")
        if self.cleanup_digest is not None and (
            not isinstance(self.cleanup_digest, str)
            or _SHA256_HEX.fullmatch(self.cleanup_digest) is None
        ):
            raise ValueError("worker terminal cleanup digest is malformed")
        if (
            self.cleanup_status in ("complete", "failed")
            and self.cleanup_digest is None
        ):
            raise ValueError("worker terminal cleanup digest is missing")
        if (
            self.cleanup_status in ("missing", "unknown")
            and self.cleanup_digest is not None
        ):
            raise ValueError("worker terminal cleanup digest is contradictory")
        if (
            self.phase
            in (
                "pre_init",
                "config_write",
                "alas_import",
                "alas_construct",
                "startup",
            )
            and self.execution_state != "not_started"
        ):
            raise ValueError("worker terminal phase/execution state is contradictory")
        if self.phase == "task_run" and self.execution_state not in (
            "started",
            "unknown",
        ):
            raise ValueError("worker task terminal execution state is contradictory")
        if self.phase in ("post_run", "result_serialize") and (
            self.execution_state != "finished"
        ):
            raise ValueError("worker terminal phase/execution state is contradictory")
        if self.terminal_kind == "stop_requested":
            if (
                self.classification != "runner.worker_stop_requested"
                or self.exception_type != "RunnerStopRequested"
                or self.exit_code is not None
            ):
                raise ValueError("worker stop terminal fields are contradictory")
        elif self.classification == "runner.worker_system_exit":
            if self.exception_type != "SystemExit" or self.exit_code is None:
                raise ValueError("worker SystemExit terminal fields are contradictory")
        elif self.classification == "runner.worker_keyboard_interrupt":
            if self.exception_type != "KeyboardInterrupt" or self.exit_code is not None:
                raise ValueError(
                    "worker KeyboardInterrupt terminal fields are contradictory"
                )
        elif self.classification == "runner.worker_fatal":
            if (
                self.exception_type
                in (
                    "RunnerStopRequested",
                    "SystemExit",
                    "KeyboardInterrupt",
                )
                or self.exit_code is not None
            ):
                raise ValueError("worker fatal terminal fields are contradictory")
        else:
            raise ValueError("worker fatal terminal classification is unsupported")

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "schema": WORKER_TERMINAL_SCHEMA,
            "terminal_kind": self.terminal_kind,
            "phase": self.phase,
            "execution_state": self.execution_state,
            "classification": self.classification,
            "passed": self.passed,
            "capability_promotion": self.capability_promotion,
            "exit_code": self.exit_code,
            "exception_type": self.exception_type,
            "message": self.message,
            "traceback_digest": self.traceback_digest,
            "cleanup_status": self.cleanup_status,
            "cleanup_digest": self.cleanup_digest,
        }

    def to_bound_mapping(self, control: "WorkerControl") -> Mapping[str, Any]:
        return bind_record(control, RECORD_TERMINAL, self.to_mapping())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkerTerminal":
        expected = {
            "schema",
            "terminal_kind",
            "phase",
            "execution_state",
            "classification",
            "passed",
            "capability_promotion",
            "exit_code",
            "exception_type",
            "message",
            "traceback_digest",
            "cleanup_status",
            "cleanup_digest",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != WORKER_TERMINAL_SCHEMA
        ):
            raise ValueError("worker terminal payload is malformed")
        return cls(
            terminal_kind=value.get("terminal_kind"),
            phase=value.get("phase"),
            execution_state=value.get("execution_state"),
            classification=value.get("classification"),
            passed=value.get("passed"),
            capability_promotion=value.get("capability_promotion"),
            exit_code=value.get("exit_code"),
            exception_type=value.get("exception_type"),
            message=value.get("message"),
            traceback_digest=value.get("traceback_digest"),
            cleanup_status=value.get("cleanup_status"),
            cleanup_digest=value.get("cleanup_digest"),
        )

    @classmethod
    def from_bound_mapping(
        cls, value: Mapping[str, Any], control: "WorkerControl"
    ) -> "WorkerTerminal":
        return cls.from_mapping(verify_bound_record(control, RECORD_TERMINAL, value))


@dataclass(frozen=True)
class ForwardLease:
    binding: RunBinding
    serial: str
    local: str
    remote: str
    verified_game_pid: int
    starting_forwards: Tuple[ForwardRecord, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.verified_game_pid, bool)
            or not isinstance(self.verified_game_pid, int)
            or self.verified_game_pid <= 0
        ):
            raise ValueError("forward lease game PID is not verified")
        match = _REMOTE_FORWARD.fullmatch(self.record.remote)
        if match is None or int(match.group(1)) != self.verified_game_pid:
            raise ValueError("forward lease remote PID is not verified")
        if self.record in self.starting_forwards:
            raise ValueError("forward lease cannot claim a pre-existing forward")
        if tuple(sorted(set(self.starting_forwards))) != self.starting_forwards:
            raise ValueError("forward lease starting inventory is not canonical")

    @property
    def record(self) -> ForwardRecord:
        return ForwardRecord(self.serial, self.local, self.remote)

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "schema": FORWARD_LEASE_SCHEMA,
            "binding": self.binding.to_mapping(),
            "serial": self.serial,
            "local": self.local,
            "remote": self.remote,
            "verified_game_pid": self.verified_game_pid,
            "starting_forwards": [item.to_mapping() for item in self.starting_forwards],
        }

    def to_bound_mapping(self, control: WorkerControl) -> Mapping[str, Any]:
        if control.binding != self.binding:
            raise ValueError("forward lease control binding changed")
        return bind_record(control, RECORD_FORWARD_LEASE, self.to_mapping())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ForwardLease":
        expected = {
            "schema",
            "binding",
            "serial",
            "local",
            "remote",
            "verified_game_pid",
            "starting_forwards",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != FORWARD_LEASE_SCHEMA
        ):
            raise ValueError("forward lease schema is unsupported")
        forwards = value.get("starting_forwards")
        if not isinstance(forwards, list):
            raise ValueError("forward lease starting inventory is malformed")
        return cls(
            binding=RunBinding.from_mapping(value.get("binding")),
            serial=value.get("serial"),
            local=value.get("local"),
            remote=value.get("remote"),
            verified_game_pid=value.get("verified_game_pid"),
            starting_forwards=tuple(
                sorted(ForwardRecord.from_mapping(item) for item in forwards)
            ),
        )

    @classmethod
    def from_bound_mapping(
        cls, value: Mapping[str, Any], control: WorkerControl
    ) -> "ForwardLease":
        lease = cls.from_mapping(verify_bound_record(control, RECORD_FORWARD_LEASE, value))
        if lease.binding != control.binding:
            raise ValueError("forward lease binding does not match this run")
        return lease


@dataclass(frozen=True)
class ProcessSupervisionResult:
    reason: str
    termination_mode: str
    returncode: Optional[int]
    termination_confirmed: bool
    cooperative_stop_requested: bool
    forced_terminate: bool
    forced_kill: bool
    errors: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.reason not in (
            "completed",
            "deadline",
            "interrupted",
            "supervision_error",
        ):
            raise ValueError("supervision reason is invalid")
        if not isinstance(self.termination_mode, str) or not self.termination_mode:
            raise ValueError("supervision termination mode is invalid")
        if self.returncode is not None and (
            isinstance(self.returncode, bool) or not isinstance(self.returncode, int)
        ):
            raise ValueError("supervision return code is invalid")
        for label, value in (
            ("termination confirmed", self.termination_confirmed),
            ("cooperative stop", self.cooperative_stop_requested),
            ("forced terminate", self.forced_terminate),
            ("forced kill", self.forced_kill),
        ):
            if not isinstance(value, bool):
                raise ValueError("supervision {0} flag is invalid".format(label))
        if not isinstance(self.errors, tuple) or any(
            not isinstance(item, str) for item in self.errors
        ):
            raise ValueError("supervision errors are invalid")


@dataclass(frozen=True)
class ForwardCleanupDecision:
    record: Optional[ForwardRecord]
    already_absent: bool
    source: str
    blockers: Tuple[str, ...] = ()


@dataclass
class ExclusiveFile:
    path: Path
    fd: int
    handle: int
    root_path: Path
    root_identity: FileIdentity
    initial_identity: FileIdentity
    child_handle: int = -1
    owned: bool = True

    def close_parent(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
            self.handle = -1

    def create_child_handle(self, access: str) -> int:
        if os.name != "nt" or self.fd < 0 or self.handle <= 0:
            raise RuntimeError("exclusive artifact master handle is unavailable")
        if self.child_handle >= 0:
            raise RuntimeError("exclusive artifact child handle already exists")
        self.child_handle = _windows_duplicate_child_handle(self.handle, access)
        return self.child_handle

    def close_child_handle(self) -> None:
        if self.child_handle >= 0:
            _windows_close_handle(_windows_kernel32(), self.child_handle)
            self.child_handle = -1

    def remove_owned_path(self) -> None:
        if not self.owned or self.fd < 0:
            raise RuntimeError("exclusive file is not owned")
        remove_exclusive_file(self)

    def validate_master(self) -> None:
        if not self.owned or self.fd < 0 or self.handle <= 0:
            raise RuntimeError("exclusive artifact master handle is unavailable")
        if os.name == "nt":
            _validate_exclusive_handle(
                _windows_kernel32(),
                self.handle,
                path=self.path,
                root=self.root_path,
                root_identity=self.root_identity,
                initial_identity=self.initial_identity,
            )
        elif file_identity_from_fd(self.fd) != self.initial_identity:
            raise RuntimeError("exclusive artifact master identity changed")


@dataclass
class ImmutableInputFile:
    path: Path
    fd: int
    handle: int
    root_path: Path
    root_identity: FileIdentity
    identity: FileIdentity
    size: int
    sha256: str
    child_handle: int = -1

    def close_parent(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
            self.handle = -1

    def create_child_handle(self) -> int:
        if os.name != "nt" or self.fd < 0 or self.handle <= 0:
            raise RuntimeError("immutable input master handle is unavailable")
        if self.child_handle >= 0:
            raise RuntimeError("immutable input child handle already exists")
        self.child_handle = _windows_duplicate_child_handle(self.handle, "read")
        return self.child_handle

    def close_child_handle(self) -> None:
        if self.child_handle >= 0:
            _windows_close_handle(_windows_kernel32(), self.child_handle)
            self.child_handle = -1

    def source(self, *, capability: str, seed_name: str) -> SeedSource:
        return SeedSource(
            capability=capability,
            seed_name=seed_name,
            path=self.path,
            root_path=self.root_path,
            root_identity=self.root_identity,
            identity=self.identity,
            size=self.size,
            sha256=self.sha256,
        )


@dataclass
class ActivationPipe:
    read_fd: int
    read_handle: int
    write_fd: int

    def close_parent_read(self) -> None:
        if self.read_fd >= 0:
            os.close(self.read_fd)
            self.read_fd = -1

    def close_parent_write(self) -> None:
        if self.write_fd >= 0:
            os.close(self.write_fd)
            self.write_fd = -1


def validate_total_deadline(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("total deadline must be a strict integer")
    if not MIN_TOTAL_DEADLINE_SECONDS <= value <= MAX_TOTAL_DEADLINE_SECONDS:
        raise ValueError(
            "total deadline must be in [{0}, {1}] seconds".format(
                MIN_TOTAL_DEADLINE_SECONDS, MAX_TOTAL_DEADLINE_SECONDS
            )
        )
    return value


def remaining_seconds(
    absolute_deadline: float, monotonic: Callable[[], float] = time.monotonic
) -> float:
    remaining = float(absolute_deadline) - monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise TimeoutError("runner total deadline expired during setup")
    return remaining


def parse_forward_inventory(text: str) -> Tuple[ForwardRecord, ...]:
    if not isinstance(text, str):
        raise ValueError("ADB forward inventory must be text")
    records = []
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        if len(parts) != 3:
            raise ValueError("ADB forward inventory row is malformed")
        records.append(ForwardRecord(*parts))
    if len(set(records)) != len(records):
        raise ValueError("ADB forward inventory contains duplicates")
    return tuple(sorted(records))


def adb_forward_inventory(
    adb: str,
    serial: str,
    *,
    timeout_seconds: float,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[ForwardRecord, ...]:
    completed = command_runner(
        [adb, "-s", serial, "forward", "--list"],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return parse_forward_inventory(completed.stdout)


def adb_verified_game_pid(
    adb: str,
    serial: str,
    package: str,
    *,
    timeout_seconds: float,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> int:
    completed = command_runner(
        [adb, "-s", serial, "shell", "pidof", package],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    value = completed.stdout.strip()
    if not value.isdigit() or int(value) <= 0:
        raise RuntimeError("expected exactly one numeric game PID")
    return int(value)


def adb_remove_forward(
    adb: str,
    record: ForwardRecord,
    *,
    timeout_seconds: float,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    command_runner(
        [adb, "-s", record.serial, "forward", "--remove", record.local],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return _canonical_bytes(value)


def strict_json_mapping_bytes(
    payload: bytes, *, maximum: int, label: str
) -> Mapping[str, Any]:
    if not isinstance(payload, bytes) or not payload or len(payload) > maximum:
        raise ValueError(label + " is empty or oversized")

    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if not isinstance(key, str) or key in result:
                raise ValueError(label + " contains a duplicate or malformed key")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(label + " contains non-finite JSON number " + value)

    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(label + " is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(label + " must be a JSON object")
    return value


def file_identity_from_stat(value: os.stat_result) -> FileIdentity:
    return FileIdentity(volume_serial=int(value.st_dev), file_id=int(value.st_ino))


def file_identity_from_fd(fd: int) -> FileIdentity:
    if isinstance(fd, bool) or not isinstance(fd, int) or fd < 0:
        raise ValueError("file descriptor is malformed")
    if os.name == "nt":
        import msvcrt

        handle = int(msvcrt.get_osfhandle(fd))
        info = _windows_file_info(_windows_kernel32(), handle)
        return FileIdentity(
            volume_serial=int(info.dwVolumeSerialNumber),
            file_id=(int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
        )
    return file_identity_from_stat(os.fstat(fd))


def file_identity_from_path(path: Path) -> FileIdentity:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("identity path must be absolute")
    if os.name == "nt":
        kernel32, handle = _windows_open_config(path, delete_access=False)
        try:
            info = _windows_file_info(kernel32, handle)
            return FileIdentity(
                volume_serial=int(info.dwVolumeSerialNumber),
                file_id=(int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
            )
        finally:
            _windows_close_handle(kernel32, handle)
    return file_identity_from_stat(os.stat(path, follow_symlinks=False))


def exclusive_create(path: Path, *, inheritable: bool) -> ExclusiveFile:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("exclusive path must be absolute")
    if not isinstance(inheritable, bool):
        raise ValueError("exclusive handle inheritance is malformed")
    root = path.parent.resolve(strict=True)
    if root != path.parent:
        raise RuntimeError("exclusive artifact root is not canonical")
    root_stat = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse_stat(root_stat):
        raise RuntimeError("exclusive artifact root is not a trusted directory")
    root_identity = file_identity_from_path(root)
    if os.name == "nt":
        return _windows_exclusive_create(
            path,
            root=root,
            root_identity=root_identity,
            inheritable=inheritable,
        )
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o600)
    try:
        handle = fd
        os.set_inheritable(fd, inheritable)
        identity = file_identity_from_fd(fd)
        return ExclusiveFile(
            path=path,
            fd=fd,
            handle=handle,
            root_path=root,
            root_identity=root_identity,
            initial_identity=identity,
        )
    except BaseException:
        os.close(fd)
        # This runner is Windows-only.  A POSIX setup failure deliberately
        # retains the O_EXCL artifact rather than risking path-based deletion.
        raise


def open_immutable_input(
    path: Path, *, maximum: int
) -> tuple[ImmutableInputFile, bytes]:
    """Open and pin one pre-existing, single-link, immutable input object."""

    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum <= 0
    ):
        raise ValueError("immutable input contract is malformed")
    root = path.parent.resolve(strict=True)
    if root != path.parent:
        raise RuntimeError("immutable input root is not canonical")
    root_stat = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse_stat(root_stat):
        raise RuntimeError("immutable input root is not a trusted directory")
    root_identity = file_identity_from_path(root)
    if os.name == "nt":
        return _windows_open_immutable_input(
            path,
            root=root,
            root_identity=root_identity,
            maximum=maximum,
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or _is_reparse_stat(before)
            or int(before.st_nlink) != 1
            or int(before.st_size) <= 0
            or int(before.st_size) > maximum
        ):
            raise RuntimeError("immutable input type, link count, or size is unsafe")
        payload = os.read(fd, maximum + 1)
        after = os.fstat(fd)
        if before != after or len(payload) != int(before.st_size):
            raise RuntimeError("immutable input changed while it was read")
        identity = file_identity_from_stat(after)
        return (
            ImmutableInputFile(
                path=path,
                fd=fd,
                handle=fd,
                root_path=root,
                root_identity=root_identity,
                identity=identity,
                size=len(payload),
                sha256=_sha256_hex(payload),
            ),
            payload,
        )
    except BaseException:
        os.close(fd)
        raise


def write_owned_file(file: ExclusiveFile, payload: bytes) -> None:
    if file.fd < 0 or not file.owned:
        raise RuntimeError("owned file is not writable")
    os.lseek(file.fd, 0, os.SEEK_SET)
    view = memoryview(payload)
    while view:
        written = os.write(file.fd, view)
        if written <= 0:
            raise OSError("owned file write did not advance")
        view = view[written:]
    os.fsync(file.fd)


def read_owned_file(file: ExclusiveFile, maximum: int) -> bytes:
    """Read one exact master artifact without releasing its pathname lock."""

    if (
        not isinstance(file, ExclusiveFile)
        or file.fd < 0
        or not file.owned
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum <= 0
    ):
        raise ValueError("owned file read contract is malformed")
    file.validate_master()
    position = os.lseek(file.fd, 0, os.SEEK_CUR)
    try:
        os.lseek(file.fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            chunk = os.read(file.fd, min(65536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        payload = b"".join(chunks)
    finally:
        os.lseek(file.fd, position, os.SEEK_SET)
    if len(payload) > maximum:
        raise ValueError("owned file is oversized")
    return payload


def read_bytes_handle(handle: int, maximum: int) -> tuple[bytes, FileIdentity]:
    if (
        isinstance(handle, bool)
        or not isinstance(handle, int)
        or handle <= 0
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum <= 0
    ):
        raise ValueError("inherited read handle contract is malformed")
    if os.name == "nt":
        import msvcrt

        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    else:
        fd = handle
    with os.fdopen(fd, "rb", closefd=True) as stream:
        identity = file_identity_from_fd(stream.fileno())
        stream.seek(0)
        payload = stream.read(maximum + 1)
    if not payload or len(payload) > maximum:
        raise RuntimeError("inherited artifact is empty or oversized")
    return payload, identity


def write_bytes_handle(
    handle: int,
    payload: bytes,
    *,
    expected_identity: Optional[FileIdentity] = None,
) -> FileIdentity:
    if not isinstance(payload, bytes):
        raise ValueError("inherited handle payload must be bytes")
    if os.name == "nt":
        import msvcrt

        flags = os.O_WRONLY | getattr(os, "O_BINARY", 0)
        fd = msvcrt.open_osfhandle(handle, flags)
    else:
        fd = handle
    with os.fdopen(fd, "wb", closefd=True) as stream:
        actual_identity = file_identity_from_fd(stream.fileno())
        if expected_identity is not None and actual_identity != expected_identity:
            raise RuntimeError("inherited file identity changed")
        stream.seek(0)
        stream.truncate(0)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return actual_identity


def close_inherited_handle(handle: int) -> None:
    if isinstance(handle, bool) or not isinstance(handle, int) or handle <= 0:
        raise ValueError("inherited handle is malformed")
    if os.name == "nt":
        kernel32 = _windows_kernel32()
        _windows_close_handle(kernel32, handle)
    else:
        os.close(handle)


def write_json_handle(
    handle: int,
    value: Mapping[str, Any],
    *,
    expected_identity: Optional[FileIdentity] = None,
) -> FileIdentity:
    return write_bytes_handle(
        handle,
        canonical_json_bytes(value),
        expected_identity=expected_identity,
    )


def read_json_mapping(path: Path) -> Mapping[str, Any]:
    return strict_json_mapping_bytes(
        path.read_bytes(), maximum=MAX_CONFIG_BYTES, label="JSON file"
    )


def _path_attributes(value: os.stat_result) -> int:
    return int(getattr(value, "st_file_attributes", 0))


def _is_reparse_stat(value: os.stat_result) -> bool:
    return bool(_path_attributes(value) & 0x400)


def validate_worker_control_root(control: WorkerControl) -> None:
    """Bind seed and run-owned config to one current canonical directory object."""

    if not isinstance(control, WorkerControl):
        raise RuntimeError("worker control root admission is malformed")
    ownership = control.config_ownership
    source = control.seed_source
    root = ownership.config_root
    if (
        root != control.binding.config_path.parent
        or source.root_path != root
        or source.path.parent != root
    ):
        raise RuntimeError("config root/path binding changed")
    if source.root_identity != ownership.root_identity:
        raise RuntimeError("seed/config root identity changed")
    validate_config_basename(control.binding.run_id, control.binding.config_path.name)
    resolved = root.resolve(strict=True)
    if resolved != root:
        raise RuntimeError("config root is not the exact canonical path")
    root_stat = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse_stat(root_stat):
        raise RuntimeError("config root is not a trusted non-reparse directory")
    current_identity = file_identity_from_path(root)
    if (
        current_identity != ownership.root_identity
        or current_identity != source.root_identity
    ):
        raise RuntimeError("config root identity changed")


def validate_config_root(control: WorkerControl) -> None:
    validate_worker_control_root(control)


def _strict_config_payload(payload: bytes, control: WorkerControl) -> Mapping[str, Any]:
    value = strict_json_mapping_bytes(
        payload, maximum=MAX_CONFIG_BYTES, label="run-owned config"
    )
    validate_config_marker(value, control.binding, control.config_ownership)
    return value


@dataclass(frozen=True)
class ConfigDeleteResult:
    deleted: bool
    already_absent: bool
    foreign_replacement: bool
    blocker: Optional[str]
    state: ConfigFileState

    def __post_init__(self) -> None:
        for value in (self.deleted, self.already_absent, self.foreign_replacement):
            if not isinstance(value, bool):
                raise ValueError("config delete result flag is malformed")
        if sum((self.deleted, self.already_absent, self.foreign_replacement)) > 1:
            raise ValueError("config delete result is contradictory")
        if self.blocker is not None and (
            not isinstance(self.blocker, str) or not self.blocker
        ):
            raise ValueError("config delete blocker is malformed")


def _absent_config_state() -> ConfigFileState:
    return ConfigFileState(
        exists=False,
        identity=None,
        attributes=None,
        link_count=None,
        size=None,
        is_directory=False,
        is_reparse_point=False,
        marker_verified=False,
        marker_error=None,
    )


def _config_state_matches(left: ConfigFileState, right: ConfigFileState) -> bool:
    return (
        left.exists == right.exists
        and left.identity == right.identity
        and left.attributes == right.attributes
        and left.link_count == right.link_count
        and left.size == right.size
        and left.is_directory == right.is_directory
        and left.is_reparse_point == right.is_reparse_point
        and left.marker_verified == right.marker_verified
    )


class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = (
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    )


class _FILE_DISPOSITION_INFO(ctypes.Structure):
    _fields_ = (("DeleteFile", wintypes.BOOL),)


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = (
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    )


def _windows_kernel32() -> Any:
    if os.name != "nt":
        raise RuntimeError("Windows config handle API is unavailable")
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _windows_open_config(path: Path, *, delete_access: bool) -> tuple[Any, int]:
    kernel32 = _windows_kernel32()
    create = kernel32.CreateFileW
    create.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create.restype = wintypes.HANDLE
    desired = 0x80000000 | 0x00000080  # GENERIC_READ | FILE_READ_ATTRIBUTES
    if delete_access:
        desired |= 0x00010000  # DELETE
    handle = create(
        str(path),
        desired,
        0 if delete_access else 0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x02000000,  # OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not handle or int(handle) == invalid_handle:
        error = ctypes.get_last_error()
        if error in (2, 3):
            raise FileNotFoundError(error, "run-owned config is absent", str(path))
        raise OSError(error, "CreateFileW(run-owned config) failed", str(path))
    return kernel32, int(handle)


def _windows_close_handle(kernel32: Any, handle: int) -> None:
    close = kernel32.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    if not close(handle):
        raise OSError(ctypes.get_last_error(), "CloseHandle(config) failed")


def _windows_file_info(kernel32: Any, handle: int) -> _BY_HANDLE_FILE_INFORMATION:
    getter = kernel32.GetFileInformationByHandle
    getter.argtypes = (wintypes.HANDLE, ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION))
    getter.restype = wintypes.BOOL
    info = _BY_HANDLE_FILE_INFORMATION()
    if not getter(handle, ctypes.byref(info)):
        raise OSError(
            ctypes.get_last_error(), "GetFileInformationByHandle(config) failed"
        )
    return info


def _windows_final_path(kernel32: Any, handle: int) -> Path:
    getter = kernel32.GetFinalPathNameByHandleW
    getter.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD)
    getter.restype = wintypes.DWORD
    size = getter(handle, None, 0, 0)
    if not size:
        raise OSError(ctypes.get_last_error(), "GetFinalPathNameByHandleW failed")
    buffer = ctypes.create_unicode_buffer(size + 1)
    written = getter(handle, buffer, len(buffer), 0)
    if not written or written >= len(buffer):
        raise OSError(ctypes.get_last_error(), "GetFinalPathNameByHandleW failed")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def _identity_from_windows_info(info: _BY_HANDLE_FILE_INFORMATION) -> FileIdentity:
    return FileIdentity(
        volume_serial=int(info.dwVolumeSerialNumber),
        file_id=(int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
    )


def _windows_info_snapshot(info: _BY_HANDLE_FILE_INFORMATION) -> tuple[int, ...]:
    return (
        int(info.dwFileAttributes),
        int(info.ftCreationTime.dwHighDateTime),
        int(info.ftCreationTime.dwLowDateTime),
        int(info.ftLastWriteTime.dwHighDateTime),
        int(info.ftLastWriteTime.dwLowDateTime),
        int(info.dwVolumeSerialNumber),
        int(info.nFileSizeHigh),
        int(info.nFileSizeLow),
        int(info.nNumberOfLinks),
        int(info.nFileIndexHigh),
        int(info.nFileIndexLow),
    )


def _windows_set_disposition(kernel32: Any, handle: int) -> None:
    setter = kernel32.SetFileInformationByHandle
    setter.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    setter.restype = wintypes.BOOL
    disposition = _FILE_DISPOSITION_INFO()
    disposition.DeleteFile = True
    if not setter(
        handle,
        4,  # FileDispositionInfo
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise OSError(
            ctypes.get_last_error(), "SetFileInformationByHandle(delete) failed"
        )


def _windows_cancel_disposition(kernel32: Any, handle: int) -> None:
    setter = kernel32.SetFileInformationByHandle
    setter.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    setter.restype = wintypes.BOOL
    disposition = _FILE_DISPOSITION_INFO()
    disposition.DeleteFile = False
    if not setter(
        handle,
        4,
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise OSError(
            ctypes.get_last_error(), "SetFileInformationByHandle(cancel) failed"
        )


def _windows_duplicate_child_handle(master_handle: int, access: str) -> int:
    access_mask = {
        "read": 0x80000000 | 0x00000080,
        "write": 0x40000000 | 0x00000080,
        "read_write": 0x80000000 | 0x40000000 | 0x00000080,
    }.get(access)
    if access_mask is None:
        raise ValueError("exclusive child handle access is unsupported")
    kernel32 = _windows_kernel32()
    current_process = kernel32.GetCurrentProcess
    current_process.argtypes = ()
    current_process.restype = wintypes.HANDLE
    duplicate = kernel32.DuplicateHandle
    duplicate.argtypes = (
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    duplicate.restype = wintypes.BOOL
    process = current_process()
    child = wintypes.HANDLE()
    if not duplicate(
        process,
        master_handle,
        process,
        ctypes.byref(child),
        access_mask,
        True,
        0,
    ):
        raise OSError(ctypes.get_last_error(), "DuplicateHandle(child) failed")
    return int(child.value)


def _validate_exclusive_root(
    path: Path, root: Path, expected_identity: FileIdentity
) -> None:
    if path.parent != root or root.resolve(strict=True) != root:
        raise RuntimeError("exclusive artifact root/path binding changed")
    value = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(value.st_mode) or _is_reparse_stat(value):
        raise RuntimeError("exclusive artifact root is not trusted")
    if file_identity_from_path(root) != expected_identity:
        raise RuntimeError("exclusive artifact root identity changed")


def _validate_exclusive_handle(
    kernel32: Any,
    handle: int,
    *,
    path: Path,
    root: Path,
    root_identity: FileIdentity,
    initial_identity: FileIdentity,
) -> _BY_HANDLE_FILE_INFORMATION:
    _validate_exclusive_root(path, root, root_identity)
    info = _windows_file_info(kernel32, handle)
    if _identity_from_windows_info(info) != initial_identity:
        raise RuntimeError("exclusive artifact handle identity changed")
    attributes = int(info.dwFileAttributes)
    if attributes & (0x10 | 0x400):
        raise RuntimeError("exclusive artifact is a directory or reparse point")
    if int(info.nNumberOfLinks) != 1:
        raise RuntimeError("exclusive artifact has multiple hard links")
    if _windows_final_path(kernel32, handle) != path:
        raise RuntimeError("exclusive artifact final path changed")
    return info


def _windows_exclusive_create(
    path: Path,
    *,
    root: Path,
    root_identity: FileIdentity,
    inheritable: bool,
) -> ExclusiveFile:
    import msvcrt

    # The public flag remains for compatibility; inheritance is granted only
    # through an explicitly downgraded DuplicateHandle child capability.
    _ = inheritable
    kernel32 = _windows_kernel32()
    create = kernel32.CreateFileW
    create.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create.restype = wintypes.HANDLE
    security = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, False)
    handle = create(
        str(path),
        0x80000000 | 0x40000000 | 0x00010000 | 0x00000080,
        0,
        ctypes.byref(security),
        1,  # CREATE_NEW
        0x00000080,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not handle or int(handle) == invalid_handle:
        error = ctypes.get_last_error()
        if error in (80, 183):
            raise FileExistsError(error, "exclusive artifact already exists", str(path))
        raise OSError(error, "CreateFileW(CREATE_NEW) failed", str(path))
    handle = int(handle)
    initial_identity: FileIdentity | None = None
    disposition_succeeded = False
    fd = -1
    try:
        info = _windows_file_info(kernel32, handle)
        initial_identity = _identity_from_windows_info(info)
        _validate_exclusive_handle(
            kernel32,
            handle,
            path=path,
            root=root,
            root_identity=root_identity,
            initial_identity=initial_identity,
        )
        if os.get_handle_inheritable(handle):
            raise RuntimeError("exclusive artifact master handle is inheritable")
        fd = msvcrt.open_osfhandle(handle, os.O_RDWR | getattr(os, "O_BINARY", 0))
        handle = int(msvcrt.get_osfhandle(fd))
        return ExclusiveFile(
            path=path,
            fd=fd,
            handle=handle,
            root_path=root,
            root_identity=root_identity,
            initial_identity=initial_identity,
        )
    except BaseException:
        if fd >= 0:
            handle = int(msvcrt.get_osfhandle(fd))
        if initial_identity is not None:
            try:
                _validate_exclusive_handle(
                    kernel32,
                    handle,
                    path=path,
                    root=root,
                    root_identity=root_identity,
                    initial_identity=initial_identity,
                )
                _windows_set_disposition(kernel32, handle)
                if int(_windows_file_info(kernel32, handle).nNumberOfLinks) == 0:
                    disposition_succeeded = True
                else:
                    _windows_cancel_disposition(kernel32, handle)
            except BaseException:
                pass
        if fd >= 0:
            os.close(fd)
        else:
            _windows_close_handle(kernel32, handle)
        if disposition_succeeded:
            try:
                remaining = file_identity_from_path(path)
            except FileNotFoundError:
                remaining = None
            if remaining == initial_identity:
                raise RuntimeError(
                    "exclusive create rollback did not remove its object"
                )
        raise


def _windows_open_immutable_input(
    path: Path,
    *,
    root: Path,
    root_identity: FileIdentity,
    maximum: int,
) -> tuple[ImmutableInputFile, bytes]:
    import msvcrt

    kernel32 = _windows_kernel32()
    create = kernel32.CreateFileW
    create.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create.restype = wintypes.HANDLE
    security = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, False)
    handle = create(
        str(path),
        0x80000000 | 0x00000080,  # GENERIC_READ | FILE_READ_ATTRIBUTES
        0x00000001,  # FILE_SHARE_READ: no writer, rename, or delete may join.
        ctypes.byref(security),
        3,  # OPEN_EXISTING
        0x00200000 | 0x02000000,  # OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not handle or int(handle) == invalid_handle:
        error = ctypes.get_last_error()
        if error in (2, 3):
            raise FileNotFoundError(error, "immutable input is absent", str(path))
        raise OSError(error, "CreateFileW(immutable input) failed", str(path))
    handle = int(handle)
    fd = -1
    try:
        info = _windows_file_info(kernel32, handle)
        identity = _identity_from_windows_info(info)
        _validate_exclusive_handle(
            kernel32,
            handle,
            path=path,
            root=root,
            root_identity=root_identity,
            initial_identity=identity,
        )
        size = (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)
        if size <= 0 or size > maximum:
            raise RuntimeError("immutable input is empty or oversized")
        if os.get_handle_inheritable(handle):
            raise RuntimeError("immutable input master handle is inheritable")
        payload = _windows_read_handle(kernel32, handle, maximum)
        after = _windows_file_info(kernel32, handle)
        if len(payload) != size or _windows_info_snapshot(
            after
        ) != _windows_info_snapshot(info):
            raise RuntimeError("immutable input changed while it was read")
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        handle = int(msvcrt.get_osfhandle(fd))
        return (
            ImmutableInputFile(
                path=path,
                fd=fd,
                handle=handle,
                root_path=root,
                root_identity=root_identity,
                identity=identity,
                size=size,
                sha256=_sha256_hex(payload),
            ),
            payload,
        )
    except BaseException:
        if fd >= 0:
            os.close(fd)
        else:
            _windows_close_handle(kernel32, handle)
        raise


def remove_exclusive_file(file: ExclusiveFile) -> None:
    if os.name != "nt":
        raise RuntimeError("exact-handle exclusive artifact deletion is unavailable")
    import msvcrt

    kernel32 = _windows_kernel32()
    current_handle = int(msvcrt.get_osfhandle(file.fd))
    if current_handle != file.handle:
        raise RuntimeError("exclusive artifact CRT/native handle binding changed")
    info = _validate_exclusive_handle(
        kernel32,
        file.handle,
        path=file.path,
        root=file.root_path,
        root_identity=file.root_identity,
        initial_identity=file.initial_identity,
    )
    size = (int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow)
    if size > MAX_IMMUTABLE_ARTIFACT_BYTES:
        raise RuntimeError("exclusive artifact payload is oversized")
    payload = read_owned_file(file, MAX_IMMUTABLE_ARTIFACT_BYTES)
    if payload:
        # All immutable runner artifacts are JSON objects.  Parsing through the
        # same still-open master prevents a close/pathname race and rejects a
        # corrupted foreign-shaped payload before disposition is armed.
        strict_json_mapping_bytes(
            payload,
            maximum=MAX_IMMUTABLE_ARTIFACT_BYTES,
            label="exclusive artifact",
        )
        if _windows_info_snapshot(_windows_file_info(kernel32, file.handle)) != (
            _windows_info_snapshot(info)
        ):
            raise RuntimeError("exclusive artifact changed during payload validation")
    _windows_set_disposition(kernel32, file.handle)
    post_disposition = _windows_file_info(kernel32, file.handle)
    if int(post_disposition.nNumberOfLinks) != 0:
        try:
            _windows_cancel_disposition(kernel32, file.handle)
        except BaseException as cancel_exc:
            raise RuntimeError(
                "exclusive artifact disposition race and cancellation failed"
            ) from cancel_exc
        raise RuntimeError("exclusive artifact hardlink race was retained")
    file.close_parent()
    file.owned = False
    try:
        remaining = file_identity_from_path(file.path)
    except FileNotFoundError:
        return
    if remaining != file.initial_identity:
        raise RuntimeError("exclusive artifact foreign replacement was preserved")
    raise RuntimeError("exclusive artifact remained after handle disposition")


def _state_from_windows_info(
    info: _BY_HANDLE_FILE_INFORMATION,
    *,
    marker_verified: bool,
    marker_error: Optional[str],
) -> ConfigFileState:
    attributes = int(info.dwFileAttributes)
    return ConfigFileState(
        exists=True,
        identity=FileIdentity(
            volume_serial=int(info.dwVolumeSerialNumber),
            file_id=(int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow),
        ),
        attributes=attributes,
        link_count=int(info.nNumberOfLinks),
        size=(int(info.nFileSizeHigh) << 32) | int(info.nFileSizeLow),
        is_directory=bool(attributes & 0x10),
        is_reparse_point=bool(attributes & 0x400),
        marker_verified=marker_verified,
        marker_error=marker_error,
    )


def _windows_read_handle(kernel32: Any, handle: int, maximum: int) -> bytes:
    reader = kernel32.ReadFile
    reader.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    )
    reader.restype = wintypes.BOOL
    chunks: list[bytes] = []
    total = 0
    while total <= maximum:
        requested = min(65536, maximum + 1 - total)
        buffer = ctypes.create_string_buffer(requested)
        read = wintypes.DWORD()
        if not reader(handle, buffer, requested, ctypes.byref(read), None):
            raise OSError(ctypes.get_last_error(), "ReadFile(config) failed")
        count = int(read.value)
        if count == 0:
            break
        chunks.append(buffer.raw[:count])
        total += count
    payload = b"".join(chunks)
    if len(payload) > maximum:
        raise ValueError("run-owned config is oversized")
    return payload


def _inspect_windows_config_handle(
    kernel32: Any, handle: int, control: WorkerControl
) -> ConfigFileState:
    before = _windows_file_info(kernel32, handle)
    preliminary = _state_from_windows_info(
        before, marker_verified=False, marker_error="marker_not_checked"
    )
    if preliminary.is_directory:
        return _state_from_windows_info(
            before, marker_verified=False, marker_error="config_is_directory"
        )
    if preliminary.is_reparse_point:
        return _state_from_windows_info(
            before, marker_verified=False, marker_error="config_is_reparse_point"
        )
    if preliminary.link_count != 1:
        return _state_from_windows_info(
            before, marker_verified=False, marker_error="config_has_multiple_links"
        )
    if preliminary.size is None or preliminary.size > MAX_CONFIG_BYTES:
        return _state_from_windows_info(
            before, marker_verified=False, marker_error="config_is_oversized"
        )
    try:
        payload = _windows_read_handle(kernel32, handle, MAX_CONFIG_BYTES)
        _strict_config_payload(payload, control)
        marker_verified = True
        marker_error = None
    except Exception as exc:
        marker_verified = False
        marker_error = secret_free_exception_label(exc, "config_marker")
    after = _windows_file_info(kernel32, handle)
    before_state = _state_from_windows_info(
        before, marker_verified=marker_verified, marker_error=marker_error
    )
    after_state = _state_from_windows_info(
        after, marker_verified=marker_verified, marker_error=marker_error
    )
    if not _config_state_matches(before_state, after_state):
        raise RuntimeError("run-owned config changed while its handle was inspected")
    return after_state


def inspect_owned_config(control: WorkerControl) -> ConfigFileState:
    validate_config_root(control)
    if os.name == "nt":
        try:
            kernel32, handle = _windows_open_config(
                control.binding.config_path, delete_access=False
            )
        except FileNotFoundError:
            return _absent_config_state()
        try:
            return _inspect_windows_config_handle(kernel32, handle, control)
        finally:
            _windows_close_handle(kernel32, handle)
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(control.binding.config_path, flags)
    except FileNotFoundError:
        return _absent_config_state()
    try:
        value = os.fstat(fd)
        attributes = _path_attributes(value)
        is_directory = stat.S_ISDIR(value.st_mode)
        is_reparse = _is_reparse_stat(value)
        payload = b""
        marker_error = None
        marker_verified = False
        if not is_directory and not is_reparse and value.st_nlink == 1:
            while len(payload) <= MAX_CONFIG_BYTES:
                chunk = os.read(fd, min(65536, MAX_CONFIG_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload += chunk
            try:
                _strict_config_payload(payload, control)
                marker_verified = True
            except Exception as exc:
                marker_error = secret_free_exception_label(exc, "config_marker")
        else:
            marker_error = "config_type_or_link_count_is_unsafe"
        return ConfigFileState(
            exists=True,
            identity=file_identity_from_stat(value),
            attributes=attributes,
            link_count=int(value.st_nlink),
            size=int(value.st_size),
            is_directory=is_directory,
            is_reparse_point=is_reparse,
            marker_verified=marker_verified,
            marker_error=marker_error,
        )
    finally:
        os.close(fd)


def verify_initial_config(control: WorkerControl) -> ConfigFileState:
    state = inspect_owned_config(control)
    if (
        not state.exists
        or state.identity != control.config_ownership.initial_identity
        or state.is_directory
        or state.is_reparse_point
        or state.link_count != 1
        or not state.marker_verified
    ):
        raise RuntimeError("initial run-owned config identity or marker changed")
    return state


def validate_control_lease(control_file: ExclusiveFile, control: WorkerControl) -> None:
    if (
        not isinstance(control_file, ExclusiveFile)
        or not control_file.owned
        or control_file.fd < 0
        or control_file.path != control.binding.control_path
    ):
        raise RuntimeError("config control lease is not held")
    expected_identity = control.config_ownership.control_identity
    if file_identity_from_fd(control_file.fd) != expected_identity:
        raise RuntimeError("config control lease identity changed")
    if os.name == "nt":
        _validate_exclusive_handle(
            _windows_kernel32(),
            control_file.handle,
            path=control_file.path,
            root=control_file.root_path,
            root_identity=control_file.root_identity,
            initial_identity=control_file.initial_identity,
        )
    position = os.lseek(control_file.fd, 0, os.SEEK_CUR)
    try:
        os.lseek(control_file.fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while total <= _MAX_CONTROL_BYTES:
            chunk = os.read(control_file.fd, min(65536, _MAX_CONTROL_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        payload = b"".join(chunks)
    finally:
        os.lseek(control_file.fd, position, os.SEEK_SET)
    expected_control = _bind_record_to_binding(
        control.binding, RECORD_WORKER_CONTROL, control._body_mapping()
    )
    if payload != canonical_json_bytes(expected_control):
        raise RuntimeError("config control lease content changed")


def delete_owned_config_windows(
    control_file: ExclusiveFile,
    control: WorkerControl,
    final_state: ConfigFileState,
) -> ConfigDeleteResult:
    """Validate and delete the exact object through one Windows HANDLE."""

    if os.name != "nt":
        return ConfigDeleteResult(
            deleted=False,
            already_absent=False,
            foreign_replacement=False,
            blocker="runner.cleanup.config_handle_delete_unavailable",
            state=final_state,
        )
    try:
        validate_control_lease(control_file, control)
        validate_config_root(control)
    except Exception:
        return ConfigDeleteResult(
            deleted=False,
            already_absent=False,
            foreign_replacement=False,
            blocker="runner.cleanup.config_control_lease_invalid",
            state=final_state,
        )
    try:
        kernel32, handle = _windows_open_config(
            control.binding.config_path, delete_access=True
        )
    except FileNotFoundError:
        if final_state.exists:
            return ConfigDeleteResult(
                deleted=False,
                already_absent=False,
                foreign_replacement=False,
                blocker="runner.cleanup.config_final_identity_mismatch",
                state=_absent_config_state(),
            )
        return ConfigDeleteResult(
            deleted=False,
            already_absent=True,
            foreign_replacement=False,
            blocker=None,
            state=_absent_config_state(),
        )
    except Exception:
        return ConfigDeleteResult(
            deleted=False,
            already_absent=False,
            foreign_replacement=False,
            blocker="runner.cleanup.config_handle_open_failed",
            state=final_state,
        )

    state = final_state
    disposition_succeeded = False
    decision: ConfigDeleteResult | None = None
    close_error: BaseException | None = None
    try:
        state = _inspect_windows_config_handle(kernel32, handle, control)
        if not final_state.exists or not _config_state_matches(state, final_state):
            decision = ConfigDeleteResult(
                deleted=False,
                already_absent=False,
                foreign_replacement=False,
                blocker="runner.cleanup.config_final_identity_mismatch",
                state=state,
            )
        elif (
            not state.marker_verified
            or state.is_directory
            or state.is_reparse_point
            or state.link_count != 1
            or state.size is None
            or state.size > MAX_CONFIG_BYTES
        ):
            decision = ConfigDeleteResult(
                deleted=False,
                already_absent=False,
                foreign_replacement=False,
                blocker="runner.cleanup.config_provenance_invalid",
                state=state,
            )
        else:
            try:
                _windows_set_disposition(kernel32, handle)
                if int(_windows_file_info(kernel32, handle).nNumberOfLinks) != 0:
                    _windows_cancel_disposition(kernel32, handle)
                    decision = ConfigDeleteResult(
                        deleted=False,
                        already_absent=False,
                        foreign_replacement=False,
                        blocker="runner.cleanup.config_hardlink_race_retained",
                        state=state,
                    )
                else:
                    disposition_succeeded = True
            except Exception:
                decision = ConfigDeleteResult(
                    deleted=False,
                    already_absent=False,
                    foreign_replacement=False,
                    blocker="runner.cleanup.config_handle_delete_failed",
                    state=state,
                )
    except Exception:
        decision = ConfigDeleteResult(
            deleted=False,
            already_absent=False,
            foreign_replacement=False,
            blocker="runner.cleanup.config_handle_inspect_failed",
            state=state,
        )
    finally:
        try:
            _windows_close_handle(kernel32, handle)
        except BaseException as exc:
            close_error = exc

    if close_error is not None:
        return ConfigDeleteResult(
            deleted=False,
            already_absent=False,
            foreign_replacement=False,
            blocker="runner.cleanup.config_handle_close_failed",
            state=state,
        )
    if decision is not None:
        return decision
    if not disposition_succeeded:
        return ConfigDeleteResult(
            deleted=False,
            already_absent=False,
            foreign_replacement=False,
            blocker="runner.cleanup.config_handle_delete_failed",
            state=state,
        )
    try:
        replacement_identity = file_identity_from_path(control.binding.config_path)
    except FileNotFoundError:
        return ConfigDeleteResult(
            deleted=True,
            already_absent=False,
            foreign_replacement=False,
            blocker=None,
            state=state,
        )
    if replacement_identity != state.identity:
        return ConfigDeleteResult(
            deleted=False,
            already_absent=False,
            foreign_replacement=True,
            blocker="runner.cleanup.config_foreign_replacement_preserved",
            state=state,
        )
    return ConfigDeleteResult(
        deleted=False,
        already_absent=False,
        foreign_replacement=False,
        blocker="runner.cleanup.config_delete_not_absent",
        state=state,
    )


def create_activation_pipe() -> ActivationPipe:
    read_fd, write_fd = os.pipe()
    try:
        # The parent performs exactly one small capability write before it
        # enters the supervisor.  Nonblocking mode makes an unexpected kernel
        # capacity failure fail closed instead of consuming the total deadline.
        os.set_blocking(write_fd, False)
        if os.get_blocking(write_fd):
            raise RuntimeError("activation pipe write end remained blocking")
        if os.name == "nt":
            import msvcrt

            read_handle = int(msvcrt.get_osfhandle(read_fd))
            write_handle = int(msvcrt.get_osfhandle(write_fd))
            os.set_handle_inheritable(read_handle, True)
            os.set_handle_inheritable(write_handle, False)
        else:
            read_handle = read_fd
            os.set_inheritable(read_fd, True)
            os.set_inheritable(write_fd, False)
        return ActivationPipe(read_fd, read_handle, write_fd)
    except BaseException:
        os.close(read_fd)
        os.close(write_fd)
        raise


def _activation_control_digest(control_path: Path, control_bytes: bytes) -> bytes:
    if not isinstance(control_path, Path) or not control_path.is_absolute():
        raise ValueError("worker control path must be absolute")
    if not isinstance(control_bytes, bytes):
        raise ValueError("worker control payload must be bytes")
    path_bytes = str(control_path).encode("utf-8")
    if len(path_bytes) > 0xFFFFFFFF:
        raise ValueError("worker control path is too long")
    framed = (
        b"alas-headless.runner-worker-control-digest/v2\0"
        + len(path_bytes).to_bytes(4, "big")
        + path_bytes
        + control_bytes
    )
    return hashlib.sha256(framed).digest()


def send_activation(
    pipe: ActivationPipe,
    control: WorkerControl,
    control_path: Path,
    *,
    absolute_deadline: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Deliver one fixed-size capability without a blocking write loop."""

    remaining_seconds(absolute_deadline, monotonic)
    if control_path != control.binding.control_path:
        raise RuntimeError("worker activation control path changed")
    control_bytes = canonical_json_bytes(control.to_mapping())
    if not control_bytes or len(control_bytes) > _MAX_CONTROL_BYTES:
        raise RuntimeError("worker control is empty or oversized")
    token = control.activation_token
    payload = (
        _ACTIVATION_MAGIC
        + token
        + _activation_control_digest(control_path, control_bytes)
    )
    if len(payload) != ACTIVATION_RECORD_BYTES:
        raise RuntimeError("worker activation capability size changed")
    # Re-check immediately before the only kernel write.  The fresh pipe is
    # empty, its write end is nonblocking, and this record is only 72 bytes.
    remaining_seconds(absolute_deadline, monotonic)
    written = os.write(pipe.write_fd, payload)
    if written != ACTIVATION_RECORD_BYTES:
        raise OSError(
            "activation capability short write: {0}/{1}".format(
                written, ACTIVATION_RECORD_BYTES
            )
        )
    pipe.close_parent_write()


def _read_activation_handle(handle: int) -> tuple[bytes, bytes]:
    if os.name == "nt":
        import msvcrt

        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    else:
        fd = handle
    with os.fdopen(fd, "rb", closefd=True) as stream:
        payload = stream.read(ACTIVATION_RECORD_BYTES + 1)
    if len(payload) != ACTIVATION_RECORD_BYTES:
        raise RuntimeError("worker activation capability is partial or oversized")
    if not hmac.compare_digest(payload[: len(_ACTIVATION_MAGIC)], _ACTIVATION_MAGIC):
        raise RuntimeError("worker activation schema is invalid")
    token_start = len(_ACTIVATION_MAGIC)
    token_end = token_start + _ACTIVATION_TOKEN_BYTES
    return payload[token_start:token_end], payload[token_end:]


def _read_bounded_file(path: Path, maximum: int, label: str) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if not payload or len(payload) > maximum:
        raise RuntimeError(label + " is empty or oversized")
    return payload


def worker_control_from_activation(
    environment: Mapping[str, str],
    *,
    get_parent_pid: Callable[[], int] = os.getppid,
    get_process_identity: Callable[[int], str] = lambda pid: process_identity(pid),
) -> Optional[WorkerControl]:
    role = environment.get(WORKER_ROLE_ENV)
    if role is None:
        return None
    if role != "worker":
        raise RuntimeError("runner internal role is invalid")
    try:
        activation_handle = int(environment[WORKER_ACTIVATION_HANDLE_ENV])
        environment_handles = WorkerHandles(
            control=int(environment[WORKER_CONTROL_HANDLE_ENV]),
            config=int(environment[WORKER_CONFIG_HANDLE_ENV]),
            result=int(environment[WORKER_RESULT_HANDLE_ENV]),
            cleanup=int(environment[WORKER_CLEANUP_HANDLE_ENV]),
            lease=int(environment[WORKER_LEASE_HANDLE_ENV]),
            seed=int(environment[WORKER_SEED_HANDLE_ENV]),
        )
        control_path = Path(environment[WORKER_CONTROL_ENV])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "runner worker has no inherited activation authority"
        ) from exc
    activation_token, activation_digest = _read_activation_handle(activation_handle)
    control_bytes, control_identity = read_bytes_handle(
        environment_handles.control, _MAX_CONTROL_BYTES
    )
    if not hmac.compare_digest(
        activation_digest,
        _activation_control_digest(control_path, control_bytes),
    ):
        raise RuntimeError("worker activation control digest changed")
    control_mapping = strict_json_mapping_bytes(
        control_bytes, maximum=_MAX_CONTROL_BYTES, label="worker control"
    )
    if control_bytes != canonical_json_bytes(control_mapping):
        raise RuntimeError("worker control serialization is not canonical")
    try:
        control = WorkerControl.from_mapping(
            control_mapping, activation_token=activation_token
        )
    except ValueError as exc:
        raise RuntimeError(
            "worker activation token or control binding changed"
        ) from exc
    if control_path != control.binding.control_path:
        raise RuntimeError("worker activation control path changed")
    if not hmac.compare_digest(
        hashlib.sha256(activation_token).hexdigest(), control.binding.token_digest
    ):
        raise RuntimeError("worker activation token digest changed")
    if environment_handles != control.handles:
        raise RuntimeError("worker inherited output handles changed")
    if control_identity != control.config_ownership.control_identity:
        raise RuntimeError("worker inherited control identity changed")
    if control.binding.worker_pid != os.getpid():
        raise RuntimeError("worker activation PID does not match this process")
    actual_parent = get_parent_pid()
    if actual_parent != control.binding.parent_pid:
        raise RuntimeError("worker activation parent PID changed")
    if get_process_identity(actual_parent) != control.binding.parent_identity:
        raise RuntimeError("worker activation parent process changed")
    for label, handle in environment_handles.to_mapping().items():
        if label == "control":
            continue
        if os.name == "nt":
            os.set_handle_inheritable(handle, False)
        else:
            os.set_inheritable(handle, False)
    # This marker is deliberately absent from the serialized control and is not
    # accepted by WorkerControl.__init__.  It records that this specific object
    # was produced by consuming the live activation channel.
    control.bind_activation_token(activation_token, verified=True)
    return control


def process_identity(pid: int) -> str:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("process identity PID is invalid")
    if os.name != "nt":
        stat = Path("/proc") / str(pid) / "stat"
        fields = stat.read_text(encoding="utf-8").split()
        return "{0}:{1}".format(pid, int(fields[21]))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    get_times = kernel32.GetProcessTimes
    get_times.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    get_times.restype = wintypes.BOOL
    close = kernel32.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    handle = open_process(0x1000, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not get_times(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
        ticks = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        return "{0}:{1}".format(pid, ticks)
    finally:
        if not close(handle):
            raise OSError(ctypes.get_last_error(), "CloseHandle(process) failed")


class WindowsWorkerJob:
    """Kill-on-close containment for the worker and its host-side children."""

    _KILL_ON_CLOSE = 0x00002000

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("EventSp worker containment requires Windows")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = self._kernel32.CreateJobObjectW
        create.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        create.restype = wintypes.HANDLE
        self._handle = create(None, None)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
        try:
            set_handle_information = self._kernel32.SetHandleInformation
            set_handle_information.argtypes = (
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
            )
            set_handle_information.restype = wintypes.BOOL
            if not set_handle_information(self._handle, 1, 0):
                raise OSError(
                    ctypes.get_last_error(), "SetHandleInformation(job) failed"
                )
            self._configure()
        except BaseException:
            self.close()
            raise

    def _configure(self) -> None:
        class BASIC_LIMITS(ctypes.Structure):
            _fields_ = (
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            )

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = tuple(
                (name, ctypes.c_ulonglong)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            )

        class EXTENDED_LIMITS(ctypes.Structure):
            _fields_ = (
                ("BasicLimitInformation", BASIC_LIMITS),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            )

        info = EXTENDED_LIMITS()
        info.BasicLimitInformation.LimitFlags = self._KILL_ON_CLOSE
        setter = self._kernel32.SetInformationJobObject
        setter.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        setter.restype = wintypes.BOOL
        if not setter(self._handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def assign(self, process: subprocess.Popen) -> None:
        assign = self._kernel32.AssignProcessToJobObject
        assign.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        assign.restype = wintypes.BOOL
        process_handle = getattr(process, "_handle", None)
        if process_handle is None or not assign(self._handle, int(process_handle)):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        if not self.contains(process):
            raise RuntimeError("worker process was not contained by its Job Object")

    def contains(self, process: subprocess.Popen) -> bool:
        checker = self._kernel32.IsProcessInJob
        checker.argtypes = (
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.BOOL),
        )
        checker.restype = wintypes.BOOL
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            return False
        result = wintypes.BOOL()
        if not checker(int(process_handle), self._handle, ctypes.byref(result)):
            raise OSError(ctypes.get_last_error(), "IsProcessInJob failed")
        return bool(result.value)

    def active_process_count(self) -> int:
        class BASIC_ACCOUNTING(ctypes.Structure):
            _fields_ = (
                ("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            )

        info = BASIC_ACCOUNTING()
        query = self._kernel32.QueryInformationJobObject
        query.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        )
        query.restype = wintypes.BOOL
        if not query(self._handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
        return int(info.ActiveProcesses)

    def terminate(self, exit_code: int = 124) -> None:
        terminate = self._kernel32.TerminateJobObject
        terminate.argtypes = (wintypes.HANDLE, wintypes.UINT)
        terminate.restype = wintypes.BOOL
        if not terminate(self._handle, exit_code):
            raise OSError(ctypes.get_last_error(), "TerminateJobObject failed")

    def close(self) -> None:
        if self._handle:
            handle = self._handle
            close = self._kernel32.CloseHandle
            close.argtypes = (wintypes.HANDLE,)
            close.restype = wintypes.BOOL
            if not close(handle):
                raise OSError(ctypes.get_last_error(), "CloseHandle(job) failed")
            self._handle = None


def install_worker_stop_handler() -> Callable[[], None]:
    stop_signal = (
        signal.SIGBREAK
        if os.name == "nt" and hasattr(signal, "SIGBREAK")
        else signal.SIGTERM
    )
    previous = signal.getsignal(stop_signal)

    def request_stop(_signum: int, _frame: Any) -> None:
        raise RunnerStopRequested("runner supervisor requested cooperative stop")

    signal.signal(stop_signal, request_stop)
    return lambda: signal.signal(stop_signal, previous)


def _send_cooperative_stop(process: subprocess.Popen) -> None:
    value = (
        signal.CTRL_BREAK_EVENT
        if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT")
        else signal.SIGTERM
    )
    process.send_signal(value)


def _confirm_process_dead(
    process: subprocess.Popen,
) -> tuple[bool, Optional[int], Optional[str]]:
    try:
        code = process.poll()
    except BaseException as exc:
        return False, None, secret_free_exception_label(exc, "process_poll")
    return code is not None, code, None


def _wait_for_job_empty(job: Any, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        if job.active_process_count() == 0:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))


def shutdown_worker(
    process: subprocess.Popen,
    job: Any,
    *,
    reason: str,
    send_cooperative_stop: Callable[[subprocess.Popen], None] = _send_cooperative_stop,
    cleanup_grace_seconds: float = WORKER_CLEANUP_GRACE_SECONDS,
    force_stop_grace_seconds: float = WORKER_FORCE_STOP_GRACE_SECONDS,
    wait_for_job_empty: Callable[[Any, float], bool] = _wait_for_job_empty,
) -> ProcessSupervisionResult:
    """Escalate inside the owned Job and prove that the Job is empty.

    A dead root PID is insufficient: a child could still be using the leased
    forward or an inherited output handle.  Therefore artifact cleanup is
    authorized only when the root is dead and the Job active-process count is
    observed at zero.  The separate root proof matters if assignment itself
    failed and the Job was empty from the start.
    """

    errors = []
    cooperative = forced_terminate = forced_kill = False
    mode = reason + "_cooperative"
    code: Optional[int] = None
    root_dead = False

    def job_empty(label: str, timeout_seconds: float = 0.0) -> bool:
        try:
            return wait_for_job_empty(job, timeout_seconds)
        except BaseException as exc:
            errors.append(secret_free_exception_label(exc, label))
            return False

    try:
        send_cooperative_stop(process)
        cooperative = True
    except BaseException as exc:
        errors.append(secret_free_exception_label(exc, "ctrl_break"))
    try:
        code = process.wait(timeout=cleanup_grace_seconds)
        root_dead = True
    except BaseException as exc:
        errors.append(secret_free_exception_label(exc, "cooperative_wait"))
        root_dead, code, poll_error = _confirm_process_dead(process)
        if poll_error:
            errors.append("cooperative_poll:" + poll_error)

    confirmed = root_dead and job_empty("cooperative_job_query")
    if not confirmed:
        mode = reason + "_terminated_job"
        try:
            job.terminate(124)
            forced_terminate = True
        except BaseException as exc:
            errors.append(secret_free_exception_label(exc, "job_terminate"))
        try:
            code = process.wait(timeout=force_stop_grace_seconds)
            root_dead = True
        except BaseException as exc:
            errors.append(secret_free_exception_label(exc, "job_wait"))
            root_dead, code, poll_error = _confirm_process_dead(process)
            if poll_error:
                errors.append("job_poll:" + poll_error)
        confirmed = root_dead and job_empty(
            "terminated_job_query", force_stop_grace_seconds
        )

    # If assignment or TerminateJobObject failed to stop the root, host-only
    # terminate/kill remains a bounded last resort.  It never targets the game,
    # emulator, or ADB server; and it still cannot authorize cleanup unless the
    # Job subsequently proves empty.
    if not root_dead:
        mode = reason + "_terminated_worker"
        try:
            process.terminate()
            forced_terminate = True
        except BaseException as exc:
            errors.append(secret_free_exception_label(exc, "terminate"))
        try:
            code = process.wait(timeout=force_stop_grace_seconds)
            root_dead = True
        except BaseException as exc:
            errors.append(secret_free_exception_label(exc, "terminate_wait"))
            root_dead, code, poll_error = _confirm_process_dead(process)
            if poll_error:
                errors.append("terminate_poll:" + poll_error)
        confirmed = root_dead and job_empty(
            "worker_terminate_job_query", force_stop_grace_seconds
        )
    if not root_dead:
        mode = reason + "_killed_worker"
        try:
            process.kill()
            forced_kill = True
        except BaseException as exc:
            errors.append(secret_free_exception_label(exc, "kill"))
        try:
            code = process.wait(timeout=force_stop_grace_seconds)
            root_dead = True
        except BaseException as exc:
            errors.append(secret_free_exception_label(exc, "kill_wait"))
            root_dead, code, poll_error = _confirm_process_dead(process)
            if poll_error:
                errors.append("kill_poll:" + poll_error)
        confirmed = root_dead and job_empty(
            "worker_kill_job_query", force_stop_grace_seconds
        )
    return ProcessSupervisionResult(
        reason=reason,
        termination_mode=mode if confirmed else reason + "_unconfirmed",
        returncode=code,
        termination_confirmed=confirmed,
        cooperative_stop_requested=cooperative,
        forced_terminate=forced_terminate,
        forced_kill=forced_kill,
        errors=tuple(errors),
    )


def supervise_process(
    process: subprocess.Popen,
    job: Any,
    *,
    absolute_deadline: float,
    monotonic: Callable[[], float] = time.monotonic,
    shutdown: Callable[..., ProcessSupervisionResult] = shutdown_worker,
) -> ProcessSupervisionResult:
    """Wait through the absolute deadline; every exceptional path shuts down."""

    def stop(
        reason: str, original: BaseException | None = None
    ) -> ProcessSupervisionResult:
        try:
            result = shutdown(process, job, reason=reason)
        except BaseException as exc:
            messages = []
            if original is not None:
                messages.append(secret_free_exception_label(original, "wait"))
            messages.append(secret_free_exception_label(exc, "shutdown"))
            return ProcessSupervisionResult(
                reason=reason,
                termination_mode=reason + "_unconfirmed",
                returncode=None,
                termination_confirmed=False,
                cooperative_stop_requested=False,
                forced_terminate=False,
                forced_kill=False,
                errors=tuple(messages),
            )
        if original is None:
            return result
        return ProcessSupervisionResult(
            reason=result.reason,
            termination_mode=result.termination_mode,
            returncode=result.returncode,
            termination_confirmed=result.termination_confirmed,
            cooperative_stop_requested=result.cooperative_stop_requested,
            forced_terminate=result.forced_terminate,
            forced_kill=result.forced_kill,
            errors=(
                *result.errors,
                secret_free_exception_label(original, "wait"),
            ),
        )

    try:
        code = process.wait(timeout=max(0.0, absolute_deadline - monotonic()))
    except subprocess.TimeoutExpired as exc:
        return stop("deadline", exc)
    except KeyboardInterrupt as exc:
        return stop("interrupted", exc)
    except BaseException as exc:
        return stop("supervision_error", exc)
    if monotonic() >= absolute_deadline:
        # A wait result at the boundary is late even if the worker serialized a
        # success immediately before exit.  Deadline always wins.
        if not _job_is_empty(job):
            return stop("deadline")
        return ProcessSupervisionResult(
            reason="deadline",
            termination_mode="deadline_late_exit",
            returncode=code,
            termination_confirmed=_job_is_empty(job),
            cooperative_stop_requested=False,
            forced_terminate=False,
            forced_kill=False,
        )
    if not _job_is_empty(job):
        return stop("supervision_error")
    return ProcessSupervisionResult(
        reason="completed",
        termination_mode="completed",
        returncode=code,
        termination_confirmed=True,
        cooperative_stop_requested=False,
        forced_terminate=False,
        forced_kill=False,
    )


def _job_is_empty(job: Any) -> bool:
    try:
        return job.active_process_count() == 0
    except BaseException:
        return False


def select_forward_cleanup(
    *,
    binding: RunBinding,
    serial: str,
    verified_game_pid: int,
    starting: Sequence[ForwardRecord],
    ending: Sequence[ForwardRecord],
    lease: Optional[ForwardLease],
) -> ForwardCleanupDecision:
    start = tuple(sorted(set(starting)))
    end = tuple(sorted(set(ending)))
    expected_remote = "localabstract:alas.g3.{0}".format(verified_game_pid)
    if lease is not None:
        if (
            lease.binding != binding
            or lease.serial != serial
            or lease.verified_game_pid != verified_game_pid
            or lease.remote != expected_remote
            or lease.starting_forwards != start
        ):
            return ForwardCleanupDecision(
                None,
                False,
                "lease",
                ("runner.cleanup.forward_lease_identity_mismatch",),
            )
        if lease.record in start:
            return ForwardCleanupDecision(
                None,
                False,
                "lease",
                ("runner.cleanup.forward_lease_claims_preexisting",),
            )
        if lease.record not in end:
            return ForwardCleanupDecision(None, True, "lease")
        return ForwardCleanupDecision(lease.record, False, "lease")
    delta = tuple(item for item in end if item not in start)
    observer_delta = tuple(
        item
        for item in delta
        if item.serial == serial and _REMOTE_FORWARD.fullmatch(item.remote) is not None
    )
    if not observer_delta:
        return ForwardCleanupDecision(None, True, "inventory_delta")
    if any(item.remote != expected_remote for item in observer_delta):
        return ForwardCleanupDecision(
            None,
            False,
            "inventory_delta",
            ("runner.cleanup.forward_delta_identity_mismatch",),
        )
    if len(observer_delta) != 1:
        return ForwardCleanupDecision(
            None, False, "inventory_delta", ("runner.cleanup.forward_delta_ambiguous",)
        )
    return ForwardCleanupDecision(observer_delta[0], False, "inventory_delta")
