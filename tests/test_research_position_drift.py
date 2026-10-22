import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, ResearchProjectStatus, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.semantic_support.adapter_fixtures import FakeOracle


def test_retained_reordered_cards_preserve_native_unique_project_decision():
    p = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r19.json'
    if not p.exists():
        pytest.skip('retained r19 frame unavailable')
    t = next(t for t in json.loads(p.read_text(encoding='utf-8'))['tasks']
             if t['selected_task'] == 'Research')
    frame = t['failure_observation']
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui']['snapshot']
    # Preserve the captured card layout in a stationary coherent replay.
    generation = max(s['generation'] for s in (b.snapshot, b.buttons, b.ui))
    for s in (b.snapshot, b.buttons, b.ui):
        s['generation'] = generation
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_research()
    states = o.research_projects()
    assert states[0].code == 'H-387-MI'
    assert states[1].code == 'G-236-MI'
    receipt = SimpleNamespace(semantic_id='research/project/2', generation=generation)
    o.click_research_project = Mock(return_value=receipt)
    assert a.click_research_project_code('G-236-MI', position=0) is receipt
    o.click_research_project.assert_called_once_with(2, expected_code='G-236-MI', expected_series=9)
    assert a._research_context.selected_code == 'G-236-MI'
    assert a._research_context.selected_slot == 2
    assert b.taps == []


@pytest.mark.parametrize('change', ['duplicate', 'replaced', 'finished'])
def test_position_drift_cannot_guess_through_changed_project_identity(change):
    o = FakeOracle()
    selected = SimpleNamespace(slot=2, unity_index=2, code='G-236-MI',
                               status=ResearchProjectStatus.DETAIL)
    other = SimpleNamespace(slot=1, unity_index=1, code='C-153-MI',
                            status=ResearchProjectStatus.DETAIL)
    o.research_project_values = [other, selected]
    if change == 'duplicate':
        o.research_project_values.append(SimpleNamespace(slot=3, unity_index=3,
            code='G-236-MI', status=ResearchProjectStatus.DETAIL))
    elif change == 'replaced':
        selected.code = 'D-737-MI'
    else:
        selected.status = ResearchProjectStatus.FINISHED
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_research()
    with pytest.raises(SemanticGateClosed):
        a.click_research_project_code('G-236-MI', position=0)
    assert o.click_calls == []
