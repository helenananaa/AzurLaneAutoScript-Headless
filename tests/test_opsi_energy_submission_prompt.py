import copy
from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_text, make_image, make_ui)

ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
PAGE = 'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/back_button'

def fixture():
    buttons = [make_button('back_button', PAGE, raycast_top=False),
               make_button('custom_button_1(Clone)', ROOT+'button_container/custom_button_1(Clone)', 790, 515),
               make_button('custom_button_2(Clone)', ROOT+'button_container/custom_button_2(Clone)', 490, 515),
               make_button('resource', 'LevelCamera/top/adapt/top_stage/resources/WorldResPanel(Clone)/gold', raycast_top=False)]
    b = FakeBackend(buttons)
    b.ui = make_ui([make_text(t, ROOT+p) for p,t in (
        ('item_panel/Text', '是否提交以下物品?'),
        ('button_container/custom_button_1(Clone)/pic', '确 定'),
        ('button_container/custom_button_2(Clone)/pic', '取 消'),
        ('item_panel/scrollview/list/item/IconTpl/icon_bg/count', '1'))],
        images=[make_image(ROOT+'item_panel/scrollview/list/item/IconTpl/icon_bg/icon', 'jingtidianchi')])
    return b, make_oracle(b)

@pytest.mark.parametrize('confirm', [True, False])
def test_native_map_confirmation_uses_exact_energy_item_and_postcondition(confirm):
    b,o = fixture();a=AlasSemanticAdapter(o,package_gate=lambda:None)
    assert a.appear(SimpleNamespace(name='POPUP_CONFIRM'))
    assert a.appear(SimpleNamespace(name='POPUP_CANCEL'))
    assert not a.appear(SimpleNamespace(name='GOTO_MAIN'))
    assert not a.appear(SimpleNamespace(name='OS_CHECK'))
    assert not a.appear(SimpleNamespace(name='LOGIN_GAME_UPDATE_RESTART'))
    assert not a.appear(SimpleNamespace(name='UNRELATED_OPTIONAL_PROMPT'))
    def dismiss():
        b.snapshot['generation']=11
        b.buttons=make_buttons([make_button('back_button',PAGE)],generation=11)
        b.ui=make_ui([],generation=11)
    b.on_tap=dismiss
    receipt=a.click(SimpleNamespace(name='POPUP_CONFIRM' if confirm else 'POPUP_CANCEL'))
    assert receipt.semantic_id=='os/map/energy-submit/'+('confirm' if confirm else 'cancel')
    assert b.taps==[(790 if confirm else 490,515)]

@pytest.mark.parametrize('change',['purchase','wrong_label','duplicate','bad_count','wrong_item','duplicate_item','covered','other_blocker','no_map','stale','truncated'])
def test_unproven_submission_never_inputs(change):
    b,o=fixture()
    if change=='purchase':b.ui['texts'][0]['text']='是否花费钻石购买？'
    if change=='wrong_label':b.ui['texts'][1]['text']='购买'
    if change=='duplicate':
        b.ui['texts'].append(copy.deepcopy(b.ui['texts'][0]));b.ui['text_count']+=1
    if change=='bad_count':b.ui['texts'][-1]['text']='2'
    if change=='wrong_item':b.ui['images'][0]['sprite']='gem'
    if change=='duplicate_item':
        b.ui['images'].append(copy.deepcopy(b.ui['images'][0]));b.ui['image_count']+=1
    if change=='covered':b.buttons['buttons'][1]['raycast_top']=False
    if change=='other_blocker':
        b.buttons['buttons'].append(make_button('block','root/UIOverlay/Loading(Clone)/button'));b.buttons['button_count']+=1
    if change=='no_map':b.buttons['buttons']=b.buttons['buttons'][1:];b.buttons['button_count']-=1
    if change=='stale':b.ui['generation']+=3
    if change=='truncated':b.ui['image_truncated']=True
    with pytest.raises(SemanticGateClosed):o.click_operation_siren_energy_submission(confirm=True)
    assert b.taps==[]

def test_unadvanced_submission_dispatches_only_once():
    b,o=fixture()
    with pytest.raises(SemanticGateClosed):o.click_operation_siren_energy_submission(confirm=True)
    assert b.taps==[(790,515)]

def test_unrelated_popup_keeps_existing_classification():
    b,o=fixture();b.ui['texts'][0]['text']='是否花费钻石购买？'
    assert not o.operation_siren_energy_submission_prompt_visible()
    assert b.taps==[]

def test_same_item_dialog_outside_opsi_stays_unavailable_only_here():
    b,o=fixture()
    b.buttons['buttons']=b.buttons['buttons'][1:]
    b.buttons['button_count']-=1
    assert not o.operation_siren_energy_submission_prompt_visible()
    assert b.taps==[]

def test_generic_update_probe_yields_to_owned_item_panel_without_restart():
    from alas_headless import AlasSemanticSession
    from unittest.mock import Mock
    b,o=fixture();a=AlasSemanticAdapter(o,package_gate=lambda:None)
    a.login_update_restart_prompt_available=Mock(side_effect=AssertionError('not a restart prompt'))
    s=SimpleNamespace(_login_update_restart_performed=False, open=lambda:a)
    assert not AlasSemanticSession.restart_game_after_update(s)
    a.login_update_restart_prompt_available.assert_not_called()
    assert b.taps==[]
