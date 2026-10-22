from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from alas_headless.oracle.errors import SemanticInputBlocked


def session():
    oracle = Mock()
    oracle.input_dispatch_count = 0
    oracle.exercise_opponent_power.side_effect = [(10, 20), (30, 40), (50, 60), (70, 80)]
    oracle.exercise_opponent_detail_visible.return_value = True
    oracle.exercise_opponent_levels.return_value = (125, 0, 0, 120, 0, 0)
    oracle.exercise_page_visible.return_value = True
    oracle.read_state.return_value = SimpleNamespace(buttons=())
    oracle.read_ui_state.return_value = SimpleNamespace(generation=12)
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.open = lambda: SimpleNamespace(oracle=oracle, _require_frame_observation_oracle=lambda: oracle)
    s.refresh_frame = Mock()
    return s, oracle


def test_loading_before_input_reuses_same_detail_deadline_then_inspects_all_rivals(monkeypatch):
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', lambda _: None)
    s, oracle = session()
    targets = []

    def click(target):
        targets.append(target)
        if len(targets) == 4:
            # The first three detail visits succeeded; their last return is
            # temporarily covered when selecting the fourth rival.
            raise SemanticInputBlocked(target, 11, ('loading',))
        oracle.input_dispatch_count += 1
        return SimpleNamespace(generation=12, upstream_metadata='additive')

    oracle.click.side_effect = click
    assert s.exercise_opponents() == tuple((power, (125, 0, 0, 120, 0, 0))
        for power in ((10, 20), (30, 40), (50, 60), (70, 80)))
    assert targets == ['exercise/opponent/1', 'exercise/opponent/2',
                       'exercise/opponent/3', 'exercise/opponent/4', 'exercise/opponent/4']
    assert oracle.input_dispatch_count == 4
    assert oracle.click_exercise_opponent_back.call_count == 4
    assert s.refresh_frame.call_count == 10


@pytest.mark.parametrize('uncertain', [False, True])
def test_expired_selection_cannot_retry_after_unknown_or_changed_dispatch_count(uncertain):
    s, oracle = session()
    error = StaleFrameError()
    oracle.input_dispatch_count = 0 if uncertain else None
    def click(target):
        if uncertain:
            oracle.input_dispatch_count += 1
        raise error
    oracle.click.side_effect = click
    with pytest.raises(StaleFrameError) as caught:
        s.exercise_opponents()
    assert caught.value is error
    oracle.click.assert_called_once_with('exercise/opponent/1')
    oracle.click_exercise_opponent_back.assert_not_called()


@pytest.mark.parametrize('case', ['other_blocker', 'mixed_blocker', 'wrong_target',
                                 'no_overview', 'unknown_counter', 'dispatched',
                                 'identity', 'ambiguous'])
def test_unproven_or_uncertain_selection_keeps_original_error(case):
    s, oracle = session()
    error = SemanticInputBlocked('exercise/opponent/1', 11, ('loading',))
    if case == 'other_blocker':
        error = SemanticInputBlocked('exercise/opponent/1', 11, ('msgbox',))
    elif case == 'mixed_blocker':
        error = SemanticInputBlocked('exercise/opponent/1', 11, ('loading', 'msgbox'))
    elif case == 'wrong_target':
        error = SemanticInputBlocked('exercise/opponent/2', 11, ('loading',))
    elif case == 'no_overview':
        oracle.exercise_page_visible.return_value = False
    elif case == 'unknown_counter':
        oracle.input_dispatch_count = None
    elif case in ('identity', 'ambiguous'):
        error = SemanticGateClosed(case)

    def click(target):
        if case == 'dispatched':
            oracle.input_dispatch_count += 1
        raise error

    oracle.click.side_effect = click
    with pytest.raises(SemanticGateClosed) as raised:
        s.exercise_opponents()
    assert raised.value is error
    oracle.click.assert_called_once_with('exercise/opponent/1')
    oracle.click_exercise_opponent_back.assert_not_called()


def test_persistent_loading_preserves_classified_task_deferral_at_existing_deadline(monkeypatch):
    s, oracle = session()
    # Power observation uses two clock reads; detail deadline is then 20.
    clock = iter((0, 0, 0, 0, 21))
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.monotonic', lambda: next(clock))
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', lambda _: None)
    error = SemanticInputBlocked('exercise/opponent/1', 11, ('loading',))
    oracle.click.side_effect = error
    with pytest.raises(SemanticInputBlocked) as raised:
        s.exercise_opponents()
    assert raised.value is error
    assert oracle.click.call_count == 2
    assert oracle.input_dispatch_count == 0


def test_real_oracle_never_taps_loading_and_revalidates_fresh_reviewed_rivals(monkeypatch):
    from tests.semantic_support.observer_fixtures import (
        FakeBackend, make_button, make_buttons, make_oracle, make_snapshot, make_text, make_ui,
    )
    page = 'root/UICamera/Canvas/UIMain/MilitaryExerciseUI(Clone)/'
    rivals = [make_button('rivaltpl_' + str(i), page + 'center/rival_list/rivaltpl_' + str(i),
                         200 * i, 236) for i in range(1, 5)]
    buttons = [make_button('backBtn', page + 'blur_panel/adapt/top/backBtn'), *rivals]
    count = make_text('4/10', page + 'center/season_info/count')
    backend = FakeBackend([*buttons, make_button('Loading(Clone)',
                            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')])
    backend.ui = make_ui([count])
    oracle = make_oracle(backend)
    oracle.exercise_opponent_power = lambda i: (10 * i, 20 * i)
    oracle.exercise_opponent_detail_visible = lambda: True
    oracle.exercise_opponent_levels = lambda: (125, 0, 0, 120, 0, 0)
    oracle.click_exercise_opponent_back = Mock()
    s = AlasSemanticSession.__new__(AlasSemanticSession)
    s.open = lambda: SimpleNamespace(oracle=oracle, _require_frame_observation_oracle=lambda: oracle)
    s.refresh_frame = Mock()
    waits = []

    def loading_unmount(_):
        waits.append(True)
        assert backend.taps == []
        assert oracle.input_dispatch_count == 0
        backend.snapshot = make_snapshot(generation=11)
        backend.snapshot['upstream_metadata'] = 'new release'
        backend.buttons = make_buttons(list(reversed(buttons)), generation=11)
        backend.ui = make_ui([count], generation=11)

    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', loading_unmount)
    result = s.exercise_opponents()
    assert len(result) == 4 and len(waits) == 1
    assert backend.taps == [(200, 236), (400, 236), (600, 236), (800, 236)]
    assert oracle.input_dispatch_count == 4
