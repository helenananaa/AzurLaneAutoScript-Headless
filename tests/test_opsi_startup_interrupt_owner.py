"""Native interrupt can recover an inherited fight with a bounded startup owner."""
import time
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button, FakeBackend, make_oracle, make_ui, make_text


@pytest.mark.parametrize('case', ['ready', 'drift', 'no-owner', 'expired', 'loading', 'foreign', 'disappeared'])
def test_native_startup_interrupt_uses_actual_pause_and_fresh_final_input(case):
    backend,oracle,adapter=host(case=='drift',fixture='opsi-inherited-combat-pause-r99.json')
    adapter._operation_siren_startup_search_provisional=case!='no-owner'
    adapter._operation_siren_entry_transition_until=time.monotonic()+30 if case!='expired' else 0
    session=AlasSemanticSession.__new__(AlasSemanticSession);session.open=lambda:adapter
    if case=='loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)','OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count']+=1
    if case=='foreign':backend.foreground='other/.Activity'
    def fresh():
        if case=='disappeared':
            backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if not b['path'].endswith('/PauseBtn')]
            backend.buttons['button_count']=len(backend.buttons['buttons'])
        return oracle
    adapter._fresh_input_oracle=Mock(side_effect=fresh)
    if case in ('ready','drift'):
        assert session.handle_operation_siren_combat_interrupt() is True
        assert len(backend.taps)==1
        assert session._operation_siren_interrupt_receipts[-1].semantic_id=='combat/pause'
        adapter._fresh_input_oracle.assert_called_once()
    elif case in ('no-owner','expired','disappeared'):
        assert session.handle_operation_siren_combat_interrupt() is False
        assert not backend.taps
    else:
        with pytest.raises(SemanticGateClosed):session.handle_operation_siren_combat_interrupt()
        assert not backend.taps


@pytest.mark.parametrize('step', ['leave', 'confirm'])
@pytest.mark.parametrize('blocker', ['loading', 'foreign'])
def test_existing_leave_confirmation_ports_reject_covered_or_foreign_input(step,blocker):
    pause=make_button('PauseBtn','UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn',raycast_top=None)
    root='root/OverlayCamera/Overlay/UIMain/'
    records=[pause]
    if step=='leave':
        records.append(make_button('leave',root+'Msgbox/window/button_container/leave',raycast_top=None))
    else:
        records.extend([make_button('custom_button_3(Clone)',root+'Msgbox(Clone)/window/button_container/custom_button_3(Clone)',raycast_top=None),
                        make_button('custom_button_1(Clone)',root+'Msgbox(Clone)/window/button_container/custom_button_1(Clone)')])
    backend=FakeBackend(records)
    backend.ui=make_ui([make_text('confirm quit',root+'Msgbox(Clone)/window/msg_panel/content')])
    if blocker=='loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)','OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count']+=1
    else:backend.foreground='other/.Activity'
    oracle=make_oracle(backend)
    with pytest.raises(SemanticGateClosed):
        (oracle.click_exercise_combat_leave if step=='leave' else oracle.click_exercise_combat_quit_confirm)()
    assert not backend.taps


def test_accepted_interrupt_waits_for_each_next_surface_instead_of_repeating_pause_or_leave():
    backend,oracle,adapter=host(fixture='opsi-inherited-combat-pause-r99.json')
    adapter._operation_siren_startup_search_provisional=True
    adapter._operation_siren_entry_transition_until=time.monotonic()+30
    adapter._fresh_input_oracle=lambda:oracle
    session=AlasSemanticSession.__new__(AlasSemanticSession);session.open=lambda:adapter
    assert session.handle_operation_siren_combat_interrupt()
    assert session.handle_operation_siren_combat_interrupt() is False
    assert len(backend.taps)==1
    backend.buttons['buttons'].append(make_button('leave','OverlayCamera/Overlay/UIMain/Msgbox/window/button_container/leave',raycast_top=None))
    backend.buttons['button_count']+=1
    assert session.handle_operation_siren_combat_interrupt()
    assert session.handle_operation_siren_combat_interrupt() is False
    backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if b['name']!='leave']
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    assert session.handle_operation_siren_combat_interrupt() is False
    assert len(backend.taps)==2
