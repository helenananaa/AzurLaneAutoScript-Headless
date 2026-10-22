"""Portable structural captures and pinned native observation method bodies."""

import ast
import copy
import json
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


def capture(name):
    payload = json.loads((FIXTURES / 'campaign-native-transition-structures.json').read_text(encoding='utf-8'))
    return copy.deepcopy(payload['captures'][name])


def own_auto_search(adapter):
    adapter.operation_siren_combat_committed = lambda: False
    adapter.begin_campaign_pre_sortie('12-4')
    context = adapter._campaign_context
    context.sortie_receipt = SimpleNamespace(generation=1)
    context.sortie_proof = SimpleNamespace(map_generation=2)
    context.auto_search_role_state = SimpleNamespace(fleet1_role='mob', fleet2_role='boss')
    context.requested_fleets = (1, 2, 0)
    context.auto_search_started_at = time.monotonic() - 600.0
    context.passive_transition_until = 0.0
    return context


def _method(tree, owner, name):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner)
    function = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    function.decorator_list = []
    # ast.unparse reindents docstrings when moving a method into the fixture
    # class. They do not participate in these observation/watcher contracts.
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)
            and isinstance(function.body[0].value.value, str)):
        function.body.pop(0)
    return function


@lru_cache
def _native_body(owner, name, relative):
    fixture = ast.parse((FIXTURES / 'campaign-native-observation-methods.py').read_text(encoding='utf-8'))
    expected = _method(fixture, owner, name)
    # Local development checks the fixture against the actual current applied
    # series and executes that source. Clean checkouts execute the identical
    # retained method AST, so the boundary regressions never silently skip.
    from tests.test_alas_config_branch_compatibility import UPSTREAM, source
    if UPSTREAM.is_dir():
        current = _method(ast.parse(source(relative)), owner, name)
        assert ast.dump(current) == ast.dump(expected), 'native method fixture drift: ' + relative + ':' + name
        return current
    return expected


def native(owner, name, relative, **namespace):
    body = _native_body(owner, name, relative)
    namespace.setdefault('logger', Mock())
    namespace.setdefault('CampaignEnd', RuntimeError)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(body)], type_ignores=[])),
        relative, 'exec'), namespace)
    return namespace[name]
