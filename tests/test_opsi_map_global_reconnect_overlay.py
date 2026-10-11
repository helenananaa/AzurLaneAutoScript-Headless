"""Known typed reconnect fixture above a retained real OpSi map underlay.

This is an offline reconstructed combination, not a live network-failure claim.
"""
import copy
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_text, make_ui, make_oracle


def reconnect_over_map(case='map'):
    popup = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    buttons = [make_button('custom_button_2(Clone)', popup + 'button_container/custom_button_2(Clone)'),
        make_button('custom_button_1(Clone)', popup + 'button_container/custom_button_1(Clone)')]
    texts = [make_text('服务器连接失败，是否重新连接？\n[NetworkDown]', popup + 'msg_panel/content'),
        make_text('取 消', popup + 'button_container/custom_button_2(Clone)/pic'),
        make_text('确 定', popup + 'button_container/custom_button_1(Clone)/pic')]
    if case == 'baseline':
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts)
        oracle = make_oracle(backend)
    else:
        path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-r31-story-reward-close-failed-frame-r1.json'
        if not path.exists():
            pytest.skip('retained r31 OpSi underlay unavailable; baseline reconnect cases still run')
        frame = json.loads(path.read_text(encoding='utf-8'))['failure_observation']
        backend = FakeBackend([])
        backend.snapshot = frame['state']['snapshot']
        backend.buttons = frame['state']['buttons_snapshot']
        backend.ui = frame['ui']['snapshot']
        generation = max(x['generation'] for x in (backend.snapshot, backend.buttons, backend.ui))
        for snapshot in (backend.snapshot, backend.buttons, backend.ui):
            snapshot['generation'] = generation
        if case == 'purchase':
            texts[0]['text'] = '是否购买资源？'
        elif case == 'unknown_error':
            texts[0]['text'] = '服务器连接失败，是否重新连接？\n[UnknownNetworkError]'
        elif case == 'covered':
            buttons[1]['raycast_top'] = False
        elif case == 'duplicate':
            buttons.append(copy.deepcopy(buttons[1]))
        backend.buttons['buttons'] += buttons
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
        backend.ui['texts'] += texts
        backend.ui['text_count'] = len(backend.ui['texts'])
        if case == 'metadata':
            backend.snapshot['future_optional_field'] = {'version': 2}
            backend.buttons['buttons'].reverse()
            backend.ui['texts'].reverse()
        oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
            OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
                driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    adapter = AlasSemanticAdapter(oracle, package_gate=Mock())
    adapter._frame_observation_oracle = lambda: oracle
    adapter.operation_siren_combat_committed = lambda: True
    session = AlasSemanticSession('replay', oracle.fingerprint.driver_revision)
    session.adapter = adapter
    session.refresh_frame = Mock()
    session._live_combat_visible = Mock(return_value=())
    session._live_combat_click = Mock(side_effect=SemanticGateClosed('unrelated combat-table input'))
    return backend, oracle, adapter, session


@pytest.mark.parametrize('case', ['baseline', 'map', 'metadata'])
@pytest.mark.parametrize('name', ['POPUP_CONFIRM', 'POPUP_CANCEL'])
def test_reviewed_global_reconnect_keeps_native_popup_pair_and_input_available(case, name):
    backend, oracle, adapter, session = reconnect_over_map(case)
    assert session.appear(NamedButton('POPUP_CANCEL'))
    assert session.appear(NamedButton('POPUP_CONFIRM'))
    receipt = session.click(NamedButton(name))
    assert receipt.semantic_id == ('overlay/network-reconnect/confirm' if name == 'POPUP_CONFIRM'
                                   else 'overlay/network-reconnect/cancel')
    assert len(backend.taps) == 1
    session._live_combat_visible.assert_not_called()
    session._live_combat_click.assert_not_called()


@pytest.mark.parametrize('case', ['purchase', 'unknown_error', 'covered', 'duplicate'])
def test_overlay_permission_does_not_bypass_prompt_identity_or_target(case):
    backend, oracle, adapter, session = reconnect_over_map(case)
    if case == 'duplicate':
        with pytest.raises(SemanticGateClosed):
            oracle.enabled('overlay/network-reconnect/confirm')
    else:
        assert not oracle.enabled('overlay/network-reconnect/confirm')
    with pytest.raises(SemanticGateClosed):
        oracle.click('overlay/network-reconnect/confirm')
    assert backend.taps == []


def test_reconnect_overlay_does_not_allow_a_covered_map_input():
    backend, oracle, adapter, session = reconnect_over_map()
    assert not oracle.enabled('os/map/order')
    with pytest.raises(SemanticGateClosed):
        oracle.click('os/map/order')
    assert backend.taps == []


@pytest.mark.parametrize('change', ['purchase', 'covered', 'pid', 'unmounted'])
def test_refresh_cannot_redirect_an_owned_reconnect_to_another_popup_or_combat_input(change):
    backend, oracle, adapter, session = reconnect_over_map('baseline')
    def refresh():
        if change == 'purchase':
            next(t for t in backend.ui['texts'] if t['path'].endswith('/msg_panel/content'))['text'] = '是否购买资源？'
        elif change == 'covered':
            next(b for b in backend.buttons['buttons'] if b['name'] == 'custom_button_1(Clone)')['raycast_top'] = False
        elif change == 'pid':
            backend.snapshot['pid'] += 1
        else:
            backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if '/Msgbox(Clone)/' not in b['path']]
            backend.buttons['button_count'] = len(backend.buttons['buttons'])
    session.refresh_frame = Mock(side_effect=refresh)
    with pytest.raises(SemanticGateClosed):
        session.click(NamedButton('POPUP_CONFIRM'))
    assert backend.taps == []
    assert adapter._network_reconnect_transition_until == 0
    session._live_combat_click.assert_not_called()


def test_original_info_handler_annotated_shared_asset_reaches_the_exact_global_owner():
    backend, oracle, adapter, session = reconnect_over_map('baseline')
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/alas-runtime/module/handler/info_handler.py'
    if not path.exists():
        pytest.skip('installed native InfoHandler unavailable; direct session cases still run')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'InfoHandler')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'handle_popup_confirm')
    confirm, cancel = NamedButton('POPUP_CONFIRM'), NamedButton('POPUP_CANCEL')
    scope = dict(POPUP_CONFIRM=confirm, POPUP_CANCEL=cancel)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    native = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session, click=session.click),
        _popup_offset=(3, 30), appear=lambda button, **kwargs: session.appear(button))
    with patch.dict('sys.modules', {'module.handler.assets': SimpleNamespace(POPUP_CONFIRM=confirm, POPUP_CANCEL=cancel)}):
        assert scope['handle_popup_confirm'](native)
    assert confirm.name == 'POPUP_CONFIRM'
    assert len(backend.taps) == 1
    session._live_combat_click.assert_not_called()


def test_absent_network_overlay_preserves_the_existing_committed_combat_route():
    backend, oracle, adapter, session = reconnect_over_map('baseline')
    backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if '/Msgbox(Clone)/' not in b['path']]
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    prior_route = SimpleNamespace(semantic_id='combat-owned-confirm')
    session._live_combat_click = Mock(return_value=prior_route)
    assert session.click(NamedButton('POPUP_CONFIRM')) is prior_route
    session._live_combat_click.assert_called_once_with('POPUP_CONFIRM')
    assert backend.taps == []


def test_reconnect_reuses_the_existing_campaign_and_global_passive_transition():
    backend, oracle, adapter, session = reconnect_over_map('baseline')
    adapter._campaign_context = SimpleNamespace(passive_transition_until=0)
    session.click(NamedButton('POPUP_CONFIRM'))
    assert adapter._network_reconnect_transition_until > 0
    assert adapter._campaign_context.passive_transition_until > 0
    assert len(backend.taps) == 1
