from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.adapter_fixtures import FakeOracle


def test_task_back_transition_uses_one_frame_even_after_live_main_arrives():
    import time
    from alas_headless import AlasSemanticUnmapped
    live, frame = FakeOracle(), FakeOracle()
    live.main_page_visible_value = True
    host = AlasSemanticAdapter(live, package_gate=lambda: None,
                              frame_observation_oracle=lambda: frame)
    host._mission_page_return_transition_until = time.monotonic() + 15
    assert host.appear(SimpleNamespace(name='GAME_ROOM_CHECK')) is False
    assert live.click_calls == []
    host._mission_page_return_transition_until = time.monotonic() - 1
    with pytest.raises(AlasSemanticUnmapped):
        host.appear(SimpleNamespace(name='GAME_ROOM_CHECK'))


@pytest.mark.parametrize('probe', ['GAME_ROOM_CHECK', 'PRIVATE_QUARTERS_CHECK', 'SHIPYARD_CHECK',
                                 'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP', 'GET_MISSION',
                                 'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON',
                                 'LOGIN_RETURN_SIGN', 'PLAYER_CHECK', 'POPUP_SINGLE_WHITE',
                                 'GAME_TIPS', 'DORM_INFO', 'MEOWFFICER_INFO', 'MEOWFFICER_BUY',
                                 'MAP_PREPARATION', 'EXERCISE_PREPARATION', 'MAINTENANCE_ANNOUNCE'])
def test_complete_inherited_task_scene_owns_all_registered_page_probes(probe):
    live, frame = FakeOracle(), FakeOracle()
    frame.exists_values['task/page/back'] = True
    frame.mission_page_state = lambda: SimpleNamespace(disposition='unfinished')
    host = AlasSemanticAdapter(live, package_gate=lambda: None,
                              frame_observation_oracle=lambda: frame)
    assert host.appear(SimpleNamespace(name=probe)) is False
    assert host.appear(SimpleNamespace(name='MISSION_CHECK')) is True
    assert live.click_calls == []


def test_incomplete_inherited_task_scene_does_not_suppress_unknown_game_room():
    from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
    live, frame = FakeOracle(), FakeOracle()
    frame.exists_values['task/page/back'] = True
    def obscured():
        raise SemanticGateClosed('task page obscured')
    frame.mission_page_state = obscured
    host = AlasSemanticAdapter(live, package_gate=lambda: None,
                              frame_observation_oracle=lambda: frame)
    with pytest.raises(AlasSemanticUnmapped):
        host.appear(SimpleNamespace(name='GAME_ROOM_CHECK'))
    assert live.click_calls == []


@pytest.mark.parametrize('notice,foreign,absent', [(False, False, True), (True, False, False),
                                                  (False, True, False)])
def test_task_scene_proves_absent_notice_without_hiding_a_present_owner(notice, foreign, absent):
    frame = FakeOracle()
    frame.observation_target_present = lambda target: target == 'task/page/back'
    frame.exists_values['task/page/back'] = True
    def page():
        from alas_headless import SemanticGateClosed
        if foreign:
            raise SemanticGateClosed('foreign overlay')
        return SimpleNamespace(disposition='unfinished')
    frame.mission_page_state = page
    frame._blocking_rules = lambda *args: [SimpleNamespace(blocker_id=
        'unknown-overlay' if foreign else 'task-page')]
    frame._campaign_urgent_notice_matches = lambda state: notice
    host = AlasSemanticAdapter(frame, package_gate=lambda: None)
    assert (host._appear_priority('GET_MISSION') is False) is absent
    assert frame.click_calls == []


@pytest.mark.parametrize('name', ['WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM', 'DOCK_CHECK'])
@pytest.mark.parametrize('back, blockers, owned', [
    (True, [], True), (True, ['task-page'], True),
    (False, [], False), (True, ['task-page', 'msgbox'], False),
    (True, ['task-page', 'unknown-overlay'], False),
])
def test_inherited_task_list_owns_only_unobscured_popup_absence(name, back, blockers, owned):
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'task/page/back' and back
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=key) for key in blockers]
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert (adapter._appear_priority(name) is False) == owned
    assert oracle.click_calls == []


@pytest.mark.parametrize('blockers, waiting', [
    (['loading'], True), (['loading', 'msgbox'], False),
    (['unknown-overlay'], False), ([], False),
])
def test_page_checks_wait_only_for_exact_loading(blockers, waiting):
    oracle = FakeOracle()
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=name) for name in blockers]
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    result = host._appear_priority('DOCK_CHECK')
    assert (result is False) == waiting
    assert oracle.click_calls == []


@pytest.mark.parametrize('retained_minigame', [False, True])
@pytest.mark.parametrize('resource', ['GOTO_MAIN', 'GAME_ROOM_GOTO_MAIN'])
@pytest.mark.parametrize('generic_enabled', [True, False])
def test_game_room_handoff_uses_original_page_graph_home(retained_minigame, resource, generic_enabled):
    oracle = FakeOracle()
    oracle.game_room_page_visible = lambda: True
    oracle.observation_target_present = lambda target: target in ('game-room/back', 'game-room/home')
    oracle.enabled = lambda target: target == 'game-room/home' and generic_enabled
    original_click = oracle.click
    def arrive(target):
        receipt = original_click(target)
        oracle.state_generation = receipt.generation + 1
        oracle.main_page_visible_value = True
        return receipt
    oracle.click = arrive
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if retained_minigame:
        host.begin_minigame()
    assert host._appear_priority('DOCK_CHECK') is False
    assert host._appear_priority('GAME_ROOM_CHECK') is True
    assert host._click_priority(resource).semantic_id == 'game-room/home'
    assert oracle.click_calls == ['game-room/home']


@pytest.mark.parametrize('home_enabled', [True, False])
def test_game_room_passive_identity_does_not_require_home_raycasts(home_enabled):
    oracle = FakeOracle()
    oracle.game_room_page_visible = lambda: True
    oracle.observation_target_present = lambda target: target in ('game-room/back', 'game-room/home')
    oracle.enabled = lambda target: target == 'game-room/home' and home_enabled
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert host._appear_priority('FLEET_CHECK') is False
    assert host._appear_priority('GAME_ROOM_CHECK') is True
    assert oracle.click_calls == []

def test_game_room_home_blocked_return_stops_after_one_input(monkeypatch):
    import alas_headless.adapter.semantic.dispatch_actions as actions
    from alas_headless import SemanticGateClosed
    oracle = FakeOracle()
    oracle.game_room_page_visible = lambda: True
    oracle.observation_target_present = lambda target: target in ('game-room/back', 'game-room/home')
    oracle.enabled = lambda target: target == 'game-room/home'
    original_click = oracle.click
    def blocked_return(target):
        receipt = original_click(target)
        oracle.state_generation = receipt.generation + 1
        oracle.main_page_visible_value = True
        oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id='msgbox')]
        return receipt
    oracle.click = blocked_return
    ticks = iter((0, 0, 13))
    monkeypatch.setattr(actions.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(actions.time, 'sleep', lambda _: None)
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed, match='home return was not proven'):
        host._click_priority('GOTO_MAIN')
    assert oracle.click_calls == ['game-room/home']


@pytest.mark.parametrize('owned, main, back, blockers, waiting', [
    (True, False, False, [], True),
    (True, False, False, ['commission-page'], True),
    (False, False, False, [], False),
    (True, True, False, [], False),
    (True, False, True, [], False),
    (True, False, False, ['msgbox'], False),
])
@pytest.mark.parametrize('probe', ['FLEET_CHECK', 'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
def test_commission_back_handoff_yields_only_owned_passive_checks(owned, main, back, blockers, waiting, probe):
    import time
    oracle = FakeOracle()
    oracle.main_page_visible = lambda: main
    oracle.enabled = lambda target: target == 'commission/page/back' and back
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=name) for name in blockers]
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._commission_return_transition_until = time.monotonic() + (12 if owned else -1)
    if main and probe == 'FLEET_CHECK':
        assert host._appear_priority('MAIN_CHECK') is UNHANDLED
        assert host._appear_priority('FLEET_CHECK') is False
    elif not main:
        expected = waiting or (owned and back and not blockers and probe.startswith('GET_ITEMS_'))
        assert (host._appear_priority(probe) is False) == expected
    assert oracle.click_calls == []


@pytest.mark.parametrize('tactical', [False, True])
@pytest.mark.parametrize('back_enabled', [False, True])
def test_inherited_exercise_identity_precedes_task_context(tactical, back_enabled):
    oracle = FakeOracle()
    oracle.exercise_page_visible = lambda: True
    oracle.enabled = lambda target: target == 'exercise/page/back' and back_enabled
    oracle.observation_target_present = lambda target: target == 'exercise/page/back'
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if tactical: host.begin_tactical()
    assert host._appear_priority('EXERCISE_CHECK') is True
    assert host._appear_priority('TACTICAL_CHECK') is False
    assert host._appear_priority('FLEET_CHECK') is False
    assert oracle.click_calls == []


def test_unknown_exercise_identity_grants_no_return_input():
    oracle = FakeOracle()
    oracle.exercise_page_visible = lambda: False
    oracle.observation_target_present = lambda target: target == 'exercise/page/back'
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_tactical()
    assert host._click_priority('BACK_ARROW') is UNHANDLED
    assert oracle.click_calls == []


@pytest.mark.parametrize('retained_tactical', [False, True])
@pytest.mark.parametrize('blockers, owned', [([], True), (['tactical-page'], True),
                                          (['tactical-page', 'loading'], True),
                                          (['msgbox'], False), (['unknown-overlay'], False)])
def test_classroom_page_identity_precedes_inherited_task_context(retained_tactical, blockers, owned):
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'tactical/page/back'
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=name) for name in blockers]
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if retained_tactical:
        host.begin_tactical()
    assert (host._appear_priority('FLEET_CHECK') is False) == owned
    result = host._appear_priority('TACTICAL_CHECK')
    if retained_tactical and owned and 'loading' not in blockers:
        # The active tactical reader owns its child-panel exclusions; a
        # passive back marker must not bypass the book/course/dock checks.
        assert result is UNHANDLED
    else:
        assert (result is True) == (owned and 'loading' not in blockers)
    assert oracle.click_calls == []


@pytest.mark.parametrize('back', [True, False])
def test_retained_dorm_home_aliases_require_actionable_return(back):
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'dorm/page/manage'
    oracle.enabled = lambda target: target == 'dorm/page/back' and back
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    for name in ('GOTO_MAIN_WHITE', 'RPG_HOME'):
        assert (host._appear_priority(name) is False) == back
    assert oracle.click_calls == []


def test_event_back_accepts_proven_retained_chapter_without_second_input():
    oracle = FakeOracle()
    receipt = oracle.click_receipt('campaign-menu/page/back', generation=7)
    clicked = []
    oracle.click = lambda target: (clicked.append(target) or receipt)
    oracle.read_state = lambda: SimpleNamespace(generation=8 if clicked else 7)
    oracle.campaign_page_is_normal = lambda: bool(clicked)
    oracle.event_campaign_page_visible = lambda: not clicked
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._goto_main_target = lambda: 'campaign-menu/page/back'
    assert host._click_main('GOTO_MAIN', None) == receipt
    assert clicked == ['campaign-menu/page/back']


def test_event_back_still_rejects_unchanged_selector(monkeypatch):
    import itertools
    from alas_headless.semantic_oracle import SemanticGateClosed
    from alas_headless.adapter.semantic import dispatch_actions
    clock = itertools.count(0, 3)
    monkeypatch.setattr(dispatch_actions.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(dispatch_actions.time, 'sleep', lambda _: None)
    oracle = FakeOracle()
    oracle.read_state = lambda: SimpleNamespace(generation=8)
    oracle.campaign_page_is_normal = lambda: False
    oracle.event_campaign_page_visible = lambda: True
    oracle.campaign_menu_is_entry = lambda: False
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._goto_main_target = lambda: 'campaign-menu/page/back'
    with pytest.raises(SemanticGateClosed, match='exact next page'):
        host._click_main('GOTO_MAIN', None)
    assert oracle.click_calls == ['campaign-menu/page/back']


def test_event_notice_probe_uses_existing_selector_identity():
    oracle = FakeOracle()
    oracle.event_campaign_page_visible = lambda: True
    def wrong_parser():
        raise AssertionError('event selector is not a normal chapter')
    oracle.campaign_page_is_normal = wrong_parser
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert host._campaign_notice_navigation_surface() is True
    assert oracle.click_calls == []
