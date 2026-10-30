"""Ordinary Daily start underlay is distinct from foreign blocking modals."""
import copy
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def actual(drift=False):
    return host(drift,'daily-classic-precombat-20261027.json')


@pytest.mark.parametrize('drift',[False,True])
def test_real_precombat_start_accepts_only_ordinary_daily_underlay(drift):
    b,o,a=actual(drift)
    assert o.meta_precombat_fleet_ready()
    receipt=o.click_daily_precombat_start(input_frame=lambda:o)
    assert receipt.path.endswith('/PreCombatUI(Clone)/adapt/right/start')
    assert receipt.semantic_id=='daily/precombat/start'
    assert len(b.taps)==1


@pytest.mark.parametrize('case',['foreign-modal','duplicate-start','false-start','no-start','foreign-package','empty-fleet-at-input'])
def test_start_retains_its_existing_unsafe_input_boundaries(case):
    b,o,a=actual()
    start=next(v for v in b.buttons['buttons'] if v['path'].endswith('/PreCombatUI(Clone)/adapt/right/start'))
    if case=='foreign-modal':b.buttons['buttons'].append(make_button('custom_button_1(Clone)','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif case=='duplicate-start':b.buttons['buttons'].append(copy.deepcopy(start))
    elif case=='false-start':start['raycast_top']=False
    elif case=='no-start':b.buttons['buttons'].remove(start)
    elif case=='foreign-package':b.snapshot['package']='unrelated.package'
    else:o.meta_precombat_fleet_ready=lambda:False
    b.buttons['button_count']=len(b.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):o.click_daily_precombat_start(input_frame=lambda:o)
    assert b.taps==[]


def test_known_underlay_never_grants_a_zero_budget_daily_sortie():
    b,o,a=actual()
    a._daily_kind='advance_mission';a._daily_stage=1
    with pytest.raises(AlasSemanticActionDeferred):a.click_daily_precombat_start()
    assert b.taps==[]
