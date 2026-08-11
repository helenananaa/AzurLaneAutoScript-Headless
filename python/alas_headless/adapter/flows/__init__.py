"""Flow-specific registrations for the semantic adapter kernel."""

from .login import LOGIN_CHECK_CAPABILITY, register_login_observations


__all__ = (
    "LOGIN_CHECK_CAPABILITY",
    "register_login_observations",
)
