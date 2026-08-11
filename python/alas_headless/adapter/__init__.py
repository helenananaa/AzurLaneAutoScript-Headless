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


__all__ = (
    "ActionLeaseError",
    "AdapterContractError",
    "CapabilityClosureError",
    "FlowScopeError",
    "StaleFrameError",
    "UnknownObservationError",
    "UnsupportedPixelRead",
)
