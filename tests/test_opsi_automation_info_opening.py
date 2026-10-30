"""Exact native screenshot: combat-opening information before PauseBtn mounts."""
import ast
from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from tests.alas_test_source import patched_alas_root
from tests.test_game_tips_loading_presence import host
from tests.test_presence_driven_reward_refresh import session_for


def actual(drift=False):
    backend, oracle, _ = host(drift, 'opsi-automation-info-opening-20261027.json')
    session, adapter = session_for(oracle)
    adapter._minigame_context = None
    adapter._operation_siren_combat_active = True
    return backend, oracle, session


def dismiss(backend):
    generation = max(backend.snapshot['generation'], backend.buttons['generation'], backend.ui['generation']) + 1
    for packet in (backend.snapshot, backend.buttons, backend.ui):
        packet['generation'] = generation
    for packet, family in ((backend.buttons, 'button'), (backend.ui, 'text'), (backend.ui, 'image')):
        packet[family + 's'] = [v for v in packet[family + 's'] if '/Msgbox(Clone)/' not in v['path']]
        packet[family + '_count'] = len(packet[family + 's'])


@pytest.mark.parametrize('drift', [False, True])
def test_actual_opening_information_original_handler_closes_once_without_pause(drift):
    backend, oracle, session = actual(drift)
    assert not oracle._daily_combat_visible(oracle.read_state())
    assert oracle.combat_automation_info_visible()
    backend.on_tap = lambda: dismiss(backend)
    tree = ast.parse((patched_alas_root() / 'module/combat/combat.py').read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'handle_combat_automation_confirm')
    ns = dict(AUTOMATION_CONFIRM='AUTOMATION_CONFIRM', AUTOMATION_CONFIRM_CHECK='AUTOMATION_CONFIRM_CHECK')
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<native-combat-handler>', 'exec'), ns)
    runner = SimpleNamespace(appear=lambda b, **_: session.appear(b),
                             appear_then_click=lambda b, **_: session.click_if_present(b) is not None)
    assert ns['handle_combat_automation_confirm'](runner)
    assert len(backend.taps) == 1
    # Only this information owner was extended; generic combat presence still
    # requires its existing PauseBtn proof.
    assert not oracle.daily_combat_visible()
    assert not oracle.combat_automation_info_visible()


@pytest.mark.parametrize('case', ['foreign-title', 'foreign-choice', 'no-painting', 'no-weapons',
                                  'no-timer', 'bad-timer', 'duplicate-timer', 'covered',
                                  'duplicate-choice', 'foreign-package', 'generation-gap'])
def test_opening_without_complete_owner_or_action_identity_never_clicks(case):
    backend, oracle, _ = actual()
    if case in ('foreign-title', 'foreign-choice'):
        suffix = '/help_tpl' if case == 'foreign-title' else '/custom_button_1(Clone)/pic'
        next(v for v in backend.ui['texts'] if v['path'].endswith(suffix))['text'] = '购买资源'
    elif case in ('no-painting', 'no-weapons'):
        fragment = '/SkillPainting(Clone)' if case == 'no-painting' else '/Weapon_button_container/'
        backend.buttons['buttons'] = [v for v in backend.buttons['buttons'] if fragment not in v['path']]
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif case in ('no-timer', 'bad-timer', 'duplicate-timer'):
        timer = next(v for v in backend.ui['texts'] if v['path'].endswith('/CombatUIStandard(Clone)/Timer/Text'))
        if case == 'no-timer': backend.ui['texts'].remove(timer)
        elif case == 'bad-timer': timer['text'] = 'unknown'
        else: backend.ui['texts'].append(dict(timer))
        backend.ui['text_count'] = len(backend.ui['texts'])
    elif case in ('covered', 'duplicate-choice'):
        button = next(v for v in backend.buttons['buttons'] if v['name'] == 'custom_button_1(Clone)')
        if case == 'covered': button['raycast_top'] = False
        else: backend.buttons['buttons'].append(dict(button)); backend.buttons['button_count'] += 1
    elif case == 'foreign-package': backend.snapshot['package'] = 'other.package'
    else: backend.ui['generation'] += 3
    with pytest.raises(SemanticGateClosed):
        oracle.click_combat_automation_info()
    assert not backend.taps


def test_accepted_information_close_does_not_retry_if_combat_owner_disappears():
    backend, oracle, _ = actual()
    def closed():
        dismiss(backend)
        backend.buttons['buttons'] = []
        backend.buttons['button_count'] = 0
    backend.on_tap = closed
    with pytest.raises(SemanticGateClosed, match='did not restore'):
        oracle.click_combat_automation_info()
    assert len(backend.taps) == 1
