"""Passive refresh obeys its existing OS transition deadline, not a duplicate cap."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.oracle.errors import SemanticSnapshotStale
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle, REVISION


@pytest.mark.parametrize('case', ['fresh-after-old-cap', 'expired', 'foreign', 'never-fresh'])
def test_existing_os_transition_deadline_owns_passive_snapshot_wait(case):
    session=AlasSemanticSession(driver_revision=REVISION,runtime_handle=FakeRuntimeHandle())
    session.adapter=SimpleNamespace(
        _login_flow=SimpleNamespace(snapshot=lambda:SimpleNamespace(active=False,passive_transition_until=0)),
        oracle=SimpleNamespace(stale_login_update_in_progress=lambda:False),
        _campaign_context=None,_operation_siren_entry_transition_until=30,
        _operation_siren_auto_search_transition_until=0)
    clock=[31.0 if case=='expired' else 0.0]
    frame=Mock(generation=12,frame_id='fresh')
    # Stale publications now have a task-independent acquisition wait. Keep
    # this test on the other existing, task-owned coherence retry boundary.
    error=SemanticGateClosed('observer package mismatch') if case=='foreign' else SemanticGateClosed('observer endpoints are not generation-coherent')
    acquire=Mock(side_effect=error if case=='never-fresh' else [error]*85+[frame])
    session._frame_clock=SimpleNamespace(current_frame_id='old',acquire=acquire)
    def sleep(seconds):clock[0]+=seconds
    with patch('alas_headless.alas_adapter.time.monotonic',lambda:clock[0]), \
            patch('alas_headless.alas_adapter.time.sleep',sleep):
        if case=='fresh-after-old-cap':
            assert session.refresh_frame() is frame
            assert acquire.call_count==86
        else:
            with pytest.raises(SemanticGateClosed):session.refresh_frame()
            if case=='foreign':assert acquire.call_count==1
            if case=='expired':assert acquire.call_count==3
            if case=='never-fresh':assert 30<=clock[0]<30.2


@pytest.mark.parametrize('case', ['recent-combat', 'no-owner', 'no-combat', 'missing-combat', 'expired', 'foreign', 'never-fresh'])
@pytest.mark.parametrize('owner', ['_operation_siren_auto_search_active', '_meta_beacon_active', '_meta_assist_active'])
def test_native_owned_combat_gap_uses_last_proven_combat_without_extending_on_stale(case, owner):
    session=AlasSemanticSession(driver_revision=REVISION,runtime_handle=FakeRuntimeHandle())
    session.adapter=SimpleNamespace(
        _login_flow=SimpleNamespace(snapshot=lambda:SimpleNamespace(active=False,passive_transition_until=0)),
        oracle=SimpleNamespace(stale_login_update_in_progress=lambda:False),
        _campaign_context=None,_operation_siren_entry_transition_until=0,
        _operation_siren_auto_search_transition_until=0)
    setattr(session.adapter, owner, case!='no-owner')
    session._daily_combat_seen_at=float('-inf') if case=='no-combat' else 10.0
    if case=='missing-combat':del session._daily_combat_seen_at
    clock=[41.0 if case=='expired' else 10.0]
    frame=Mock(generation=12,frame_id='fresh')
    error=SemanticGateClosed('observer package mismatch') if case=='foreign' else SemanticGateClosed('observer endpoints are not generation-coherent')
    acquire=Mock(side_effect=error if case=='never-fresh' else [error]*85+[frame])
    session._frame_clock=SimpleNamespace(current_frame_id='old',acquire=acquire)
    def sleep(seconds):clock[0]+=seconds
    with patch('alas_headless.alas_adapter.time.monotonic',lambda:clock[0]), \
            patch('alas_headless.alas_adapter.time.sleep',sleep):
        if case=='recent-combat':
            assert session.refresh_frame() is frame
            assert acquire.call_count==86
        else:
            with pytest.raises(SemanticGateClosed):session.refresh_frame()
            if case=='foreign':assert acquire.call_count==1
            if case in ('no-owner','no-combat','missing-combat','expired'):assert acquire.call_count==3
            if case=='never-fresh':assert 40<=clock[0]<40.2
