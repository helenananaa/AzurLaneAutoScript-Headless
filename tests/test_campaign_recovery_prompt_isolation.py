"""Task-local popup shapes and the original UI withdrawal decision."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
from alas_headless.adapter.semantic.session_dispatch import SessionDispatchPorts
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui, make_image, make_buttons,
)


@pytest.mark.parametrize('campaign, opsi', [(True, False), (False, True), (False, False)])
def test_account_wide_dock_modal_keeps_native_task_ownership(campaign, opsi):
    oracle = SimpleNamespace(campaign_dock_full_visible=Mock(return_value=True),
        click_campaign_dock_full_choice=Mock(return_value='receipt'))
    host = SimpleNamespace(_campaign_context=SimpleNamespace(resolved_stage_code='12-4', stage_code='12-4') if campaign else None,
        _build_context=None,
        _operation_siren_allows_passive_probe=lambda: opsi,
        _frame_or_live_observation_oracle=lambda: oracle, oracle=oracle, _package_gate=lambda: None)
    host.dock_full_recovery_owned = lambda: CampaignAdapterPorts.dock_full_recovery_owned(host)
    assert CampaignAdapterPorts.campaign_dock_full_visible(host) is (campaign or opsi)
    if campaign or opsi:
        assert CampaignAdapterPorts.click_campaign_dock_full_choice(host, 'enhance') == 'receipt'
        oracle.click_campaign_dock_full_choice.assert_called_once_with('12-4' if campaign else '', 'enhance')
    else:
        with pytest.raises(SemanticGateClosed, match='owned task'):
            CampaignAdapterPorts.click_campaign_dock_full_choice(host, 'enhance')
        oracle.click_campaign_dock_full_choice.assert_not_called()


def test_os_dock_probe_precedes_combat_reader():
    adapter = SimpleNamespace(dock_full_recovery_owned=lambda: True,
                             appear=Mock(return_value=True))
    host = SimpleNamespace(open=lambda: adapter)
    button = SimpleNamespace(name='RETIRE_APPEAR_3')
    assert SessionDispatchPorts.appear(host, button) is True
    adapter.appear.assert_called_once_with(button)


def test_dock_choices_do_not_enter_generic_two_button_confirmation():
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    confirm = root + 'button_container/custom_button_1(Clone)'
    backend = FakeBackend([make_button('custom_button_1(Clone)', confirm)])
    backend.ui = make_ui([
        make_text('船坞已满，请前往整理或扩展', root + 'msg_panel/content'),
        *[make_text(label, confirm + '/pic') for label in ('强化', '拓展', '整理')],
    ])
    oracle = make_oracle(backend)
    assert oracle.exists('research/progress/confirm') is False
    assert oracle._msgbox_prompt_parts(oracle.read_state()) is None
    assert backend.taps == []

    # Once the two-button shape is present, duplicate confirms still fail closed.
    backend.ui['texts'].append(make_text('取消', root + 'button_container/custom_button_2(Clone)/pic'))
    backend.ui['text_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        oracle._msgbox_prompt_parts(oracle.read_state())
    assert backend.taps == []


@pytest.mark.parametrize('duplicate, obscured', [(False, False), (True, False), (False, True)])
def test_dock_return_requires_unique_actionable_live_control(duplicate, obscured):
    path = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/'
    backend = FakeBackend([make_button('index_button', path + 'index_button')])
    image = make_image(path + 'back', 'icon_bg_front_1920')
    image['raycast_target'] = True
    image['raycast_top'] = False if obscured else None
    backend.ui = make_ui([], images=[image, dict(image)] if duplicate else [image])
    oracle = make_oracle(backend)
    oracle._enhancement_dock_records = lambda: (oracle.read_state(), oracle.read_ui_state())
    if duplicate or obscured:
        with pytest.raises(SemanticGateClosed):
            oracle.enhancement_dock_back_control()
    else:
        state, target = oracle.enhancement_dock_back_control()
        assert target.path == path + 'back'
        assert state.generation == 10
    assert backend.taps == []



@pytest.mark.parametrize('semantic, owned, expected', [(True, True, True), (True, False, False), (False, False, False)])
def test_original_ui_routes_only_semantic_owned_withdrawal(semantic, owned, expected):
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/ui/ui.py'
    if not source.exists():
        pytest.skip('materialized patched ALAS tree unavailable')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                and "self.handle_popup_confirm('WITHDRAW')" in ast.unparse(n.test))
    function = ast.FunctionDef(name='decision', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='self')],
        kwonlyargs=[], kw_defaults=[], defaults=[]), body=[node, ast.Return(ast.Constant(False))], decorator_list=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(source), 'exec'), namespace)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=object() if semantic else None),
                           handle_popup_confirm=Mock(return_value=owned))
    assert namespace['decision'](host) is expected
    if semantic:
        host.handle_popup_confirm.assert_called_once_with('WITHDRAW')
    else:
        host.handle_popup_confirm.assert_not_called()


@pytest.mark.parametrize('advance', [True, False])
def test_dock_exit_requires_new_generation_after_one_input(advance):
    path = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/'
    backend = FakeBackend([make_button('index_button', path + 'index_button')])
    image = make_image(path + 'back', 'icon_bg_front_1920')
    image['raycast_target'] = True
    backend.ui = make_ui([], images=[image])
    oracle = make_oracle(backend)
    oracle._enhancement_dock_records = lambda: (oracle.read_state(), oracle.read_ui_state())
    if advance:
        backend.on_tap = lambda *_: setattr(backend, 'buttons', make_buttons([], generation=11))
        assert oracle.click_enhancement_dock_back().semantic_id == 'enhancement/dock/exit'
    else:
        with pytest.raises(SemanticGateClosed, match='has not advanced'):
            oracle.click_enhancement_dock_back()
    assert len(backend.taps) == 1
