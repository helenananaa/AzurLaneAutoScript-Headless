"""A completed native tab switch needs observation, not a redundant input."""
from tests.alas_test_source import patched_alas_root
import ast
import copy
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.test_game_tips_loading_presence import host
from tests.test_presence_driven_reward_refresh import session_for
from tests.semantic_support.observer_fixtures import make_button


def frozen_host(drift=False):
    b, original, _ = host(drift, 'shop-merit-selected-r151.json')
    o = _FrameBoundSemanticOracle(b.request, b.foreground_component, b.tap,
        original.fingerprint, frame_guard=lambda: None)
    return b, o


@pytest.mark.parametrize('drift', [False, True])
def test_actual_selected_merit_tab_continues_without_input(drift):
    b, o = frozen_host(drift)
    assert o.read_state().generation == 13649
    assert o.shop_selected_tab_label() == '军需'
    assert o.click_shop_tab('军需') is None
    assert not b.taps and o.input_dispatch_count == 0


def test_native_switch_and_device_recheck_selected_tab_after_no_input():
    b, o = frozen_host()
    s, _ = session_for(o)
    root = patched_alas_root()
    if not root.is_dir():
        pytest.skip('retained native ALAS unavailable')
    switch_source = root / 'module/ui/switch.py'
    cls = next(v for v in ast.parse(switch_source.read_text(encoding='utf8')).body
               if isinstance(v, ast.ClassDef) and v.name == 'Switch')
    methods = [v for v in cls.body if isinstance(v, ast.FunctionDef)
               and v.name in ('set', 'click', 'get_data')]
    messages = []
    ns = {'logger': SimpleNamespace(info=messages.append, attr=lambda *a: None)}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(switch_source), 'exec'), ns)
    control = root / 'module/device/control.py'
    click = next(v for v in ast.walk(ast.parse(control.read_text(encoding='utf8')))
                 if isinstance(v, ast.FunctionDef) and v.name == 'click')
    control_ns = {'logger': SimpleNamespace(info=messages.append)}
    exec(compile(ast.Module(body=[click], type_ignores=[]), str(control), 'exec'), control_ns)
    timer = SimpleNamespace(reset=lambda: timer, clear=lambda: timer, reached=lambda: True)
    button = SimpleNamespace(name='TAB_MERIT')
    device = SimpleNamespace(semantic_adapter=s, handle_control_check=lambda b: None,
                             screenshot=lambda: None)
    device.click = MethodType(control_ns['click'], device)
    main = SimpleNamespace(device=device)
    observations = iter(['TAB_GENERAL', 'TAB_MERIT'])
    runner = SimpleNamespace(name='shop_tab', state_list=[{'state': 'TAB_MERIT', 'click_button': button}],
        is_selector=True, set_unknown_timer=timer, set_click_timer=timer,
        get=lambda main: next(observations), handle_additional=lambda main: False)
    for name in ('click', 'get_data'):
        setattr(runner, name, MethodType(ns[name], runner))
    assert ns['set'](runner, 'TAB_MERIT', main) is True
    assert not b.taps and any('without input' in m for m in messages)


@pytest.mark.parametrize('case', ['wrong-tab', 'duplicate', 'foreign', 'truncated', 'covered'])
def test_selected_continuation_requires_clear_unique_current_identity(case):
    b, o = frozen_host()
    if case == 'wrong-tab':
        label = '不存在的页签'
    else:
        label = '军需'
    if case == 'duplicate':
        b.ui['texts'].append(copy.deepcopy(next(t for t in b.ui['texts']
                            if t['path'].endswith('/selected/Label'))))
        b.ui['text_count'] = len(b.ui['texts'])
    elif case == 'foreign':
        b.snapshot['package'] = 'other.package'
    elif case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'covered':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        o.click_shop_tab(label)
    assert not b.taps and o.input_dispatch_count == 0
