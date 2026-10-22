"""Passive combat ports share ALAS' screenshot; inputs keep live guards."""
from unittest.mock import Mock, patch
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticSession
from alas_headless.adapter import AdbRuntimeHandle, semantic_runtime_fingerprint_sha256
from alas_headless.semantic_oracle import AdbObserverBridge
from alas_headless.oracle.errors import SemanticSnapshotStale
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)


PAUSE = 'UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn'
RESULT = ('OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/'
          'NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn')


def host(surface, drift, **session_options):
    backend = FakeBackend([])
    texts = []
    if surface == 'combat':
        backend.buttons['buttons'] = [make_button('PauseBtn', PAUSE)]
    elif surface == 'result':
        backend.buttons['buttons'] = [make_button('confirmBtn', RESULT)]
    else:
        path = 'UICamera/Canvas/UIMain/CombatLoadUI(Clone)/loading/loading_label'
        texts = [make_text('NOW LOADING...', path), make_text('44.28%', path+'/percent')]
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    backend.ui = make_ui(texts)
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['optional_metadata'] = {'new_field': True}
    oracle = make_oracle(backend)
    bridge = AdbObserverBridge('offline-combat-frame', backend.snapshot['package'])
    bridge.pid = backend.snapshot['pid']
    bridge.request = backend.request
    bridge.foreground_component = Mock(side_effect=backend.foreground_component)
    bridge.tap, bridge.swipe = backend.tap, backend.swipe
    bridge.package_pid = Mock(return_value=bridge.pid)
    revision = oracle.fingerprint.driver_revision
    fingerprint = semantic_runtime_fingerprint_sha256(
        package=backend.snapshot['package'], component=backend.foreground,
        driver_revision=revision, required_primary_abi='x86_64')
    session = AlasSemanticSession(driver_revision=revision,
        runtime_handle=AdbRuntimeHandle(bridge, fingerprint_sha256=fingerprint), **session_options)
    session.refresh_frame()
    bridge.foreground_component.reset_mock()
    return backend, session, bridge


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('surface,loading,executing', [
    ('combat', True, True), ('loading', True, False), ('result', False, False),
])
def test_passive_combat_ports_reuse_frozen_frame_without_live_reads(
        surface, loading, executing, drift):
    backend, session, bridge = host(surface, drift)
    # Live state can advance after the screenshot. It must not replace that
    # screenshot inside the same original ALAS scan.
    live = session.open().oracle
    live.read_state = Mock(side_effect=AssertionError('split live combat observation'))
    live.read_ui_state = Mock(side_effect=AssertionError('split live combat UI'))
    assert session.combat_is_loading() is loading
    assert session.combat_is_executing() is executing
    bridge.foreground_component.assert_not_called()
    assert not backend.taps


def test_direct_combat_probe_without_screenshot_keeps_live_fallback():
    backend, session, bridge = host('combat', False)
    session._frame_clock.release_frame()
    assert session.combat_is_executing()
    bridge.foreground_component.assert_called()
    assert not backend.taps


def test_native_pause_polls_keep_existing_postcombat_wait_tied_to_latest_combat():
    _, session, _ = host('combat', False)
    session.open().begin_meta_beacon()
    session._daily_combat_seen_at = 10.0
    clock = [120.0]  # A long battle no longer probes the auto toggle.
    error = SemanticSnapshotStale(16775, 10000)
    frame = Mock(generation=12, frame_id='returned-meta')
    acquire = Mock(side_effect=[error]*85+[frame])
    with patch('alas_headless.adapter.semantic.session_combat.time.monotonic', lambda: clock[0]), \
            patch('alas_headless.adapter.semantic.session_combat.time.sleep',
                  lambda seconds: clock.__setitem__(0, clock[0]+seconds)):
        assert session.combat_is_executing()
        assert session._daily_combat_seen_at == 120.0
        session._frame_clock = SimpleNamespace(current_frame_id='old', acquire=acquire)
        assert session.refresh_frame() is frame
    assert acquire.call_count == 86
    assert session._daily_combat_seen_at == 120.0


@pytest.mark.parametrize('surface', ['result', 'loading', 'stale'])
def test_noncombat_and_stale_grace_do_not_renew_last_proven_pause(surface):
    _, session, _ = host('combat' if surface == 'stale' else surface, False)
    session.open().begin_meta_beacon()
    session.open()._operation_siren_combat_active = True
    session._daily_combat_seen_at = 10.0
    if surface == 'stale':
        session._frame_clock.release_frame()
        session.open().oracle.read_state = Mock(side_effect=SemanticSnapshotStale(16775, 10000))
    with patch('alas_headless.adapter.semantic.session_combat.time.monotonic', return_value=120.0):
        assert session.combat_is_executing() is (surface == 'stale')
    assert session._daily_combat_seen_at == 10.0
