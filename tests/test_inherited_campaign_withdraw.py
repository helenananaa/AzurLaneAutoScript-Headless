import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from alas_headless.adapter.task_lifecycle import semantic_task_scope
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend,make_ui,make_oracle,DRIVER_REVISION
from tests.semantic_support.adapter_fixtures import FakeOracle

def retained_prompt():
    p=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r32-original-map-recovery-r2-20260930.json'
    if not p.exists():pytest.skip('native withdrawal prompt unavailable')
    r=json.loads(p.read_text(encoding='utf8'));b=FakeBackend(r['after']['buttons_snapshot']['buttons'])
    u=r['ui_after']['snapshot'];b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    return b

def test_inherited_prompt_reuses_exact_native_withdraw_control():
    b=retained_prompt();o=make_oracle(b)
    assert o.inherited_campaign_withdraw_control(confirm=True) is not None
    assert b.taps==[]

@pytest.mark.parametrize('duplicate',[False,True])
def test_confirmation_text_before_button_yields_without_input(duplicate):
    b=retained_prompt()
    path='OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'
    target=next(x for x in b.buttons['buttons'] if x['path']==path)
    records=[x for x in b.buttons['buttons'] if x['path']!=path]
    if duplicate:records.extend([dict(target),dict(target)])
    b.buttons['buttons']=records;b.buttons['button_count']=len(records)
    o=make_oracle(b)
    if duplicate:
        with pytest.raises(SemanticGateClosed):o.campaign_withdraw_control(confirm=True)
    else:assert o.campaign_withdraw_control(confirm=True) is None
    assert b.taps==[]

@pytest.mark.parametrize('text',['真的要消费钻石撤退吗?','是否购买?','服务器维护'])
def test_other_modal_does_not_inherit_withdraw_authority(text):
    b=retained_prompt()
    for t in b.ui['texts']:
        if t['path'].endswith('/msg_panel/content'):t['text']=text
    assert make_oracle(b).inherited_campaign_withdraw_control(confirm=True) is None
    assert b.taps==[]

def test_foreign_maintenance_probe_skips_stable_modal_parser():
    b=retained_prompt();o=make_oracle(b)
    o._stable_msgbox_ui_state=Mock(side_effect=AssertionError('foreign modal'))
    assert o.server_maintenance_visible() is False
    o._stable_msgbox_ui_state.assert_not_called()

def test_inherited_withdraw_dispatch_waits_postcondition_and_rejects_repeat():
    o=FakeOracle();r=SimpleNamespace(generation=10)
    o.inherited_campaign_withdraw_control=Mock(return_value=(object(),10))
    o.click_campaign_withdraw=Mock(return_value=r)
    o.read_state=Mock(return_value=SimpleNamespace(generation=11,buttons=()))
    o.campaign_withdraw_control=Mock(return_value=None)
    a=AlasSemanticAdapter(o,package_gate=lambda:None)
    a._fresh_input_oracle=lambda:o
    assert a._click_priority('CAMPAIGN_WITHDRAW_CONFIRM') is r
    with pytest.raises(SemanticGateClosed,match='already submitted'):
        a._click_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    o.click_campaign_withdraw.assert_called_once_with(confirm=True)

def test_inherited_withdraw_rejects_missing_target_before_input():
    o=FakeOracle();o.inherited_campaign_withdraw_control=Mock(return_value=None)
    o.click_campaign_withdraw=Mock()
    a=AlasSemanticAdapter(o,package_gate=lambda:None);a._fresh_input_oracle=lambda:o
    with pytest.raises(SemanticGateClosed,match='not actionable'):a._click_priority('WITHDRAW')
    o.click_campaign_withdraw.assert_not_called()


@pytest.mark.parametrize('confirm', [False, True])
def test_task_boundary_releases_completed_withdraw_without_allowing_same_task_repeat(confirm):
    o = FakeOracle()
    receipts = [SimpleNamespace(generation=10), SimpleNamespace(generation=20)]
    o.inherited_campaign_withdraw_control = Mock(return_value=(object(), 10))
    o.click_campaign_withdraw = Mock(side_effect=receipts)
    o.read_state = Mock(side_effect=[SimpleNamespace(generation=11, buttons=()),
                                   SimpleNamespace(generation=21, buttons=())])
    o.campaign_withdraw_control = Mock(return_value=None if confirm else object())
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._fresh_input_oracle = lambda: o
    session = AlasSemanticSession(serial='offline-test', driver_revision=DRIVER_REVISION)
    session.adapter = a
    name = 'CAMPAIGN_WITHDRAW_CONFIRM' if confirm else 'WITHDRAW'
    for receipt in receipts:
        with semantic_task_scope(session, 'goto_main'):
            assert a._click_priority(name) is receipt
            with pytest.raises(SemanticGateClosed, match='already submitted'):
                a._click_priority(name)
    assert o.click_campaign_withdraw.call_args_list == [call(confirm=confirm)] * 2


def test_task_boundary_still_requires_new_actionable_withdraw_owner():
    o = FakeOracle()
    o.inherited_campaign_withdraw_control = Mock(side_effect=[(object(), 10), None])
    o.click_campaign_withdraw = Mock(return_value=SimpleNamespace(generation=10))
    o.read_state = Mock(return_value=SimpleNamespace(generation=11, buttons=()))
    o.campaign_withdraw_control = Mock(return_value=None)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._fresh_input_oracle = lambda: o
    session = AlasSemanticSession(serial='offline-test', driver_revision=DRIVER_REVISION)
    session.adapter = a
    with semantic_task_scope(session, 'goto_main'):
        a._click_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        with semantic_task_scope(session, 'goto_main'):
            a._click_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    o.click_campaign_withdraw.assert_called_once_with(confirm=True)

def test_inherited_total_reward_keeps_original_exit_handler_visible():
    p=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r33-readonly-20260930.json'
    if not p.exists():pytest.skip('native total reward unavailable')
    r=json.loads(p.read_text(encoding='utf8'));b=FakeBackend(r['state']['buttons_snapshot']['buttons'])
    u=r['ui']['snapshot'];b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    o=make_oracle(b);a=AlasSemanticAdapter(o,package_gate=lambda:None)
    assert a._appear_priority('AUTO_SEARCH_MENU_EXIT') is True
    assert a._appear_priority('EVENT_CHECK') is False
    assert b.taps==[]

def test_inherited_total_exit_checks_event_destination_after_one_input():
    o=FakeOracle();r=SimpleNamespace(generation=10)
    o.observation_target_present=Mock(side_effect=[True,False])
    o.click=Mock(return_value=r);o.read_state=Mock(return_value=SimpleNamespace(generation=11))
    o.event_campaign_page_visible=Mock(return_value=True)
    a=AlasSemanticAdapter(o,package_gate=lambda:None);a._fresh_input_oracle=lambda:o
    assert a._click_priority('AUTO_SEARCH_MENU_EXIT') is r
    o.click.assert_called_once_with('reward/campaign-total/exit')

def test_withdraw_postcondition_never_borrows_invalidated_input_frame():
    live=FakeOracle();leased=FakeOracle();r=SimpleNamespace(generation=10)
    leased.inherited_campaign_withdraw_control=Mock(return_value=(object(),10))
    leased.click_campaign_withdraw=Mock(return_value=r)
    leased.read_state=Mock(side_effect=AssertionError('input frame invalidated'))
    live.read_state=Mock(return_value=SimpleNamespace(generation=11,buttons=()))
    live.campaign_withdraw_control=Mock(return_value=None)
    a=AlasSemanticAdapter(live,package_gate=lambda:None);a._fresh_input_oracle=lambda:leased
    assert a._click_priority('CAMPAIGN_WITHDRAW_CONFIRM') is r
    leased.read_state.assert_not_called()

def test_confirm_disappearance_without_map_unload_is_not_success(monkeypatch):
    from alas_headless.adapter.semantic import dispatch_actions
    ticks=iter((0,1,100))
    monkeypatch.setattr(dispatch_actions.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(dispatch_actions.time,'sleep',lambda _:None)
    o=FakeOracle();o.inherited_campaign_withdraw_control=Mock(return_value=(object(),10))
    o.click_campaign_withdraw=Mock(return_value=SimpleNamespace(generation=10))
    o.read_state=Mock(return_value=SimpleNamespace(generation=11,buttons=(SimpleNamespace(
        path='LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/op1/retreat',
        active_in_hierarchy=True,active_and_enabled=True),)))
    o.campaign_withdraw_control=Mock(return_value=None)
    a=AlasSemanticAdapter(o,package_gate=lambda:None);a._fresh_input_oracle=lambda:o
    with pytest.raises(SemanticGateClosed,match='postcondition not observed'):
        a._click_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    with pytest.raises(SemanticGateClosed,match='already submitted'):
        a._click_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    o.click_campaign_withdraw.assert_called_once_with(confirm=True)
