"""Task-local compatibility outcomes at the original ALAS run boundary."""

from contextlib import contextmanager

from .errors import UnknownObservationError, UnsupportedPixelRead
from .semantic.contracts import AlasSemanticUnmapped


class TaskCapabilityUnavailable(RuntimeError):
    """An unsupported typed port deferred this task, without completing it."""

    def __init__(self, task, cause):
        self.task = task
        self.cause = cause
        super().__init__(f"semantic capability unavailable for {task}: {cause}")


@contextmanager
def semantic_task_scope(session, task):
    """Clean borrowed task state; ALAS still schedules, retries and recovers."""
    if session is None:
        yield
        return
    outcome = "returned"
    try:
        yield
    except (AlasSemanticUnmapped, UnknownObservationError, UnsupportedPixelRead) as exc:
        outcome = "capability-unavailable"
        raise TaskCapabilityUnavailable(task, exc) from exc
    except BaseException:
        outcome = "raised"
        raise
    finally:
        session.discard_task_state()
        session.last_task_outcome = {"task": task, "outcome": outcome}
        if session.trace is not None:
            session.trace.emit("semantic.task.end", fields=session.last_task_outcome)
