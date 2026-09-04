"""Errors for the typed ALAS boundary."""

from __future__ import annotations




class SemanticOracleError(RuntimeError):
    """Base error for semantic observation and action failures."""


class SemanticGateClosed(SemanticOracleError):
    """The requested action was refused because a safety gate is not proven."""


class SemanticTargetMissing(SemanticGateClosed):
    """A mapped semantic target is not present in the current valid snapshot."""


class ObserverTransportError(SemanticOracleError):
    """The local observer transport failed or returned malformed data."""


class ObserverResponseTimeout(ObserverTransportError):
    """A connected observer did not finish its response within the read bound."""
