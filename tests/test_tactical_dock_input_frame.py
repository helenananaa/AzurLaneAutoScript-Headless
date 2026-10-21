"""Dock candidate text and ship input share coherent immutable projections."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle, semantic_runtime_fingerprint_sha256
from alas_headless.adapter.errors import StaleFrameError
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.semantic_support.observer_fixtures import FakeBackend


class ShipAccepted(Exception):
    """Stop at the original live destination wait after the ship tap."""


def dock():
    # This fresh read-only capture of the retained Dock contains candidates;
    # the older passive-shell fixture intentionally contains no candidate list.
    raw = json.loads((Path(__file__).parent / 'fixtures/tactical-dock-frame-r915.json').read_text(encoding='utf-8'))['frame']['projections']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (copy.deepcopy(raw[key]) for key in ('snapshot', 'buttons', 'ui'))
    bridge = AdbObserverBridge('offline-tactical-frame', backend.snapshot['package'])
    bridge.pid = backend.snapshot['pid']
    bridge.request = backend.request
    bridge.foreground_component = Mock(side_effect=backend.foreground_component)
    bridge.tap, bridge.swipe = backend.tap, backend.swipe
    bridge.package_pid = Mock(return_value=bridge.pid)
    revision = backend.snapshot['driver_revision']
    fingerprint = semantic_runtime_fingerprint_sha256(package=backend.snapshot['package'],
        component=backend.foreground, driver_revision=revision, required_primary_abi='x86_64')
    session = AlasSemanticSession(driver_revision=revision,
        runtime_handle=AdbRuntimeHandle(bridge, fingerprint_sha256=fingerprint),
        policy_grants={'tactical.assign': 1, 'shop.purchase': 0})
    session.refresh_frame()
    session.begin_tactical()
    adapter = session.open()
    # Favourite is unchanged in this regression; its independent mutation and
    # postcondition remain covered by Dock tests.
    adapter._refresh_tactical_input_frame = Mock()
    adapter.oracle.set_enhancement_dock_favourite = Mock(return_value=None)
    adapter.oracle.wait_for = Mock(side_effect=ShipAccepted())
    return backend, session, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_candidate_observation_uses_original_screenshot_without_live_reads(drift):
    backend, session, adapter = dock()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['compatible_extra_field'] = True
        session.refresh_frame()
    adapter.oracle.tactical_candidate_ships = Mock(side_effect=AssertionError('split live read'))
    candidates = session.tactical_candidate_ships()
    assert candidates and all(candidate.ship_name and candidate.level > 0 for candidate in candidates)
    assert not backend.taps


def test_selection_and_final_ship_input_use_frames_before_live_destination_wait():
    backend, session, adapter = dock()
    adapter.oracle.tactical_candidate_ships = Mock(side_effect=AssertionError('split live read'))
    adapter.oracle.click_tactical_ship = Mock(side_effect=AssertionError('split live input proof'))
    before = session._frame_clock._ordinal
    with pytest.raises(ShipAccepted):
        session.tactical_select_suitable_ship(False, 1, 0)
    assert session._frame_clock._ordinal == before + 2
    assert len(backend.taps) == 1
    assert session.action_ledger.remaining('tactical.assign') == 1
    adapter.oracle.wait_for.assert_called_once()
    assert adapter.oracle.wait_for.call_args.args == ('tactical/dock/confirm',)


@pytest.mark.parametrize('change', ['foreign', 'stale', 'incoherent', 'duplicate', 'covered', 'missing-text'])
def test_final_frame_refuses_changed_identity_state_or_target_without_input(change):
    backend, session, adapter = dock()
    refresh = adapter._input_frame_refresher
    count = 0
    selected_path = adapter._require_frame_observation_oracle().tactical_candidate_ships()[0].button.path

    def changed_refresh():
        nonlocal count
        count += 1
        if count == 2:
            if change == 'foreign':
                backend.foreground = 'other.package/.Activity'
            elif change == 'stale':
                # Acquisition owns its waiting policy; an exhausted acquisition
                # must propagate instead of reverting to the old Dock frame.
                raise StaleFrameError()
            elif change == 'incoherent':
                backend.ui['generation'] += 100
            else:
                button = next(b for b in backend.buttons['buttons'] if b['path'] == selected_path)
                if change == 'duplicate':
                    backend.buttons['buttons'].append(copy.deepcopy(button))
                    backend.buttons['button_count'] += 1
                elif change == 'covered':
                    for item in backend.buttons['buttons']:
                        if '/DockyardUI(Clone)/main/ship_container/ships/' in item['path']:
                            item['raycast_top'] = False
                else:
                    backend.ui['texts'] = [t for t in backend.ui['texts'] if not t['path'].endswith('/content/dockyard/lv/Text')]
                    backend.ui['text_count'] = len(backend.ui['texts'])
        return refresh()

    adapter._input_frame_refresher = changed_refresh
    with patch('alas_headless.adapter.frame.time.sleep', lambda _: None):
        with pytest.raises(SemanticGateClosed):
            session.tactical_select_suitable_ship(False, 1, 0)
    assert not backend.taps
    assert session.action_ledger.remaining('tactical.assign') == 1
