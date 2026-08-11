"""Read-only login observations admitted to the contextual registry."""

from __future__ import annotations

from typing import Callable

from ..ports import ObserveRequest, ObserveResult, SemanticFrameIdentity
from ..registry import ObservationRegistry


LOGIN_CHECK_CAPABILITY = "login.observe-entry"
LOGIN_ENTRY_SEMANTIC_ID = "login/enter"


def register_login_observations(
    registry: ObservationRegistry,
    *,
    enabled: Callable[[str], bool],
    frame_identity: Callable[[ObserveRequest], SemanticFrameIdentity],
) -> None:
    """Register the first compatibility-facade read without adding authority."""

    def login_check(request: ObserveRequest) -> ObserveResult:
        value = enabled(LOGIN_ENTRY_SEMANTIC_ID)
        return ObserveResult(request, frame_identity(request), value)

    registry.register_exact(
        flow_kind="login",
        operation="startup",
        primitive="appear",
        resource="LOGIN_CHECK",
        capability=LOGIN_CHECK_CAPABILITY,
        handler=login_check,
    )
