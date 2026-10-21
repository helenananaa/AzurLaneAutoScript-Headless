"""Optional navigation diagnostics preserve actual inputs and error behavior."""
import importlib.util
import json
from pathlib import Path

import pytest

from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_buttons


def module(monkeypatch):
    root = Path(__file__).resolve().parents[1] / 'scripts/python'
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location('navigation_capture', root / 'navigation_input_telemetry.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def oracle_for(cls, semantic_id='main/live', drift=False, missing=False):
    b = FakeBackend([])
    fingerprint = make_oracle(b).fingerprint
    options = dict(frame_guard=lambda: None) if issubclass(cls, _FrameBoundSemanticOracle) else {}
    o = cls(b.request, b.foreground_component, b.tap, fingerprint, **options)
    target = o._targets[semantic_id]
    suffix = target.path_suffix
    if isinstance(suffix, tuple):
        suffix = suffix[-1 if drift else 0]
    b.buttons = make_buttons([] if missing else [make_button(target.name, 'root/' + suffix)])
    if drift:
        b.buttons['optional_upstream_metadata'] = True
    return b, o


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('semantic_id', ['main/live', 'dorm-menu/academy'])
def test_existing_live_reads_and_input_are_identical_with_capture(monkeypatch, tmp_path, drift, semantic_id):
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b0, o0 = oracle_for(SemanticOracle, semantic_id, drift)
    expected = o0.click(semantic_id)
    b, o = oracle_for(Traced, semantic_id, drift)
    path = tmp_path / 'trace.jsonl'
    stats = capture.install(Traced, path)
    actual = o.click(semantic_id)
    assert actual == expected
    assert b.taps == b0.taps and b.requests == b0.requests
    assert b.foreground_requests == b0.foreground_requests
    assert 'read_state' not in o.__dict__
    row = json.loads(path.read_text('utf-8'))
    assert row['source']['generation'] == row['receipt_generation'] == actual.generation
    assert stats['written'] == 1


def test_cached_frame_read_is_recorded_without_another_endpoint(monkeypatch, tmp_path):
    capture = module(monkeypatch)
    class Frame(_FrameBoundSemanticOracle):
        pass
    b, o = oracle_for(Frame)
    o.read_state()
    b.requests.clear()
    path = tmp_path / 'trace.jsonl'
    capture.install(Frame, path)
    o.click('main/live')
    assert not b.requests
    assert len(b.taps) == 1
    assert json.loads(path.read_text('utf-8'))['source']['generation'] == 10


def test_missing_target_keeps_original_error_and_retains_missing_source(monkeypatch, tmp_path):
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b, o = oracle_for(Traced, missing=True)
    path = tmp_path / 'trace.jsonl'
    capture.install(Traced, path)
    from alas_headless.oracle.errors import SemanticInputTargetMissing
    with pytest.raises(SemanticInputTargetMissing) as caught:
        o.click('main/live')
    row = json.loads(path.read_text('utf-8'))
    assert row['source']['generation'] == caught.value.generation
    assert row['error_type'] == type(caught.value).__name__
    assert not b.taps and 'read_state' not in o.__dict__


@pytest.mark.parametrize('failure', ['encoding', 'writing', 'limit'])
def test_diagnostic_failure_or_limit_never_blocks_input(monkeypatch, tmp_path, failure):
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b, o = oracle_for(Traced)
    path = tmp_path / 'trace.jsonl'
    stats = capture.install(Traced, path, limit=0 if failure == 'limit' else 128)
    if failure == 'encoding':
        monkeypatch.setattr(capture, 'encode_receipt_value', lambda _: (_ for _ in ()).throw(ValueError('encode failed')))
    elif failure == 'writing':
        path.rename(tmp_path / 'reserved.jsonl')
        path.mkdir()
    assert o.click('main/live').generation == 10
    assert len(b.taps) == 1 and 'read_state' not in o.__dict__
    assert stats[{'encoding': 'capture_errors', 'writing': 'write_errors', 'limit': 'dropped'}[failure]] == 1


def test_unavailable_log_disables_only_diagnostics(monkeypatch, tmp_path):
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b, o = oracle_for(Traced)
    original = Traced.click
    stats = capture.install(Traced, tmp_path / 'missing' / 'trace.jsonl')
    assert not stats['installed'] and Traced.click is original
    assert o.click('main/live').generation == 10 and len(b.taps) == 1


def test_record_freezes_source_before_input_mutates_reused_producer_buffers(monkeypatch, tmp_path):
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b, o = oracle_for(Traced)
    def mutate():
        b.snapshot['generation'] = b.buttons['generation'] = 99
    b.on_tap = mutate
    path = tmp_path / 'trace.jsonl'
    capture.install(Traced, path)
    assert o.click('main/live').generation == 10
    source = json.loads(path.read_text('utf-8'))['source']
    assert source['generation'] == source['snapshot']['generation'] == source['buttons']['generation'] == 10


def test_existing_read_override_survives_a_click_exception(monkeypatch, tmp_path):
    from unittest.mock import Mock
    from alas_headless.oracle.errors import SemanticInputTargetMissing
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b, o = oracle_for(Traced, missing=True)
    override = Mock(wraps=o.read_state)
    o.read_state = override
    capture.install(Traced, tmp_path / 'trace.jsonl')
    with pytest.raises(SemanticInputTargetMissing):
        o.click('main/live')
    assert o.read_state is override and override.call_count == 1 and not b.taps


def test_unrelated_target_does_not_capture_or_change_reads(monkeypatch, tmp_path):
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b, o = oracle_for(Traced, 'main/more')
    path = tmp_path / 'trace.jsonl'
    stats = capture.install(Traced, path)
    assert o.click('main/more').generation == 10
    assert len(b.taps) == 1 and len(b.requests) == 1
    assert stats['offered'] == stats['written'] == 0
    assert not path.read_text('utf-8')


@pytest.mark.parametrize('drift', [False, True])
def test_opt_in_sidebar_capture_preserves_input_and_query_counts(monkeypatch, tmp_path, drift):
    capture = module(monkeypatch)
    class Traced(SemanticOracle):
        pass
    b0, o0 = oracle_for(SemanticOracle, 'main/more', drift)
    expected = o0.click('main/more')
    b, o = oracle_for(Traced, 'main/more', drift)
    path = tmp_path / 'sidebar.jsonl'
    capture.install(Traced, path, semantic_ids=('main/more',))
    assert o.click('main/more') == expected
    assert b.taps == b0.taps and b.requests == b0.requests
    assert b.foreground_requests == b0.foreground_requests
    row = json.loads(path.read_text('utf-8'))
    assert row['semantic_id'] == 'main/more'
    assert row['source']['generation'] == expected.generation
