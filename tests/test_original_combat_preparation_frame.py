"""Native preparation observes its screenshot even while live state advances."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import method
from tests.test_combat_screenshot_observation import host, PAUSE
from tests.semantic_support.observer_fixtures import make_button, make_ui


@pytest.mark.parametrize('drift', [False, True])
def test_native_loader_to_pause_uses_frozen_frame_and_no_extra_live_reads(drift):
    backend, session, bridge = host('loading', drift)
    adapter = session.open()
    adapter.begin_meta_beacon()
    live = adapter.oracle
    live.read_state = Mock(side_effect=AssertionError('split native screenshot'))
    live.read_ui_state = Mock(side_effect=AssertionError('split native screenshot UI'))
    observed = []
    def loop():
        # Loading is the current screenshot. The live surface changes before
        # its three passive preparation probes; it belongs to the next scan.
        backend.buttons['buttons'] = [make_button('PauseBtn', PAUSE)]
        backend.buttons['button_count'] = 1
        backend.ui = make_ui([])
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] = 11
        yield
        observed.append(session.combat_is_executing())
        live.read_state.reset_mock(side_effect=True)
        live.read_ui_state.reset_mock(side_effect=True)
        # Restore actual live acquisition only at the next original screenshot.
        del live.read_state
        del live.read_ui_state
        session.refresh_frame()
        # Any additional live read after that acquisition is a regression.
        live.read_state = Mock(side_effect=AssertionError('extra preparation read'))
        live.read_ui_state = Mock(side_effect=AssertionError('extra preparation UI'))
        yield
    false = lambda *a, **k: False
    device = SimpleNamespace(semantic_adapter=session, stuck_record_clear=Mock(),
        click_record_clear=Mock(), screenshot_interval_set=Mock())
    native = SimpleNamespace(device=device, loop=loop,
        handle_combat_automation_confirm=false, appear=false,
        handle_retirement=false, handle_combat_low_emotion=false,
        handle_battle_preparation=false, handle_story_skip=false,
        is_combat_loading=session.combat_is_loading,
        is_combat_executing=lambda: 'PAUSE' if session.combat_is_executing() else False)
    prepare = method('module/combat/combat.py', 'Combat', 'combat_preparation',
        time=time, BATTLE_PREPARATION=object())
    bridge.foreground_component.reset_mock()
    assert prepare(native) is False
    assert observed == [False]
    assert session.combat_is_executing()
    # One real foreground proof belongs to the next screenshot acquisition.
    assert bridge.foreground_component.call_count == 1
    assert not backend.taps and not backend.swipes
