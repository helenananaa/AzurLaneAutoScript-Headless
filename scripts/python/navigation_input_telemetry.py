"""Bounded diagnostic capture of existing reads inside selected navigation clicks."""
import datetime
import functools
import json
import time

from run_alas_configured_task_live import encode_receipt_value


def install(oracle_class, path, limit=128,
            semantic_ids=('main/live', 'dorm-menu/academy')):
    semantic_ids = frozenset(semantic_ids)
    stats = dict(installed=False, offered=0, written=0, dropped=0,
                 capture_errors=0, write_errors=0, limit=limit)
    try:
        with path.open('x', encoding='utf-8'):
            pass
    except OSError as exc:
        stats['disabled_error'] = str(exc)
        return stats
    original = oracle_class.click

    @functools.wraps(original)
    def click(self, semantic_id):
        if semantic_id not in semantic_ids:
            return original(self, semantic_id)
        if stats['offered'] >= limit:
            stats['dropped'] += 1
            return original(self, semantic_id)
        stats['offered'] += 1
        row = dict(at=datetime.datetime.now().astimezone().isoformat(),
                   semantic_id=semantic_id, state_reads=0,
                   scope='Existing reads inside click; last admitted source, not a new observation or input permission')
        previous = self.__dict__.get('read_state')
        had_override = 'read_state' in self.__dict__
        read = self.read_state
        began = time.monotonic()

        def capture(*args, **kwargs):
            state = read(*args, **kwargs)
            row['state_reads'] += 1
            try:
                # Freeze before input can mutate a producer's reused buffers.
                # No extra endpoint, foreground query or action is performed.
                row['source'] = encode_receipt_value(dict(
                    generation=state.generation, scene_handle=state.scene_handle,
                    snapshot=state.snapshot, buttons=state.buttons_snapshot))
            except Exception as exc:
                stats['capture_errors'] += 1
                row['capture_error'] = str(exc)
            return state

        self.read_state = capture
        try:
            receipt = original(self, semantic_id)
            row['outcome'] = 'returned'
            try:
                row['receipt_generation'] = getattr(receipt, 'generation', None)
            except Exception as exc:
                stats['capture_errors'] += 1
                row['capture_error'] = str(exc)
            return receipt
        except BaseException as exc:
            row.update(outcome='raised', error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            if had_override:
                self.read_state = previous
            else:
                self.__dict__.pop('read_state', None)
            row['duration_seconds'] = round(time.monotonic() - began, 6)
            try:
                with path.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + '\n')
                stats['written'] += 1
            except Exception:
                stats['write_errors'] += 1

    oracle_class.click = click
    stats['installed'] = True
    return stats
