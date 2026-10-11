from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_snapshot,
)


def setup_entry():
    b = FakeBackend([make_button('transport_button',
        'root/top/adapt/right_stage/btn_list/dock/transport_button', raycast_top=None)])
    o = make_oracle(b)
    o.operation_siren_state = Mock()

    def publish():
        b.snapshot = make_snapshot(generation=12)
        b.buttons = make_buttons(b.buttons['buttons'], generation=12)
        # The native entry now also reads the typed leave prompt before the
        # Globe panel. Publish its UI envelope with the same coherent frame.
        b.ui['generation'] = 12

    b.on_tap = publish
    return b, o


def test_globe_entry_waits_for_complete_panel_after_one_input():
    b, o = setup_entry()
    o.operation_siren_globe_state = Mock(side_effect=[
        SemanticGateClosed('operation siren selected-zone title is absent or ambiguous'),
        object(),
    ])
    assert o.click_operation_siren_globe().semantic_id == 'os/map/globe'
    assert len(b.taps) == 1
    assert o.operation_siren_globe_state.call_count == 2


def test_globe_entry_does_not_repeat_input_when_destination_stays_unknown():
    b, o = setup_entry()
    o.operation_siren_globe_state = Mock(side_effect=SemanticGateClosed('unknown globe'))
    with pytest.raises(SemanticGateClosed, match='unknown globe'):
        o.click_operation_siren_globe()
    assert len(b.taps) == 1
    assert o.operation_siren_globe_state.call_count == 32


def test_globe_entry_requires_a_newer_destination_generation():
    b, o = setup_entry()
    b.on_tap = None
    o.operation_siren_globe_state = Mock(return_value=object())
    with pytest.raises(SemanticGateClosed, match='not newer than input'):
        o.click_operation_siren_globe()
    assert len(b.taps) == 1


def test_globe_entry_rejects_foreground_loss_without_another_input():
    b, o = setup_entry()
    b.on_tap = lambda: setattr(b, 'foreground', 'other/package.Activity')
    o.operation_siren_globe_state = Mock()
    with pytest.raises(SemanticGateClosed, match='activity changed after globe entry'):
        o.click_operation_siren_globe()
    assert len(b.taps) == 1
    o.operation_siren_globe_state.assert_not_called()
