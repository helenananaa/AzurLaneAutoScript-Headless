"""Native result decisions must belong to one semantic screenshot."""

from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, AlasSemanticUnmapped
from alas_headless.adapter import SemanticFrameClock, SemanticFrameReader
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.campaign_live_fixtures import native, own_auto_search
from tests.semantic_support.observer_fixtures import make_button, make_text
from tests.test_adapter_frame import FakeRuntimeHandle, MutableClock


def phase(handle, name, generation):
    for payload in (handle.snapshot, handle.buttons, handle.ui):
        payload['generation'] = generation
    handle.buttons['buttons'] = []
    handle.ui['texts'] = []
    if name == 'combat':
        handle.buttons['buttons'] = [make_button('PauseBtn',
            'UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn')]
    elif name == 'combat-tail':
        handle.buttons['buttons'] = [make_button('chatBtn',
            'UICamera/Canvas/UIMain/CombatUIStandard(Clone)/chatBtnContainer/chatBtn')]
    elif name == 'result':
        root = 'OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)'
        handle.ui['texts'] = [
            make_text('VICTORY', root + '/Effect/bg03/Text'),
            make_text('点击继续', root + '/NewBattleResultGradePage(Clone)/bg/'
                'ResultEffect/Tips/dianjijixu/bg20'),
        ]
    handle.buttons['button_count'] = len(handle.buttons['buttons'])
    handle.ui['text_count'] = len(handle.ui['texts'])


def runtime(owned=True):
    handle = FakeRuntimeHandle()
    oracle = SemanticOracle(handle.observer_request, handle.foreground_component,
        handle.tap, OracleFingerprint(package=handle.snapshot['package'],
            component=handle.component, driver_revision=handle.snapshot['driver_revision'],
            expected_pid=handle.pid), sleep=lambda _: None)
    clock = SemanticFrameClock(handle, oracle, monotonic_ns=MutableClock())
    reader = SemanticFrameReader(clock, oracle)
    adapter = AlasSemanticAdapter(oracle, lambda: None,
        frame_observation_oracle=reader.oracle)
    if owned:
        own_auto_search(adapter)
    session = AlasSemanticSession('offline', oracle.fingerprint.driver_revision)
    session.adapter = adapter
    session.open = lambda: adapter
    session._frame_clock = clock
    return handle, clock, adapter, session


@pytest.mark.parametrize('frozen,live', [
    ('combat', 'result'), ('combat-tail', 'result'), ('result', 'combat')])
@pytest.mark.parametrize('name', ['BATTLE_STATUS_S', 'EXP_INFO_S', 'POPUP_CONFIRM'])
def test_campaign_result_probe_does_not_consume_a_later_live_phase(frozen, live, name):
    handle, clock, _adapter, session = runtime()
    phase(handle, frozen, 10)
    clock.acquire(include_ui=True)
    phase(handle, live, 11)
    requests = len(handle.requests)
    assert session.appear(name) is (frozen == 'result' and name == 'BATTLE_STATUS_S')
    assert len(handle.requests) == requests
    assert not handle.taps


def test_original_execute_waits_for_the_result_screenshot_despite_live_phase_drift():
    handle, clock, _adapter, session = runtime()
    passes = []
    loops = []

    def loop():
        loops.append(True)
        phases = [('combat', 'combat')] if len(loops) == 1 else [
            ('combat-tail', 'result'), ('result', 'combat')]
        for index, (frozen, live) in enumerate(phases):
            generation = len(loops) * 100 + index * 10
            phase(handle, frozen, generation)
            clock.acquire(include_ui=True)
            phase(handle, live, generation + 1)
            passes.append(frozen)
            yield None

    host = SimpleNamespace(loop=loop, device=Mock(), emotion=Mock(),
        config=SimpleNamespace(Submarine_Fleet=0, Fleet_Fleet1Mode='combat_auto'),
        is_combat_executing=session.combat_is_executing,
        appear=session.appear, is_in_auto_search_menu=lambda: False,
        _handle_auto_search_menu_missing=lambda: False,
        is_auto_search_running=lambda: False, auto_mode_checked=False)
    for name in ('handle_combat_automation_confirm', 'handle_popup_confirm',
                 'handle_urgent_commission', 'handle_guild_popup_cancel',
                 'handle_story_skip', 'handle_vote_popup', 'handle_submarine_call',
                 'handle_combat_auto', 'handle_combat_manual',
                 'handle_mission_popup_ack', 'handle_get_ship', 'auto_search_combat_end'):
        setattr(host, name, lambda *args: False)
    for name in ('submarine_call_reset', 'combat_auto_reset', 'combat_manual_reset'):
        setattr(host, name, Mock())
    execute = native('AutoSearchCombat', 'auto_search_combat_execute',
        'module/combat/auto_search_combat.py', **{name: name for name in (
            'BATTLE_STATUS_S', 'BATTLE_STATUS_A', 'BATTLE_STATUS_B',
            'EXP_INFO_S', 'EXP_INFO_A', 'EXP_INFO_B')})
    execute(host, emotion_reduce=True, fleet_index=1)
    assert passes == ['combat', 'combat-tail', 'result']
    assert session._combat_result_observation[0] == 'BATTLE_STATUS_S'
    assert not handle.taps


@pytest.mark.parametrize('fresh,live,name,expected', [
    ('combat', 'result', 'BATTLE_STATUS_S', False),
    ('result', 'combat', 'BATTLE_STATUS_S', True),
    ('combat', 'result', 'AUTOMATION_ON', True),
])
def test_unmapped_retry_classifies_the_single_refreshed_frame(fresh, live, name, expected):
    handle, clock, adapter, session = runtime(owned=False)
    phase(handle, 'empty', 10)
    clock.acquire(include_ui=True)
    adapter.appear = Mock(side_effect=AlasSemanticUnmapped('unmounted transition'))
    requests_after_refresh = []

    def refresh():
        phase(handle, fresh, 11)
        frame = clock.acquire(include_ui=True)
        phase(handle, live, 12)
        requests_after_refresh.append(len(handle.requests))
        return frame

    session.refresh_frame = Mock(side_effect=refresh)
    assert session.appear(name) is expected
    session.refresh_frame.assert_called_once()
    assert len(handle.requests) == requests_after_refresh[0]
    assert not handle.taps
