"""Contextual exact dispatch registry for ALAS semantic observations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .errors import (
    AdapterContractError,
    CapabilityClosureError,
    UnknownObservationError,
)
from .ports import FlowScope, ObserveRequest, ObserveResult


_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_RESOURCE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_SAFE_PATTERN_PATTERN = re.compile(r"^\^[A-Z][A-Z0-9_]{2,}.*\$$")

ObservationHandler = Callable[[ObserveRequest], ObserveResult]


@dataclass(frozen=True, order=True)
class ObservationRegistration:
    flow_kind: str
    operation: str
    primitive: str
    selector: str
    selector_kind: str
    capability: str


@dataclass(frozen=True)
class _RegisteredHandler:
    registration: ObservationRegistration
    handler: ObservationHandler
    pattern: re.Pattern[str] | None = None


def _require_token(value: str, field: str) -> str:
    if not isinstance(value, str) or _TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError("{0} must be a canonical token".format(field))
    return value


def _require_capability(value: str) -> str:
    if not isinstance(value, str) or _CAPABILITY_PATTERN.fullmatch(value) is None:
        raise ValueError("capability must be a canonical dotted name")
    return value


class ObservationRegistry:
    """Map one exact ALAS flow/request context to one reviewed handler."""

    def __init__(self) -> None:
        self._exact: dict[tuple[str, str, str, str], _RegisteredHandler] = {}
        self._patterns: list[_RegisteredHandler] = []

    @staticmethod
    def _context(
        flow_kind: str,
        operation: str,
        primitive: str,
    ) -> tuple[str, str, str]:
        return (
            _require_token(flow_kind, "flow kind"),
            _require_token(operation, "operation"),
            _require_token(primitive, "primitive"),
        )

    def register_exact(
        self,
        *,
        flow_kind: str,
        operation: str,
        primitive: str,
        resource: str,
        capability: str,
        handler: ObservationHandler,
    ) -> None:
        context = self._context(flow_kind, operation, primitive)
        if not isinstance(resource, str) or _RESOURCE_PATTERN.fullmatch(resource) is None:
            raise ValueError("resource must be a canonical ALAS name")
        _require_capability(capability)
        if not callable(handler):
            raise ValueError("observation handler must be callable")
        key = (*context, resource)
        if key in self._exact:
            raise AdapterContractError()
        registration = ObservationRegistration(
            *context,
            selector=resource,
            selector_kind="exact",
            capability=capability,
        )
        self._exact[key] = _RegisteredHandler(registration, handler)

    def register_pattern(
        self,
        *,
        flow_kind: str,
        operation: str,
        primitive: str,
        resource_pattern: str,
        capability: str,
        handler: ObservationHandler,
    ) -> None:
        context = self._context(flow_kind, operation, primitive)
        if (
            not isinstance(resource_pattern, str)
            or _SAFE_PATTERN_PATTERN.fullmatch(resource_pattern) is None
        ):
            raise ValueError("resource pattern must have a fixed ALAS prefix")
        _require_capability(capability)
        if not callable(handler):
            raise ValueError("observation handler must be callable")
        try:
            pattern = re.compile(resource_pattern)
        except re.error as exc:
            raise ValueError("resource pattern is malformed") from exc
        registration = ObservationRegistration(
            *context,
            selector=resource_pattern,
            selector_kind="pattern",
            capability=capability,
        )
        if any(
            (
                item.registration.flow_kind,
                item.registration.operation,
                item.registration.primitive,
                item.registration.selector,
            )
            == (flow_kind, operation, primitive, resource_pattern)
            for item in self._patterns
        ):
            raise AdapterContractError()
        self._patterns.append(_RegisteredHandler(registration, handler, pattern))

    def inventory(self) -> tuple[ObservationRegistration, ...]:
        registrations = [item.registration for item in self._exact.values()]
        registrations.extend(item.registration for item in self._patterns)
        return tuple(sorted(registrations))

    def required_capabilities(self) -> tuple[str, ...]:
        return tuple(sorted({item.capability for item in self.inventory()}))

    def dispatch(self, scope: FlowScope, request: ObserveRequest) -> ObserveResult:
        if not isinstance(scope, FlowScope) or not isinstance(request, ObserveRequest):
            raise AdapterContractError()
        if request.scope_id != scope.scope_id:
            raise AdapterContractError()
        context = (scope.kind, scope.operation, request.primitive)
        exact = self._exact.get((*context, request.alas_resource))
        if exact is not None:
            selected = exact
        else:
            matches = [
                item
                for item in self._patterns
                if item.registration.flow_kind == scope.kind
                and item.registration.operation == scope.operation
                and item.registration.primitive == request.primitive
                and item.pattern is not None
                and item.pattern.fullmatch(request.alas_resource) is not None
            ]
            if not matches:
                raise UnknownObservationError()
            if len(matches) != 1:
                raise AdapterContractError()
            selected = matches[0]
        if selected.registration.capability not in scope.allowed_capabilities:
            raise CapabilityClosureError()
        result = selected.handler(request)
        if not isinstance(result, ObserveResult) or result.request != request:
            raise AdapterContractError()
        return result
