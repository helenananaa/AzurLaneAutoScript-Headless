import ast
import copy
import os
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_presence_driven_reward_refresh import session_for


@pytest.mark.parametrize('drift', [False, True])
def test_actual_combat_information_uses_original_handler_once(drift):
    b, o, _ = host(drift, 'opsi-combat-automation-info-r148.json')
    s, a = session_for(o)
    a._minigame_context = None
    a._operation_siren_combat_active = True
    assert o.combat_automation_info_visible()
    assert s.appear('AUTOMATION_CONFIRM_CHECK')
    path = Path(__file__).parents[1] / 'artifacts/continuity-20261004/alas-runtime/module/combat/combat.py'
    if not path.exists():
        pytest.skip('retained ALAS unavailable')
    method = next(v for v in ast.walk(ast.parse(path.read_text(encoding='utf8')))
                  if isinstance(v, ast.FunctionDef) and v.name == 'handle_combat_automation_confirm')
    names = {'AUTOMATION_CONFIRM_CHECK': 'AUTOMATION_CONFIRM_CHECK', 'AUTOMATION_CONFIRM': 'AUTOMATION_CONFIRM'}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), names)
    def closed():
        for projection in (b.snapshot, b.buttons, b.ui):
            projection['generation'] = 9339
        b.buttons['buttons'] = [v for v in b.buttons['buttons'] if '/Msgbox(Clone)/' not in v['path']]
        b.buttons['button_count'] = len(b.buttons['buttons'])
        b.ui['texts'] = [v for v in b.ui['texts'] if '/Msgbox(Clone)/' not in v['path']]
        b.ui['text_count'] = len(b.ui['texts'])
    b.on_tap = closed
    runner = SimpleNamespace(appear=lambda button, **_: s.appear(button),
        appear_then_click=lambda button, **_: s.click_if_present(button) is not None)
    assert names['handle_combat_automation_confirm'](runner)
    assert len(b.taps) == 1 and o.daily_combat_visible()


@pytest.mark.parametrize('case', ['foreign-package', 'foreign-text', 'duplicate-choice', 'covered', 'loading'])
def test_combat_information_input_keeps_typed_boundaries(case):
    b, o, _ = host(fixture='opsi-combat-automation-info-r148.json')
    if case == 'foreign-package':
        b.snapshot['package'] = 'other.package'
    elif case == 'foreign-text':
        next(v for v in b.ui['texts'] if v['path'].endswith('help_panel/list/help_tpl'))['text'] = '是否购买资源？'
    elif case == 'duplicate-choice':
        b.buttons['buttons'].append(copy.deepcopy(next(v for v in b.buttons['buttons'] if v['name'] == 'custom_button_1(Clone)')))
        b.buttons['button_count'] += 1
    elif case == 'covered':
        next(v for v in b.buttons['buttons'] if v['name'] == 'custom_button_1(Clone)')['raycast_top'] = False
    else:
        from tests.semantic_support.observer_fixtures import make_button
        b.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        o.click_combat_automation_info()
    assert not b.taps


def test_original_semantic_combat_checks_information_after_legacy_timer():
    path = Path(os.environ.get('ALAS_TEST_COMBAT_SOURCE',
        str(Path(__file__).parents[1] / 'artifacts/continuity-20261004/alas-runtime/module/combat/combat.py')))
    if not path.is_file():
        pytest.skip('retained ALAS unavailable')
    method = next(v for v in ast.walk(ast.parse(path.read_text(encoding='utf8')))
                  if isinstance(v, ast.FunctionDef) and v.name == 'combat_execute')
    names = {'logger': SimpleNamespace(info=lambda _: None),
             'Timer': lambda _: SimpleNamespace(start=lambda: None, reached=lambda: True)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), names)
    calls = []
    runner = SimpleNamespace(loop=lambda: iter([0]),
        device=SimpleNamespace(semantic_adapter=object(), stuck_record_clear=lambda: None,
                               click_record_clear=lambda: None),
        handle_combat_automation_confirm=lambda: calls.append(True) or True)
    for name in ('submarine_call_reset', 'combat_auto_reset', 'combat_manual_reset',
                 'handle_story_skip', 'handle_combat_auto', 'handle_combat_manual',
                 'handle_submarine_call', 'handle_popup_confirm', 'handle_urgent_commission',
                 'handle_guild_popup_cancel', 'handle_vote_popup', 'handle_mission_popup_ack',
                 'handle_battle_status', 'handle_get_items'):
        setattr(runner, name, lambda *args, **kwargs: False)
    names['combat_execute'](runner)
    assert calls == [True]
