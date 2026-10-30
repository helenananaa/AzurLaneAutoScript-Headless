"""Real retained selected-page identity must survive the empty-tip transition."""
import copy
import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.old_retirement_dialog import prepare_old_retirement_alias_target
from tests.semantic_support.old_retirement import build_old_frame_rig


def selected_rig():
    raw = json.loads((Path(__file__).parent / 'fixtures/retirement-manual-selected-phase-20261026.json').read_text(encoding='utf-8'))
    rig = build_old_frame_rig()
    rig.handle.snapshot = copy.deepcopy(raw['snapshot'])
    rig.handle.buttons = copy.deepcopy(raw['buttons'])
    rig.handle.ui = copy.deepcopy(raw['ui'])
    return rig


def test_real_selected_page_has_count_one_and_no_empty_instruction():
    rig = selected_rig()
    state = rig.oracle.retirement_selection_state()
    assert state.selected_count == 1
    assert (state.capacity_used, state.capacity_total) == (866, 1010)
    assert rig.oracle.retirement_selection_visible()
    assert rig.oracle._retirement_screen_kind() == 'selection'
    assert not rig.handle.taps


def test_native_confirmation_uses_its_own_label_after_empty_tip_disappears():
    rig = selected_rig()
    target = prepare_old_retirement_alias_target(
        rig.oracle, 'SHIP_CONFIRM', selected_count=1, allowed_rarities={'N','R'})
    assert target.semantic_id == 'retirement/preconfirm/open'
    assert target.identity_text_suffix.endswith('/confirm_button/confirm')
    assert target.identity_text == '确 定'
    assert not rig.handle.taps


@pytest.mark.parametrize('damage', ['empty-count', 'missing-header', 'wrong-purpose'])
def test_missing_tip_does_not_turn_an_unproven_page_into_retirement(damage):
    rig = selected_rig()
    texts = rig.handle.ui['texts']
    if damage == 'empty-count':
        next(t for t in texts if t['path'].endswith('/bottom_info/bg_input/count'))['text'] = '0'
    elif damage == 'missing-header':
        texts[:] = [t for t in texts if not t['path'].endswith('/bottom_info/bg_input/Tselected')]
    else:
        # Another active instruction must not be ignored because count>0.
        source = next(t for t in texts if t['path'].endswith('/bottom_info/bg_input/selected'))
        foreign = copy.deepcopy(source)
        foreign.update(path='OverlayCamera/Overlay/UIMain/blur_panel/select_panel/tip',text='请选择用于强化的角色')
        texts.append(foreign)
    with pytest.raises(SemanticGateClosed):
        rig.oracle.retirement_selection_state()
    assert not rig.handle.taps
