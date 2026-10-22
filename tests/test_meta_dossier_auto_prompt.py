from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_image, make_oracle, make_text, make_ui)

ROOT = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/'
DETAIL = ROOT+'pages/ArchivesWorldBossDetailUI(Clone)/'
PROMPT = ROOT+'ArchivesWorldBossAutoBattleTipUI(Clone)/window/'


def backend():
    b = FakeBackend([make_button('list_btn', DETAIL+'list_btn'),
                     make_button('auto_btn', DETAIL+'btns/auto_btn', raycast_top=None),
                     make_button('start', PROMPT+'btns/start', raycast_top=None)])
    b.ui = make_ui([make_text(t, DETAIL+p) for p, t in (
        ('progress/value', '160/1400'), ('hp/Text', '1247166/1600000'), ('hp/level/Text', '15'))]
        +[make_text(t, PROMPT+p) for p, t in (
            ('top/title', '自动作战'), ('btns/start/pic', '开始'),
            ('msg_panel/time/Text', '15MIN'), ('msg_panel/oil/Text', '90'),
            ('msg_panel/battle_cnt/Text', '4'), ('msg_panel/highest_damage/Text', '352834'))],
        images=[make_image(DETAIL+'btns/auto_btn', 'auto_01'),
                make_image(PROMPT+'btns/start', 'btn_big_red')])
    return b


def test_prompt_original_auto_branch_and_confirm_single_input():
    b = backend()
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    assert o.meta_dossier_auto_prompt() == dict(minutes=15, oil=90, battle_count=4, highest_damage=352834)
    assert a.appear(SimpleNamespace(name='META_AUTO_ATTACK_START'))
    assert a.appear(SimpleNamespace(name='META_AUTO_ATTACK_CONFIRM'))
    assert not a.appear(SimpleNamespace(name='META_AUTO_ATTACKING'))
    assert a.appear(SimpleNamespace(name='HELP_ENTER'))
    assert not a.appear(SimpleNamespace(name='BEACON_REWARD'))
    with pytest.raises(SemanticGateClosed, match='obscured'):
        o.click_meta_dossier_auto_start()
    assert not b.taps
    def activate():
        b.snapshot['generation'] = 11
        b.buttons = make_buttons(b.buttons['buttons'][:2], generation=11)
        b.ui['generation'] = 11
        b.ui['images'][0]['sprite'] = 'auto_02'
        b.ui['texts'].append(make_text('00:14:59', DETAIL+'btns/auto_btn/Text'))
        b.ui['text_count'] += 1
    b.on_tap = activate
    assert a.click(SimpleNamespace(name='META_AUTO_ATTACK_CONFIRM')).semantic_id == 'meta/dossier/auto/confirm'
    assert len(b.taps) == 1
    assert o.meta_dossier_auto_remaining_seconds() == 899
    assert a.appear(SimpleNamespace(name='META_AUTO_ATTACKING'))
    assert not a.appear(SimpleNamespace(name='META_AUTO_ATTACK_START'))


@pytest.mark.parametrize('timer', ['00:60:00', 'unknown', ''])
def test_auto_sprite_alone_does_not_prove_running(timer):
    b = backend()
    b.buttons = make_buttons(b.buttons['buttons'][:2])
    b.ui['images'][0]['sprite'] = 'auto_02'
    b.ui['texts'].append(make_text(timer, DETAIL+'btns/auto_btn/Text'))
    b.ui['text_count'] += 1
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='countdown'):
        o.meta_dossier_auto_remaining_seconds()
    assert not b.taps


@pytest.mark.parametrize('change', ['title', 'cost', 'duplicate', 'sprite', 'covered', 'foreground', 'generation'])
def test_unproved_prompt_never_confirms(change):
    b = backend()
    if change == 'title': b.ui['texts'][3]['text'] = '购买'
    if change == 'cost': b.ui['texts'][6]['text'] = '钻石90'
    if change == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][2]))
        b.buttons['button_count'] += 1
    if change == 'sprite': b.ui['images'][1]['sprite'] = 'unknown'
    if change == 'covered': b.buttons['buttons'][2]['raycast_top'] = False
    if change == 'generation': b.ui['generation'] += 3
    o = make_oracle(b)
    o._sleep = lambda _: None
    if change == 'foreground': o._foreground_component = lambda: 'other/activity'
    with pytest.raises(SemanticGateClosed): o.click_meta_dossier_auto_confirm()
    assert not b.taps
