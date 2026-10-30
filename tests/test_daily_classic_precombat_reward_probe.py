"""Daily transition recovery reclassifies one existing refreshed screenshot."""
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.test_presence_driven_reward_refresh import session_for
from tests.semantic_support.observer_fixtures import make_button


def actual(drift=False):
    b,o,_=host(drift,'daily-classic-precombat-20261027.json')
    s,a=session_for(o)
    a._minigame_context=None
    a._daily_kind='advance_mission'; a._daily_stage=1
    original=a.appear
    first=True
    def preceding_transition(button):
        nonlocal first
        if first:
            first=False
            raise AlasSemanticUnmapped('preceding transition has no owned surface')
        return original(button)
    a.appear=Mock(side_effect=preceding_transition)
    return b,o,s,a


@pytest.mark.parametrize('drift',[False,True])
@pytest.mark.parametrize('name',['GET_ITEMS_1','GET_ITEMS_2','GET_ITEMS_3'])
def test_existing_refresh_reclassifies_proven_daily_precombat(drift,name):
    b,o,s,a=actual(drift)
    assert o.daily_precombat_visible()
    assert s.appear(name) is False
    assert s.refresh_frame.call_count==1
    assert a.appear.call_count==2
    assert b.taps==[]


@pytest.mark.parametrize('case',['unowned','foreign-modal','unknown-page'])
def test_unproven_refreshed_owner_keeps_original_error(case):
    b,o,s,a=actual()
    if case=='unowned': a._daily_kind=None
    elif case=='foreign-modal':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count']=len(b.buttons['buttons'])
    else:
        b.buttons['buttons']=[v for v in b.buttons['buttons'] if '/PreCombatUI(Clone)/' not in v['path'] and '/DailyLevelUI(Clone)/' not in v['path']]
        b.buttons['button_count']=len(b.buttons['buttons'])
    with pytest.raises(AlasSemanticUnmapped,match='preceding transition'):
        s.appear('GET_ITEMS_1')
    assert s.refresh_frame.call_count==1
    assert b.taps==[]
