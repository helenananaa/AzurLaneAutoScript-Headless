from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize('bought,coins,semantic,expected', [
    (0, 22500, True, 1), (1, 22500, True, 14),
    (0, 4898, True, 1), (1, 4898, True, 3),
    (4, 0, True, 0), (15, 22500, True, 0),
    (0, 22500, False, 15), (0, 0, False, 1)])
def test_original_count_preserves_policy_but_splits_native_free_panel(bought, coins, semantic, expected):
    path = patched_alas_root() / 'module/meowfficer/buy.py'
    tree = ast.parse(path.read_text(encoding='utf8'))
    scope = dict(BUY_MAX=15, BUY_PRIZE=1500,
                 logger=SimpleNamespace(attr=Mock(), info=Mock(), warning=Mock()))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and n.name in ('meow_get_buy_count', '_meow_get_buy_count')]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    state = SimpleNamespace(purchased=bought, purchase_total=15, coins=coins)
    adapter = SimpleNamespace(meowfficer_dock_state=lambda: state) if semantic else None
    scope.update(MEOWFFICER=SimpleNamespace(ocr=lambda _: (15-bought, bought, 15)),
                 MEOWFFICER_COINS=SimpleNamespace(ocr=lambda _: coins))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, image=None),
        loop=lambda **_: iter(range(1)), _meow_get_buy_count=scope['_meow_get_buy_count'])
    assert scope['meow_get_buy_count'](host, 15, -1) == expected
