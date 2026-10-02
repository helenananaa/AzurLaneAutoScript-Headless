from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed


def session():
    o = Mock()
    o.exercise_page_visible.side_effect = [False, True]
    o.exercise_merit_shop_visible.return_value = False
    o.exercise_reward_item_info_visible.return_value = False
    o.award_info_page_visible.return_value = False
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.open = lambda: SimpleNamespace(oracle=o)
    return s, o


def test_stale_presence_waits_for_fresh_overview_without_input(monkeypatch):
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', lambda _: None)
    s, o = session()
    o.daily_battle_result_visible.side_effect = SemanticGateClosed('observer snapshot is stale')
    assert s.complete_exercise_battle_result() == ()
    o.click_daily_battle_result.assert_not_called()


@pytest.mark.parametrize('failure', ['ambiguous result', 'wrong package'])
def test_unknown_result_observation_is_not_retried(failure):
    s, o = session()
    o.daily_battle_result_visible.side_effect = SemanticGateClosed(failure)
    with pytest.raises(SemanticGateClosed, match=failure): s.complete_exercise_battle_result()
    o.click_daily_battle_result.assert_not_called()


def test_input_failure_is_not_retried_even_if_it_reports_stale():
    s, o = session()
    o.daily_battle_result_visible.return_value = True
    o.click_daily_battle_result.side_effect = SemanticGateClosed('observer snapshot is stale')
    with pytest.raises(SemanticGateClosed): s.complete_exercise_battle_result()
    o.click_daily_battle_result.assert_called_once()


@pytest.mark.parametrize('pause_present', [True, False])
def test_exercise_pause_and_hp_use_the_same_screenshot_frame(pause_present):
    live, frame = Mock(), Mock()
    live.daily_combat_visible.side_effect = AssertionError('live combat poll mixes generations')
    live.exercise_duel_hp.side_effect = AssertionError('live HP poll mixes generations')
    frame.daily_combat_visible.return_value = pause_present
    frame.exercise_duel_hp.return_value = (.95, .0)
    adapter = SimpleNamespace(oracle=live, _exercise_execution_active=True,
                              _frame_or_live_observation_oracle=lambda: frame)
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.open = lambda: adapter
    assert s.combat_is_executing() is pause_present
    if pause_present:
        assert s.exercise_duel_hp() == (.95, .0)
    live.daily_combat_visible.assert_not_called()
    live.exercise_duel_hp.assert_not_called()


def test_exercise_hp_keeps_ambiguous_frame_failure():
    live, frame = Mock(), Mock()
    frame.exercise_duel_hp.side_effect = SemanticGateClosed('exercise duel HP bar is ambiguous')
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.open = lambda: SimpleNamespace(oracle=live, _frame_or_live_observation_oracle=lambda: frame)
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        s.exercise_duel_hp()
    live.exercise_duel_hp.assert_not_called()


def test_retained_weapon_controls_during_loading_do_not_trigger_exercise_hp():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    backend = FakeBackend([
        make_button('ActCtl', 'UICamera/Canvas/UIMain/CombatUIStandard(Clone)/Weapon_button_container/Skill_1/ActCtl'),
        make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'),
    ])
    frame = make_oracle(backend)
    assert not frame.daily_combat_visible()
    live = Mock()
    live.daily_battle_result_visible.return_value = False
    live.daily_combat_visible.return_value = True
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.open = lambda: SimpleNamespace(oracle=live, _exercise_execution_active=True,
                                    _frame_or_live_observation_oracle=lambda: frame)
    assert not s.combat_is_executing()
    live.daily_combat_visible.assert_not_called()
    assert backend.taps == []
