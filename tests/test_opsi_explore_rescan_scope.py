from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

@pytest.mark.parametrize('explore,empty,rescan,skip', [
    (True,True,True,False),(False,True,True,True),
    (False,False,True,False),(True,True,False,False)])
def test_original_alas_explore_keeps_full_map_rescan(explore,empty,rescan,skip):
    source=patched_alas_root() / 'module/os/map.py'
    if not source.exists():pytest.skip('materialized ALAS absent')
    tree=ast.parse(source.read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.If)
              and 'semantic_empty' in ast.unparse(n.test))
    assert eval(compile(ast.Expression(node.test),str(source),'eval'),
        {'self':SimpleNamespace(is_in_task_explore=explore),'semantic_empty':empty,'rescan':rescan}) is skip
