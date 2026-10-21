"""Task-local bounded trace with a small reserve for late failures."""
import threading

from alas_headless.runtime_trace import RuntimeTraceRecorder


class BoundedTrace(RuntimeTraceRecorder):
    def __init__(self, path):
        self._budget_lock = threading.Lock()
        self._offered = 0
        self._failure_offered = 0
        self._budget_dropped = 0
        super().__init__(path, enabled=True, maximum_queue_size=1024)

    def emit(self, event, outcome='ok', duration_ns=None, fields=None):
        failed = (outcome in ('error', 'timeout', 'refused')
                  or (event == 'semantic.task.end' and isinstance(fields, dict)
                      and fields.get('outcome') == 'raised'))
        with self._budget_lock:
            if self._offered < 5000:
                self._offered += 1
            elif failed and self._failure_offered < 64:
                self._failure_offered += 1
            else:
                self._budget_dropped += 1
                return False
        return super().emit(event, outcome=outcome, duration_ns=duration_ns, fields=fields)

    def summary(self):
        value = dict(super().summary())
        with self._budget_lock:
            value.update(event_limit=5000, offered=self._offered,
                failure_reserve_limit=64, failure_reserve_offered=self._failure_offered,
                budget_dropped=self._budget_dropped)
        return value
