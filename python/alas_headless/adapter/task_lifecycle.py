"""Task-local compatibility outcomes at the original ALAS run boundary."""

from contextlib import contextmanager
import traceback

from .errors import UnknownObservationError, UnsupportedPixelRead
from .semantic.contracts import (AlasSemanticActionDeferred, AlasSemanticUnmapped,
                                AlasSemanticDormFeedResultUnproven,
                                AlasSemanticCommissionStartUnproven,
                                AlasSemanticGuildDispatchUnproven)
from ..oracle.errors import (SemanticCommissionRowIncomplete, SemanticSnapshotStale, SemanticRaidUnavailable,
                             SemanticInputBlocked, SemanticTargetNotActionable,
                             SemanticNavigationPending,
                             SemanticGlobeSelectionMissed, SemanticGlobeDragPathUnavailable,
                             SemanticStrongholdEntryLocked, SemanticGuildFormationUnavailable)


class TaskCapabilityUnavailable(RuntimeError):
    """A typed port or exhausted action grant deferred only this task."""

    def __init__(self, task, cause):
        self.task = task
        self.cause = cause
        reason = ('semantic action deferred' if isinstance(cause, AlasSemanticActionDeferred)
                  else 'semantic navigation pending' if isinstance(cause, SemanticNavigationPending)
                  else 'semantic resource result unproven' if isinstance(cause, (AlasSemanticDormFeedResultUnproven, AlasSemanticGuildDispatchUnproven))
                  else 'semantic input deferred' if isinstance(cause, (SemanticInputBlocked, SemanticTargetNotActionable))
                  else 'semantic observation not ready' if isinstance(cause, (SemanticCommissionRowIncomplete, SemanticSnapshotStale))
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
    except SemanticSnapshotStale as exc:
        if exc.input_outcome_uncertain:
            outcome, failure = 'raised', exc
            raise
        # No frame or input is accepted from this stale read. Preserve the
        # refusal, release this task's borrowed state and let ALAS choose its
        # existing failure interval. Other tasks still prove fresh frames.
        outcome, failure = 'observation-not-ready', exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except AlasSemanticDormFeedResultUnproven as exc:
        if task.lower() != 'dorm':
            outcome, failure = 'raised', exc
            raise
        # This accepted batch stopped with a complete fresh owning panel; it
        # never permits another food input or reports success. Original ALAS
        # chooses the failure interval and next task. Uncertain dispatch or
        # invalid observation never produces this narrow result classification.
        outcome, failure = 'result-unproven', exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except AlasSemanticCommissionStartUnproven as exc:
        if task.lower() != 'commission':
            outcome, failure = 'raised', exc
            raise
        # Only the complete exact pending detail can produce this result.
        # Original ALAS owns the failure interval and the next task; no retry
        # of this accepted start or success proof is manufactured here.
        outcome, failure = 'result-unproven', exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except SemanticRaidUnavailable as exc:
        if task.lower() not in ('raid', 'raid_daily', 'raiddaily'):
            outcome, failure = 'raised', exc
            raise
        outcome, failure = 'capability-unavailable', exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except AlasSemanticGuildDispatchUnproven as exc:
        if task.lower() != 'guild':
            outcome, failure = 'raised', exc
            raise
        outcome, failure = 'result-unproven', exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except SemanticGuildFormationUnavailable as exc:
        if task.lower() != 'guild':
            outcome = 'raised'
            failure = exc
            raise
        outcome = 'capability-unavailable'
        failure = exc
        raise TaskCapabilityUnavailable(task, exc) from exc
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
    except SemanticNavigationPending as exc:
        # The navigation owner proves a fresh healthy source/destination before
        # raising this result. No task success or replay of its accepted input
        # is implied; ALAS keeps the configured failure interval and next task.
        outcome, failure = 'navigation-pending', exc
        raise TaskCapabilityUnavailable(task, exc) from exc
    except (SemanticInputBlocked, SemanticTargetNotActionable) as exc:
        # These classified refusals are raised before the requested input.
        # After the caller's native retries, ALAS' existing failure interval
        # owns re-entry. Other tasks still prove their own fresh inputs;
        # uncertain accepted results and identity errors retain their failure.
        outcome = 'input-unavailable'
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
        if isinstance(failure, SemanticSnapshotStale):
            session.last_task_error.update(
                age_ms=failure.age_ms,
                max_age_ms=failure.max_age_ms,
                input_outcome_uncertain=failure.input_outcome_uncertain,
                read_stack=[{'file': frame.filename, 'line': frame.lineno,
                             'function': frame.name}
                            for frame in traceback.extract_tb(failure.__traceback__)],
            )
        if isinstance(failure, (SemanticInputBlocked, SemanticTargetNotActionable)):
            session.last_task_error.update(semantic_id=failure.semantic_id,
                                           generation=failure.generation)
            if isinstance(failure, SemanticInputBlocked):
                session.last_task_error['blockers'] = list(failure.blockers)
        if (isinstance(failure, SemanticNavigationPending)
                and isinstance(failure.receipt, dict)):
            # Preserve the already collected source/destination/gesture facts;
            # later diagnostic reads cannot reconstruct a missed input frame.
            session.last_task_error.update(semantic_id=failure.semantic_id,
                generation=failure.generation, navigation_receipt=dict(failure.receipt))
        if session.trace is not None:
            session.trace.emit("semantic.task.end", fields=session.last_task_outcome)
