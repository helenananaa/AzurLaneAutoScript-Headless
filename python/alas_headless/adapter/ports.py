"""Immutable value objects and protocols for the semantic adapter kernel."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from numbers import Real
from types import MappingProxyType
from typing import Any, Callable, FrozenSet, Mapping, Tuple

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # Python 3.7 in the pinned ALAS runtime
    from typing_extensions import Protocol, runtime_checkable

from ..semantic_oracle import Bounds, Point


_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_RESOURCE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _require_token(value: str, field: str) -> str:
    if not isinstance(value, str) or _TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError("{0} must be a canonical token".format(field))
    return value


def _require_capability(value: str) -> str:
    if not isinstance(value, str) or _CAPABILITY_PATTERN.fullmatch(value) is None:
        raise ValueError("capability must be a canonical dotted name")
    return value


def _require_sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError("{0} must be a lowercase SHA-256".format(field))
    return value


def _require_integer(
    value: int,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("{0} must be an integer in range".format(field))
    if maximum is not None and value > maximum:
        raise ValueError("{0} must be an integer in range".format(field))
    return value


def _require_path_identifier(value: str, field: str, *, unity: bool = False) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
        or value.startswith(("/", "\\"))
        or value.endswith(("/", "\\"))
        or ".." in value.replace("\\", "/").split("/")
        or (unity and "/" not in value)
        or (unity and "*" in value)
    ):
        raise ValueError("{0} must be an exact relative identity".format(field))
    return value


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("mapping keys must be non-empty strings")
            frozen[key] = _freeze_value(child)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(child) for child in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(child) for child in value)
    if isinstance(value, (str, int, float, bool, bytes, type(None))):
        return value
    dataclass_parameters = getattr(value, "__dataclass_params__", None)
    if dataclass_parameters is not None:
        if dataclass_parameters.frozen:
            return value
        raise ValueError("adapter contract dataclass must be frozen")
    raise ValueError("adapter contract value is not immutable")


def _validate_point_and_bounds(point: Point, bounds: Bounds) -> None:
    if not isinstance(point, Point) or not isinstance(bounds, Bounds):
        raise ValueError("action geometry must use typed point and bounds")
    values = (bounds.left, bounds.top, bounds.right, bounds.bottom, point.x, point.y)
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError("action geometry must be finite numeric values")
    if bounds.left >= bounds.right or bounds.top >= bounds.bottom:
        raise ValueError("action bounds must have positive area")
    if not (
        bounds.left <= point.x <= bounds.right
        and bounds.top <= point.y <= bounds.bottom
    ):
        raise ValueError("action point must stay inside bounds")


@dataclass(frozen=True)
class FlowScope:
    scope_id: str
    kind: str
    operation: str
    parent_scope_id: str | None
    task_config_sha256: str
    allowed_capabilities: FrozenSet[str]
    deadline_monotonic_ns: int

    def __post_init__(self) -> None:
        _require_token(self.scope_id, "scope_id")
        _require_token(self.kind, "flow kind")
        _require_token(self.operation, "flow operation")
        if self.parent_scope_id is not None:
            _require_token(self.parent_scope_id, "parent_scope_id")
            if self.parent_scope_id == self.scope_id:
                raise ValueError("flow scope cannot parent itself")
        _require_sha256(self.task_config_sha256, "task_config_sha256")
        capabilities = frozenset(self.allowed_capabilities)
        if any(not isinstance(item, str) for item in capabilities):
            raise ValueError("allowed capabilities must be strings")
        for capability in capabilities:
            _require_capability(capability)
        _require_integer(
            self.deadline_monotonic_ns,
            "deadline_monotonic_ns",
            minimum=1,
        )
        object.__setattr__(self, "allowed_capabilities", capabilities)


@dataclass(frozen=True)
class FlowScopeToken:
    session_id: str
    scope_id: str
    ordinal: int

    def __post_init__(self) -> None:
        _require_token(self.session_id, "session_id")
        _require_token(self.scope_id, "scope_id")
        _require_integer(self.ordinal, "scope ordinal")


@dataclass(frozen=True)
class SemanticFrameIdentity:
    frame_id: str
    pid: int
    generation: int
    scene_handle: int
    fingerprint_sha256: str
    raw_state_sha256: str

    def __post_init__(self) -> None:
        _require_token(self.frame_id, "frame_id")
        _require_integer(self.pid, "pid", minimum=1)
        _require_integer(self.generation, "generation")
        if isinstance(self.scene_handle, bool) or not isinstance(
            self.scene_handle, int
        ):
            raise ValueError("scene_handle must be an integer")
        _require_sha256(self.fingerprint_sha256, "fingerprint_sha256")
        _require_sha256(self.raw_state_sha256, "raw_state_sha256")


@dataclass(frozen=True)
class ObserveRequest:
    scope_id: str
    primitive: str
    alas_resource: str
    parameters: Mapping[str, Any]
    frame_id: str

    def __post_init__(self) -> None:
        _require_token(self.scope_id, "scope_id")
        _require_token(self.primitive, "observation primitive")
        if (
            not isinstance(self.alas_resource, str)
            or _RESOURCE_PATTERN.fullmatch(self.alas_resource) is None
        ):
            raise ValueError("ALAS resource must be a canonical resource name")
        _require_token(self.frame_id, "frame_id")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("observation parameters must be a mapping")
        object.__setattr__(self, "parameters", _freeze_value(self.parameters))


@dataclass(frozen=True)
class ObserveResult:
    request: ObserveRequest
    frame: SemanticFrameIdentity
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.request, ObserveRequest):
            raise ValueError("observation result request is not typed")
        if not isinstance(self.frame, SemanticFrameIdentity):
            raise ValueError("observation result frame is not typed")
        if self.request.frame_id != self.frame.frame_id:
            raise ValueError("observation result frame changed")
        object.__setattr__(self, "value", _freeze_value(self.value))


@dataclass(frozen=True)
class ActionIntent:
    intent_id: str
    scope_id: str
    capability: str
    logical_action: str
    target_semantic_id: str
    frame_id: str
    expected_postcondition: str

    def __post_init__(self) -> None:
        _require_token(self.intent_id, "intent_id")
        _require_token(self.scope_id, "scope_id")
        _require_capability(self.capability)
        _require_token(self.logical_action, "logical_action")
        _require_path_identifier(self.target_semantic_id, "target_semantic_id")
        _require_token(self.frame_id, "frame_id")
        _require_token(self.expected_postcondition, "expected_postcondition")


@dataclass(frozen=True)
class ActionLease:
    intent: ActionIntent
    frame: SemanticFrameIdentity
    session_id: str
    pid: int
    fingerprint_sha256: str
    policy_sha256: str
    remaining_budget: int
    expires_monotonic_ns: int

    def __post_init__(self) -> None:
        if not isinstance(self.intent, ActionIntent):
            raise ValueError("action lease intent is not typed")
        if not isinstance(self.frame, SemanticFrameIdentity):
            raise ValueError("action lease frame is not typed")
        _require_token(self.session_id, "session_id")
        _require_integer(self.pid, "pid", minimum=1)
        _require_sha256(self.fingerprint_sha256, "fingerprint_sha256")
        _require_sha256(self.policy_sha256, "policy_sha256")
        _require_integer(self.remaining_budget, "remaining_budget", minimum=1, maximum=1)
        _require_integer(
            self.expires_monotonic_ns,
            "expires_monotonic_ns",
            minimum=1,
        )
        if self.intent.frame_id != self.frame.frame_id:
            raise ValueError("action lease frame changed")
        if self.pid != self.frame.pid:
            raise ValueError("action lease PID changed")
        if self.fingerprint_sha256 != self.frame.fingerprint_sha256:
            raise ValueError("action lease fingerprint changed")


@dataclass(frozen=True)
class ActionReceiptV2:
    lease: ActionLease
    intent_id: str
    pid: int
    before_generation: int
    action_generation: int
    semantic_id: str
    unity_path: str
    bounds: Bounds
    point: Point
    top_raycast: bool
    injected: bool
    backend_method: str

    def __post_init__(self) -> None:
        if not isinstance(self.lease, ActionLease):
            raise ValueError("action receipt lease is not typed")
        _require_token(self.intent_id, "intent_id")
        _require_integer(self.pid, "pid", minimum=1)
        _require_integer(self.before_generation, "before_generation")
        _require_integer(self.action_generation, "action_generation")
        _require_path_identifier(self.semantic_id, "semantic_id")
        _require_path_identifier(self.unity_path, "unity_path", unity=True)
        _require_token(self.backend_method, "backend_method")
        if not isinstance(self.top_raycast, bool) or not isinstance(self.injected, bool):
            raise ValueError("action receipt flags must be booleans")
        if self.intent_id != self.lease.intent.intent_id:
            raise ValueError("action receipt intent changed")
        if self.pid != self.lease.pid:
            raise ValueError("action receipt PID changed")
        if self.before_generation != self.lease.frame.generation:
            raise ValueError("action receipt input generation changed")
        if self.action_generation < self.before_generation:
            raise ValueError("action receipt generation moved backwards")
        if self.semantic_id != self.lease.intent.target_semantic_id:
            raise ValueError("action receipt semantic target changed")
        if self.injected and not self.top_raycast:
            raise ValueError("injected action requires top raycast")
        _validate_point_and_bounds(self.point, self.bounds)


@runtime_checkable
class ObservationPort(Protocol):
    def observe(self, request: ObserveRequest) -> ObserveResult:
        """Resolve one exact contextual observation from the current frame."""


@runtime_checkable
class ActionPort(Protocol):
    def dispatch(self, intent: ActionIntent, lease: ActionLease) -> ActionReceiptV2:
        """Dispatch one admitted final input and return its bound receipt."""


@runtime_checkable
class RuntimeHandlePort(Protocol):
    @property
    def fingerprint_sha256(self) -> str:
        """Return the immutable runtime identity used by frame/action leases."""

    @property
    def pid(self) -> int:
        """Return the exact currently attached game PID."""

    def observer_request(self, request_line: str) -> Mapping[str, Any]:
        """Request one allowlisted record from the semantic observer."""

    def foreground_component(self) -> str:
        """Return the exact top-resumed Android component."""

    def tap(self, x: float, y: float) -> None:
        """Dispatch one already-authorized point input."""

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        """Dispatch one already-authorized typed gesture."""


RuntimeHandleFactory = Callable[[], RuntimeHandlePort]
