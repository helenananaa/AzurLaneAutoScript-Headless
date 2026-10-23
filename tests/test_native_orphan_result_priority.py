"""Exact orphan rewards precede retained pages in original ALAS navigation."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def native_ui():
    root = os.environ.get('ALAS_TEST_ROOT')
    if not root:
        pytest.skip('set ALAS_TEST_ROOT to the verified patched ALAS tree')
    tree = ast.parse(Path(root, 'module/ui/ui.py').read_text(encoding='utf-8'))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def bind(host, ns, name):
    exec(compile(ast.fix_missing_locations(ast.Module(body=[native_ui()[name]],
        type_ignores=[])), '<native orphan priority>', 'exec'), ns)
    setattr(host, name, lambda *a, **kw: ns[name](host, *a, **kw))


@pytest.mark.parametrize('orphan', [False, True])
def test_native_discovery_drains_exact_orphan_before_accepting_covered_campaign(orphan):
    page = SimpleNamespace(name='page_campaign', check_button=object())
    present = [orphan]
    events = []
    def recover():
        events.append('recover')
        present[0] = False
    adapter = SimpleNamespace(orphan_combat_result_visible=lambda: present[0],
        recover_orphan_combat_result=recover, mail_reward_active=lambda: False)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,
        has_cached_image=True, screenshot=Mock()),
        _check_semantic_client_version=Mock(), config=SimpleNamespace())
    def appear(**kwargs):
        events.append('page')
        assert not present[0], 'covered page must never win'
        return True
    host.ui_page_appear = appear
    timer = SimpleNamespace(reached=lambda: False, reset=Mock())
    timer.start = lambda: timer
    ns = dict(logger=Mock(), run_once=lambda f: f, Timer=lambda *a, **kw: timer,
        Page=SimpleNamespace(iter_pages=lambda: [page]), page_mail=page)
    bind(host, ns, '_handle_semantic_orphan_result')
    bind(host, ns, 'ui_get_current_page')
    assert host.ui_get_current_page() is page
    assert events == (['recover', 'page'] if orphan else ['page'])
    assert host.device.screenshot.call_count == int(orphan)


@pytest.mark.parametrize('orphan', [False, True])
def test_native_ensure_shortcut_keeps_same_priority_without_duplicate_navigation(orphan):
    events = []
    adapter = SimpleNamespace(orphan_combat_result_visible=lambda: orphan,
        recover_orphan_combat_result=lambda: events.append('recover'))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
        ui_page_appear=lambda **kw: events.append('page') or True)
    ns = dict(logger=Mock())
    bind(host, ns, '_handle_semantic_orphan_result')
    bind(host, ns, 'ui_ensure')
    assert host.ui_ensure('campaign') is False
    assert events == (['recover', 'page'] if orphan else ['page'])


@pytest.mark.parametrize('orphan', [False, True])
def test_native_goto_recovers_newly_mounted_orphan_before_accepting_destination(orphan):
    method = native_ui()['ui_goto']
    loop = next(n for n in ast.walk(method) if isinstance(n, ast.While))
    # Execute the actual native loop through destination acceptance. Later
    # page-edge input must never be necessary in this already-arrived case.
    destination_check = next(i for i, n in enumerate(loop.body) if isinstance(n, ast.If)
        and isinstance(n.test, ast.Call) and isinstance(n.test.func, ast.Attribute)
        and n.test.func.attr == 'ui_page_appear')
    loop.body = loop.body[:destination_check + 1]
    events, present = [], [orphan]
    def recover():
        events.append('recover')
        present[0] = False
    adapter = SimpleNamespace(orphan_combat_result_visible=lambda: present[0],
        recover_orphan_combat_result=recover)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,
        has_cached_image=True, screenshot=Mock()), _check_semantic_client_version=Mock())
    def appear(**kwargs):
        assert not present[0], 'retained destination is covered'
        events.append('page')
        return True
    host.ui_page_appear = appear
    ns = dict(self=host, logger=Mock(), skip_first_screenshot=True,
        destination='campaign', offset=(30, 30), GOTO_MAIN=SimpleNamespace(clear_offset=Mock()))
    bind(host, ns, '_handle_semantic_orphan_result')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])),
        '<native goto result priority>', 'exec'), ns)
    assert events == (['recover', 'page'] if orphan else ['page'])
    assert host.device.screenshot.call_count == int(orphan)
