"""Fail-closed contract for ALAS error-recovery enablement."""

from __future__ import annotations

from .semantic_oracle import SemanticGateClosed


def validate_alas_handle_error_config(value: object) -> bool:
    """Admit only a real boolean before restart or withdrawal decisions."""

    if type(value) is not bool:
        raise SemanticGateClosed("Error.HandleError must be a boolean")
    return value
