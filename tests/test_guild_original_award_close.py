import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize('case', ['dismissed', 'covered', 'stale', 'unavailable'])
def test_original_guild_award_helper_waits_for_fresh_dismissal_without_repeating_input(case):
    path = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/guild/logistics.py'
    tree = ast.parse(path.read_text(encoding='utf8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'close_awards')
    visible = Mock(side_effect=[True, False]) if case == 'dismissed' else Mock(return_value=case == 'covered')
    oracle = SimpleNamespace(
        enabled=lambda target: target == 'reward/award-info/close' and case != 'unavailable',
        click=Mock(return_value=SimpleNamespace(generation=10)),
        read_state=lambda: SimpleNamespace(generation=10 if case == 'stale' else 11),
        award_info_page_visible=visible)
    host = SimpleNamespace(device=SimpleNamespace(sleep=Mock()))
    scope = {'adapter': SimpleNamespace(oracle=oracle), 'self': host}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    if case == 'dismissed':
        scope['close_awards']()
        assert visible.call_count == 2
    else:
        with pytest.raises(RuntimeError, match='Guild award close'):
            scope['close_awards']()
    assert oracle.click.call_count == (0 if case == 'unavailable' else 1)
