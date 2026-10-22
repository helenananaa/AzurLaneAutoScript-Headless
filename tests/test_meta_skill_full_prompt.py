from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_text, make_ui)

ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
CONTENT = '江风·META的当前研习技能已达满级，是否前往切换研习技能？'


def backend():
    b = FakeBackend([make_button('custom_button_1(Clone)', ROOT+'button_container/custom_button_1(Clone)'),
                     make_button('custom_button_2(Clone)', ROOT+'button_container/custom_button_2(Clone)')])
    b.ui = make_ui([make_text(CONTENT, ROOT+'msg_panel/content'),
                   make_text('确 定', ROOT+'button_container/custom_button_1(Clone)/pic'),
                   make_text('取 消', ROOT+'button_container/custom_button_2(Clone)/pic')])
    def close():
        b.snapshot['generation'] = 11
        b.buttons = make_buttons([], generation=11)
        b.ui['generation'] = 11
    b.on_tap = close
    return b


@pytest.mark.parametrize('confirm', [True, False])
def test_original_generic_handler_uses_exact_skill_full_choice(confirm):
    b = backend(); o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_tactical()
    name = 'POPUP_CONFIRM' if confirm else 'POPUP_CANCEL'
    assert a.appear(SimpleNamespace(name=name))
    assert a.click(SimpleNamespace(name=name)).semantic_id == 'meta/skill-full/' + ('confirm' if confirm else 'cancel')
    assert len(b.taps) == 1


@pytest.mark.parametrize('change', ['purchase', 'other_skill', 'labels', 'duplicate', 'truncated', 'raycast', 'loading', 'foreground'])
def test_unknown_or_obscured_skill_full_prompt_never_grants_input(change):
    b = backend(); o = make_oracle(b)
    if change == 'purchase': b.ui['texts'][0]['text'] = '购买需要花费300钻石，是否确定？'
    elif change == 'other_skill': b.ui['texts'][0]['text'] = CONTENT.replace('已达满级', '尚未满级')
    elif change == 'labels': b.ui['texts'][1]['text'] = '购买'
    elif change == 'duplicate':
        b.ui['texts'].append(dict(b.ui['texts'][0])); b.ui['text_count'] += 1
    elif change == 'truncated': b.ui['texts'][0]['flags'] |= 0x10
    elif change == 'raycast': b.buttons['buttons'][0]['raycast_top'] = False
    elif change == 'loading':
        b.buttons['buttons'].append(make_button('block', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)/block'))
        b.buttons['button_count'] += 1
    else: o._foreground_component = lambda: 'com.android.launcher/.Launcher'
    with pytest.raises(SemanticGateClosed): o.click_meta_skill_full_prompt(True)
    assert not b.taps


def test_unclosed_prompt_has_no_repeat_input():
    b = backend(); b.on_tap = None
    with pytest.raises(SemanticGateClosed, match='did not close'):
        make_oracle(b).click_meta_skill_full_prompt(True)
    assert len(b.taps) == 1


def test_foreign_mounting_dialog_does_not_enter_meta_sandwich():
    b = backend(); b.ui['texts'][0]['text'] = '是否开始战术课程？'
    b.ui['generation'] += 3
    o = make_oracle(b)
    o._msgbox_prompt_parts = lambda *_: pytest.fail('foreign dialog entered META parser')
    assert not o.meta_skill_full_prompt_visible()
    assert not b.taps


def test_inactive_shared_dialog_does_not_read_ui():
    b = backend()
    for button in b.buttons['buttons']:
        button['active_in_hierarchy'] = False
    o = make_oracle(b)
    o.read_ui_state = lambda *_: pytest.fail('inactive modal read UI')
    assert not o.meta_skill_full_prompt_visible()


def tactics_backend():
    root = 'OverlayCamera/Overlay/UIMain/MetaCharacterTacticsUI(Clone)/'
    b = FakeBackend([
        make_button('SkillTpl(Clone)', root+'SkillPanel/Skills/Content/SkillTpl(Clone)'),
        make_button('back', 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back')])
    b.ui = make_ui([make_text('江风·META', root+'NamePanel/NameMask/NameText')])
    return b


def test_original_meta_return_recognizes_tactics_page_in_tactical_context():
    b = tactics_backend(); o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None); a.begin_tactical()
    assert o.meta_character_page_visible()
    assert a.appear(SimpleNamespace(name='META_CHECK'))
    assert a.appear(SimpleNamespace(name='GOTO_MAIN'))
    assert a.click(SimpleNamespace(name='GOTO_MAIN')).semantic_id == 'meta/character/back'
    assert len(b.taps) == 1


@pytest.mark.parametrize('change', ['name', 'coherence', 'raycast', 'blocker'])
def test_tactics_return_rejects_unproven_or_obscured_input(change):
    b = tactics_backend()
    if change == 'name': b.ui['texts'][0]['text'] = ''
    elif change == 'coherence': b.ui['generation'] += 3
    elif change == 'raycast': b.buttons['buttons'][1]['raycast_top'] = False
    else:
        b.buttons['buttons'].append(make_button('block', ROOT+'button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed): make_oracle(b).click_meta_character_back()
    assert not b.taps
