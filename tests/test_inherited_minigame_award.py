from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.adapter_fixtures import FakeOracle

@pytest.mark.parametrize('minigame', [False, True])
@pytest.mark.parametrize('close', [False, True])
def test_exact_generic_award_observation_and_input_are_independent_of_mission(minigame, close):
    o = FakeOracle()
    o.award_info_page_visible = lambda: True
    o.enabled = lambda target: close and target == 'reward/award-info/close'
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    if minigame:
        a.begin_minigame()
    if close:
        assert a.appear(SimpleNamespace(name='GET_ITEMS_1')) is True
        assert a.appear(SimpleNamespace(name='GET_ITEMS_2')) is False
        assert a.click(SimpleNamespace(name='GET_ITEMS_1')).semantic_id == 'reward/award-info/close'
        assert o.click_calls == ['reward/award-info/close']
    else:
        assert a.appear(SimpleNamespace(name='GET_ITEMS_1')) is False
        assert a._appear_priority('FLEET_CHECK') is False
        assert a._appear_priority('GOTO_MAIN') is False
        assert a._click_priority('GET_ITEMS_1') is UNHANDLED
        assert o.click_calls == []

def test_foreign_close_control_without_award_identity_does_not_get_input():
    o = FakeOracle()
    o.award_info_page_visible = lambda: False
    o.enabled = lambda target: target == 'reward/award-info/close'
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a._click_priority('GET_ITEMS_1') is UNHANDLED
    assert o.click_calls == []

@pytest.mark.parametrize('name', ['GET_ITEMS_1','GET_ITEMS_2','GET_ITEMS_3'])
def test_known_minigame_before_reward_mount_waits_without_mission_flow(name):
    o = FakeOracle()
    o.game_room_page_visible = lambda: True
    o.award_info_page_visible = lambda: False
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_minigame()
    assert a.appear(SimpleNamespace(name=name)) is False
    assert o.click_calls == []


def test_idle_fushun_home_yields_unrelated_page_markers_to_native_recovery():
    o = FakeOracle()
    o.observation_target_present = lambda target: target == 'minigame/new-year/back'
    o.new_year_challenge_home_visible = lambda: True
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a._appear_priority('FLEET_CHECK') is False
    assert a._appear_priority('GAME_ROOM_CHECK') is False
    assert o.click_calls == []


@pytest.mark.parametrize('change', [None, 'old', 'list', 'popup', 'fushun'])
def test_completed_play_lease_releases_only_at_new_unobscured_game_hall_home(change):
    o = FakeOracle()
    o.game_room_page_visible = lambda: True
    o.game_room_list_visible = lambda: change == 'list'
    o._blocking_rules = lambda *_: [SimpleNamespace(blocker_id='msgbox')] if change == 'popup' else []
    buttons = (SimpleNamespace(active_in_hierarchy=True, active_and_enabled=True,
                               path='UICamera/Canvas/UIMain/GameRoomFushun2UI(Clone)/back'),) if change == 'fushun' else ()
    o.read_state = lambda: SimpleNamespace(generation=10 if change == 'old' else 11, buttons=buttons)
    a = AlasSemanticAdapter(o, package_gate=lambda: None, minigame_play_budget=3)
    a.begin_minigame()
    prior = SimpleNamespace(generation=10)
    a._minigame_context.play_receipt = prior
    assert a.minigame_play_allowed() is (change is None)
    assert a._minigame_context.play_receipt is (None if change is None else prior)
    assert o.click_calls == []
