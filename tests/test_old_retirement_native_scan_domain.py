"""Typed card observation must preserve the original caller's scan count."""
import copy
import json
import pytest
from pathlib import Path

from alas_headless.oracle.old_retirement import read_old_retirement_cards
from tests.semantic_support.old_retirement import build_old_frame_rig


def rig_with_full_retained_dock():
    rig = build_old_frame_rig()
    raw = json.loads((Path(__file__).parent / 'fixtures/old-retirement-scan-domain-20261026.json').read_text(encoding='utf-8'))
    rig.handle.snapshot = copy.deepcopy(raw['selection_state']['snapshot'])
    rig.handle.buttons = copy.deepcopy(raw['selection_state']['buttons_snapshot'])
    rig.handle.ui = copy.deepcopy(raw['selection_ui']['snapshot'])
    return rig


def observe(rig, count):
    rig.delegate.refresh_frame()
    return read_old_retirement_cards(rig.adapter._require_frame_observation_oracle(), card_limit=count)[2]


def test_native_fourteen_slots_do_not_expand_to_twenty_one_visible_cards():
    rig = rig_with_full_retained_dock()
    all_cards = observe(rig, None)
    native_cards = observe(rig, 14)
    assert len(all_cards) == 21
    assert len(native_cards) == 14
    assert [card.instance_id for card in native_cards] == [card.instance_id for card in all_cards[:14]]
    assert not rig.handle.taps


@pytest.mark.parametrize("disabled_field", ["interactable", "active_and_enabled"])
def test_disabled_native_slot_cannot_pull_third_row_into_the_native_scan(disabled_field):
    rig = rig_with_full_retained_dock()
    original = observe(rig, 14)
    disabled = original[0].instance_id
    for button in rig.handle.buttons['buttons']:
        if button.get('instance_id') == disabled:
            button[disabled_field] = False
    for value in (rig.handle.snapshot, rig.handle.buttons, rig.handle.ui):
        value['generation'] += 1
    after = observe(rig, 14)
    assert len(after) == 13
    assert {card.instance_id for card in after} == {card.instance_id for card in original} - {disabled}
    assert not rig.handle.taps


def test_compatible_larger_native_scan_can_use_its_declared_visible_slots():
    rig = rig_with_full_retained_dock()
    # The limit comes from ALAS's ButtonGrid shape, not an adapter allowlist.
    cards = observe(rig, 21)
    assert len(cards) == 21
    assert not rig.handle.taps
