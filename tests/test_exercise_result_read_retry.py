from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.oracle.errors import SemanticTargetMissing


def session():
    o = Mock()
    o.exercise_page_visible.side_effect = [False, True]
    o.exercise_merit_shop_visible.return_value = False
    o.exercise_reward_item_info_visible.return_value = False
    o.award_info_page_visible.return_value = False
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.refresh_frame = Mock()
    s.open = lambda: SimpleNamespace(oracle=o, _require_frame_observation_oracle=lambda: o)
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


def test_departing_award_reobserves_without_repeating_accepted_input(monkeypatch):
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', lambda _: None)
    s, o = session()
    o.exercise_page_visible.side_effect = [False, False, False, True]
    o.award_info_page_visible.side_effect = [True, True, False]
    o.daily_battle_result_visible.return_value = True
    o.input_dispatch_count = 0
    reward, statistics = object(), object()

    def close_award():
        if o.input_dispatch_count == 0:
            o.input_dispatch_count += 1
            return reward
        raise SemanticTargetMissing('exercise award-info page is absent')

    def close_statistics():
        o.input_dispatch_count += 1
        return statistics

    o.click_exercise_award_info_close.side_effect = close_award
    o.click_daily_battle_result.side_effect = close_statistics
    assert s.complete_exercise_battle_result() == (reward, statistics)
    assert o.input_dispatch_count == 2
    assert o.click_exercise_award_info_close.call_count == 2
    o.click_daily_battle_result.assert_called_once()


@pytest.mark.parametrize('failure', [SemanticGateClosed('ambiguous target'),
                                    SemanticGateClosed('wrong package'),
                                    SemanticGateClosed('observer snapshot is stale')])
def test_award_nonabsence_failures_remain_closed(failure):
    s, o = session()
    o.award_info_page_visible.return_value = True
    o.input_dispatch_count = 0
    o.click_exercise_award_info_close.side_effect = failure
    with pytest.raises(SemanticGateClosed, match=str(failure)):
        s.complete_exercise_battle_result()
    o.click_exercise_award_info_close.assert_called_once()


@pytest.mark.parametrize('count_known', [True, False])
def test_award_missing_after_dispatch_or_unknown_count_is_not_retried(count_known):
    s, o = session()
    o.award_info_page_visible.return_value = True
    if count_known:
        o.input_dispatch_count = 0

    def uncertain_close():
        if count_known:
            o.input_dispatch_count += 1
        raise SemanticTargetMissing('uncertain close')

    o.click_exercise_award_info_close.side_effect = uncertain_close
    with pytest.raises(SemanticTargetMissing, match='uncertain close'):
        s.complete_exercise_battle_result()
    o.click_exercise_award_info_close.assert_called_once()


@pytest.mark.parametrize('presence, action', [
    ('exercise_merit_shop_visible', 'click_exercise_merit_shop_close'),
    ('exercise_reward_item_info_visible', 'click_exercise_reward_item_info_cancel'),
    ('daily_battle_result_visible', 'click_daily_battle_result'),
])
def test_other_result_action_missing_is_not_retried(presence, action):
    s, o = session()
    getattr(o, presence).return_value = True
    o.input_dispatch_count = 0
    getattr(o, action).side_effect = SemanticTargetMissing('other target absent')
    with pytest.raises(SemanticTargetMissing):
        s.complete_exercise_battle_result()
    getattr(o, action).assert_called_once()


def test_exercise_award_absence_uses_one_current_snapshot_without_input():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    original_read = oracle.read_state
    oracle.read_state = Mock(wraps=original_read)
    with pytest.raises(SemanticTargetMissing, match='page is absent'):
        oracle.click_exercise_award_info_close()
    oracle.read_state.assert_called_once()
    assert backend.taps == []
    assert oracle.input_dispatch_count == 0


@pytest.mark.parametrize('variant', ['missing', 'duplicate', 'covered', 'foreign', 'stale'])
def test_exercise_award_close_keeps_identity_and_actionability(variant):
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    root = 'root/OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/'
    button = make_button('close', root + 'items/close')
    if variant == 'covered':
        button['raycast_top'] = False
    buttons = [button]
    if variant == 'missing':
        buttons = [make_button('icon', root + 'icon')]
    elif variant == 'duplicate':
        buttons.append(make_button('close', 'other/' + root + 'items/close'))
    backend = FakeBackend(buttons)
    if variant == 'foreign':
        backend.snapshot['package'] = 'unrelated.package'
    elif variant == 'stale':
        backend.snapshot['age_ms'] = 100000
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed) as raised:
        oracle.click_exercise_award_info_close()
    assert isinstance(raised.value, SemanticTargetMissing) is (variant == 'missing')
    assert backend.taps == []


def test_real_award_dispatch_counter_precedes_uncertain_backend_failure():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    backend = FakeBackend([make_button('close',
        'root/OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close')])
    oracle = make_oracle(backend)

    def uncertain_backend(*args):
        assert oracle.input_dispatch_count == 1
        raise SemanticTargetMissing('backend result uncertain')

    oracle._tap_backend = uncertain_backend
    s, o = session()
    o.award_info_page_visible.return_value = True
    s.open = lambda: SimpleNamespace(oracle=oracle, _require_frame_observation_oracle=lambda: oracle)
    oracle.exercise_page_visible = Mock(return_value=False)
    oracle.exercise_merit_shop_visible = Mock(return_value=False)
    oracle.exercise_reward_item_info_visible = Mock(return_value=False)
    with pytest.raises(SemanticTargetMissing, match='backend result uncertain'):
        s.complete_exercise_battle_result()
    assert oracle.input_dispatch_count == 1


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
