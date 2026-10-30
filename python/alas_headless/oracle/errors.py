"""Errors for the typed ALAS boundary."""

from __future__ import annotations




class SemanticOracleError(RuntimeError):
    """Base error for semantic observation and action failures."""


class SemanticGateClosed(SemanticOracleError):
    """The requested action was refused because a safety gate is not proven."""


class SemanticTargetMissing(SemanticGateClosed):
    """A mapped semantic target is not present in the current valid snapshot."""


class SemanticResearchStatusUnavailable(SemanticGateClosed):
    """A card status is unknown; no resource input has been submitted."""

    def __init__(self, status: str):
        self.status = status
        super().__init__('research status is not reviewed: ' + status)


class SemanticSnapshotStale(SemanticGateClosed):
    """A snapshot failed freshness; pending input results retain uncertainty."""

    def __init__(self, age_ms: int, max_age_ms=None):
        self.age_ms = age_ms
        self.max_age_ms = max_age_ms
        self.input_outcome_uncertain = False
        super().__init__("observer snapshot is stale")


class SemanticRaidUnavailable(SemanticGateClosed):
    """A Raid event is absent or its typed layout is not supported."""


class SemanticExerciseHpNotReady(SemanticGateClosed):
    """No HP decision or input: a complete duel frame still lacks a bar."""


class SemanticGuildFormationUnavailable(SemanticTargetMissing):
    """No input: the current Guild formation has no reviewed dispatch control."""

    def __init__(self, generation: int, detail: str = 'dispatch control is unavailable'):
        self.generation = generation
        super().__init__('Guild formation ' + detail + '; no input submitted')


class SemanticInputBlocked(SemanticGateClosed):
    """No input was sent: typed blockers cover an otherwise reviewed target."""

    def __init__(self, semantic_id: str, generation: int, blockers, *, observed_state=None):
        self.semantic_id = semantic_id
        self.generation = generation
        self.blockers = tuple(blockers)
        # Retain an already-read immutable state only; no query or action.
        # Terminal task diagnostics encode it after cleanup. Native waits can
        # discard the exception without copying a large frame on every poll.
        self.observed_state = observed_state
        super().__init__('semantic input is blocked by: ' + ', '.join(self.blockers))


class SemanticTargetNotActionable(SemanticGateClosed):
    """The target failed admission before any input was dispatched."""

    def __init__(self, semantic_id: str, generation: int):
        super().__init__('semantic target is not actionable')
        self.semantic_id = semantic_id
        self.generation = generation


class SemanticInputTargetMissing(SemanticTargetMissing, SemanticTargetNotActionable):
    """A valid input-admission snapshot has no target; nothing was dispatched."""

    def __init__(self, semantic_id: str, generation: int):
        SemanticGateClosed.__init__(self, 'semantic target is absent: ' + semantic_id)
        self.semantic_id = semantic_id
        self.generation = generation


class SemanticNavigationPending(SemanticGateClosed):
    """Accepted navigation did not settle; its healthy owning page is proven."""

    def __init__(self, semantic_id, receipt, generation, message):
        super().__init__(message)
        self.semantic_id = semantic_id
        self.receipt = receipt
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


class SemanticCampaignFleetIncomplete(SemanticGateClosed):
    """No fleet input: valid levels precede asynchronously mounted portraits."""

    def __init__(self, row_key: str, generation: int):
        self.row_key = row_key
        self.generation = generation
        super().__init__('campaign fleet row portraits are not ready: ' + row_key)


class ObserverTransportError(SemanticOracleError):
    """The local observer transport failed or returned malformed data."""


class ObserverConnectionInterrupted(ObserverTransportError):
    """An established observer stream was aborted, reset, or broken."""


class ObserverResponseTimeout(ObserverTransportError):
    """A connected observer did not finish its response within the read bound."""
