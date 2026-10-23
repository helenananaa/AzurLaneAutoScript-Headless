from tests.alas_test_source import patched_alas_root
import ast
import copy
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import SemanticTargetMissing
from tests.test_game_tips_loading_presence import host


def frozen_host(drift=False):
    b, original, _ = host(drift, 'supply-pack-selected-r147.json')
    # The retained lease is immutable. Its later UI projection must never
    # be followed by another earlier live button projection in this replay.
    o = _FrameBoundSemanticOracle(b.request, b.foreground_component, b.tap,
        original.fingerprint, frame_guard=lambda: None)
    a = AlasSemanticAdapter(o, lambda: None, frame_observation_oracle=lambda: o)
    return b, o, a


@pytest.mark.parametrize('drift', [False, True])
def test_actual_selected_page_yields_redundant_check_click_without_input(drift):
    b, o, a = frozen_host(drift)
    a.begin_supply_pack()
    assert o.read_state().generation == 7762
    assert o.gift_pack_page_visible()
    assert a.appear('SUPPLY_PACK_CHECK')
    with pytest.raises(SemanticTargetMissing):
        a.click('SUPPLY_PACK_CHECK')
    assert not b.taps


def test_original_supply_pack_loop_rechecks_page_after_selection_transition():
    b, o, a = frozen_host()
    a.begin_supply_pack()
    root = patched_alas_root()
    source = root / 'module/freebies/supply_pack.py'
    base = root / 'module/base/base.py'
    if not source.is_file():
        pytest.skip('retained native ALAS unavailable')
    cls = next(v for v in ast.parse(source.read_text(encoding='utf8')).body
               if isinstance(v, ast.ClassDef) and v.name == 'SupplyPack_250814')
    goto = next(v for v in cls.body if isinstance(v, ast.FunctionDef) and v.name == 'goto_supply_pack')
    then_click = next(v for v in ast.walk(ast.parse(base.read_text(encoding='utf8')))
                      if isinstance(v, ast.FunctionDef) and v.name == 'appear_then_click')
    # Page identity is used as the original links key.
    class Page:
        check_button = 'SUPPLY_PACK_CHECK'
    pack = Page()
    names = {'page_shop': SimpleNamespace(links={pack: 'SHOP_GOTO_SUPPLY_PACK'}),
             'page_supply_pack': pack, 'logger': SimpleNamespace(info=lambda _: None)}
    exec(compile(ast.Module(body=[goto, then_click], type_ignores=[]), str(source), 'exec'), names)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.click = lambda button, require_present: a.click(button)
    checks = iter([False, True])
    runner = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),
        config=SimpleNamespace(), ensure_button=lambda button: button,
        appear=lambda button, **_: a.appear(button),
        match_template_color=lambda *args, **_: next(checks), loop=lambda: iter(range(2)))
    runner.appear_then_click = MethodType(names['appear_then_click'], runner)
    names['goto_supply_pack'](runner)
    assert not b.taps


@pytest.mark.parametrize('case', ['foreign-package', 'truncated', 'unselected', 'ambiguous-toggle'])
def test_unproven_page_check_click_remains_closed(case):
    b, o, a = frozen_host()
    a.begin_supply_pack()
    if case == 'foreign-package':
        b.snapshot['package'] = 'other.package'
    elif case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'unselected':
        next(t for t in b.ui['toggles'] if 'giftPackShop' in t['path'])['checked'] = False
    else:
        b.ui['toggles'].append(copy.deepcopy(next(t for t in b.ui['toggles'] if 'giftPackShop' in t['path'])))
        if 'toggle_count' in b.ui:
            b.ui['toggle_count'] += 1
    with pytest.raises(SemanticGateClosed):
        a.click('SUPPLY_PACK_CHECK')
    assert not b.taps
