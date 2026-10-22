"""Exercise the actual patched ALAS animation wait, not a second polling loop."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def native_method(relative, name):
    root = os.environ.get('ALAS_TEST_ROOT')
    if not root:
        pytest.skip('set ALAS_TEST_ROOT to a verified patched ALAS checkout')
    source = Path(root) / relative
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = {'logger': Mock(), 'MAP_PREPARATION': object()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), 'exec'), scope)
    return scope[name], tree


@pytest.mark.parametrize('values, expected', [
    ([.13, .58, 1.0], [False, False, True]),
    ([.4, .4, .4], [False, False, True]),
    ([1.0, 1.0, 1.0], [False, False, True]),
])
def test_native_preparation_waits_for_animation_without_inventing_full_clear(values, expected):
    method, tree = native_method('module/map/map_operation.py', 'handle_map_preparation')
    host = SimpleNamespace(appear=Mock(return_value=True),
        config=SimpleNamespace(MAP_HAS_CLEAR_PERCENTAGE=True, MAP_IS_ONE_TIME_STAGE=False),
        info_bar_count=Mock(return_value=0), get_map_clear_percentage=Mock(side_effect=values),
        map_clear_percentage_prev=-1,
        map_clear_percentage_timer=SimpleNamespace(reset=Mock(), reached=Mock(side_effect=[False, True])))
    assert [method(host) for _ in values] == expected
    enter = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'enter_map')
    semantic_branch = next(n for n in ast.walk(enter) if isinstance(n, ast.If)
                          and 'semantic_adapter.campaign_pre_sortie_active()' in ast.unparse(n.test))
    assert any(isinstance(n, ast.If) and ast.unparse(n.test) == 'self.handle_map_preparation()'
               for n in ast.walk(semantic_branch))


@pytest.mark.parametrize('clear_percentage, one_time', [(False, False), (True, True)])
def test_native_optional_stage_branches_keep_their_existing_behavior(clear_percentage, one_time):
    method, _ = native_method('module/map/map_operation.py', 'handle_map_preparation')
    host = SimpleNamespace(appear=Mock(return_value=True),
        config=SimpleNamespace(MAP_HAS_CLEAR_PERCENTAGE=clear_percentage, MAP_IS_ONE_TIME_STAGE=one_time),
        get_map_clear_percentage=Mock(side_effect=AssertionError('unrelated capability')))
    assert method(host)
    host.get_map_clear_percentage.assert_not_called()


def test_native_progress_port_does_not_require_optional_star_images(monkeypatch):
    import alas_headless
    method, _ = native_method('module/handler/fast_forward.py', 'get_map_clear_percentage')
    session = SimpleNamespace(campaign_map_clear_percentage=Mock(return_value=.4),
        campaign_map_achievement_state=Mock(side_effect=AssertionError('unrelated stars')))
    monkeypatch.setattr(alas_headless, 'current_semantic_session', lambda: session)
    assert method(SimpleNamespace()) == .4
    session.campaign_map_clear_percentage.assert_called_once_with()
