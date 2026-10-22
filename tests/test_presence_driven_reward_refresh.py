import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend


def session_for(oracle):
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_minigame()
    adapter._frame_observation_oracle = lambda: oracle
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    session._opsi_sample_use = None
    session._combat_result_action_oracle = lambda _: oracle
    session._frame_clock = SimpleNamespace(borrow=Mock())
    session.refresh_frame = Mock(return_value=SimpleNamespace(frame_id='fresh-input'))
    return session, adapter


def test_retained_r21_reward_disappearance_returns_to_native_loop_without_input():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r21.json'
    if not path.exists():
        pytest.skip('retained r21 frame unavailable')
    task = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks']
                if t['selected_task'] == 'Minigame')
    frame = task['failure_observation']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    generation = max(s['generation'] for s in (backend.snapshot, backend.buttons, backend.ui))
    for snapshot in (backend.snapshot, backend.buttons, backend.ui):
        snapshot['generation'] = generation
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    session, adapter = session_for(oracle)
    assert adapter.appear(NamedButton('GET_ITEMS_1')) is False
    # Native ALAS enters this call using an earlier positive screenshot probe.
    assert session.click_if_present(NamedButton('GET_ITEMS_1')) is None
    assert session.refresh_frame.call_count == 1
    assert backend.taps == []


@pytest.mark.parametrize('state', ['present', 'absent', 'unknown'])
def test_presence_driven_generic_dispatch_rechecks_the_prepared_frame(state):
    oracle = FakeOracle()
    oracle.campaign_battle_reward_visible = lambda: False
    oracle.game_room_page_visible = lambda: state == 'absent'
    oracle.award_info_page_visible = lambda: state == 'present'
    oracle.enabled = lambda target: state == 'present' and target == 'reward/award-info/close'
    session, adapter = session_for(oracle)
    original = adapter.appear
    adapter.appear = Mock(side_effect=original)
    if state == 'unknown':
        adapter.appear.side_effect = SemanticGateClosed('unknown typed page')
        with pytest.raises(SemanticGateClosed, match='unknown typed page'):
            session.click_if_present(NamedButton('GET_ITEMS_1'))
    elif state == 'present':
        assert session.click_if_present(NamedButton('GET_ITEMS_1')).semantic_id == 'reward/award-info/close'
    else:
        assert session.click_if_present(NamedButton('GET_ITEMS_1')) is None
    adapter.appear.assert_called_once()
    assert session.refresh_frame.call_count == 1
    assert oracle.click_calls == (['reward/award-info/close'] if state == 'present' else [])


def test_direct_click_keeps_existing_strict_input_contract():
    oracle = FakeOracle()
    oracle.campaign_battle_reward_visible = lambda: False
    oracle.game_room_page_visible = lambda: True
    session, _ = session_for(oracle)
    with pytest.raises(SemanticGateClosed, match='mission resource used outside'):
        session.click(NamedButton('GET_ITEMS_1'))
    assert oracle.click_calls == []
