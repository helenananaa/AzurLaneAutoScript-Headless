"""Actual ordinary Daily retains its own selector behind PreCombatUI."""
import copy
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def actual():
    b,o,_=host(False,'daily-classic-precombat-20261027.json')
    return b,o


def test_original_precombat_back_allows_exact_daily_underlay():
    b,o=actual()
    receipt=o.click_daily_precombat_back()
    assert receipt.semantic_id=='daily/precombat/back'
    assert receipt.path.endswith('/PreCombatUI(Clone)/blur_panel/top/back_btn')
    assert len(b.taps)==1


@pytest.mark.parametrize('case',['foreign-modal','duplicate-back','missing-precombat','false-back','outside-back'])
def test_underlay_return_never_bypasses_unknown_or_nonactionable_target(case):
    b,o=actual()
    back=next(v for v in b.buttons['buttons'] if v['path'].endswith('/PreCombatUI(Clone)/blur_panel/top/back_btn'))
    if case=='foreign-modal':b.buttons['buttons'].append(make_button('custom_button_1(Clone)','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif case=='duplicate-back':b.buttons['buttons'].append(copy.deepcopy(back))
    elif case=='missing-precombat':b.buttons['buttons']=[v for v in b.buttons['buttons'] if not v['path'].endswith('/PreCombatUI(Clone)/adapt/right/start')]
    elif case=='false-back':back['raycast_top']=False
    else:
        back['adb_point']['x']=-100
    b.buttons['button_count']=len(b.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):o.click_daily_precombat_back()
    assert b.taps==[]


def test_return_support_never_grants_an_adapter_sortie_without_daily_intent():
    b,o,a=host(False,'daily-classic-precombat-20261027.json')
    with pytest.raises(SemanticGateClosed,match='intent is incomplete'):a.click_daily_precombat_start()
    assert b.taps==[]
