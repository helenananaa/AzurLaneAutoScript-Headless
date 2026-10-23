"""An owned Exercise loop waits for missing bars without guessing HP or input."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from alas_headless.oracle.errors import SemanticExerciseHpNotReady
from tests.semantic_support.observer_fixtures import FakeBackend


def host():
    data = json.loads((Path(__file__).parent / 'fixtures/exercise-mounted-duel-bars-r128.json').read_text(encoding='utf8'))
    backend = FakeBackend([])
    backend.snapshot = copy.deepcopy(data['snapshot'])
    backend.buttons = copy.deepcopy(data['buttons'])
    backend.ui = copy.deepcopy(data['ui'])
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid'],
            max_age_ms=10000))
    live = Mock()
    live.daily_combat_visible.side_effect = AssertionError('live pause would mix frames')
    live.exercise_duel_hp.side_effect = AssertionError('live HP would mix frames')
    adapter = SimpleNamespace(oracle=live, _exercise_execution_active=True,
        _frame_or_live_observation_oracle=lambda: oracle,
        _campaign_context=None, operation_siren_combat_committed=lambda: False)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    return backend, oracle, session


def bar(image):
    return '/DuelDamageRate/' in image['path'] and image['path'].endswith('/bar/progress')


@pytest.mark.parametrize('missing', ['left', 'both'])
def test_controlled_early_frame_waits_then_exact_mounted_frame_recovers(missing):
    backend, oracle, session = host()
    mounted = copy.deepcopy(backend.ui)
    backend.ui['images'] = [x for x in mounted['images'] if not (
        bar(x) and (missing == 'both' or '/leftDamageBar/' in x['path']))]
    backend.ui['image_count'] = len(backend.ui['images'])
    with pytest.raises(SemanticExerciseHpNotReady):
        oracle.exercise_duel_hp()
    assert session.combat_is_executing() is False
    backend.ui = mounted  # Models the next original ALAS screenshot, not a live fallback.
    assert session.combat_is_executing() is True
    assert oracle.exercise_duel_hp() == pytest.approx((.883482, .852425))
    assert not backend.taps


@pytest.mark.parametrize('case', ['duplicate', 'malformed', 'truncated', 'missing-pause', 'foreign-package', 'stale'])
def test_real_uncertainty_remains_closed_even_with_another_bar_missing(case):
    backend, oracle, session = host()
    images = [x for x in backend.ui['images'] if bar(x)]
    if case == 'duplicate':
        backend.ui['images'].append(copy.deepcopy(images[1]))
        backend.ui['images'] = [x for x in backend.ui['images'] if '/rightDamageBar/bar/progress' not in x['path']]
    elif case == 'malformed':
        images[0]['fill_amount'] = 2
    elif case == 'truncated':
        images[0]['flags'] |= 0x10
    elif case == 'missing-pause':
        backend.buttons['buttons'] = [x for x in backend.buttons['buttons'] if x['name'] != 'PauseBtn']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.snapshot['age_ms'] = 10001
    backend.ui['image_count'] = len(backend.ui['images'])
    with pytest.raises(SemanticGateClosed) as error:
        oracle.exercise_duel_hp()
    assert not isinstance(error.value, SemanticExerciseHpNotReady)
    if case != 'missing-pause':
        with pytest.raises(SemanticGateClosed):
            session.combat_is_executing()
    assert not backend.taps


@pytest.mark.parametrize('page', ['exercise', 'main', 'unknown'])
def test_orphan_result_accepts_exact_exercise_return_and_preserves_task_isolation(page, monkeypatch):
    oracle = Mock()
    for name in ('daily_battle_result_visible', 'campaign_battle_reward_visible',
            'operation_siren_page_visible', 'daily_page_visible',
            'meta_page_visible',
            'main_page_visible', 'event_campaign_page_visible', 'exercise_page_visible'):
        getattr(oracle, name).return_value = False
    oracle.campaign_is_in_map.return_value = False
    oracle.enabled.return_value = False
    oracle.campaign_page_is_normal.return_value = False
    adapter = SimpleNamespace(_require_frame_observation_oracle=lambda: oracle,
        meta_beacon_active=lambda: False, _meta_assist_active=False)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    session.refresh_frame = lambda: None
    session.orphan_combat_result_visible = lambda: True
    session._combat_result_transition_until = 0
    if page == 'main':
        oracle.main_page_visible.return_value = True
        oracle.exercise_page_visible.side_effect = AssertionError('optional Exercise must not break Main')
    elif page == 'exercise':
        oracle.exercise_page_visible.return_value = True
    else:
        monkeypatch.setattr('alas_headless.adapter.semantic.session_combat.time.sleep', lambda _: None)
        monkeypatch.setattr('alas_headless.adapter.semantic.session_combat.time.monotonic', Mock(side_effect=[0, 0, 1]))
    if page == 'unknown':
        with pytest.raises(SemanticGateClosed, match='reviewed stable page'):
            session.recover_orphan_combat_result(timeout_seconds=.1)
    else:
        assert session.recover_orphan_combat_result() == ()
    oracle.click_daily_battle_result.assert_not_called()
    oracle.click.assert_not_called()
