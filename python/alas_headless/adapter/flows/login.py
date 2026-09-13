"""Read-only login observations admitted to the contextual registry."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping

from ...semantic_oracle import SemanticGateClosed
from ..errors import UnknownObservationError
from ..ports import ObserveRequest, ObserveResult, SemanticFrameIdentity
from ..registry import ObservationRegistry


LOGIN_CHECK_CAPABILITY = "login.observe-entry"
LOGIN_ENTRY_SEMANTIC_ID = "login/enter"
LOGIN_INITIAL_TRANSITION_SECONDS = 20.0
LOGIN_ACTION_TRANSITION_SECONDS = 60.0
LOGIN_STALE_GRACE_SECONDS = 5.0

LOGIN_OBSERVATION_TARGETS: Mapping[str, str] = MappingProxyType(
    {
        "MAIN_GOTO_CAMPAIGN_WHITE": "main/battle",
        "MAIN_GOTO_FLEET": "main/formation",
        "LOGIN_CHECK": LOGIN_ENTRY_SEMANTIC_ID,
        "LOGIN_ANNOUNCE": "overlay/bulletin/close",
        "LOGIN_ANNOUNCE_2": "overlay/bulletin/close",
        "LOGIN_GAME_UPDATE": "login/update/download",
        "POPUP_CANCEL": "overlay/network-reconnect/cancel",
        "POPUP_CONFIRM_WHITE": "overlay/login-data-expired/confirm",
    }
)

LOGIN_ACTION_TARGETS: Mapping[str, str] = MappingProxyType(
    {
        "LOGIN_CHECK": LOGIN_ENTRY_SEMANTIC_ID,
        "LOGIN_ANNOUNCE": "overlay/bulletin/close",
        "LOGIN_ANNOUNCE_2": "overlay/bulletin/close",
        "LOGIN_GAME_UPDATE": "login/update/download",
        "POPUP_CANCEL": "overlay/network-reconnect/cancel",
        "POPUP_CONFIRM_WHITE": "overlay/login-data-expired/confirm",
    }
)

LOGIN_RECORDED_TRANSITION_TARGETS = frozenset(
    {
        LOGIN_ENTRY_SEMANTIC_ID,
        "overlay/bulletin/close",
        "reward/award-info/close",
        "reward/award-info1/close",
        "overlay/login-data-expired/confirm",
        "login/update/download",
    }
)

LOGIN_KNOWN_FALLBACK_TARGETS = (
    "overlay/bulletin/close",
    "overlay/network-reconnect/confirm",
    "overlay/login-data-expired/confirm",
)

LOGIN_POPUP_CONFIRM_TARGETS = (
    "overlay/login-data-expired/confirm",
    "overlay/network-reconnect/confirm",
)

LOGIN_TRANSIENT_MESSAGES = frozenset(
    {
        "observer snapshot is stale",
        "observer endpoints are not generation-coherent",
        "Msgbox snapshots are not coherent",
    }
)

LOGIN_UNSUPPORTED_PRESENCE_RESOURCES = frozenset(
    {
        "ANDROID_NO_RESPOND",
        "AVATAR_EXPIRED",
        "BACK_ARROW",
        "EVENT_LIST_CHECK",
        "LOGIN_RETURN_INFO",
        "LOGIN_RETURN_SIGN",
        "MAINTENANCE_ANNOUNCE",
        "BATTLE_PASS_NEW_SEASON",
        "BATTLE_PASS_NOTICE",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_SHIP",
        "META_CHECK",
        "MONTHLY_PASS_NOTICE",
        "PLAYER_CHECK",
        "SHIPYARD_CHECK",
        "GET_MISSION",
        "POPUP_SINGLE_WHITE",
    }
)


@dataclass(frozen=True)
class LoginFlowSnapshot:
    active: bool
    passive_transition_until: float
    entry_receipt: Any | None
    action_budget: None = None


@dataclass(frozen=True)
class LoginActionIntent:
    """Resolved compatibility target; this is not an authorized action lease."""

    alas_resource: str
    semantic_id: str


@dataclass
class _LoginContext:
    passive_transition_until: float
    entry_receipt: Any | None = None


class LoginFlow:
    """Staged login-flow implementation used as the C02 parity candidate."""

    def __init__(
        self,
        package_gate: Callable[[], None],
        *,
        observation_oracle: Callable[[], Any],
        monotonic: Callable[[], float] = time.monotonic,
        entry_observer: Callable[[], bool] | None = None,
    ) -> None:
        if package_gate is None or not callable(package_gate):
            raise ValueError("login flow requires a package identity gate")
        if not callable(monotonic):
            raise ValueError("login flow requires a monotonic clock")
        if not callable(observation_oracle):
            raise ValueError("login flow requires an explicit frame observer")
        self._observation_oracle = observation_oracle
        self._package_gate = package_gate
        self._monotonic = monotonic
        self._entry_observer = (
            entry_observer
            if entry_observer is not None
            else lambda: self._reader().enabled(LOGIN_ENTRY_SEMANTIC_ID)
        )
        if not callable(self._entry_observer):
            raise ValueError("login entry observer must be callable")
        self._context: _LoginContext | None = None
        self._last_action_intent: LoginActionIntent | None = None

    @property
    def active(self) -> bool:
        return self._context is not None

    @property
    def last_action_intent(self) -> LoginActionIntent | None:
        return self._last_action_intent

    def snapshot(self) -> LoginFlowSnapshot:
        context = self._context
        if context is None:
            return LoginFlowSnapshot(False, 0.0, None)
        return LoginFlowSnapshot(
            True,
            context.passive_transition_until,
            context.entry_receipt,
        )

    def begin(self, *, conflicting_flow_active: bool) -> None:
        self._package_gate()
        if self._context is not None or conflicting_flow_active:
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._context = _LoginContext(
            passive_transition_until=(
                self._monotonic() + LOGIN_INITIAL_TRANSITION_SECONDS
            )
        )
        self._last_action_intent = None

    def end(self) -> None:
        self._context = None
        self._last_action_intent = None

    def extend_passive_transition(self, seconds: float) -> None:
        """Extend only an active owned login transition after a cold restart."""

        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise TypeError("login transition extension must be numeric")
        if not 0 < float(seconds) <= 120.0:
            raise ValueError("login transition extension must be within (0, 120]")
        context = self._context
        if context is None:
            raise SemanticGateClosed("login flow is not active")
        context.passive_transition_until = max(
            context.passive_transition_until,
            self._monotonic() + float(seconds),
        )

    @contextmanager
    def activate(self, *, conflicting_flow_active: bool) -> Iterator[None]:
        self.begin(conflicting_flow_active=conflicting_flow_active)
        try:
            yield
        finally:
            self.end()

    def popup_target(self) -> str | None:
        reader = self._reader()
        targets = tuple(
            semantic_id
            for semantic_id in LOGIN_POPUP_CONFIRM_TARGETS
            if reader.enabled(semantic_id)
        )
        if len(targets) > 1:
            raise SemanticGateClosed("login popup target is ambiguous")
        return targets[0] if targets else None

    @staticmethod
    def normalize_resource(resource: str) -> str:
        if resource == "POPUP_CONFIRM_LOGIN":
            return "POPUP_CONFIRM"
        if resource == "POPUP_CONFIRM_WHITE_LOGIN":
            return "POPUP_CONFIRM_WHITE"
        return resource

    def known_surface_exists(self) -> bool:
        reader = self._reader()
        try:
            reader.campaign_is_in_map()
        except SemanticGateClosed:
            return any(
                reader.enabled(target)
                for target in LOGIN_KNOWN_FALLBACK_TARGETS
            )
        return True

    def allows_passive_probe(self) -> bool:
        context = self._context
        return bool(
            context is not None
            and (
                self._monotonic() <= context.passive_transition_until
                or self.known_surface_exists()
            )
        )

    def observe(self, resource: str) -> bool:
        resource = self.normalize_resource(resource)
        context = self._context
        if context is not None and resource == "POPUP_CONFIRM":
            return self.popup_target() is not None
        if (
            context is not None
            and resource == "LOGIN_CHECK"
            and context.entry_receipt is not None
            and self._monotonic() <= context.passive_transition_until
        ):
            return False
        target = LOGIN_OBSERVATION_TARGETS.get(resource)
        if target is None:
            raise UnknownObservationError()
        self._package_gate()
        if resource in ("MAIN_GOTO_CAMPAIGN_WHITE", "MAIN_GOTO_FLEET"):
            # Main-page skins do not guarantee that either legacy navigation
            # button is currently enabled. The exact root identity is the
            # stable login-completion contract for both ALAS aliases.
            reader = self._reader()
            return (reader.main_page_visible()
                    and not reader.enabled("overlay/bulletin/close"))
        if resource == "LOGIN_CHECK":
            return self._entry_observer()
        return self._reader().enabled(target)

    def observe_unknown(self) -> bool:
        self._package_gate()
        context = self._context
        if context is None:
            raise UnknownObservationError()
        if self._monotonic() <= context.passive_transition_until:
            return False
        if self.known_surface_exists():
            return False
        raise UnknownObservationError()

    def observe_unsupported_presence(self, resource: str) -> bool:
        """Bound an explicitly non-semantic login presence probe to absence.

        Legacy login code probes a handful of screenshot assets which have no
        Unity semantic equivalent, including Android-system UI.  The adapter
        must retain package identity enforcement but cannot prove the asset or
        safely dismiss it, so the only safe result is an inactive match.
        """
        if resource not in LOGIN_UNSUPPORTED_PRESENCE_RESOURCES:
            raise UnknownObservationError()
        self._package_gate()
        if self._context is None:
            raise UnknownObservationError()
        return False

    def goto_main_target(self) -> str | None:
        reader = self._reader()
        targets = []
        if reader.campaign_menu_is_entry() and reader.enabled(
            "campaign-menu/page/back"
        ):
            targets.append("campaign-menu/page/back")
        try:
            reader.build_queue_timers()
        except SemanticGateClosed:
            pass
        else:
            if reader.enabled("build/page/back"):
                targets.append("build/page/back")
        for identity, target in (
            ("event-list/page/back", "event-list/page/back"),
            ("task/page/back", "task/page/back"),
            ("build/page/start", "build/page/back"),
            ("research-menu/page/back", "research-menu/page/back"),
            ("research/page/back", "research/page/back"),
            ("shipyard/page/root", "shipyard/page/back"),
        ):
            if reader.exists(identity) and reader.enabled(target):
                targets.append(target)
        unique = tuple(dict.fromkeys(targets))
        if len(unique) > 1:
            raise SemanticGateClosed("GOTO_MAIN target is ambiguous")
        return unique[0] if unique else None

    def observe_goto_main(self) -> bool:
        self._package_gate()
        return self.goto_main_target() is not None

    def click(self, resource: str) -> Any:
        self._last_action_intent = None
        resource = self.normalize_resource(resource)
        context = self._context
        if context is not None and resource == "POPUP_CONFIRM":
            semantic_id = self.popup_target()
            if semantic_id is None:
                raise SemanticGateClosed("login popup identity is not proven")
            self._package_gate()
        elif resource == "GOTO_MAIN":
            self._package_gate()
            semantic_id = self.goto_main_target()
            if semantic_id is None:
                raise SemanticGateClosed("GOTO_MAIN has no reviewed page target")
        else:
            semantic_id = LOGIN_ACTION_TARGETS.get(resource)
            if semantic_id is None:
                raise UnknownObservationError()
            self._package_gate()
        self._last_action_intent = LoginActionIntent(resource, semantic_id)
        receipt = self._reader().click(semantic_id)
        if context is not None and semantic_id in LOGIN_RECORDED_TRANSITION_TARGETS:
            if semantic_id == LOGIN_ENTRY_SEMANTIC_ID:
                context.entry_receipt = receipt
            context.passive_transition_until = (
                self._monotonic() + LOGIN_ACTION_TRANSITION_SECONDS
            )
        return receipt

    def _reader(self) -> Any:
        reader = self._observation_oracle()
        if reader is None:
            raise SemanticGateClosed("login frame observer is unavailable")
        return reader

    def handle_presence_failure(
        self,
        error: SemanticGateClosed,
        stale_since: float | None,
    ) -> tuple[bool, float]:
        message = str(error)
        transient = message in LOGIN_TRANSIENT_MESSAGES
        if message == "game activity is not top-resumed" and self.active:
            transient = True
        if not transient:
            raise error
        now = self._monotonic()
        first_stale = now if stale_since is None else stale_since
        context = self._context
        if context is not None and now <= context.passive_transition_until:
            return False, first_stale
        if now - first_stale <= LOGIN_STALE_GRACE_SECONDS:
            return False, first_stale
        raise error


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
