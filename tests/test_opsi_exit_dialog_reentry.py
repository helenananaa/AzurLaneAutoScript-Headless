import time

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt, Bounds, Point
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_snapshot, make_buttons, make_text, make_ui,
)


def case(change=None):
    # r170 actual input811 closed the dialog; later827/UI828 still displayed
    # the abyss local-map title. No Main/CampaignMenu/Globe was required for
    # this acknowledgement of the accepted close.
    buttons = [make_button('back_button',
        'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/back_button', raycast_top=None)]
    if change == 'foreign':
        buttons.append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    generation = 811 if change == 'same_generation' else 827
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons(buttons, generation=generation)
    backend.ui = make_ui([make_text('东大陆架A-深渊海域',
        'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/title/name')], generation=generation + 1)
    if change == 'stale':
        backend.snapshot['age_ms'] = 10001
    if change == 'foreground':
        backend.foreground = 'other.package/.Activity'
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    receipt = ActionReceipt('os/exit/confirm', 811, Point(790, 515),
        Bounds(699, 481.333, 881, 548.667),
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')
    adapter._operation_siren_exit_receipt = None if change == 'no_receipt' else receipt
    adapter._operation_siren_entry_transition_until = 0 if change == 'expired' else time.monotonic() + 30
    return backend, adapter, receipt


def test_accepted_exit_dialog_close_yields_to_native_local_map_rediscovery():
    backend, adapter, receipt = case()
    assert adapter.click('POPUP_CONFIRM') is receipt
    assert backend.taps == []
    assert adapter._operation_siren_exit_receipt is None


@pytest.mark.parametrize('change', ['foreign', 'same_generation', 'stale', 'foreground', 'no_receipt', 'expired'])
def test_exit_acknowledgement_does_not_authorize_unsafe_or_unowned_input(change):
    backend, adapter, _ = case(change)
    with pytest.raises(SemanticGateClosed):
        adapter.click('POPUP_CONFIRM')
    assert backend.taps == []
