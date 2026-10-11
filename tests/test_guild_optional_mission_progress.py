import copy
import json
from pathlib import Path

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.test_guild_logistics_rich_text import retained_logistics


def retained_office():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r20.json'
    if not path.exists():
        pytest.skip('retained r20 Guild frame unavailable')
    task = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks']
                if t['selected_task'] == 'Guild')
    frame = task['failure_observation']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    # Preserve the captured shape; hold separate endpoint copies at the latest
    # captured coherent generation for repeated stationary replay reads.
    generation = max(s['generation'] for s in (backend.snapshot, backend.buttons, backend.ui))
    for snapshot in (backend.snapshot, backend.buttons, backend.ui):
        snapshot['generation'] = generation
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    return backend, oracle


def test_retained_missing_weekly_progress_preserves_supply_and_exchange():
    backend, oracle = retained_office()
    state = oracle.guild_logistics_state()
    assert (state.supply_remaining, state.supply_total) == (1, 3)
    assert state.supply_claimable
    assert state.exchange_remaining == 3
    assert len(state.exchange_items) == 3
    assert state.mission_current is None and state.mission_total is None
    assert not state.mission_claimable
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed, match='guild mission is not claimable'):
        adapter.claim_guild_mission()
    assert backend.taps == []


def test_known_baseline_mission_progress_remains_known():
    backend, oracle = retained_logistics()
    state = oracle.guild_logistics_state()
    assert isinstance(state.mission_current, int)
    assert isinstance(state.mission_total, int)
    assert backend.taps == []


@pytest.mark.parametrize('change', ['malformed', 'duplicate', 'truncated', 'claim-target'])
def test_optional_missing_progress_does_not_accept_ambiguous_or_actionable_mission(change):
    backend, oracle = retained_office()
    baseline, _ = retained_logistics()
    if change == 'claim-target':
        source = next(b for b in baseline.buttons['buttons']
                      if b['path'].endswith('TaskPanel/open/bottom/accept'))
        backend.buttons['buttons'].append(copy.deepcopy(source))
    else:
        source = next(t for t in baseline.ui['texts']
                      if t['path'].endswith('TaskPanel/open/top/progress'))
        progress = copy.deepcopy(source)
        progress['text'] = 'unknown' if change == 'malformed' else '1/3'
        progress['truncated'] = change == 'truncated'
        backend.ui['texts'].append(progress)
        if change == 'duplicate':
            backend.ui['texts'].append(copy.deepcopy(progress))
    with pytest.raises(SemanticGateClosed):
        oracle.guild_logistics_state()
    assert backend.taps == []
