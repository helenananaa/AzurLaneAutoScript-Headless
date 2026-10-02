"""Task-local compatibility outcomes at the original ALAS run boundary."""

from contextlib import contextmanager

from .errors import UnknownObservationError, UnsupportedPixelRead
from .semantic.contracts import AlasSemanticActionDeferred, AlasSemanticUnmapped
from ..oracle.errors import (SemanticCommissionRowIncomplete,
                             SemanticGlobeSelectionMissed, SemanticGlobeDragPathUnavailable,
                             SemanticStrongholdEntryLocked)


class TaskCapabilityUnavailable(RuntimeError):
    """A typed port or exhausted action grant deferred only this task."""

    def __init__(self, task, cause):
        self.task = task
        self.cause = cause
        reason = ('semantic action deferred' if isinstance(cause, AlasSemanticActionDeferred)
                  else 'semantic observation not ready' if isinstance(cause, SemanticCommissionRowIncomplete)
                  else 'game prerequisite pending' if isinstance(cause, SemanticStrongholdEntryLocked)
                  else 'semantic capability unavailable')
        super().__init__(f"{reason} for {task}: {cause}")


@contextmanager
def semantic_task_scope(session, task):
    """Clean borrowed task state; ALAS still schedules, retries and recovers."""
    if session is None:
        yield
        return
    outcome = "returned"
    failure = None
    try:
        yield
    except SemanticCommissionRowIncomplete as exc:
        # The complete row read remains closed. Original ALAS applies its
        # configured failure interval while unrelated tasks keep running.
        if task.lower() != 'commission':
            outcome = 'raised'
            failure = exc
            raise
        outcome = 'observation-not-ready'
        failure = exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except SemanticStrongholdEntryLocked as exc:
        # The exact native lock was observed before entrance. Keep this game
        # prerequisite local; ALAS applies its existing failure interval.
        outcome = 'prerequisite-pending'
        failure = exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except AlasSemanticActionDeferred as exc:
        outcome = "action-deferred"
        failure = exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except (AlasSemanticUnmapped, UnknownObservationError, UnsupportedPixelRead,
            SemanticGlobeSelectionMissed, SemanticGlobeDragPathUnavailable) as exc:
        # A globe miss reaches this boundary only after ALAS' own bounded
        # focus retries. Each miss already proves fresh complete unselected
        # state; keep its port failure local to the task's failure interval.
        # Exhausted globe drag sampling likewise proves no candidate input
        # was dispatched. Defer that task without stopping unrelated tasks.
        outcome = "capability-unavailable"
        failure = exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except BaseException as exc:
        outcome = "raised"
        failure = exc
        raise
    finally:
        session.discard_task_state()
        session.last_task_outcome = {"task": task, "outcome": outcome}
        session.last_task_error = (
            None if failure is None else
            {"type": type(failure).__name__, "message": str(failure)}
        )
        if session.trace is not None:
            session.trace.emit("semantic.task.end", fields=session.last_task_outcome)
