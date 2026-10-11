"""Original synchronous oil recovery has a Dorm child, not a second task engine."""
import ast
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_alas_config_branch_compatibility import source


@pytest.mark.parametrize('fails', [False, True])
def test_original_child_restores_exact_parent_even_when_unavailable(fails):
    backend, _, adapter = host(fixture='commission-oil-maxed-r182.json')
    adapter.begin_commission()
    parent = adapter._commission_context
    tree = ast.parse(source('module/dorm/dorm.py'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RewardDorm')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'dorm_food_run')
    ns = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<original-dorm-recovery>', 'exec'), ns)
    def child(amount):
        assert amount == 10
        assert adapter._commission_context is None
        assert adapter._dorm_context is not None
        if fails: raise RuntimeError('unsupported food port')
        return 'original-return'
    native = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
        _dorm_food_run_alas_state_machine=child)
    if fails:
        with pytest.raises(RuntimeError, match='unsupported food port'):
            ns['dorm_food_run'](native, 10)
    else:
        assert ns['dorm_food_run'](native, 10) == 'original-return'
    assert adapter._commission_context is parent
    assert adapter._dorm_context is None
    assert not backend.taps


@pytest.mark.parametrize('case', ['ordinary-nesting', 'no-parent', 'mail', 'login'])
def test_unrelated_nesting_is_not_admitted(case):
    backend, _, adapter = host(fixture='commission-oil-maxed-r182.json')
    if case != 'no-parent': adapter.begin_commission()
    if case == 'mail': adapter._mail_context = object()
    if case == 'login': adapter._login_flow = SimpleNamespace(active=True)
    parent = adapter._commission_context
    with pytest.raises(SemanticGateClosed):
        adapter.begin_dorm(commission_recovery=case != 'ordinary-nesting')
    assert adapter._commission_context is parent
    assert adapter._dorm_context is None
    assert not backend.taps


def test_task_reset_does_not_retain_suspended_parent():
    _, _, adapter = host(fixture='commission-oil-maxed-r182.json')
    adapter.begin_commission()
    adapter.begin_dorm(commission_recovery=True)
    adapter.reset_task_state()
    adapter.end_dorm()
    assert adapter._commission_context is None


def test_original_zero_quantity_does_not_open_child_context():
    tree = ast.parse(source('module/dorm/dorm.py'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RewardDorm')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'dorm_food_run')
    ns = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<original-dorm-recovery>', 'exec'), ns)
    adapter, child = Mock(), Mock(return_value=None)
    native = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
        _dorm_food_run_alas_state_machine=child)
    assert ns['dorm_food_run'](native, 0) is None
    adapter.begin_dorm.assert_not_called()
    child.assert_called_once_with(0)
