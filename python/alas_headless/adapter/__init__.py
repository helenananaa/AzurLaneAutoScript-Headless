"""Stable kernel contracts for the ALAS semantic adaptation boundary."""

from .errors import (
    ActionLeaseError,
    AdapterContractError,
    CapabilityClosureError,
    FlowScopeError,
    StaleFrameError,
    UnknownObservationError,
    UnsupportedPixelRead,
)
from .ports import (
    ActionIntent,
    ActionLease,
    ActionPort,
    ActionReceiptV2,
    FlowScope,
    FlowScopeToken,
    ObservationPort,
    ObserveRequest,
    ObserveResult,
    RuntimeHandleFactory,
    RuntimeHandlePort,
    SemanticFrameIdentity,
)
from .registry import (
    ObservationHandler,
    ObservationRegistration,
    ObservationRegistry,
)
from .runtime_handle import (
    AdbRuntimeHandle,
    semantic_runtime_fingerprint_sha256,
)
from .scope import FlowScopeStack


__all__ = (
    "ActionLeaseError",
    "ActionIntent",
    "ActionLease",
    "ActionPort",
    "ActionReceiptV2",
    "AdbRuntimeHandle",
    "AdapterContractError",
    "CapabilityClosureError",
    "FlowScope",
    "FlowScopeError",
    "FlowScopeStack",
    "FlowScopeToken",
    "ObservationPort",
    "ObservationHandler",
    "ObservationRegistration",
    "ObservationRegistry",
    "ObserveRequest",
    "ObserveResult",
    "RuntimeHandleFactory",
    "RuntimeHandlePort",
    "SemanticFrameIdentity",
    "semantic_runtime_fingerprint_sha256",
    "StaleFrameError",
    "UnknownObservationError",
    "UnsupportedPixelRead",
)
