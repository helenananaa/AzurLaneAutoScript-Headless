from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest


@pytest.mark.parametrize('nav,session,reward,expected', [
    ('GACHA_SIDE_NAVBAR', True, True, True),
    ('GACHA_SIDE_NAVBAR', True, False, False),
    ('GACHA_SIDE_NAVBAR', False, True, False),
    ('OTHER_NAVBAR', True, True, False),
    ('SHOP_BOTTOM_NAVBAR', True, False, False),
])
def test_original_navbar_uses_original_gacha_reward_handler_only_in_semantic_mode(nav, session, reward, expected):
    root=Path(__file__).resolve().parents[1]
    source=(patched_alas_root() / 'module/ui/navbar.py').read_text(encoding='utf-8')
    tree=ast.parse(source)
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Navbar')
    method=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='_shop_obstruct_handle')
    namespace={name:object() for name in ('GET_SHIP','GET_ITEMS_1','GET_ITEMS_2')}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'<original-navbar>','exec'),namespace)
    main=SimpleNamespace(handle_get_items_ship=Mock(return_value=reward),appear=Mock(return_value=False))
    with patch('alas_headless.current_semantic_session',return_value=object() if session else None):
        assert namespace['_shop_obstruct_handle'](SimpleNamespace(name=nav),main) is expected
    assert main.handle_get_items_ship.call_count == int(nav=='GACHA_SIDE_NAVBAR' and session)
