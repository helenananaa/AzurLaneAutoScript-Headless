"""A finished duel yields to native result handling without any pause input."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed


@pytest.mark.parametrize('case', ['result-next-read', 'wrong-package', 'duplicate-pause',
                                 'already-dispatched', 'result-never-mounts'])
def test_fresh_pause_refusal_only_yields_to_proven_result(case, monkeypatch):
    oracle = Mock()
    oracle.input_dispatch_count = 0
    oracle.exercise_combat_pause_menu_visible.return_value = False
    error = SemanticGateClosed('package differs' if case == 'wrong-package'
                               else 'exercise combat identity is not proven')
    def pause():
        if case == 'already-dispatched': oracle.input_dispatch_count = 1
        raise error
    oracle.click_exercise_combat_pause.side_effect = pause
    oracle._matches.return_value = [object(), object()] if case == 'duplicate-pause' else []
    oracle.daily_battle_result_visible.side_effect = [False, True] if case == 'result-next-read' else [False]
    if case == 'result-never-mounts': oracle.daily_battle_result_visible.side_effect = None
    if case == 'result-never-mounts': oracle.daily_battle_result_visible.return_value = False
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: SimpleNamespace(oracle=oracle)
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', lambda _: None)
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.monotonic',
                        Mock(side_effect=[0, 0, 1, 11]))
    if case == 'result-next-read':
        assert session.exercise_quit_low_hp() == ()
        assert oracle.daily_battle_result_visible.call_count == 2
    else:
        with pytest.raises(SemanticGateClosed) as caught:
            session.exercise_quit_low_hp()
        assert caught.value is error
    oracle.click_exercise_combat_pause.assert_called_once()
    oracle.click_exercise_combat_leave.assert_not_called()
    oracle.click_exercise_combat_quit_confirm.assert_not_called()


@pytest.mark.parametrize('drift', [False, True])
def test_retained_duel_unmount_then_exact_result_returns_without_input(drift, monkeypatch):
    from tests.test_game_tips_loading_presence import host
    backend, oracle, _ = host(drift, 'exercise-before-result-r190.json')
    after, _, _ = host(drift, 'exercise-after-result-r190.json')
    assert not oracle._matches(oracle.read_state(), 'exercise/combat/pause')
    assert not oracle.daily_battle_result_visible()
    def result_mounts(_):
        backend.snapshot, backend.buttons, backend.ui = after.snapshot, after.buttons, after.ui
    monkeypatch.setattr('alas_headless.adapter.semantic.session_tasks.time.sleep', result_mounts)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: SimpleNamespace(oracle=oracle)
    assert session.exercise_quit_low_hp() == ()
    assert oracle.daily_battle_result_visible()
    assert not backend.taps
