from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.oracle.private_quarters import ROOT
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_text, make_ui, make_oracle, make_image


def backend(count='3/3', raycast=True):
    b = FakeBackend([make_button('btn_back', ROOT+'Main/btn_back'),
                     make_button('home', ROOT+'Main/option/home', raycast_top=raycast)])
    b.ui = make_ui([make_text(count, ROOT+'Main/stamina/Text'),
                   make_text('PRIVATE QUARTERS', ROOT+'Main/title/Text/en'),
                   make_text('locale with additive content', ROOT+'Main/btn_switch/switch/currentName')])
    return b


def test_live_area_overlay_wins_over_the_main_underlay():
    b = FakeBackend([make_button('MainLiveAreaUI(Clone)', 'OverlayCamera/Overlay/UIMain/MainLiveAreaUI(Clone)', raycast_top=None)])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='DORMMENU_CHECK'))
    assert not a.appear(SimpleNamespace(name='MAIN_GOTO_CAMPAIGN'))


def test_repeated_live_entry_reuses_only_a_real_receipt_at_its_destination():
    from tests.semantic_support.adapter_fixtures import FakeOracle
    o = FakeOracle()
    o.observation_target_present = lambda target: target == 'dorm-menu/dorm'
    o.enabled = lambda target: True
    o.read_state = lambda: SimpleNamespace(generation=11)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    prior = SimpleNamespace(generation=10)
    a._main_live_entry_receipt = prior
    assert a._click_mapped('MAIN_GOTO_DORMMENU', 'main/live') is prior
    assert o.click_calls == []
    a.reset_task_state()
    assert a._main_live_entry_receipt is None


@pytest.mark.parametrize('count,remaining', [('3/3',3),('0/3',0),('2/5',2)])
def test_real_counter_and_capacity_are_preserved(count, remaining):
    b = backend(count)
    b.ui['texts'].append(make_text('new field', ROOT+'Main/new/text'))
    b.ui['text_count'] += 1
    o = make_oracle(b)
    assert o.private_quarters_overview().remaining == remaining
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='PRIVATE_QUARTERS_CHECK'))
    assert not a.appear(SimpleNamespace(name='FLEET_CHECK'))


@pytest.mark.parametrize('count', ['', '0/0', '4/3', '3', 'unknown'])
def test_unknown_count_is_not_zero(count):
    b = backend(count)
    with pytest.raises(SemanticGateClosed, match='malformed'):
        make_oracle(b).private_quarters_overview()
    assert b.taps == []


@pytest.mark.parametrize('raycast', [False, None])
def test_home_does_not_accept_unknown_or_blocked_hit(raycast):
    b = backend(raycast=raycast)
    with pytest.raises(SemanticGateClosed, match='actionable'):
        make_oracle(b).click_private_quarters_home()
    assert b.taps == []


def test_home_uses_reviewed_target_and_other_popup_blocks_it():
    b = backend()
    assert make_oracle(b).click_private_quarters_home().semantic_id == 'private-quarters/home'
    assert len(b.taps) == 1
    b.buttons['buttons'].append(make_button('confirm','root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='actionable'):
        make_oracle(b).click_private_quarters_home()
    assert len(b.taps) == 1


def test_counter_drift_does_not_disable_independent_home_navigation():
    b = backend('unknown')
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='malformed'):
        o.private_quarters_overview()
    assert o.click_private_quarters_home().semantic_id == 'private-quarters/home'


@pytest.mark.parametrize('mode', ['base', 'watch', 'ik'])
@pytest.mark.parametrize('hit', [True, False, None])
def test_room_back_alias_requires_exact_hit(hit, mode):
    path = f'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/{mode}/btn_back'
    b = FakeBackend([make_button('btn_back', path, raycast_top=hit)])
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None)
    if hit:
        assert a.appear(SimpleNamespace(name='PRIVATE_QUARTERS_ROOM_CHECK'))
        assert a.click(SimpleNamespace(name='PRIVATE_QUARTERS_ROOM_BACK')).path == path
    else:
        with pytest.raises(SemanticGateClosed):
            a.click(SimpleNamespace(name='PRIVATE_QUARTERS_ROOM_BACK'))
        assert b.taps == []


@pytest.mark.parametrize('locked', [True, False])
def test_room_requires_positive_unlock_state(locked):
    b = backend()
    path = ROOT+'Map/floor_2/Xinzexi'
    b.buttons['buttons'].append(make_button('Xinzexi', path))
    b.buttons['button_count'] += 1
    b.ui['images'] = [make_image(path+'/icon', 'room_icon_xinzexi')]
    if locked:
        b.ui['images'].append(make_image(path+'/front/lock/Image', 'state_lock'))
    else:
        b.ui['texts'].append(make_text('2', path+'/front/complete/favor/Text'))
        b.ui['text_count'] += 1
    b.ui['image_count'] = len(b.ui['images'])
    o = make_oracle(b)
    assert o.private_quarters_new_jersey_unlocked() is (not locked)
    if locked:
        with pytest.raises(SemanticGateClosed, match='locked'):
            o.click_private_quarters_new_jersey()
        assert b.taps == []
    else:
        assert o.click_private_quarters_new_jersey().path == path


@pytest.mark.parametrize('speaker,choice,allowed', [('新泽西',False,True),('其他角色',False,False),('新泽西',True,False)])
def test_dialogue_requires_reviewed_speaker_and_no_choices(speaker, choice, allowed):
    path = 'OverlayCamera/Overlay/UIOverlay/NewStoryUI(Clone)'
    b = FakeBackend([make_button('NewStoryUI(Clone)', path)])
    b.ui = make_ui([make_text(speaker,path+'/front/dialogue/2/content/name/Text'),
                   make_text('A greeting',path+'/front/dialogue/2/content')])
    if choice:
        b.buttons['buttons'].append(make_button('option', path+'/front/options/1'))
        b.buttons['button_count'] += 1
    if allowed:
        assert make_oracle(b).click_private_quarters_new_jersey_dialogue().semantic_id == 'private-quarters/dialogue/continue'
        assert len(b.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            make_oracle(b).click_private_quarters_new_jersey_dialogue()
        with pytest.raises(SemanticGateClosed):
            make_oracle(b).click('private-quarters/dialogue/continue')
        assert b.taps == []


def test_ik_check_requires_both_controls_and_preserves_unrelated_navigation():
    root = 'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/ik/'
    b = FakeBackend([make_button('btn_back', root+'btn_back'),
                     make_button('btn_camera', root+'Right/btn_camera')])
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a.appear(SimpleNamespace(name='PRIVATE_QUARTERS_INTERACT_CHECK'))
    b.buttons['buttons'].pop()
    b.buttons['button_count'] -= 1
    with pytest.raises(SemanticGateClosed, match='incomplete'):
        o.private_quarters_interact_check_visible()
    assert o.click_private_quarters_room_back().path == root+'btn_back'


def test_touch_identity_drift_rejects_input():
    root = 'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/watch/Role/Touch/tpl'
    b = FakeBackend([make_button('tpl', root)])
    b.ui = make_ui([make_text('触摸（日光棉岛）',root+'/bg/Text')],
                   images=[make_image(path=root+'/bg/Image',sprite='icon_touch')])
    o = make_oracle(b)
    assert o.private_quarters_interact_visible()
    assert o.click_private_quarters_interact().path == root
    b.ui['texts'][0]['text'] = '购买'
    with pytest.raises(SemanticGateClosed, match='identity'):
        o.click_private_quarters_interact()
    assert len(b.taps) == 1



def test_absent_touch_yields_to_original_presence_loop():
    from alas_headless.oracle.errors import SemanticTargetMissing
    b = FakeBackend([])
    with pytest.raises(SemanticTargetMissing):
        make_oracle(b).click_private_quarters_interact()
    assert b.taps == []
