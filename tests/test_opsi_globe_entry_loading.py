"""A SAFE pin can finish Loading before its first unsubmitted entry input."""
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import semantic_runtime_fingerprint_sha256
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.test_game_tips_loading_presence import host
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle
from tests.semantic_support.observer_fixtures import make_button

LOADING = 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'


def actual(drift=False):
    b, o, a = host(drift, 'opsi-globe-pin-after-loading-20261029.json')
    zone = o.operation_siren_globe_state().zone_name
    # Static fake endpoints, not a reconstruction of the rejected input frame.
    generation = max(p['generation'] for p in (b.snapshot, b.buttons, b.ui))
    for packet in (b.snapshot, b.buttons, b.ui):
        packet['generation'] = generation
    b.buttons['buttons'].append(make_button('Loading(Clone)', LOADING))
    b.buttons['button_count'] += 1
    return b, o, a, zone


def advance(b):
    b.buttons['buttons'] = [v for v in b.buttons['buttons'] if v['path'] != LOADING]
    b.buttons['button_count'] = len(b.buttons['buttons'])
    for packet in (b.snapshot, b.buttons, b.ui):
        packet['generation'] += 1


@pytest.mark.parametrize('drift', [False, True])
def test_loading_only_reacquires_same_pin_then_submits_one_input(drift):
    b, o, a, zone = actual(drift)
    def acquire():
        if fresh.call_count == 2:
            advance(b)
        return o
    fresh = Mock(side_effect=acquire)
    a._fresh_input_oracle = fresh
    with patch('time.sleep', lambda _: None):
        receipt = a.click_operation_siren_globe_zone_enter(zone)
    assert fresh.call_count == 2 and len(b.taps) == 1
    assert receipt.semantic_id == 'os/globe/zone-enter'
    assert a._operation_siren_entry_receipt is receipt


@pytest.mark.parametrize('case', ['mixed', 'changed-pin', 'persistent', 'post-input'])
def test_unproven_or_already_submitted_entry_is_never_replayed(case):
    b, o, a, zone = actual()
    if case == 'mixed':
        b.buttons['buttons'].append(make_button('Msgbox',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button'))
        b.buttons['button_count'] += 1
    if case == 'post-input':
        def dispatched(_):
            o._tap(100, 100)
            raise SemanticInputBlocked('os/globe/zone-enter', 1, ('loading',))
        o.click_operation_siren_globe_zone_enter = Mock(side_effect=dispatched)
    def acquire():
        if case == 'changed-pin' and fresh.call_count == 2:
            advance(b)
            title = next(v for v in b.ui['texts'] if v['path'].endswith('/title/name/subText'))
            title['text'] = title['text'].replace(zone, 'changed-zone')
        return o
    fresh = Mock(side_effect=acquire)
    a._fresh_input_oracle = fresh
    with patch('time.sleep', lambda _: None), pytest.raises(SemanticGateClosed):
        a.click_operation_siren_globe_zone_enter(zone)
    assert len(b.taps) == int(case == 'post-input')
    assert fresh.call_count == {'mixed': 1, 'changed-pin': 2, 'persistent': 4, 'post-input': 1}[case]
    assert a._operation_siren_entry_receipt is None


def test_real_session_input_frame_is_refreshed_after_loading_without_extra_tap():
    b, _, _, zone = actual()
    revision = b.snapshot['driver_revision']
    handle = FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=b.snapshot['package'], component=b.foreground,
        driver_revision=revision, required_primary_abi='x86_64'))
    handle.pid = b.snapshot['pid']
    handle.observer_request, handle.foreground_component = b.request, b.foreground_component
    handle.tap, handle.swipe = b.tap, b.swipe
    s = AlasSemanticSession(driver_revision=revision, runtime_handle=handle)
    try:
        a = s.open()
        def acquire():
            if fresh.call_count == 2:
                advance(b)
            return s.refresh_frame()
        fresh = Mock(side_effect=acquire)
        a._input_frame_refresher = fresh
        with patch('time.sleep', lambda _: None):
            receipt = s.click_operation_siren_globe_zone_enter(zone)
        assert fresh.call_count == 2 and len(b.taps) == 1
        assert receipt.generation == b.snapshot['generation']
    finally:
        s.close()
