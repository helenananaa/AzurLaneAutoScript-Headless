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
from .combat import (
    CombatFlow,
    CombatFlowState,
    G36_NORMAL_APPEAR_RESOURCES,
    G36_NORMAL_COLOR_COUNT_RESOURCES,
    G36_NORMAL_COMBAT_PHASES,
)


__all__ = (
    "CombatFlow",
    "CombatFlowState",
    "G36_NORMAL_APPEAR_RESOURCES",
    "G36_NORMAL_COLOR_COUNT_RESOURCES",
    "G36_NORMAL_COMBAT_PHASES",
    "LOGIN_ACTION_TARGETS",
    "LOGIN_CHECK_CAPABILITY",
    "LOGIN_OBSERVATION_TARGETS",
    "LOGIN_UNSUPPORTED_PRESENCE_RESOURCES",
    "LoginActionIntent",
    "LoginFlow",
    "LoginFlowSnapshot",
    "register_login_observations",
)
