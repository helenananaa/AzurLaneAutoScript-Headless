"""Errors for the typed ALAS boundary."""

from __future__ import annotations




class SemanticOracleError(RuntimeError):
    """Base error for semantic observation and action failures."""


class SemanticGateClosed(SemanticOracleError):
    """The requested action was refused because a safety gate is not proven."""


class SemanticTargetMissing(SemanticGateClosed):
    """A mapped semantic target is not present in the current valid snapshot."""


class SemanticTargetNotActionable(SemanticGateClosed):
    """The target failed admission before any input was dispatched."""

    def __init__(self, semantic_id: str, generation: int):
        super().__init__('semantic target is not actionable')
        self.semantic_id = semantic_id
        self.generation = generation


class SemanticViewportReanchorRequired(SemanticGateClosed):
    """No input was sent: ALAS must refresh its View and recompute the gesture."""


class SemanticGlobeDragPathUnavailable(SemanticGateClosed):
    """No input was sent: valid native proofs rejected every ALAS drag candidate."""


class SemanticGlobeSelectionMissed(SemanticGateClosed):
    """One selection input was sent; fresh complete globe frames prove no pin."""


class SemanticStrongholdEntryLocked(SemanticGateClosed):
    """No entrance input: the game reports neighbouring zones uncleared."""

    def __init__(self, zone_id):
        self.zone_id = zone_id
        super().__init__(
            f'Operation Siren stronghold zone {zone_id} is locked; '
            'stronghold requires neighbouring zones to be suppressed'
        )


class SemanticCommissionRowIncomplete(SemanticGateClosed):
    """No row input: a coherent commission row still lacks its type Image."""

    def __init__(self, path: str, generation: int):
        self.path = path
        self.generation = generation
        super().__init__(f'commission row type Image is not ready: {path}')


class ObserverTransportError(SemanticOracleError):
    """The local observer transport failed or returned malformed data."""


class ObserverResponseTimeout(ObserverTransportError):
    """A connected observer did not finish its response within the read bound."""
