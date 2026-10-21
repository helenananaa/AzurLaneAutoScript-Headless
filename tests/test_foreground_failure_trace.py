"""Keep bounded diagnostics for the actual slow foreground-query failure class."""
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.semantic_oracle import AdbObserverBridge, ObserverTransportError


QUERY = ('shell', 'dumpsys', 'activity', 'activities')


def test_failed_foreground_query_preserves_cause_and_bounded_error_without_dump(monkeypatch):
    error = subprocess.CalledProcessError(1, ['adb'],
        output=b'private activity content\n*** SERVICE DUMP TIMEOUT EXPIRED ***',
        stderr=b'x' * 1000 + b'cannot connect to daemon')
    run = Mock(side_effect=error)
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', run)
    trace = SimpleNamespace(emit=Mock())
    bridge = AdbObserverBridge('test-serial', 'com.bilibili.azurlane', adb_server_port=5037, trace=trace)
    with pytest.raises(ObserverTransportError) as caught:
        bridge._run(QUERY, timeout_seconds=30)
    assert caught.value.__cause__ is error
    run.assert_called_once()
    fields = trace.emit.call_args.kwargs['fields']
    assert fields['returncode'] == 1 and fields['timeout_seconds'] == 30
    assert fields['adb_executable'] == 'adb' and fields['adb_server_port'] == 5037
    assert len(fields['stderr_tail']) == 512
    assert fields['stderr_tail'].endswith('cannot connect to daemon')
    assert fields['activity_dump_timeout'] is True
    assert 'private activity content' not in str(fields)


@pytest.mark.parametrize('stderr', [b'\xffdevice offline', 'device offline', None])
def test_foreground_failure_diagnostics_are_json_safe_for_adb_error_forms(monkeypatch, stderr):
    import json
    error = subprocess.CalledProcessError(1, ['adb'], stderr=stderr)
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', Mock(side_effect=error))
    trace = SimpleNamespace(emit=Mock())
    with pytest.raises(ObserverTransportError):
        AdbObserverBridge('test', 'com.bilibili.azurlane', trace=trace)._run(QUERY)
    fields = trace.emit.call_args.kwargs['fields']
    json.dumps(fields)
    assert ('stderr_tail' in fields) is bool(stderr)


def test_mutation_error_diagnostics_do_not_expand_or_retry_input(monkeypatch):
    error = subprocess.CalledProcessError(1, ['adb'], stderr=b'unrelated input error')
    run = Mock(side_effect=error)
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', run)
    trace = SimpleNamespace(emit=Mock())
    with pytest.raises(ObserverTransportError) as caught:
        AdbObserverBridge('test', 'com.bilibili.azurlane', trace=trace)._run(('shell', 'input', 'tap', '1', '2'))
    assert caught.value.__cause__ is error
    run.assert_called_once()
    assert trace.emit.call_args.kwargs['fields'] == {
        'operation': 'input-tap', 'exception_type': 'CalledProcessError'}


def test_foreground_error_fields_pass_actual_trace_serialization(monkeypatch, tmp_path):
    import json
    from alas_headless.runtime_trace import RuntimeTraceRecorder
    error = subprocess.CalledProcessError(1, ['adb'], stderr=b'cannot connect to daemon')
    monkeypatch.setattr('alas_headless.oracle.transport.subprocess.run', Mock(side_effect=error))
    trace = RuntimeTraceRecorder(tmp_path / 'error.jsonl', enabled=True)
    with pytest.raises(ObserverTransportError) as caught:
        AdbObserverBridge('test', 'com.bilibili.azurlane', trace=trace)._run(QUERY)
    assert caught.value.__cause__ is error
    assert trace.close()['recorded'] == 1
    record = json.loads((tmp_path / 'error.jsonl').read_text(encoding='utf-8'))
    assert record['outcome'] == 'error'
    assert record['fields']['stderr_tail'] == 'cannot connect to daemon'
