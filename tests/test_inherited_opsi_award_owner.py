from tests.alas_test_source import patched_alas_root
import copy
import ast
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.test_presence_driven_reward_refresh import session_for
from tests.test_game_tips_loading_presence import host


def frozen_host(drift=False):
    b, original, _ = host(drift, 'opsi-inherited-award-r148.json')
    o = _FrameBoundSemanticOracle(b.request, b.foreground_component, b.tap,
                                 original.fingerprint, frame_guard=lambda: None)
    a = AlasSemanticAdapter(o, lambda: None, frame_observation_oracle=lambda: o)
    return b, o, a


@pytest.mark.parametrize('drift', [False, True])
def test_actual_inherited_reward_hides_os_page_and_home_before_original_close(drift):
    b, o, a = frozen_host(drift)
    assert a._commission_context is None
    assert o.observation_target_present('reward/award-info/close')
    assert a.appear('GET_ITEMS_1')
    for resource in ('OS_CHECK', 'GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME', 'GET_ADAPTABILITY'):
        assert a.appear(resource) is False, resource
    assert not b.taps


def test_original_os_adaptability_probe_yields_to_known_award_close():
    b, o, a = frozen_host()
    a._operation_siren_combat_active = True
    assert a.appear('GET_ADAPTABILITY') is False
    assert a.appear('GET_ITEMS_1')
    receipt = a.click('GET_ITEMS_1')
    assert receipt.semantic_id == 'reward/award-info/close'
    assert len(b.taps) == 1


def test_native_back_refusal_classifies_current_award_for_original_ui_loop():
    b, o, _ = frozen_host()
    with pytest.raises(SemanticInputBlocked) as caught:
        o.click_operation_siren_back()
    assert caught.value.semantic_id == 'os/page/back'
    assert caught.value.blockers == ('award-info',)
    assert not b.taps


@pytest.mark.parametrize('drift', [False, True])
def test_native_result_probe_reclassifies_map_in_existing_single_refresh(drift):
    b, o, _ = host(drift, 'opsi-result-return-empty-r148.json')
    later, next_o, _ = host(drift, 'opsi-result-return-map-r148.json')
    frame = _FrameBoundSemanticOracle(later.request, later.foreground_component, later.tap,
                                      next_o.fingerprint, frame_guard=lambda: None)
    s, a = session_for(o)
    a._minigame_context = None
    a._frame_observation_oracle = lambda: o
    refreshes = []
    def refreshed():
        refreshes.append(True)
        a._live_oracle = frame
        a._frame_observation_oracle = lambda: frame
    s.refresh_frame = refreshed
    assert s.appear('GET_ADAPTABILITY') is False
    assert len(refreshes) == 1 and not b.taps and not later.taps


@pytest.mark.parametrize('semantic_id, blockers, accepted', [
    ('os/page/back', ('award-info',), True),
    ('os/page/back', ('loading',), True),
    ('os/page/back', ('loading', 'foreign-modal'), False),
    ('os/page/back', ('foreign-modal',), False),
    ('daily/precombat/back', ('loading',), False),
])
def test_original_ui_goto_handles_award_mount_between_page_and_click(semantic_id, blockers, accepted):
    path = Path(os.environ.get('ALAS_TEST_UI_SOURCE',
        str(patched_alas_root() / 'module/ui/ui.py')))
    if not path.exists():
        pytest.skip('retained native ALAS unavailable')
    method = next(v for v in ast.walk(ast.parse(path.read_text(encoding='utf8')))
                  if isinstance(v, ast.FunctionDef) and v.name == 'ui_goto')
    destination = object()
    class Page:
        parent = destination
        check_button = 'OS_CHECK'
        links = {destination: 'GOTO_MAIN'}
    page = Page()
    names = {'Page': SimpleNamespace(init_connection=lambda _: None, iter_check_buttons=lambda: [],
        iter_pages=lambda: [page], clear_connection=lambda: None),
        'GOTO_MAIN': SimpleNamespace(clear_offset=lambda: None),
        'logger': SimpleNamespace(hr=lambda _: None, info=lambda _: None)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), names)
    stage = {'covered': False, 'closed': False}
    def click(_):
        stage['covered'] = True
        raise SemanticInputBlocked(semantic_id, 9465, blockers)
    def additional(**_):
        assert stage['covered']
        stage['closed'] = True
        return True
    runner = SimpleNamespace(interval_clear=lambda _: None, ui_button_interval_reset=lambda _: None,
        _check_semantic_client_version=lambda: None,
        _handle_semantic_orphan_result=lambda: False,
        ui_page_appear=lambda **_: stage['closed'],
        appear=lambda target, *args, **_: target == 'OS_CHECK' and not stage['covered'],
        ui_additional=additional, device=SimpleNamespace(semantic_adapter=SimpleNamespace(
            mail_reward_active=lambda: False), click=click, screenshot=lambda: None))
    if accepted:
        names['ui_goto'](runner, destination)
        assert stage['closed']
    else:
        with pytest.raises(SemanticInputBlocked) as rejected:
            names['ui_goto'](runner, destination)
        assert rejected.value.semantic_id == semantic_id
        assert rejected.value.blockers == blockers
        assert not stage['closed']


@pytest.mark.parametrize('case', ['foreign-package', 'truncated', 'ambiguous-close', 'covered-close'])
def test_reward_close_never_uses_covered_os_back(case):
    b, o, a = frozen_host()
    if case == 'foreign-package':
        b.snapshot['package'] = 'other.package'
    elif case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'ambiguous-close':
        b.buttons['buttons'].append(copy.deepcopy(next(v for v in b.buttons['buttons'] if v['name'] == 'close')))
        b.buttons['button_count'] += 1
    else:
        next(v for v in b.buttons['buttons'] if v['name'] == 'close')['raycast_top'] = False
    with pytest.raises(SemanticGateClosed):
        a.click('GET_ITEMS_1')
    assert not b.taps
