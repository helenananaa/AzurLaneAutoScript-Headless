"""Login for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...adapter import FlowScope, ObserveRequest, UnknownObservationError
from ...adapter.flows import (
    LOGIN_ACTION_TARGETS,
    LOGIN_CHECK_CAPABILITY,
    LOGIN_OBSERVATION_TARGETS,
    LOGIN_UNSUPPORTED_PRESENCE_RESOURCES,
)
from ...semantic_oracle import ActionReceipt
from .contracts import AlasSemanticUnmapped
from .dispatch_result import UNHANDLED
from .resources import _LEGACY_TASK_CONFIG_SHA256


class LoginAdapterPorts:
    """Login ports on the shared adapter context."""

    def _dispatch_login_check_registry(self) -> bool:
        self._compat_observation_ordinal += 1
        ordinal = self._compat_observation_ordinal
        scope_id = "login-startup-{0}".format(ordinal)
        frame_id = self._current_frame_identity().frame_id
        scope = FlowScope(
            scope_id=scope_id,
            kind="login",
            operation="startup",
            parent_scope_id=None,
            task_config_sha256=_LEGACY_TASK_CONFIG_SHA256,
            allowed_capabilities=frozenset((LOGIN_CHECK_CAPABILITY,)),
            deadline_monotonic_ns=time.monotonic_ns() + 1_000_000_000,
        )
        request = ObserveRequest(
            scope_id=scope_id,
            primitive="appear",
            alas_resource="LOGIN_CHECK",
            parameters={},
            frame_id=frame_id,
        )
        return self._observation_registry.dispatch(scope, request).value

    def begin_login(self) -> None:
        """Open one original ALAS LoginHandler invocation."""

        conflicting_flow_active = any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._supply_pack_context,
                self._minigame_context,
                self._build_context,
                self._campaign_context,
            )
        )
        self._login_flow.begin(conflicting_flow_active=conflicting_flow_active)

    def end_login(self) -> None:
        self._login_flow.end()

    def server_maintenance_visible(self) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().server_maintenance_visible()

    def login_update_in_progress(self) -> bool:
        self._package_gate()
        reader = self._frame_or_live_observation_oracle()
        reader._login_update_seen = self.oracle._login_update_seen
        visible = reader.login_update_in_progress()
        # ALAS' screenshot supplies a coherent immutable view. Keep the
        # observed-update latch on the process oracle for the later native
        # completion/restart probe; no input is admitted by this observation.
        self.oracle._login_update_seen = reader._login_update_seen
        if visible and self._login_flow.active:
            # Updating and entering the client are native login transitions
            # too. Reuse the existing passive grace after a fresh typed
            # updater observation, so brief SDK foreground/state turnover
            # cannot terminate the handler. Input still requires a fresh frame.
            self._login_flow.extend_passive_transition(60.0)
        return visible

    def login_update_restart_required(self) -> bool:
        self._package_gate()
        return self.oracle.login_update_restart_required()

    def login_update_restart_prompt_available(self) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().login_update_restart_prompt_available()

    def click_login_update_restart_prompt(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_login_update_restart_prompt()

    def _appear_login(self, name):
        if self._login_flow.active and name == 'GET_SHIP':
            return self.oracle.new_ship_reward_visible()
        if name == "LOGIN_CHECK" or (
            self._login_flow.active and name in LOGIN_OBSERVATION_TARGETS
        ):
            return self._login_flow.observe(name)
        if (
            self._login_flow.active
            and name in ("GET_ITEMS_1", "GET_ITEMS_2")
        ):
            # Monthly sign-in and other post-login rewards use the same exact
            # AwardInfo close controls as task rewards. Expose one canonical
            # ALAS alias so the legacy popup loop cannot submit it twice.
            return name == "GET_ITEMS_1" and self._award_close_target() is not None
        if self._login_flow.active and name == "POPUP_CONFIRM":
            return self._login_flow.observe(name)
        if self._login_flow.active and name == "GOTO_MAIN":
            return self._login_flow.observe_goto_main()
        if (
            self._login_flow.active
            and name in LOGIN_UNSUPPORTED_PRESENCE_RESOURCES
        ):
            # These legacy image assets are only presence probes in the login
            # handler.  They include Android-system UI such as
            # ``ANDROID_NO_RESPOND``, which Unity's observer cannot prove.  A
            # semantic adapter must neither infer their presence nor send an
            # input to dismiss them.  Keep the answer bounded to absence while
            # the explicit login context is active, including the narrow
            # startup-update transition before a known Unity surface exists.
            return self._login_flow.observe_unsupported_presence(name)
        return UNHANDLED

    def _click_login(self, name):
        if name == 'POPUP_CANCEL' and not self._login_flow.active:
            # This shared control also cancels reviewed task prompts. The
            # global NetworkDown owner is handled before this dispatcher;
            # an inactive login flow must not steal another task's choice.
            return UNHANDLED
        if name in LOGIN_ACTION_TARGETS or (
            self._login_flow.active and name in ("POPUP_CONFIRM", "GOTO_MAIN")
        ):
            try:
                return self._login_flow.click(name)
            except UnknownObservationError as exc:
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped for input: {0}".format(
                        name
                    )
                ) from exc
        return UNHANDLED
