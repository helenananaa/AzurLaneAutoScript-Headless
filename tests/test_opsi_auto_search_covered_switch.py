"""A newly mounted reward must not become a fresh map-enable attempt."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_ui
from tests.test_opsi_header_projection_retry import scene
from tests.test_opsi_original_reward_before_map_switch import CampaignEnd, method


@pytest.mark.parametrize('overlay', [
    'OverlayCamera/Overlay/UIMain/WorldAutoFightRewardUI(Clone)/Window/Fixed/ButtonExit',
    'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/cancel_button',
    'OverlayCamera/Overlay/UIOverlay/Loading(Clone)',
])
def test_covered_switch_is_not_actionable_or_an_empty_completion(overlay):
    backend, oracle = scene()
    backend.buttons['buttons'].append(make_button('overlay', overlay))
    backend.buttons['button_count'] += 1
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._operation_siren_auto_search_active = True

    with pytest.raises(SemanticGateClosed, match='absent or inconsistent'):
        adapter.operation_siren_auto_search_state()

    assert adapter._operation_siren_auto_search_active
    assert not adapter.operation_siren_auto_search_completed_empty()
    assert not backend.taps


@pytest.mark.parametrize('value', ['off', 'on'])
def test_uncovered_switch_still_accepts_harmless_projection_drift(value):
    backend, oracle = scene()
    switch = backend.buttons['buttons'][1]
    switch['name'] = value
    switch['path'] = switch['path'].removesuffix('off') + value
    backend.buttons['buttons'].reverse()
    backend.ui['texts'].reverse()
    backend.ui['additional_metadata'] = {'future_field': True}
    assert oracle.operation_siren_auto_search_state() == value
    assert not backend.taps


def test_reward_arriving_after_native_probe_returns_to_original_reward_branch(monkeypatch):
    import alas_headless

    backend, oracle = scene()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    monkeypatch.setattr(alas_headless, 'current_semantic_session', lambda: adapter)

    def reward_mounted_after_probe():
        backend.buttons['buttons'].append(make_button('ButtonExit',
            'OverlayCamera/Overlay/UIMain/WorldAutoFightRewardUI(Clone)/Window/Fixed/ButtonExit'))
        backend.buttons['button_count'] += 1
        return True  # The retained local-map shell is still mounted underneath.

    semantic = SimpleNamespace(operation_siren_map_visible=reward_mounted_after_probe)
    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=semantic, screenshot_interval_set=Mock(),
            click=Mock(side_effect=AssertionError('covered switch must not be clicked'))),
        appear=Mock(return_value=False), match_template_color=Mock(return_value=False),
        os_auto_search_quit=Mock(return_value=True))
    native_method = method()
    native_method.__globals__['Timer'] = Mock()
    assert native_method(host) is False
    host.device.click.assert_not_called()
    host.os_auto_search_quit.assert_not_called()

    # ALAS' next screenshot observes the reward and its existing branch owns it.
    host.appear = lambda button, **kwargs: button == 'AUTO_SEARCH_REWARD'
    with pytest.raises(CampaignEnd):
        native_method(host)
    host.os_auto_search_quit.assert_called_once_with(drop=None)
    assert not backend.taps


def test_retained_cl1_reward_replay_rejects_covered_off_without_input():
    source = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261024/native-r6.json'
    if not source.exists():
        pytest.skip('private CL1 failure receipt unavailable')
    task = json.loads(source.read_text(encoding='utf-8'))['tasks'][2]
    projections = task['failed_click']['retained_screenshot_before_error_handler']['frame']['projections']
    backend = FakeBackend(projections['buttons']['buttons'])
    ui = projections['ui']
    # Replay the retained structure using the fixture's common offline identity.
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    oracle = make_oracle(backend)
    assert oracle.enabled('os/auto-search/reward/close')
    with pytest.raises(SemanticGateClosed, match='absent or inconsistent'):
        oracle.operation_siren_auto_search_state()
    assert not backend.taps
