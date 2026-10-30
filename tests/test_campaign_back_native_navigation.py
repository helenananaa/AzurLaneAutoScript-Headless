"""Native page navigation owns arrival after each reviewed campaign Back."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed, AlasSemanticUnmapped
from alas_headless.adapter import semantic_runtime_fingerprint_sha256
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
from tests.test_game_tips_loading_presence import host
from tests.test_alas_config_branch_compatibility import method
from tests.semantic_support.observer_fixtures import make_button


def actual(drift=False):
    b, _, _ = host(drift, 'campaign-back-still-menu-20261029.json')
    generation = max(p['generation'] for p in (b.snapshot, b.buttons, b.ui))
    for packet in (b.snapshot, b.buttons, b.ui):
        packet['generation'] = generation
    revision = b.snapshot['driver_revision']
    h = FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(package=b.snapshot['package'],
        component=b.foreground, driver_revision=revision, required_primary_abi='x86_64'))
    h.pid = b.snapshot['pid']
    h.observer_request, h.foreground_component = b.request, b.foreground_component
    h.tap, h.swipe = b.tap, b.swipe
    return b, AlasSemanticSession(driver_revision=revision, runtime_handle=h)


def advance(b, arrived=False):
    generation = max(p['generation'] for p in (b.snapshot, b.buttons, b.ui)) + 1
    after = json.loads((Path(__file__).parent / 'fixtures/guild-notice-expired-main-r386.json').read_bytes()) if arrived else None
    for key, packet in (('snapshot', b.snapshot), ('buttons', b.buttons), ('ui', b.ui)):
        new = deepcopy(after[key] if after else packet)
        new.update({k: packet[k] for k in ('package', 'pid', 'driver_revision')})
        new['generation'] = generation
        setattr(b, key, new)


def test_single_edge_receipt_does_not_manufacture_main_or_repeat_input():
    b, s = actual()
    b.on_tap = lambda: advance(b)
    try:
        s.refresh_frame()
        receipt = s.click('GOTO_MAIN')
        assert receipt.semantic_id == 'campaign-menu/page/back' and len(b.taps) == 1
        s.refresh_frame()
        oracle = s.open()._require_frame_observation_oracle()
        assert oracle.campaign_menu_is_entry() and not oracle.main_page_visible()
    finally:
        s.close()


@pytest.mark.parametrize('drift', [False, True])
def test_original_native_ui_rechecks_source_then_owns_retry_and_main_postcondition(drift):
    b, s = actual(drift)
    b.on_tap = lambda: advance(b, arrived=len(b.taps) == 2)
    destination = object()
    home = SimpleNamespace(name='GOTO_MAIN', clear_offset=Mock())
    page = SimpleNamespace(parent=destination, check_button=SimpleNamespace(name='CAMPAIGN_MENU_CHECK'), links={destination: home})
    checks, input_generations = [], []
    def reached(**_):
        value = s.open()._require_frame_observation_oracle().main_page_visible()
        checks.append(value)
        return value
    def click(button):
        assert not s.open()._require_frame_observation_oracle().main_page_visible()
        input_generations.append(s._frame_clock._current.generation)
        s.click(button.name)
    runner = SimpleNamespace(device=SimpleNamespace(semantic_adapter=s, screenshot=s.refresh_frame, click=click),
        interval_clear=Mock(), ui_button_interval_reset=Mock(), _check_semantic_client_version=Mock(),
        _handle_semantic_orphan_result=lambda: False, ui_page_appear=reached,
        appear=lambda button, **_: s.appear(button.name), ui_additional=Mock(return_value=False))
    native = method('module/ui/ui.py', 'UI', 'ui_goto', GOTO_MAIN=home, logger=Mock(),
        Page=SimpleNamespace(init_connection=Mock(), iter_check_buttons=lambda: [],
            iter_pages=lambda: [page], clear_connection=Mock()))
    try:
        s.refresh_frame()
        native(runner, destination)
        assert checks == [False, False, True]
        assert len(b.taps) == 2 and input_generations[1] > input_generations[0]
        assert s.open().oracle.main_page_visible()
    finally:
        s.close()


@pytest.mark.parametrize('fault', ['foreign', 'stale', 'duplicate', 'covered'])
def test_single_edge_keeps_unsafe_input_closed(fault):
    b, s = actual()
    back = next(v for v in b.buttons['buttons'] if v['path'].endswith('/top/top_chapter/back_button'))
    if fault == 'foreign':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    elif fault == 'stale':
        b.snapshot['age_ms'] = b.buttons['age_ms'] = 1000000
    elif fault == 'duplicate':
        b.buttons['buttons'].append(deepcopy(back))
        b.buttons['button_count'] += 1
    else:
        back['raycast_top'] = False
    try:
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            # Test the live input boundary directly; session acquisition owns
            # a separate bounded freshness wait before it offers any frame.
            (s.open().click if fault == 'stale' else s.click)('GOTO_MAIN')
        assert not b.taps
    finally:
        s.close()
