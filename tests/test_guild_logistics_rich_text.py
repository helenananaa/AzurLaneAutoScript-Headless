import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.test_alas_config_branch_compatibility import method


def retained_logistics():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r10.json'
    if not path.exists():
        pytest.skip('retained Guild logistics frame unavailable')
    frame = json.loads(path.read_text(encoding='utf-8'))['tasks'][-1]['failure_observation']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    return backend, oracle


@pytest.mark.parametrize('value', ['487/600', '<color=#FF5C5CFF>487</color>/600'])
def test_shortage_display_markup_preserves_logistics_values_without_enabling_input(value):
    backend, oracle = retained_logistics()
    row = next(t for t in backend.ui['texts'] if t['text'] == '<color=#FF5C5CFF>487</color>/600')
    row['text'] = value
    state = oracle.guild_logistics_state()
    coin = next(item for item in state.exchange_items if item.owned == 487)
    assert coin.required == 600
    assert state.exchange_remaining == 0
    assert not coin.button.interactable
    assert backend.taps == []


@pytest.mark.parametrize('value', ['487/600/7', '<color=#FF5C5CFF>unknown</color>/600'])
def test_markup_does_not_turn_malformed_quantities_into_valid_resources(value):
    backend, oracle = retained_logistics()
    next(t for t in backend.ui['texts'] if t['text'] == '<color=#FF5C5CFF>487</color>/600')['text'] = value
    with pytest.raises(SemanticGateClosed):
        oracle.guild_logistics_state()
    assert backend.taps == []


@pytest.mark.parametrize('error,local', [
    (SemanticGateClosed('guild exchange row values are malformed'), True),
    (SemanticGateClosed('foreground component differs from expected identity'), False),
    (ConnectionError('observer transport lost'), False),
])
def test_native_guild_reader_keeps_error_cause_and_only_classifies_local_parser_failures(error, local):
    adapter = SimpleNamespace(ensure_guild_section=Mock(), guild_logistics_state=Mock(side_effect=error))
    host = SimpleNamespace(device=SimpleNamespace(
        semantic_adapter=SimpleNamespace(open=lambda: adapter), sleep=Mock()))
    original = method('module/guild/logistics.py', 'GuildLogistics', 'guild_logistics',
        SemanticGateClosed=SemanticGateClosed, AlasSemanticUnmapped=AlasSemanticUnmapped)
    with pytest.raises(AlasSemanticUnmapped if local else type(error), match=str(error)):
        original(host)
    assert adapter.guild_logistics_state.call_count == (30 if local else 1)
    assert host.device.sleep.call_count == (30 if local else 0)


def test_unavailable_guild_parser_releases_task_state_for_the_next_native_task():
    from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
    session = SimpleNamespace(discard_task_state=Mock(), trace=None)
    with pytest.raises(TaskCapabilityUnavailable, match='guild exchange row values'):
        with semantic_task_scope(session, 'guild'):
            raise AlasSemanticUnmapped('Guild logistics unavailable: guild exchange row values are malformed')
    assert session.last_task_outcome == {'task': 'guild', 'outcome': 'capability-unavailable'}
    with semantic_task_scope(session, 'research'):
        pass
    assert session.last_task_outcome == {'task': 'research', 'outcome': 'returned'}
    assert session.discard_task_state.call_count == 2
