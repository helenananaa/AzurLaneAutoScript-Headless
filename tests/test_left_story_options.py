import copy
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_text, make_image, make_ui)

ROOT='OverlayCamera/Overlay/UIOverlay/NewStoryUI(Clone)'
def fixture():
    buttons=[make_button('NewStoryUI(Clone)',ROOT),make_button('skip_button',ROOT+'/front/btns/btns/skip_button',raycast_top=None)]
    texts=[];images=[]
    for n,label in enumerate(('攻击','耐久','效能','不做选择')):
        path=ROOT+'/front/dialogue/1/options_panel/options_l/option_tpl'+('(Clone)' if n else '')
        bounds={'left':800,'top':160+n*75,'right':1280,'bottom':208+n*75}
        buttons.append(make_button(path.rsplit('/',1)[1],path,1040,184+n*75,bounds,raycast_top=None))
        texts.append(make_text(label,path+'/content/Text',bounds))
        image=make_image(path+'/content','option_bg_left',bounds);image['raycast_target']=True;images.append(image)
    b=FakeBackend(list(reversed(buttons)));b.ui=make_ui(texts,images=images)
    return b,make_oracle(b)

def test_left_clone_choices_preserve_native_top_to_bottom_policy():
    b,o=fixture();assert o.event_story_option_count()==4
    def dismiss():
        b.snapshot['generation']=11;b.buttons=make_buttons([],generation=11);b.ui=make_ui([],generation=11)
    b.on_tap=dismiss
    receipt=o.click_event_story_option(1)
    assert receipt.semantic_id=='story/option/1'
    assert b.taps==[(1040,259)]

@pytest.mark.parametrize('change',['duplicate_button','duplicate_label','unknown_graphic','covered','stale','missing_label','foreign_blocker','unknown_layout'])
def test_left_options_require_complete_unique_current_proof(change):
    b,o=fixture()
    if change=='duplicate_button':b.buttons['buttons'].append(copy.deepcopy(b.buttons['buttons'][0]));b.buttons['button_count']+=1
    if change=='duplicate_label':b.ui['texts'].append(copy.deepcopy(b.ui['texts'][0]));b.ui['text_count']+=1
    if change=='unknown_graphic':b.ui['images'][0]['sprite']='other'
    if change=='covered':b.buttons['buttons'][0]['raycast_top']=False
    if change=='stale':b.ui['generation']+=3
    if change=='missing_label':b.ui['texts']=b.ui['texts'][1:];b.ui['text_count']-=1
    if change=='foreign_blocker':b.buttons['buttons'].append(make_button('block','root/UIOverlay/Loading(Clone)/button'));b.buttons['button_count']+=1
    if change=='unknown_layout':b.buttons['buttons'][0]['path']=b.buttons['buttons'][0]['path'].replace('options_l','options_r')
    with pytest.raises(SemanticGateClosed):o.click_event_story_option(0)
    assert b.taps==[]

def test_left_selection_without_transition_sends_only_one_input():
    b,o=fixture()
    with pytest.raises(SemanticGateClosed):o.click_event_story_option(0)
    assert b.taps==[(1040,184)]
