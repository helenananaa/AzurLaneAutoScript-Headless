"""Clear progress belongs to the same ALAS screenshot as stage presence."""
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle, semantic_runtime_fingerprint_sha256
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.test_game_tips_loading_presence import host


def session_for_hard(drift=False):
    backend, oracle, _ = host(drift, 'hard-clear-percentage-r361.json')
    # Static replay only: the real fixture retains adjacent live endpoint
    # clocks. Normalize in memory so a newer UI is not replayed forever.
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for p in (backend.snapshot, backend.buttons, backend.ui):
        p['generation'] = generation
    bridge = AdbObserverBridge('offline-hard-progress', backend.snapshot['package'])
    bridge.pid = backend.snapshot['pid']
    bridge.request = backend.request
    bridge.foreground_component = backend.foreground_component
    bridge.tap, bridge.swipe = backend.tap, backend.swipe
    bridge.package_pid = Mock(return_value=bridge.pid)
    rev = oracle.fingerprint.driver_revision
    fingerprint = semantic_runtime_fingerprint_sha256(package=backend.snapshot['package'],
        component=backend.foreground, driver_revision=rev, required_primary_abi='x86_64')
    session = AlasSemanticSession(driver_revision=rev,
        runtime_handle=AdbRuntimeHandle(bridge, fingerprint_sha256=fingerprint))
    session.refresh_frame()
    session.open().begin_campaign_pre_sortie('12-4', mode='hard')
    return backend, session


@pytest.mark.parametrize('drift', [False, True])
def test_actual_hard_progress_uses_its_screenshot_without_split_live_reads(drift):
    backend, session = session_for_hard(drift)
    live = session.open().oracle
    live.campaign_preparation_state = Mock(side_effect=AssertionError('split preparation view'))
    live.campaign_map_clear_percentage = Mock(side_effect=AssertionError('split progress view'))
    before = len(backend.requests), backend.foreground_requests
    assert session.campaign_map_clear_percentage() == 1.0
    assert session.campaign_map_clear_percentage() == 1.0
    assert (len(backend.requests), backend.foreground_requests) == before
    assert not backend.taps


@pytest.mark.parametrize('damage', ['sprite', 'progress', 'hard-underlay', 'duplicate', 'wrong-stage', 'text-truncated'])
def test_frozen_progress_is_replaced_only_by_next_screenshot_and_guards_stay_closed(damage):
    backend, session = session_for_hard()
    root = 'OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/'
    if damage == 'sprite':
        next(i for i in backend.ui['images'] if i['path'] == root+'start_button_l')['sprite'] = 'unreviewed'
    elif damage == 'progress':
        backend.ui['texts'] = [t for t in backend.ui['texts'] if t['path'] != root+'progress/Text/value']
        backend.ui['text_count'] = len(backend.ui['texts'])
    elif damage == 'hard-underlay':
        next(b for b in backend.buttons['buttons'] if b['name'] == 'btn_normal')['active_in_hierarchy'] = False
    elif damage == 'duplicate':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons'] if b['name'] == 'start_button_l')))
        backend.buttons['button_count'] += 1
    elif damage == 'wrong-stage':
        next(t for t in backend.ui['texts'] if t['path'] == root+'title_form/title_index')['text'] = '11-4'
    else:
        # Progress consumes the text family. A global partial image list alone
        # does not erase an already present exact required button sprite.
        backend.ui['text_truncated'] = True
    assert session.campaign_map_clear_percentage() == 1.0
    session.refresh_frame()
    with pytest.raises(SemanticGateClosed):
        session.campaign_map_clear_percentage()
    assert not backend.taps
