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
from .scope import FlowScopeStack


__all__ = (
    "ActionLeaseError",
    "ActionIntent",
    "ActionLease",
    "ActionPort",
    "ActionReceiptV2",
    "AdapterContractError",
    "CapabilityClosureError",
    "FlowScope",
    "FlowScopeError",
    "FlowScopeStack",
    "FlowScopeToken",
    "ObservationPort",
    "ObserveRequest",
    "ObserveResult",
    "RuntimeHandleFactory",
    "RuntimeHandlePort",
    "SemanticFrameIdentity",
    "StaleFrameError",
    "UnknownObservationError",
    "UnsupportedPixelRead",
)
