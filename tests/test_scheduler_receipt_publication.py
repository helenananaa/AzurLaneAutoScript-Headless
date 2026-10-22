"""Live receipt readers see a complete old or new JSON, including busy Windows readers."""
import json
from unittest.mock import Mock
import pytest
from tests.test_scheduler_failure_screenshot import load_runner


def test_retained_diagnostics_encode_only_at_publication_without_mutating_live_record(monkeypatch):
    from dataclasses import dataclass
    from types import MappingProxyType
    runner = load_runner(monkeypatch)
    @dataclass(frozen=True)
    class Observation:
        generation: int
        snapshot: object
    observed = Observation(13, MappingProxyType({'owner': 'guild'}))
    task = {'command': 'guild', 'guild_node_post_input_observation': {'state': observed}}
    result = {'tasks': [task], 'terminal': False}
    encoder = Mock(wraps=runner.encode_receipt_value)
    monkeypatch.setattr(runner, 'encode_receipt_value', encoder)
    assert task['guild_node_post_input_observation']['state'] is observed
    assert not encoder.called
    published = runner.scheduler_receipt_payload(result)
    assert json.loads(json.dumps(published))['tasks'][0]['guild_node_post_input_observation']['state'] == {
        'generation': 13, 'snapshot': {'owner': 'guild'}}
    assert task['guild_node_post_input_observation']['state'] is observed
    assert result['tasks'][0] is task


def test_complete_old_receipt_survives_until_new_receipt_is_published(tmp_path, monkeypatch):
    runner = load_runner(monkeypatch)
    path = tmp_path / 'native 日常.json'
    old, new = {'terminal': False, 'generation': 7}, {'terminal': True, 'tasks': ['日常'] * 1000}
    path.write_text(json.dumps(old), encoding='utf8')
    replace = runner.os.replace
    def inspect_before_publish(temporary, destination):
        assert json.loads(destination.read_text(encoding='utf8')) == old
        assert json.loads(temporary.read_text(encoding='utf8')) == new
        replace(temporary, destination)
    monkeypatch.setattr(runner.os, 'replace', inspect_before_publish)
    runner.write_scheduler_receipt(path, new)
    assert json.loads(path.read_text(encoding='utf8')) == new
    assert not path.with_name(path.name + '.tmp').exists()


def test_busy_reader_retries_promotion_without_rewriting_or_truncating_receipt(tmp_path, monkeypatch):
    runner = load_runner(monkeypatch)
    path = tmp_path / 'live.json'
    old, new = {'value': 'old'}, {'value': 'new'}
    path.write_text(json.dumps(old), encoding='utf8')
    replace = runner.os.replace
    attempts, sleeps = [], []
    def busy_reader(temporary, destination):
        attempts.append(True)
        assert json.loads(destination.read_text(encoding='utf8')) == old
        if len(attempts) < 3: raise PermissionError('busy reader')
        replace(temporary, destination)
    monkeypatch.setattr(runner.os, 'replace', busy_reader)
    monkeypatch.setattr(runner.time, 'sleep', sleeps.append)
    runner.write_scheduler_receipt(path, new)
    assert json.loads(path.read_text(encoding='utf8')) == new
    assert sleeps == [.025, .025]


def test_permanent_publication_failure_preserves_both_complete_receipts(tmp_path, monkeypatch):
    runner = load_runner(monkeypatch)
    path = tmp_path / 'live.json'
    old, new = {'value': 'old'}, {'value': 'latest unpublished'}
    path.write_text(json.dumps(old), encoding='utf8')
    replace = Mock(side_effect=PermissionError('destination held'))
    monkeypatch.setattr(runner.os, 'replace', replace)
    monkeypatch.setattr(runner.time, 'sleep', lambda _: None)
    with pytest.raises(PermissionError): runner.write_scheduler_receipt(path, new)
    assert json.loads(path.read_text(encoding='utf8')) == old
    assert json.loads(path.with_name(path.name + '.tmp').read_text(encoding='utf8')) == new
    assert replace.call_count == 20
