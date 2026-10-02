import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_text, make_ui

ROOT='UICamera/Canvas/UIMain/MilitaryExerciseUI(Clone)/'

def backend():
    b=FakeBackend([
        make_button('backBtn', ROOT+'blur_panel/adapt/top/backBtn', raycast_top=None),
        make_button('option', ROOT+'blur_panel/adapt/top/option', raycast_top=None),
        *[make_button(f'rivaltpl_{i}', ROOT+f'center/rival_list/rivaltpl_{i}', raycast_top=None) for i in range(1,5)],
    ])
    b.ui=make_ui([make_text('0/10',ROOT+'center/season_info/count')],
                 images=[make_image(ROOT+'blur_panel/adapt/top/option','viewall_1920')])
    b.ui['images'][0]['raycast_target']=True
    return b

@pytest.mark.parametrize('raycast_top', [None, True])
def test_exercise_home_uses_option_instead_of_stack_back(raycast_top):
    b=backend();o=make_oracle(b)
    b.buttons['buttons'][1]['raycast_top'] = raycast_top
    receipt=o.click_exercise_home()
    assert receipt.semantic_id=='exercise/page/home'
    assert receipt.path.endswith('/top/option')
    assert len(b.taps)==1

def test_exercise_home_rejects_foreground_change_before_input():
    b=backend();o=make_oracle(b)
    original=o.read_ui_state
    calls=0
    def read_ui():
        nonlocal calls
        result=original()
        calls+=1
        if calls==2:o._foreground_component=lambda:'com.android.launcher/.Launcher'
        return result
    o.read_ui_state=read_ui
    with pytest.raises(SemanticGateClosed, match='foreground changed'):
        o.click_exercise_home()
    assert b.taps==[]

@pytest.mark.parametrize('change',['duplicate','sprite','raycast','blocker','coherence'])
def test_exercise_home_rejects_unknown_or_obscured_state(change):
    b=backend()
    if change=='duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][1]))
        b.buttons['button_count']+=1
    elif change=='sprite':b.ui['images'][0]['sprite']='unknown'
    elif change=='raycast':b.buttons['buttons'][1]['raycast_top']=False
    elif change=='blocker':
        b.buttons['buttons'].append(make_button('confirm','root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count']+=1
    else:b.ui['generation']=b.buttons['generation']+3
    with pytest.raises(SemanticGateClosed):make_oracle(b).click_exercise_home()
    assert b.taps==[]
