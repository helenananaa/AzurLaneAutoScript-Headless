"""Keep native event tab selection when another T page is visible."""

import ast
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.alas_test_source import patched_alas_root


def method():
    source = patched_alas_root() / 'module/campaign/campaign_ui.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
        if isinstance(n, ast.FunctionDef) and n.name == 'campaign_ensure_aside_20241219')
    switch = Mock()
    scope = {'ASIDE_SWITCH_20241219': switch, 'logger': Mock()}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
    return scope[node.name], switch


@pytest.mark.parametrize('stage,visible,aside,should_switch', [
    ('t1', ('t4', 't5', 't6'), 'part1', True),
    ('t6', ('t1', 't2', 't3'), 'part2', True),
    ('t1', ('t1', 't2', 't3'), 'part1', False),
    ('t6', ('t4', 't5', 't6'), 'part2', False),
    ('a1', ('a1', 'a2', 'a3'), 'part1', False),
    ('b3', ('a1', 'a2', 'a3'), 'part2', True),
    ('ht1', ('ht4', 'ht5', 'ht6'), 'part1', True),
])
def test_exact_stage_presence_controls_semantic_shortcut(stage, visible, aside, should_switch):
    oracle = SimpleNamespace(
        campaign_preparation_state=Mock(return_value=None),
        campaign_page_state=Mock(return_value=SimpleNamespace(stages=[
            SimpleNamespace(stage_code=value) for value in reversed(visible)])),
        _campaign_stage_chapter=lambda value: ''.join(c for c in value if not c.isdigit()))
    adapter = SimpleNamespace(refresh_frame=Mock(), open=lambda: SimpleNamespace(oracle=oracle))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
        config=SimpleNamespace(Campaign_Name=stage.upper()))
    native, switch = method()
    native(host, aside)
    if should_switch:
        switch.set.assert_called_once_with(aside, main=host)
    else:
        switch.set.assert_not_called()


def test_preparation_still_owns_its_existing_page():
    oracle = SimpleNamespace(campaign_preparation_state=Mock(return_value=object()),
        campaign_page_state=Mock(side_effect=AssertionError('preparation owns the page')))
    adapter = SimpleNamespace(refresh_frame=Mock(), open=lambda: SimpleNamespace(oracle=oracle))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
        config=SimpleNamespace(Campaign_Name='T1'))
    native, switch = method()
    native(host, 'part1')
    switch.set.assert_not_called()


def test_nonsemantic_native_switch_is_unchanged():
    host = SimpleNamespace(device=SimpleNamespace())
    native, switch = method()
    native(host, 'part2')
    switch.set.assert_called_once_with('part2', main=host)
