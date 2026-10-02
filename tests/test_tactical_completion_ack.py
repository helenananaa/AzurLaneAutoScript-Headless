from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_text, make_ui)

ROOT = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
CONTENT = '<color=#92fc63>「瑟堡」</color>学习完成，<color=#92fc63>「波谲云诡」</color>技能获得<color=#92fc63>150</color>点经验(技能等级提升:9→10）！'
STUDENTS = 'UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/NewNavalTacticsStudentsPage(Clone)/1/info/skill/level'

def backend():
    b = FakeBackend([make_button('custom_button_1(Clone)', ROOT+'button_container/custom_button_1(Clone)')])
    b.ui = make_ui([make_text(CONTENT, ROOT+'msg_panel/content'),
                   make_text('确 定', ROOT+'button_container/custom_button_1(Clone)/pic'),
                   make_text('10', STUDENTS)])
    def close():
        b.snapshot['generation'] = 11
        b.buttons = make_buttons([], generation=11)
        b.ui['generation'] = 11
    b.on_tap = close
    return b

@pytest.mark.parametrize('content', [CONTENT, '「A」学习完成，「B」技能获得300点经验（技能等级提升:9→10)！'])
def test_original_urgent_notice_handler_acknowledges_max_level(content):
    b = backend(); b.ui['texts'][0]['text'] = content
    a = AlasSemanticAdapter(make_oracle(b), package_gate=lambda: None, allow_tactical_rewards=True)
    a.begin_tactical()
    button = SimpleNamespace(name='GET_MISSION')
    assert a.appear(button)
    assert a.click(button).semantic_id == 'tactical/completion/ack'
    assert len(b.taps) == 1

@pytest.mark.parametrize('change', ['purchase', 'continue', 'not_max', 'label', 'duplicate', 'truncated', 'raycast', 'loading', 'foreground', 'students', 'two_buttons', 'coherence'])
def test_unproven_completion_never_grants_input(change):
    b = backend(); o = make_oracle(b)
    if change == 'purchase': b.ui['texts'][0]['text'] = '是否购买教材？'
    elif change == 'continue': b.ui['texts'][0]['text'] += '是否继续学习该技能？'
    elif change == 'not_max': b.ui['texts'][0]['text'] = CONTENT.replace('→10', '→9')
    elif change == 'label': b.ui['texts'][1]['text'] = '购买'
    elif change == 'duplicate':
        b.ui['texts'].append(dict(b.ui['texts'][0])); b.ui['text_count'] += 1
    elif change == 'truncated': b.ui['texts'][0]['flags'] |= 0x10
    elif change == 'raycast': b.buttons['buttons'][0]['raycast_top'] = False
    elif change == 'loading':
        b.buttons['buttons'].append(make_button('block', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)/block'))
        b.buttons['button_count'] += 1
    elif change == 'foreground': o._foreground_component = lambda: 'com.android.launcher/.Launcher'
    elif change == 'students': b.ui['texts'][2]['path'] = 'UnrelatedUI/level'
    elif change == 'two_buttons':
        b.buttons['buttons'].append(make_button('custom_button_2(Clone)', ROOT+'button_container/custom_button_2(Clone)'))
        b.buttons['button_count'] += 1
    else: b.ui['generation'] += 3
    with pytest.raises(SemanticGateClosed): o.click_tactical_completion_ack()
    assert not b.taps

def test_unclosed_popup_does_not_repeat_input():
    b = backend(); b.on_tap = None
    with pytest.raises(SemanticGateClosed, match='did not close'):
        make_oracle(b).click_tactical_completion_ack()
    assert len(b.taps) == 1

def test_reward_permission_and_task_context_are_required():
    b = backend(); o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None); a.begin_tactical()
    button = SimpleNamespace(name='GET_MISSION')
    assert not a.appear(button)
    with pytest.raises(SemanticGateClosed): a.click(button)
    assert not b.taps

def test_disappeared_course_waits_for_new_running_slot_without_input(monkeypatch):
    from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
    o = FakeOracle()
    a = AlasSemanticAdapter(o, package_gate=lambda: None, tactical_assign_budget=1)
    a.begin_tactical()
    o.tactical_slot_values = []
    prior = a.click(NamedButton('POPUP_CONFIRM'))
    o.enabled_values['tactical/course/confirm'] = False
    o.read_state = lambda: SimpleNamespace(generation=prior.generation + 1)
    samples = iter([(), (), (SimpleNamespace(slot=1, ship_id=207094, status='running'),)])
    o.tactical_slots = lambda: next(samples)
    monkeypatch.setattr('alas_headless.adapter.semantic.tactical.time.sleep', lambda _: None)
    assert a.click(NamedButton('POPUP_CONFIRM')) is prior
    assert o.click_calls == ['tactical/course/confirm']

def test_finished_same_student_becomes_running_after_confirmation():
    from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
    o = FakeOracle()
    a = AlasSemanticAdapter(o, package_gate=lambda: None, tactical_assign_budget=1)
    a.begin_tactical()
    o.tactical_slot_values = [SimpleNamespace(slot=1, ship_id=207094, status='finished')]
    prior = a.click(NamedButton('POPUP_CONFIRM'))
    o.enabled_values['tactical/course/confirm'] = False
    o.read_state = lambda: SimpleNamespace(generation=prior.generation + 1)
    o.tactical_slot_values[0].status = 'running'
    assert a.click(NamedButton('POPUP_CONFIRM')) is prior
    assert o.click_calls == ['tactical/course/confirm']

def test_missing_prior_slots_cannot_reuse_existing_running_course():
    from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
    o = FakeOracle()
    a = AlasSemanticAdapter(o, package_gate=lambda: None, tactical_assign_budget=1)
    a.begin_tactical()
    def missing():
        raise SemanticGateClosed('missing classroom observation')
    o.tactical_slots = missing
    a.click(NamedButton('POPUP_CONFIRM'))
    o.enabled_values['tactical/course/confirm'] = False
    o.tactical_slots = lambda: (SimpleNamespace(slot=1, ship_id=207094, status='running'),)
    with pytest.raises(SemanticGateClosed, match='prior tactical course slot observation'):
        a.click(NamedButton('POPUP_CONFIRM'))
    assert o.click_calls == ['tactical/course/confirm']
