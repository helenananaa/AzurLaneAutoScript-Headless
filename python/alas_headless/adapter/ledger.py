"""Single-use action grant ledger for semantic mutation dispatch."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Generic, Mapping, TypeVar

from .capabilities import (
    CapabilityClosureReport,
    CapabilityInventory,
    TaskCapabilityProfile,
    capability_closure_report,
)
from .errors import ActionGrantExhausted, ActionLeaseError, CapabilityClosureError
from .policy import RecoveryPolicy


T = TypeVar("T")


def compatibility_policy_sha256(
    profile_id: str,
    grants: Mapping[str, int],
    recovery_policy: RecoveryPolicy = RecoveryPolicy.QUALIFICATION_STOP,
) -> str:
    """Bind a legacy compatibility ledger without inventing a RunPolicy."""

    document = {
        "schema": "alas-headless.legacy-policy-grants/v1",
        "profile_id": profile_id,
        "grants": dict(grants),
        "recovery_policy": recovery_policy.value,
    }
    try:
        encoded = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("legacy compatibility policy is malformed") from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ActionGrantDispatch(Generic[T]):
    capability: str
    policy_sha256: str
    remaining_after_dispatch: int
    value: T


class ActionNotDispatched(Exception):
    """Internal signal that a reserved grant provably produced no input."""

    def __init__(self, cause: Exception) -> None:
        if not isinstance(cause, Exception):
            raise TypeError("undispatched action cause must be an Exception")
        self.cause = cause
        super().__init__("semantic action was not dispatched")


class ActionLedger:
    """Reserve before dispatch; refund only an explicit zero-input outcome."""

    def __init__(
        self,
        *,
        profile: TaskCapabilityProfile,
        inventory: CapabilityInventory,
        grants: Mapping[str, int],
        recovery_policy: RecoveryPolicy,
        policy_sha256: str,
    ) -> None:
        if not isinstance(policy_sha256, str) or len(policy_sha256) != 64:
            raise ValueError("action ledger policy hash is malformed")
        try:
            int(policy_sha256, 16)
        except ValueError as exc:
            raise ValueError("action ledger policy hash is malformed") from exc
        self.profile = profile
        self.inventory = inventory
        self.recovery_policy = recovery_policy
        self.policy_sha256 = policy_sha256.lower()
        self._remaining = dict(grants)
        self._initial = MappingProxyType(dict(grants))
        self._lock = threading.Lock()
        self._closed = False
        self._report = capability_closure_report(
            profile,
            inventory,
            grants,
            recovery_policy,
        )

    @property
    def initial_grants(self) -> Mapping[str, int]:
        return self._initial

    def preflight(self) -> CapabilityClosureReport:
        return self._report

    def require_preflight(self) -> CapabilityClosureReport:
        if not self._report.ready:
            raise CapabilityClosureError()
        return self._report

    def remaining(self, capability: str) -> int:
        with self._lock:
            return self._remaining.get(capability, 0)

    def allowed(self, capability: str) -> bool:
        if not self._report.ready or capability not in self.profile.required_grants:
            return False
        with self._lock:
            return not self._closed and self._remaining.get(capability, 0) > 0

    def require_available(self, capability: str, *, units: int = 1) -> None:
        """Classify a no-input budget refusal without reserving a grant.

        Compatibility profiles omit explicitly zero grants from required
        actions. They are still a budget refusal, whereas a closed ledger,
        missing capability, or incomplete preflight remains a contract error.
        Dispatch keeps its atomic reservation and authority checks.
        """
        if type(units) is not int or units <= 0:
            raise ValueError('action grant units must be a positive integer')
        self.require_preflight()
        with self._lock:
            if self._closed:
                raise ActionLeaseError()
            if (capability in self._initial
                    and capability in self.inventory.actions
                    and self._remaining.get(capability, 0) < units):
                raise ActionGrantExhausted()
            if capability not in self.profile.required_grants:
                raise ActionLeaseError()

    def dispatch(
        self,
        capability: str,
        operation: Callable[[], T],
        *,
        units: int = 1,
    ) -> ActionGrantDispatch[T]:
        if not callable(operation):
            raise TypeError("action ledger operation is not callable")
        if type(units) is not int or units <= 0:
            raise ValueError('action grant units must be a positive integer')
        self.require_preflight()
        if capability not in self.profile.required_grants:
            raise ActionLeaseError()
        with self._lock:
            if self._closed or self._remaining.get(capability, 0) < units:
                raise ActionLeaseError()
            self._remaining[capability] -= units
            remaining = self._remaining[capability]
        try:
            value = operation()
        except ActionNotDispatched as marker:
            with self._lock:
                self._remaining[capability] += units
            raise marker.cause.with_traceback(marker.cause.__traceback__) from None
        return ActionGrantDispatch(
            capability=capability,
            policy_sha256=self.policy_sha256,
            remaining_after_dispatch=remaining,
            value=value,
        )

    def close(self) -> None:
        with self._lock:
            self._closed = True
