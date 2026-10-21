"""Known automation information must reach ALAS' existing combat handler."""
import ast
from types import SimpleNamespace
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_presence_driven_reward_refresh import session_for
from tests.test_alas_config_branch_compatibility import source
from tests.semantic_support.observer_fixtures import make_button


def actual(drift=False):
    backend, oracle, _ = host(drift, 'hard-auto-search-information-r29.json')
    session, adapter = session_for(oracle)
    adapter._minigame_context = None
    adapter.begin_campaign_pre_sortie('12-4', mode='hard')
    context = adapter._campaign_context
    context.sortie_receipt = SimpleNamespace(generation=1)
    context.sortie_proof = SimpleNamespace(map_generation=2)
    context.auto_search_role_state = SimpleNamespace(fleet1_role='all', fleet2_role='standby')
    return backend, oracle, adapter, session


@pytest.mark.parametrize('drift', [False, True])
def test_native_moving_enters_loading_and_original_handler_closes_exact_information(drift):
    backend, oracle, adapter, session = actual(drift)
    assert session.combat_is_loading() is True
    assert session.combat_is_executing() is False
    assert session.appear('AUTOMATION_CONFIRM_CHECK') is True
    tree = ast.parse(source('module/combat/combat.py'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == 'handle_combat_automation_confirm')
    namespace = dict(AUTOMATION_CONFIRM='AUTOMATION_CONFIRM',
                     AUTOMATION_CONFIRM_CHECK='AUTOMATION_CONFIRM_CHECK')
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<native-combat-handler>', 'exec'), namespace)
    def closed():
        generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui)) + 1
        for packet in (backend.snapshot, backend.buttons, backend.ui): packet['generation'] = generation
        for packet, kind in ((backend.buttons, 'button'), (backend.ui, 'text'), (backend.ui, 'image')):
            packet[kind + 's'] = [r for r in packet[kind + 's'] if '/Msgbox(Clone)/' not in r['path']]
            packet[kind + '_count'] = len(packet[kind + 's'])
    backend.on_tap = closed
    runner = SimpleNamespace(appear=lambda b, **_: session.appear(b),
        appear_then_click=lambda b, **_: session.click_if_present(b) is not None)
    assert namespace['handle_combat_automation_confirm'](runner)
    assert len(backend.taps) == 1
    assert session.combat_is_executing() is True


@pytest.mark.parametrize('case', ['foreign-text', 'extra-overlay', 'covered', 'foreign-package'])
def test_unknown_or_covered_popup_never_opens_official_loading_handoff(case):
    backend, oracle, _, session = actual()
    if case == 'foreign-text':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/help_tpl'))['text'] = '是否购买资源？'
    elif case == 'extra-overlay':
        backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'covered':
        next(b for b in backend.buttons['buttons'] if b['name'] == 'custom_button_1(Clone)')['raycast_top'] = False
    else: backend.snapshot['package'] = 'other.package'
    if case == 'foreign-package':
        with pytest.raises(SemanticGateClosed): session.combat_is_loading()
    else:
        assert session.combat_is_loading() is False
        assert session.combat_is_executing() is False
    with pytest.raises(SemanticGateClosed): oracle.click_combat_automation_info()
    assert not backend.taps
