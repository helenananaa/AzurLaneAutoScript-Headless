"""Accepted Exercise starts keep native waiting/retry decisions, not a second timer."""
import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.mark.parametrize('drift', [False, True])
def test_recorded_post_start_loading_stays_a_passive_preparation_miss(drift):
    backend, oracle, adapter = host(drift, 'exercise-post-start-mount-r241.json')
    adapter._exercise_execution_active = True
    adapter._exercise_pending = False
    assert oracle.daily_precombat_visible()
    assert 'loading' in {r.blocker_id for r in oracle._blocking_rules(oracle.read_state(), 'daily/precombat/start')}
    assert adapter._appear_once('BATTLE_PREPARATION') is False
    assert not backend.taps


def test_native_retry_on_ready_exercise_preparation_keeps_exercise_intent():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(exercise_execute_budget=2)
    adapter._exercise_execution_active = True
    adapter._exercise_pending = False
    oracle.daily_precombat_visible = lambda: True
    oracle.enabled_values['daily/precombat/start'] = True
    assert adapter.appear('BATTLE_PREPARATION') is True
    assert adapter.click('BATTLE_PREPARATION').semantic_id == 'exercise/execute'
    assert oracle.click_calls == ['daily/precombat/start']


def test_start_without_exercise_intent_remains_rejected():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(exercise_execute_budget=2)
    with pytest.raises(SemanticGateClosed, match='intent is incomplete'):
        adapter.click_exercise_precombat_start()
    assert not oracle.click_calls
