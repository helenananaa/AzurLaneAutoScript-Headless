from tests.alas_test_source import patched_alas_root
import ast
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def test_exact_later_precombat_with_controlled_loading_refuses_then_starts_once():
    b, o, _ = host(fixture='exercise-precombat-after-loading-r149.json')
    a = AlasSemanticAdapter(o, lambda: None, exercise_execute_budget=1)
    a._exercise_pending = True
    loading = make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')
    b.buttons['buttons'].append(loading)
    b.buttons['button_count'] += 1
    with pytest.raises(SemanticInputBlocked) as caught:
        a.click_exercise_precombat_start()
    assert caught.value.semantic_id == 'daily/precombat/start'
    assert caught.value.blockers == ('loading',) and not b.taps
    assert a._exercise_pending and a._action_ledger.remaining('exercise.execute') == 1
    b.buttons['buttons'].remove(loading)
    b.buttons['button_count'] -= 1
    for projection in (b.snapshot, b.buttons, b.ui):
        projection['generation'] = 10588
    o._sleep = lambda _: None
    receipt = a.click_exercise_precombat_start()
    assert receipt.semantic_id == 'exercise/execute'
    assert len(b.taps) == 1
    assert a._exercise_execution_active and a._action_ledger.remaining('exercise.execute') == 0


def original_method():
    path = Path(os.environ.get('ALAS_TEST_COMBAT_SOURCE',
        str(patched_alas_root() / 'module/combat/combat.py')))
    if not path.exists():
        pytest.skip('retained native ALAS unavailable')
    method = next(v for v in ast.walk(ast.parse(path.read_text(encoding='utf8')))
                  if isinstance(v, ast.FunctionDef) and v.name == 'combat_preparation')
    names = {'time': time, 'logger': SimpleNamespace(info=lambda _: None, attr=lambda *_: None)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), names)
    return names['combat_preparation']


def runner(error):
    calls = []
    def start():
        calls.append(True)
        if len(calls) == 1:
            raise error
    oracle = SimpleNamespace(daily_precombat_visible=lambda: len(calls) < 2,
                             daily_combat_visible=lambda: len(calls) == 2)
    adapter = SimpleNamespace(campaign_result_ready=lambda: False,
        open=lambda: SimpleNamespace(oracle=oracle, _frame_or_live_observation_oracle=lambda: oracle),
        meta_beacon_active=lambda: False,
        click_daily_precombat_start=start)
    device = SimpleNamespace(semantic_adapter=adapter, stuck_record_clear=lambda: None,
        click_record_clear=lambda: None, screenshot_interval_set=lambda _: None)
    value = SimpleNamespace(device=device, loop=lambda: iter(range(3)),
        handle_combat_automation_confirm=lambda: False, is_combat_executing=lambda: 'PAUSE')
    return value, calls


def test_original_preparation_yields_loading_to_next_screenshot_then_commits_once():
    value, calls = runner(SemanticInputBlocked('daily/precombat/start', 10, ('loading',)))
    assert original_method()(value) is False
    assert len(calls) == 2


@pytest.mark.parametrize('error', [SemanticInputBlocked('daily/precombat/start', 10, ('loading', 'msgbox')),
    SemanticInputBlocked('different/target', 10, ('loading',)),
    SemanticGateClosed('foreground changed before daily precombat start')])
def test_original_preparation_does_not_retry_unknown_or_foreign_input(error):
    value, calls = runner(error)
    with pytest.raises(SemanticGateClosed) as caught:
        original_method()(value)
    assert caught.value is error and len(calls) == 1
