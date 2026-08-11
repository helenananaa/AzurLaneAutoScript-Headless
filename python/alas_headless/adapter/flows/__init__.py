"""Flow-specific registrations for the semantic adapter kernel."""

from .login import (
    LOGIN_ACTION_TARGETS,
    LOGIN_CHECK_CAPABILITY,
    LOGIN_OBSERVATION_TARGETS,
    LOGIN_UNSUPPORTED_PRESENCE_RESOURCES,
    LoginActionIntent,
    LoginFlow,
    LoginFlowSnapshot,
    register_login_observations,
)


__all__ = (
    "LOGIN_ACTION_TARGETS",
    "LOGIN_CHECK_CAPABILITY",
    "LOGIN_OBSERVATION_TARGETS",
    "LOGIN_UNSUPPORTED_PRESENCE_RESOURCES",
    "LoginActionIntent",
    "LoginFlow",
    "LoginFlowSnapshot",
    "register_login_observations",
)
