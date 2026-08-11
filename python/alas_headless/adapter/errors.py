"""Classified fail-closed errors for the semantic adapter kernel."""

from __future__ import annotations

from typing import ClassVar

from ..semantic_oracle import SemanticGateClosed


class AdapterContractError(SemanticGateClosed):
    """Base rejection for an invalid adapter request or lifecycle state."""

    code: ClassVar[str] = "adapter-contract"
    safe_message: ClassVar[str] = "semantic adapter contract rejected"

    def __init__(self) -> None:
        super().__init__(self.safe_message)


class FlowScopeError(AdapterContractError):
    """A flow scope is missing, mismatched, leaked, or closed out of order."""

    code = "flow-scope"
    safe_message = "semantic adapter flow scope rejected"


class UnknownObservationError(AdapterContractError):
    """No exact contextual observation mapping owns the request."""

    code = "unknown-observation"
    safe_message = "semantic adapter observation is not mapped"


class UnsupportedPixelRead(AdapterContractError):
    """A semantic-mode branch attempted to consume framebuffer pixels."""

    code = "unsupported-pixel-read"
    safe_message = "pixel observation is unsupported in semantic mode"


class StaleFrameError(AdapterContractError):
    """A read attempted to reuse an absent, stale, or invalidated frame."""

    code = "stale-frame"
    safe_message = "semantic frame is absent, stale, or invalidated"


class CapabilityClosureError(AdapterContractError):
    """The exact task profile lacks required observation or recovery closure."""

    code = "capability-closure"
    safe_message = "semantic capability closure is incomplete"


class RunPolicyError(AdapterContractError):
    """A run policy is malformed, ambiguous, or bound to another identity."""

    code = "run-policy"
    safe_message = "semantic run policy is invalid"


class ActionLeaseError(AdapterContractError):
    """An action has no valid identity-bound single-use authority."""

    code = "action-lease"
    safe_message = "semantic action lease is invalid"
