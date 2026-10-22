from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_image, make_oracle, make_text, make_ui)

ROOT = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/'
DETAIL = ROOT+'pages/ArchivesWorldBossDetailUI(Clone)/'
RESULT = ROOT+'ArchivesWorldBossAutoBattleResultUI(Clone)/window/'


def backend():
    b = FakeBackend([make_button('list_btn', DETAIL+'list_btn'),
                     make_button('award_btn', DETAIL+'btns/award_btn', raycast_top=None),
                     make_button('start', RESULT+'btns/start', raycast_top=None)])
    b.ui = make_ui([make_text(t, DETAIL+p) for p, t in (
        ('progress/value', '160/1400'), ('hp/Text', '0/1600000'), ('hp/level/Text', '15'))]
        +[make_text(t, RESULT+p) for p, t in (
            ('top/title', '自动作战'), ('btns/start/pic', '确 定'),
            ('msg_panel/label', '自动作战完成'), ('msg_panel/oil/Text', '90'),
            ('msg_panel/battle_cnt/Text', '4'), ('msg_panel/damage/Text', '1247166'))],
        images=[make_image(DETAIL+'btns/award_btn', 'btn_get'),
                make_image(RESULT+'btns/start', 'btn_big_red')])
    return b


def test_native_result_then_completed_dossier_reward_without_auto_control():
    b = backend()
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    assert o.meta_dossier_auto_result() == dict(oil=90, battle_count=4, damage=1247166)
    assert a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
    for name in ('ASH_SHOWDOWN', 'BEACON_LIST', 'DOSSIER_LIST', 'HELP_ENTER',
                 'BEACON_REWARD', 'META_AUTO_ATTACK_START', 'META_AUTO_ATTACKING',
                 'META_AUTO_ATTACK_CONFIRM'):
        assert not a.appear(SimpleNamespace(name=name))
    with pytest.raises(SemanticGateClosed, match='obscured'):
        o.click_meta_dossier_reward()
    assert not b.taps
    def close_result():
        b.snapshot['generation'] = 11
        b.buttons = make_buttons(b.buttons['buttons'][:2], generation=11)
        b.ui['generation'] = 11
    b.on_tap = close_result
    assert a.click(SimpleNamespace(name='META_AUTO_CONFIRM')).semantic_id == 'meta/dossier/auto/result/confirm'
    assert o.meta_dossier_detail_state().auto_sprite is None
    assert a.appear(SimpleNamespace(name='BEACON_REWARD'))
    for name in ('META_AUTO_ATTACK_START', 'META_AUTO_ATTACKING', 'META_AUTO_ATTACK_CONFIRM'):
        assert not a.appear(SimpleNamespace(name=name))
    def claim_reward():
        b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 12
    b.on_tap = claim_reward
    o.award_info_page_visible = lambda: True
    assert a.click(SimpleNamespace(name='BEACON_REWARD')).semantic_id == 'meta/dossier/reward'
    assert len(b.taps) == 2


def test_unknown_auto_result_hides_underlay_but_never_allows_confirmation():
    b = backend()
    b.ui['texts'][3]['text'] = '其他'
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_meta_beacon()
    assert not a.appear(SimpleNamespace(name='DOSSIER_LIST'))
    with pytest.raises(SemanticGateClosed, match='identity'):
        a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
    assert b.taps == []


@pytest.mark.parametrize('valid', [True, False])
def test_assist_reuses_original_completed_dossier_result_handler(valid):
    b = backend()
    if not valid:
        b.ui['texts'][3]['text'] = '其他'
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_meta_assist()
    assert not a.appear(SimpleNamespace(name='DOSSIER_LIST'))
    if not valid:
        with pytest.raises(SemanticGateClosed, match='identity'):
            a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
        assert not b.taps
        return
    assert a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
    def close_result():
        b.snapshot['generation'] = 11
        b.buttons = make_buttons(b.buttons['buttons'][:2], generation=11)
        b.ui['generation'] = 11
    b.on_tap = close_result
    assert a.click(SimpleNamespace(name='META_AUTO_CONFIRM')).semantic_id == 'meta/dossier/auto/result/confirm'
    assert len(b.taps) == 1
    assert a.appear(SimpleNamespace(name='DOSSIER_LIST'))


def test_result_root_mount_hides_detail_until_confirm_child_is_published():
    b = backend()
    b.buttons = make_buttons(b.buttons['buttons'][:2] + [
        make_button('ArchivesWorldBossAutoBattleResultUI(Clone)',
                    ROOT+'ArchivesWorldBossAutoBattleResultUI(Clone)')])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_meta_beacon()
    for name in ('ASH_SHOWDOWN', 'DOSSIER_LIST', 'HELP_ENTER', 'BEACON_REWARD',
                 'META_AUTO_ATTACK_START', 'META_AUTO_ATTACKING'):
        assert not a.appear(SimpleNamespace(name=name))
    assert not a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
    assert b.taps == []


@pytest.mark.parametrize('name', ['ASH_SHOWDOWN', 'BEACON_LIST', 'DOSSIER_LIST',
                                  'HELP_ENTER', 'BEACON_REWARD', 'META_AUTO_CONFIRM',
                                  'META_AUTO_ATTACK_START', 'META_AUTO_ATTACKING'])
def test_pure_loading_curtain_waits_for_next_original_meta_frame(name):
    b = backend()
    b.buttons = make_buttons(b.buttons['buttons'][:2] + [
        make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_meta_beacon()
    assert not a.appear(SimpleNamespace(name=name))
    assert b.taps == []


def test_loading_with_foreign_popup_does_not_hide_unproven_meta_detail():
    b = backend()
    b.buttons = make_buttons(b.buttons['buttons'][:2] + [
        make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'),
        make_button('custom_button_1(Clone)', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    a.begin_meta_beacon()
    with pytest.raises(SemanticGateClosed, match='obscured'):
        a.appear(SimpleNamespace(name='HELP_ENTER'))
    assert b.taps == []


@pytest.mark.parametrize('change', ['title', 'damage', 'hp', 'reward_sprite', 'duplicate', 'raycast', 'foreground', 'generation'])
def test_unproven_result_is_never_dismissed(change):
    b = backend()
    if change == 'title': b.ui['texts'][3]['text'] = '其他'
    if change == 'damage': b.ui['texts'][-1]['text'] = '-1'
    if change == 'hp': b.ui['texts'][1]['text'] = '1/1600000'
    if change == 'reward_sprite': b.ui['images'][0]['sprite'] = 'unknown'
    if change == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][-1]))
        b.buttons['button_count'] += 1
    if change == 'raycast': b.buttons['buttons'][-1]['raycast_top'] = False
    if change == 'generation': b.ui['generation'] += 3
    o = make_oracle(b)
    o._sleep = lambda _: None
    if change == 'foreground': o._foreground_component = lambda: 'other/activity'
    with pytest.raises(SemanticGateClosed): o.click_meta_dossier_auto_result_confirm()
    assert not b.taps
