"""Covered statistics controls yield passive polls, never authorize input."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, COMPONENT


FIXTURE = Path(__file__).parent / 'fixtures/opsi-statistics-passive-mount-20261026.json'
RESULT = ('OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/'
          'NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn')


def rig(owner='strategic', damage=None, drift=False):
    # The captured records stay exact. Ownership is a separate controlled
    # precondition, not a reconstruction of hidden historical Python flags.
    saved = json.loads(FIXTURE.read_text(encoding='utf-8'))['frame']['projections']
    b = FakeBackend([])
    b.snapshot = copy.deepcopy(saved['snapshot'])
    b.buttons = copy.deepcopy(saved['buttons'])
    b.ui = copy.deepcopy(saved['ui'])
    target = next(x for x in b.buttons['buttons'] if x['path'] == RESULT)
    if damage == 'duplicate':
        b.buttons['buttons'].append(copy.deepcopy(target))
        b.buttons['button_count'] += 1
    elif damage == 'unknown-top':
        target['raycast_top'] = None
    elif damage == 'ready':
        target['raycast_top'] = True
    elif damage == 'truncated':
        b.buttons['truncated'] = True
    if drift:
        b.buttons['buttons'].reverse()
        b.buttons['optional_metadata'] = {'additive_field': True}
        b.ui['optional_metadata'] = {'additive_field': True}
    oracle = _FrameBoundSemanticOracle(
        b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=COMPONENT,
                          driver_revision=b.snapshot['driver_revision'],
                          expected_pid=b.snapshot['pid']), frame_guard=lambda: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    session = AlasSemanticSession('offline-statistics-passive', oracle.fingerprint.driver_revision)
    session.adapter = adapter
    session.open = lambda: adapter
    if owner == 'strategic':
        adapter._operation_siren_strategic_search_owned = True
    elif owner == 'manual':
        adapter._operation_siren_combat_active = True
    return b, oracle, session


@pytest.mark.parametrize('owner', ['strategic', 'manual'])
def test_retained_statistics_mount_yields_native_passive_pause_poll(owner):
    b, oracle, session = rig(owner)
    assert session._live_combat_visible() == ()
    assert session.combat_is_executing() is False
    # A negative observation must not promote the same covered control to input.
    with pytest.raises(SemanticGateClosed):
        oracle.click_daily_battle_result()
    assert b.taps == []


@pytest.mark.parametrize('damage', ['duplicate', 'unknown-top', 'truncated'])
def test_mount_yield_keeps_ambiguous_unknown_and_incomplete_records_closed(damage):
    b, _, session = rig(damage=damage)
    with pytest.raises(SemanticGateClosed):
        session._live_combat_visible()
    assert b.taps == []


def test_unowned_statistics_mount_keeps_existing_owner_requirement():
    b, _, session = rig(owner=None)
    with pytest.raises(SemanticGateClosed, match='requires a committed'):
        session._live_combat_visible()
    assert b.taps == []


@pytest.mark.parametrize('drift', [False, True])
def test_ready_statistics_still_exposes_original_result_resources(drift):
    b, _, session = rig(damage='ready', drift=drift)
    visible = session._live_combat_visible()
    assert any(name.startswith('EXP_INFO') for name in visible)
    assert 'PAUSE' not in visible
    assert b.taps == []


def test_passive_mount_recheck_keeps_the_original_screenshot_oracle():
    b, oracle, session = rig()
    adapter = session.open()
    adapter._frame_or_live_observation_oracle = lambda: oracle
    adapter._live_oracle = Mock()
    adapter.oracle.read_state.side_effect = AssertionError('split passive screenshot')
    assert session._live_combat_visible() == ()
    adapter.oracle.read_state.assert_not_called()
    assert b.taps == []
