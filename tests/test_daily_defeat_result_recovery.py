"""Daily results reuse the reviewed shared defeat recommendation close."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import semantic_runtime_fingerprint_sha256
from alas_headless.oracle.errors import SemanticNavigationPending
from tests.test_game_tips_loading_presence import host
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle

ROOT = Path(__file__).parent / 'fixtures'
CLOSE = 'OverlayCamera/Overlay/UIMain/BattleFailTipUI(Clone)/Main/CloseBtn'


def actual(drift=False):
    b, o, a = host(drift, 'daily-defeat-tip-20261029.json')
    a._refresh_tactical_input_frame = lambda: None
    return b, o, a


def arrive(b):
    # Controlled postcondition, not a claim that the captured failure returned.
    after = json.loads((ROOT / 'daily-renamed-back-r181.json').read_bytes())
    generation = max(p['generation'] for p in (b.snapshot, b.buttons, b.ui)) + 1
    for key, packet in (('snapshot', b.snapshot), ('buttons', b.buttons), ('ui', b.ui)):
        new = deepcopy(after[key])
        new.update({k: packet[k] for k in ('package', 'pid', 'driver_revision')})
        new['generation'] = generation
        setattr(b, key, new)


@pytest.mark.parametrize('drift', [False, True])
def test_actual_defeat_tip_is_closed_once_without_replaying_cached_statistics(drift):
    b, o, a = actual(drift)
    assert o.campaign_battle_fail_tip_visible()
    assert not o.daily_battle_result_visible()
    b.on_tap = lambda: arrive(b)
    with patch('time.sleep', lambda _: None):
        assert a.complete_daily_battle_result() == ()
    assert b.taps == [(629, 616)]
    assert o.daily_page_visible()


@pytest.mark.parametrize('fault', ['duplicate', 'covered', 'wrong-label', 'foreground'])
def test_unproven_defeat_close_keeps_all_input_closed(fault):
    b, _, a = actual()
    button = next(v for v in b.buttons['buttons'] if v['path'] == CLOSE)
    if fault == 'duplicate':
        b.buttons['buttons'].append(deepcopy(button))
        b.buttons['button_count'] += 1
    elif fault == 'covered':
        button['raycast_top'] = False
    elif fault == 'wrong-label':
        next(v for v in b.ui['texts'] if 'BattleFailTipUI' in v['path'])['text'] = 'VICTORY'
    else:
        b.foreground = 'other.package/Activity'
    with pytest.raises(SemanticGateClosed):
        a.complete_daily_battle_result()
    assert not b.taps


def test_pending_accepted_close_preserves_its_receipt_and_is_not_replayed():
    b, _, a = actual()
    generation = max(p['generation'] for p in (b.snapshot, b.buttons, b.ui))
    for packet in (b.snapshot, b.buttons, b.ui):
        packet['generation'] = generation
    with patch('time.sleep', lambda _: None), pytest.raises(SemanticNavigationPending) as error:
        a.complete_daily_battle_result()
    assert len(b.taps) == 1
    assert error.value.receipt.path == CLOSE


@pytest.mark.parametrize('orphan', [False, True])
def test_real_session_reacquires_after_invalidated_result_frame_before_close(orphan):
    b, _, _ = actual()
    # Freeze the independent captured endpoints for this fake frame-clock turn.
    generation = max(p['generation'] for p in (b.snapshot, b.buttons, b.ui))
    for packet in (b.snapshot, b.buttons, b.ui):
        packet['generation'] = generation
    revision = b.snapshot['driver_revision']
    handle = FakeRuntimeHandle(semantic_runtime_fingerprint_sha256(
        package=b.snapshot['package'], component=b.foreground,
        driver_revision=revision, required_primary_abi='x86_64'))
    handle.pid = b.snapshot['pid']
    handle.observer_request, handle.foreground_component = b.request, b.foreground_component
    handle.tap, handle.swipe = b.tap, b.swipe
    b.on_tap = lambda: arrive(b)
    s = AlasSemanticSession(driver_revision=revision, runtime_handle=handle)
    try:
        s.refresh_frame()
        a = s.open()
        s._frame_clock.invalidate(s._frame_clock.current_frame_id)
        for packet in (b.snapshot, b.buttons, b.ui):
            packet['generation'] += 1
        with patch.object(a, '_refresh_tactical_input_frame', wraps=a._refresh_tactical_input_frame) as fresh:
            if orphan:
                assert s.orphan_combat_result_visible()
                assert s.recover_orphan_combat_result() == ()
            else:
                assert a.complete_daily_battle_result() == ()
        assert fresh.call_count == int(not orphan) and len(b.taps) == 1
        assert a.oracle.daily_page_visible()
    finally:
        s.close()
