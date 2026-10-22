"""A mounted Meowfficer page owns unrelated reward probes while loading."""
import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


def page(loading=True):
    buttons = [make_button('back_btn',
        'UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/top/back_btn',
        raycast_top=False if loading else True)]
    if loading:
        buttons.append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    backend = FakeBackend(buttons)
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    return backend, adapter


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP',
                                  'POPUP_SINGLE_WHITE', 'PLAYER_CHECK', 'GAME_TIPS',
                                  'DORM_TROPHY_CONFIRM', 'FLEET_CHECK'])
@pytest.mark.parametrize('loading', [False, True])
def test_unrelated_rewards_yield_to_the_known_meow_page(name, loading):
    backend, adapter = page(loading)
    assert adapter.appear(name) is False
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click(name)
    assert not backend.taps


def test_foreign_popup_does_not_inherit_meow_absence_proof():
    backend, adapter = page()
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    assert adapter._appear_priority('GET_ITEMS_1') is UNHANDLED
    assert adapter._appear_priority('POPUP_SINGLE_WHITE') is UNHANDLED
    assert not backend.taps
