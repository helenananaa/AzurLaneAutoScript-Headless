"""An entry raycast remount grants no input and leaves retries to ALAS."""
from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticTargetNotActionable
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('case', ['settling', 'loading', 'loading-covered',
    'loading-ready', 'loading-ready-covered', 'ready', 'disabled', 'covered', 'ambiguous'])
def test_login_input_classifies_preinput_readiness_without_dispatch(case):
    root = 'UICamera/Canvas/UIMain/LoginUI2(Clone)'
    buttons = [make_button('LoginUI2(Clone)', root, raycast_top=case in
        ('ready', 'loading-ready', 'loading-ready-covered'))]
    if case == 'disabled':
        buttons[0]['interactable'] = False
    if case == 'covered':
        buttons.append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    if case.startswith('loading'):
        buttons.append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        if case in ('loading-covered', 'loading-ready-covered'):
            buttons.append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    if case == 'ambiguous':
        buttons.append(make_button('LoginUI2(Clone)', root, raycast_top=False))
    backend = FakeBackend(buttons)
    oracle = make_oracle(backend)
    if case == 'ready':
        assert oracle.click('login/enter').semantic_id == 'login/enter'
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed) as error:
            oracle.click('login/enter')
        # All unique non-actionable targets are pre-input refusals. Duplicate
        # targets retain the fatal ambiguity classification.
        assert isinstance(error.value, SemanticTargetNotActionable) == (
            case not in ('ambiguous', 'loading-ready-covered'))
        if case == 'loading-ready':
            assert error.value.__cause__.blockers == ('loading',)
        assert backend.taps == []


def login_function():
    source = patched_alas_root() / 'module/handler/login.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'LoginHandler')
    function = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == '_handle_app_login')
    namespace = {'Timer': lambda *a, **k: Mock(reached=Mock(return_value=True)),
                 'logger': Mock(), 'LOGIN_CHECK': object()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(source), 'exec'), namespace)
    return namespace['_handle_app_login']


@pytest.mark.parametrize('first_error', [None, 'settling', 'foreign', 'wrong-target'])
def test_original_login_retries_only_refused_entry_without_claiming_login_success(first_error):
    semantic = SimpleNamespace(server_maintenance_visible=lambda: False,
        login_update_in_progress=lambda: False, restart_game_after_update=lambda: False)
    error = {'settling': SemanticTargetNotActionable('login/enter', 10),
             'foreign': SemanticGateClosed('semantic input is blocked by unknown overlay'),
             'wrong-target': SemanticTargetNotActionable('other/target', 10)}.get(first_error)
    device = SimpleNamespace(semantic_adapter=semantic, screenshot_interval_set=Mock(),
        stuck_record_clear=Mock(), click_record_clear=Mock(), screenshot=Mock(),
        get_orientation=Mock(), click=Mock(side_effect=[error, None] if error else [None]))
    caller = SimpleNamespace(device=device, is_in_main=Mock(side_effect=[False, False, True]
        if first_error == 'settling' else [False, True]), match_template_color=Mock(return_value=True))
    if first_error in ('foreign', 'wrong-target'):
        with pytest.raises(SemanticGateClosed):
            login_function()(caller)
        assert device.click.call_count == 1
    else:
        login_function()(caller)
        assert device.click.call_count == (2 if first_error == 'settling' else 1)
        assert device.screenshot.call_count == (3 if first_error == 'settling' else 2)
