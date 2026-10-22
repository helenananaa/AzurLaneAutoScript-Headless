"""An accepted OS exit can finish mounting its next native Back control."""
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from alas_headless import SemanticGateClosed
from tests.test_frame_post_input_foreground import session_for_meta
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def exit_session(drift=False):
    backend, oracle, adapter = host(drift, 'opsi-exit-chapter-menu-r413.json')
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] = generation
    with patch('tests.test_frame_post_input_foreground.host', return_value=(backend, oracle, adapter)):
        _, session, _ = session_for_meta()
    adapter = session.open()
    adapter._goto_main_target = lambda: 'campaign-menu/page/back'
    adapter._operation_siren_exit_handoff = (
        SimpleNamespace(semantic_id='os/exit/confirm', generation=generation-2),
        adapter.oracle.input_dispatch_count)
    adapter._operation_siren_entry_transition_until = time.monotonic()+30
    return backend, session


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('mounting_raycast', [False, None])
def test_owned_menu_mount_yields_then_fresh_ready_back_dispatches_once(drift, mounting_raycast):
    backend, session = exit_session(drift)
    adapter = session.open()
    back = next(b for b in backend.buttons['buttons'] if b['name']=='back_button')
    back['raycast_top'] = mounting_raycast
    live = adapter.oracle
    live.campaign_page_is_normal = Mock(side_effect=AssertionError('split live source identity'))
    live.event_campaign_page_visible = Mock(side_effect=AssertionError('split live source identity'))
    live.click = Mock(side_effect=AssertionError('split live input target'))
    assert session.click('GOTO_MAIN') is None
    assert not backend.taps
    back['raycast_top'] = True
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] += 1
    destination = json.loads((Path(__file__).parent/'fixtures/guild-notice-expired-main-r386.json').read_text(encoding='utf8'))
    def arrived():
        generation = backend.snapshot['generation']+1
        pid, revision = backend.snapshot['pid'], backend.snapshot['driver_revision']
        backend.snapshot, backend.buttons, backend.ui = (destination['snapshot'], destination['buttons'], destination['ui'])
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part.update(generation=generation, pid=pid, driver_revision=revision)
    backend.on_tap = arrived
    assert session.click('GOTO_MAIN').semantic_id == 'campaign-menu/page/back'
    assert len(backend.taps) == 1
    assert live.input_dispatch_count == 1
    live.campaign_page_is_normal.assert_not_called()
    live.event_campaign_page_visible.assert_not_called()
    live.click.assert_not_called()


@pytest.mark.parametrize('damage', ['no-receipt', 'new-input', 'foreign-popup', 'foreign-package', 'missing-back'])
def test_unknown_mount_or_changed_input_does_not_acknowledge_an_exit(damage):
    backend, session = exit_session()
    adapter = session.open()
    next(b for b in backend.buttons['buttons'] if b['name']=='back_button')['raycast_top'] = False
    if damage == 'no-receipt':
        adapter._operation_siren_exit_handoff = None
    elif damage == 'new-input':
        adapter.oracle._mark_input_dispatched()
    elif damage == 'foreign-popup':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif damage == 'foreign-package':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name']!='back_button']
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        session.click('GOTO_MAIN')
    assert not backend.taps
