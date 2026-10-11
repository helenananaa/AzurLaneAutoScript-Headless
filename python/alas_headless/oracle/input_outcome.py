"""Preserve uncertainty while observing the result of an accepted input."""

from contextlib import contextmanager

from .errors import SemanticSnapshotStale


@contextmanager
def input_result_scope(*, dispatched=True):
    """Use only for a pending action's result, never for later unrelated reads."""
    try:
        yield
    except SemanticSnapshotStale as exc:
        if dispatched:
            exc.input_outcome_uncertain = True
        raise
