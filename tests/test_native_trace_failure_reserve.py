"""Late transport failures remain observable after ordinary trace exhaustion."""
import importlib.util
import json
from pathlib import Path

def trace_type():
    path = Path(__file__).resolve().parents[1] / 'scripts/python/bounded_native_trace.py'
    spec = importlib.util.spec_from_file_location('task_bounded_native_trace', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BoundedTrace


def test_final_reserved_failure_is_written_after_regular_budget_then_bounded(tmp_path):
    trace = trace_type()(tmp_path / 'trace.jsonl')
    trace._offered = 4999
    trace._failure_offered = 63
    assert trace.emit('ordinary')
    assert not trace.emit('ordinary-after-limit')
    assert trace.emit('adb.command', outcome='error', fields={'stderr_tail': 'device offline'})
    assert not trace.emit('another-error', outcome='error')
    summary = trace.close()
    rows = [json.loads(line) for line in (tmp_path / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [r['event'] for r in rows] == ['ordinary', 'adb.command']
    assert summary['failure_reserve_offered'] == 64
    assert summary['budget_dropped'] == 2 and summary['recorded'] == 2


def test_early_failure_keeps_the_existing_regular_event_order(tmp_path):
    trace = trace_type()(tmp_path / 'trace.jsonl')
    assert trace.emit('query', outcome='error')
    assert trace.emit('query', outcome='ok')
    summary = trace.close()
    rows = [json.loads(line) for line in (tmp_path / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [r['outcome'] for r in rows] == ['error', 'ok']
    assert summary['offered'] == 2 and summary['failure_reserve_offered'] == 0


def test_late_task_exception_uses_reserve_but_success_and_unrelated_fields_do_not(tmp_path):
    trace = trace_type()(tmp_path / 'trace.jsonl')
    trace._offered = 5000
    assert not trace.emit('semantic.task.end', fields={'outcome': 'returned'})
    assert not trace.emit('unrelated', fields={'outcome': 'raised'})
    assert trace.emit('semantic.task.end', fields={'task': 'exercise', 'outcome': 'raised'})
    summary = trace.close()
    rows = [json.loads(line) for line in (tmp_path / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows) == summary['failure_reserve_offered'] == 1
    assert rows[0]['fields'] == {'task': 'exercise', 'outcome': 'raised'}
    assert summary['budget_dropped'] == 2
