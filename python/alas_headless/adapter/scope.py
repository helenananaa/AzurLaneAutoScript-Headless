"""Checked lifecycle stack for ALAS-owned semantic flow scopes."""

from __future__ import annotations

import re
from contextlib import contextmanager
from types import MappingProxyType
from typing import Iterator, Iterable, Mapping, Tuple

from .errors import FlowScopeError
from .ports import FlowScope, FlowScopeToken


_KIND_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class FlowScopeStack:
    """Own exact scope nesting for one semantic adapter session."""

    def __init__(
        self,
        session_id: str,
        *,
        allowed_parent_child_pairs: Iterable[Tuple[str, str]] = (),
    ) -> None:
        if not isinstance(session_id, str) or _KIND_PATTERN.fullmatch(session_id) is None:
            raise ValueError("session_id must be a canonical token")
        try:
            pairs = frozenset(allowed_parent_child_pairs)
        except TypeError as exc:
            raise ValueError("allowed parent/child pair is malformed") from exc
        for pair in pairs:
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or any(
                    not isinstance(kind, str) or _KIND_PATTERN.fullmatch(kind) is None
                    for kind in pair
                )
            ):
                raise ValueError("allowed parent/child pair is malformed")
        self._session_id = session_id
        self._allowed_pairs = pairs
        self._entries: list[tuple[FlowScope, FlowScopeToken]] = []
        self._issued_scope_ids: set[str] = set()
        self._next_ordinal = 0
        self._closed = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def depth(self) -> int:
        return len(self._entries)

    @property
    def active_scopes(self) -> tuple[FlowScope, ...]:
        return tuple(scope for scope, _ in self._entries)

    @property
    def active_tokens(self) -> tuple[FlowScopeToken, ...]:
        return tuple(token for _, token in self._entries)

    def open(self, scope: FlowScope) -> FlowScopeToken:
        if self._closed or not isinstance(scope, FlowScope):
            raise FlowScopeError()
        if scope.scope_id in self._issued_scope_ids:
            raise FlowScopeError()
        if not self._entries:
            if scope.parent_scope_id is not None:
                raise FlowScopeError()
        else:
            parent, _ = self._entries[-1]
            if scope.parent_scope_id != parent.scope_id:
                raise FlowScopeError()
            if (parent.kind, scope.kind) not in self._allowed_pairs:
                raise FlowScopeError()
        token = FlowScopeToken(
            session_id=self._session_id,
            scope_id=scope.scope_id,
            ordinal=self._next_ordinal,
        )
        self._next_ordinal += 1
        self._issued_scope_ids.add(scope.scope_id)
        self._entries.append((scope, token))
        return token

    def close(self, token: FlowScopeToken) -> FlowScope:
        if self._closed or not isinstance(token, FlowScopeToken) or not self._entries:
            raise FlowScopeError()
        if token.session_id != self._session_id:
            raise FlowScopeError()
        scope, expected = self._entries[-1]
        if token != expected:
            raise FlowScopeError()
        self._entries.pop()
        return scope

    @contextmanager
    def activate(self, scope: FlowScope) -> Iterator[FlowScopeToken]:
        token = self.open(scope)
        try:
            yield token
        finally:
            self.close(token)

    def trace_fields(self) -> Mapping[str, object]:
        active_scope = self._entries[-1][0] if self._entries else None
        return MappingProxyType(
            {
                "session_id": self._session_id,
                "depth": len(self._entries),
                "active_scope_id": (
                    active_scope.scope_id if active_scope is not None else ""
                ),
                "active_kind": active_scope.kind if active_scope is not None else "",
                "closed": self._closed,
            }
        )

    def shutdown(self) -> None:
        if self._closed or self._entries:
            raise FlowScopeError()
        self._closed = True
