from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


@pytest.mark.parametrize('semantic', [False, True])
@pytest.mark.parametrize('notice', [False, True])
def test_weekly_notice_keeps_original_collect_owner(semantic, notice):
    source = patched_alas_root() / 'module/reward/reward.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n, ast.FunctionDef) and n.name == '_reward_mission_weekly')
    namespace = {'MISSION_WEEKLY_RED_DOT':object(), 'logger':Mock()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), namespace)
    adapter = SimpleNamespace(claim_weekly_mission_progress_once=Mock())
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter if semantic else None),
                           image_color_count=Mock(return_value=notice),
                           reward_side_navbar_ensure=Mock(),
                           _reward_mission_collect=Mock(return_value='original result'))
    result = namespace['_reward_mission_weekly'](host)
    if notice:
        assert result == 'original result'
        host.reward_side_navbar_ensure.assert_called_once_with(upper=5)
        host._reward_mission_collect.assert_called_once_with()
    else:
        assert result is False
        host.reward_side_navbar_ensure.assert_not_called()
        host._reward_mission_collect.assert_not_called()
    adapter.claim_weekly_mission_progress_once.assert_not_called()
