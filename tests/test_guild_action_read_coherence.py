"""Guild input acquires adjacent state/UI without a redundant foreground ADB trip."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import COMPONENT, make_button


@pytest.mark.parametrize('drift', [False, True])
def test_actual_formation_entry_reads_ui_without_intermediate_foreground_trip(drift):
    backend, oracle, _ = host(drift, 'guild-dispatch-before-formation-r26.json')
    original = oracle.read_ui_state
    reader = Mock(wraps=original)
    oracle.read_ui_state = reader
    receipt = oracle.click('guild/dispatch-detail/formation')
    assert receipt.path.endswith('/GuildMissionInfoPage(Clone)/bottom/formationBtn')
    assert reader.call_args_list[0].kwargs == {'check_foreground': False}
    assert len(backend.taps) == 1
    # Initial state and final dispatch still verify foreground.
    assert backend.foreground_requests >= 2


@pytest.mark.parametrize('case', ['incoherent', 'foreground-at-dispatch', 'ambiguous', 'disabled', 'popup'])
def test_removing_duplicate_read_does_not_relax_input_proof(case):
    backend, oracle, _ = host(fixture='guild-dispatch-before-formation-r26.json')
    button = next(b for b in backend.buttons['buttons'] if b['name'] == 'formationBtn')
    if case == 'incoherent': backend.ui['generation'] += 4
    elif case == 'foreground-at-dispatch':
        oracle._foreground_component = Mock(side_effect=[COMPONENT, 'other/.Activity'])
    elif case == 'ambiguous':
        backend.buttons['buttons'].append(deepcopy(button)); backend.buttons['button_count'] += 1
    elif case == 'disabled': button['interactable'] = False
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed): oracle.click('guild/dispatch-detail/formation')
    assert not backend.taps
