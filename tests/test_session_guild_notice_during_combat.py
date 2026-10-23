from tests.alas_test_source import patched_alas_root
import copy
import ast
import json
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend, make_button


def retained_notice(case='ready'):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-r30-guild-overlay-failed-frame-r1.json'
    if not path.exists():
        pytest.skip('retained r30 guild notice unavailable')
    f = json.loads(path.read_text(encoding='utf-8'))['failure_observation']
    b = FakeBackend([])
    b.snapshot, b.buttons, b.ui = f['state']['snapshot'], f['state']['buttons_snapshot'], f['ui']['snapshot']
    generation = max(x['generation'] for x in (b.snapshot, b.buttons, b.ui))
    for x in (b.snapshot, b.buttons, b.ui):
        x['generation'] = generation
    close = next(x for x in b.buttons['buttons'] if x['path'].endswith('GuildMsgBoxUI(Clone)/frame/close'))
    if case == 'covered':
        close['raycast_top'] = False
    elif case == 'duplicate':
        b.buttons['buttons'].append(copy.deepcopy(close))
        b.buttons['button_count'] += 1
    elif case == 'foreign':
        b.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    elif case == 'absent':
        b.buttons['buttons'] = [x for x in b.buttons['buttons'] if 'GuildMsgBoxUI(Clone)' not in x['path']]
        b.buttons['button_count'] = len(b.buttons['buttons'])
    elif case == 'metadata':
        b.snapshot['future_optional_field'] = {'version': 2}
        b.buttons['buttons'].reverse()
        b.ui['texts'].reverse()
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None,
                            frame_observation_oracle=lambda: o)
    a.operation_siren_combat_committed = lambda: True
    s = AlasSemanticSession('replay', b.snapshot['driver_revision'])
    s.adapter = a
    s.refresh_frame = Mock()
    s._live_combat_visible = Mock(return_value=())
    s._live_combat_click = Mock(side_effect=SemanticGateClosed('unreviewed combat-table action'))
    return b, a, s


@pytest.mark.parametrize('case', ['ready', 'metadata'])
def test_actual_notice_during_committed_combat_uses_existing_global_owner(case):
    b, a, s = retained_notice(case)
    # Original InfoHandler asks for this pair before its cancel input.
    assert s.appear(NamedButton('GUILD_POPUP_CONFIRM'))
    assert s.appear(NamedButton('GUILD_POPUP_CANCEL'))
    receipt = s.click(NamedButton('GUILD_POPUP_CANCEL'))
    assert receipt.semantic_id == 'overlay/guild-message/close'
    assert len(b.taps) == 1
    s._live_combat_visible.assert_not_called()
    s._live_combat_click.assert_not_called()


@pytest.mark.parametrize('case', ['covered', 'duplicate', 'foreign'])
def test_notice_routing_preserves_exact_actionability_and_blockers(case):
    b, a, s = retained_notice(case)
    if case == 'duplicate':
        with pytest.raises(SemanticGateClosed):
            s.appear(NamedButton('GUILD_POPUP_CONFIRM'))
    else:
        assert not s.appear(NamedButton('GUILD_POPUP_CONFIRM'))
    with pytest.raises(SemanticGateClosed):
        s.click(NamedButton('GUILD_POPUP_CANCEL'))
    assert b.taps == []


def test_absent_global_notice_keeps_existing_combat_probe_and_action_contract():
    b, a, s = retained_notice('absent')
    assert not s.appear(NamedButton('GUILD_POPUP_CONFIRM'))
    s._live_combat_visible.assert_called_once()
    with pytest.raises(SemanticGateClosed, match='unreviewed combat-table action'):
        s.click(NamedButton('GUILD_POPUP_CANCEL'))
    s._live_combat_click.assert_called_once_with('GUILD_POPUP_CANCEL')
    assert b.taps == []


@pytest.mark.parametrize('campaign_lease', [False, True])
def test_original_map_event_guild_cancel_can_close_the_actual_notice(campaign_lease):
    b, a, s = retained_notice()
    a.campaign_combat_active = lambda: campaign_lease
    path = patched_alas_root() / 'module/handler/info_handler.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    method = next(x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef) and x.name == 'handle_guild_popup_cancel')
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=a, click=s.click),
        appear=lambda button, **kwargs: s.appear(button), _popup_offset=(20, 20))
    scope = dict(GUILD_POPUP_CANCEL=NamedButton('GUILD_POPUP_CANCEL'),
        GUILD_POPUP_CONFIRM=NamedButton('GUILD_POPUP_CONFIRM'))
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    assert scope['handle_guild_popup_cancel'](host)
    assert len(b.taps) == 1


def test_notice_does_not_grant_map_input_or_redirect_confirm_action():
    b, a, s = retained_notice()
    with pytest.raises(SemanticGateClosed):
        a.oracle.click('os/page/back')
    with pytest.raises(SemanticGateClosed, match='unreviewed combat-table action'):
        s.click(NamedButton('GUILD_POPUP_CONFIRM'))
    assert b.taps == []
