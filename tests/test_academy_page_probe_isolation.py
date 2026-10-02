from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui

def fixture():
    root='UICamera/Canvas/UIMain/NavalAcademyUI/'
    b=FakeBackend([make_button(name,root+path,raycast_top=None) for name,path in (
        ('back','blur_container/adapt/top/title/back'),('supplyShop','academyMap/map/supplyShop'),
        ('tacticRoom','academyMap/map/tacticRoom'),('minigamehall','academyMap/map/minigamehall'))])
    b.ui=make_ui([make_text(label,root+'academyMap/map/'+name+'/name/Text') for name,label in
                 (('supplyShop','补给商店'),('tacticRoom','战术学院'),('minigamehall','游戏屋'))])
    o=make_oracle(b);return b,o,AlasSemanticAdapter(o,lambda:None)

def test_academy_owns_earlier_page_and_pixel_tip_misses():
    b,o,a=fixture()
    assert a.appear(SimpleNamespace(name='ACADEMY_CHECK'))
    for name in ('FLEET_CHECK','GAME_TIPS','GOTO_MAIN','GOTO_MAIN_WHITE'):
        assert not a.appear(SimpleNamespace(name=name))
    with pytest.raises(Exception):a.click(SimpleNamespace(name='GAME_TIPS'))
    assert b.taps==[]

def test_foreign_overlay_does_not_establish_academy_discovery():
    b,o,a=fixture()
    b.buttons['buttons'].append(make_button('block','root/UIOverlay/Loading(Clone)/button'));b.buttons['button_count']+=1
    assert not a.appear(SimpleNamespace(name='ACADEMY_CHECK'))
    assert b.taps==[]
