from types import SimpleNamespace
import copy
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_text, make_ui)

ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
PAGE = 'root/TaskScene(Clone)/blur_panel/adapt/top/back_btn'


def fixture():
    buttons = [make_button('back_btn', PAGE, raycast_top=False),
               make_button('custom_button_1(Clone)', ROOT+'button_container/custom_button_1(Clone)', 790, 515),
               make_button('custom_button_2(Clone)', ROOT+'button_container/custom_button_2(Clone)', 490, 515)]
    b = FakeBackend(buttons)
    b.ui = make_ui([make_text(t, ROOT+p) for p,t in (
        ('item_panel/Text', '以下奖励因超出上限而<color=#ff5c5c>无法获得</color>，是否仍要领取？'),
        ('button_container/custom_button_1(Clone)/pic', '确 定'),
        ('button_container/custom_button_2(Clone)/pic', '取 消'),
        ('item_panel/scrollview/list/item/IconTpl/name', '特装原型'),
        ('item_panel/scrollview/list/item/IconTpl/icon_bg/count', '<color=#FF5C5CFF>125</color>'))])
    return b,make_oracle(b)


def test_original_popup_confirm_uses_mission_overflow_port():
    b,o=fixture()
    a=AlasSemanticAdapter(o,package_gate=lambda:None)
    a.begin_mission_reward(False,True)
    assert a.appear(SimpleNamespace(name='POPUP_CANCEL'))
    assert a.appear(SimpleNamespace(name='POPUP_CONFIRM'))
    def dismiss():
        b.snapshot['generation']=11
        b.buttons=make_buttons([make_button('back_btn',PAGE)],generation=11)
        b.ui=make_ui([],generation=11)
    b.on_tap=dismiss
    r=a.click(SimpleNamespace(name='POPUP_CONFIRM_MISSION_REWARD'))
    assert r.semantic_id=='task/overflow/confirm'
    assert b.taps==[(790,515)]


@pytest.mark.parametrize('change',['purchase','wrong_label','duplicate','bad_count','covered','other_blocker','no_mission','stale'])
def test_unproven_overflow_never_inputs(change):
    b,o=fixture()
    if change=='purchase': b.ui['texts'][0]['text']='是否花费钻石购买？'
    if change=='wrong_label': b.ui['texts'][1]['text']='购买'
    if change=='duplicate':
        b.ui['texts'].append(copy.deepcopy(b.ui['texts'][0]));b.ui['text_count']+=1
    if change=='bad_count': b.ui['texts'][-1]['text']='unknown'
    if change=='covered': b.buttons['buttons'][1]['raycast_top']=False
    if change=='other_blocker':
        b.buttons['buttons'].append(make_button('block','root/UIOverlay/Loading(Clone)/button'))
        b.buttons['button_count']+=1
    if change=='no_mission':
        b.buttons['buttons']=b.buttons['buttons'][1:];b.buttons['button_count']-=1
    if change=='stale': b.ui['generation']+=3
    with pytest.raises(SemanticGateClosed): o.click_mission_overflow_confirm()
    assert b.taps==[]


def test_unrelated_msgbox_remains_a_negative_probe():
    b,o=fixture();b.ui['texts'][0]['text']='是否花费钻石购买？'
    assert not o.mission_overflow_prompt_visible()
    assert b.taps==[]


def test_reordered_texts_additive_fields_and_equal_items_in_distinct_rows():
    b,o=fixture()
    for t in copy.deepcopy(b.ui['texts'][-2:]):
        t['path']=t['path'].replace('/list/item/', '/list/item(Clone)/')
        b.ui['texts'].append(t)
    b.ui['texts'].append(make_text('new harmless metadata',ROOT+'extra/Text'))
    b.ui['text_count']=len(b.ui['texts'])
    b.ui['texts'].reverse()
    assert o._mission_overflow_prompt()[1] == (('特装原型',125),('特装原型',125))
    assert b.taps==[]


def test_original_info_handler_pair_and_temporary_name():
    import ast
    from pathlib import Path
    source = Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream/module/handler/info_handler.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n,ast.FunctionDef) and n.name=='handle_popup_confirm')
    confirm=SimpleNamespace(name='POPUP_CONFIRM')
    cancel=SimpleNamespace(name='POPUP_CANCEL')
    namespace={'POPUP_CONFIRM':confirm,'POPUP_CANCEL':cancel,'POPUP_CONFIRM_WHITE':SimpleNamespace(name='POPUP_CONFIRM_WHITE')}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),namespace)
    b,o=fixture();a=AlasSemanticAdapter(o,package_gate=lambda:None)
    a.begin_mission_reward(False,True)
    def dismiss():
        b.snapshot['generation']=11
        b.buttons=make_buttons([make_button('back_btn',PAGE)],generation=11)
        b.ui=make_ui([],generation=11)
    b.on_tap=dismiss
    host=SimpleNamespace(_popup_offset=(3,30),device=SimpleNamespace(semantic_adapter=a,click=a.click),
                         appear=lambda button,**kw:a.appear(button))
    assert namespace['handle_popup_confirm'](host,'MISSION_REWARD')
    assert confirm.name=='POPUP_CONFIRM'
    assert b.taps==[(790,515)]
