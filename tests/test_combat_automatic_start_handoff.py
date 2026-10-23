"""Run the patched original preparation handler through a no-input handoff."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import (SemanticGateClosed, SemanticTargetMissing,
    build_alas_combat_trace_frame, prepare_alas_combat_resource_action)
from tests.test_alas_combat_observer import frame, qualified_manifest


def native_method():
    root = os.environ.get('ALAS_TEST_ROOT')
    if not root:
        pytest.skip('set ALAS_TEST_ROOT to the verified patched ALAS tree')
    path = Path(root, 'module/combat/combat.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == 'handle_battle_preparation')
    scope = {'BATTLE_PREPARATION': object()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 str(path), 'exec'), scope)
    return scope[method.name]


@pytest.mark.parametrize('surface', ['combat', 'loader', 'unchanged', 'malformed', 'unbound'])
def test_original_loop_requires_fresh_positive_progress_after_target_disappears(surface):
    oracle = SimpleNamespace(daily_combat_visible=Mock(return_value=surface == 'combat'),
        daily_battle_loading_visible=Mock(return_value=surface == 'loader'))
    if surface == 'malformed':
        oracle.daily_combat_visible.side_effect = SemanticGateClosed('observer snapshot is stale')
    adapter = SimpleNamespace(open=lambda: SimpleNamespace(_frame_or_live_observation_oracle=lambda: oracle))
    host = SimpleNamespace(device=SimpleNamespace(screenshot=Mock(),
        semantic_adapter=None if surface == 'unbound' else adapter),
        appear_then_click=Mock(side_effect=SemanticTargetMissing('combat action resource is not visible')))
    if surface in ('combat', 'loader'):
        assert native_method()(host)
    else:
        with pytest.raises(SemanticGateClosed):
            native_method()(host)
    assert host.device.screenshot.call_count == int(surface != 'unbound')
    # No action is retried in this handler.
    host.appear_then_click.assert_called_once()


def test_ordinary_start_keeps_original_behavior_and_does_not_refresh_again():
    host = SimpleNamespace(device=SimpleNamespace(screenshot=Mock()),
                           appear_then_click=Mock(return_value=True))
    assert native_method()(host)
    host.device.screenshot.assert_not_called()


def test_missing_combat_resource_is_classified_before_any_input():
    manifest = qualified_manifest()
    raw = frame(10, ())
    _, typed = build_alas_combat_trace_frame(raw['snapshot'], raw['buttons'], raw['ui'], manifest)
    with pytest.raises(SemanticTargetMissing, match='resource is not visible'):
        prepare_alas_combat_resource_action(typed, manifest, 'BATTLE_PREPARATION')
