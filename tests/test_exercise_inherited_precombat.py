import copy
import pytest
from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def preparation_host(drift=False):
    b, o, a = host(drift, 'exercise-inherited-precombat-r141.json')
    # Static subsequent reads of the same tree at the later retained UI turn;
    # original frozen failure state/UI generations remain in the source file.
    b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation']
    return b, o, a


@pytest.mark.parametrize('drift', [False, True])
def test_inherited_precombat_reaches_native_cancel_without_start_authority(drift):
    b, o, a = preparation_host(drift)
    assert o.daily_precombat_visible()
    assert o.exercise_page_visible()
    assert a.appear('EXERCISE_CHECK') is False
    assert a.appear('FLEET_PREPARATION') is True
    assert a.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
    assert a.appear('BATTLE_PREPARATION') is False
    def back():
        b.snapshot['generation'] += 1
        b.buttons['generation'] = b.ui['generation'] = b.snapshot['generation']
        b.buttons['buttons'] = [v for v in b.buttons['buttons'] if 'PreCombatUI(Clone)' not in v['path']]
        b.buttons['button_count'] = len(b.buttons['buttons'])
    b.on_tap = back
    receipt = a.click('MAP_PREPARATION_CANCEL')
    assert receipt.semantic_id == 'daily/precombat/back'
    assert len(b.taps) == 1
    assert not a._exercise_execution_active
    assert not a._exercise_pending


def test_owned_precombat_keeps_native_start_flow():
    b, o, a = preparation_host()
    a._exercise_pending = True
    assert a.appear('BATTLE_PREPARATION') is True
    with pytest.raises(SemanticGateClosed):
        a.click('MAP_PREPARATION_CANCEL')
    assert not b.taps


@pytest.mark.parametrize('case', ['popup', 'duplicate', 'covered', 'stale', 'package', 'outside-screen'])
def test_inherited_cancel_keeps_typed_input_boundary(case):
    b, o, a = preparation_host()
    target = next(v for v in b.buttons['buttons'] if v['path'].endswith('PreCombatUI(Clone)/blur_panel/top/back_btn'))
    if case == 'popup':
        b.buttons['buttons'].append(make_button('confirm', 'root/UIOverlay/Msgbox(Clone)/confirm'))
    elif case == 'duplicate':
        b.buttons['buttons'].append(copy.deepcopy(target))
    elif case == 'covered':
        target['raycast_top'] = False
    elif case == 'stale':
        b.snapshot['age_ms'] = 10001
    elif case == 'package':
        b.snapshot['package'] = 'unrelated.package'
    else:
        target['adb_point']['x'] = -3
        target['adb_bounds']['left'] = -20
        target['adb_bounds']['right'] = 10
    b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        a.click('MAP_PREPARATION_CANCEL')
    assert not b.taps
