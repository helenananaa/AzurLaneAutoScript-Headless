"""Shared reward presence probes must yield to the exact native combat loader."""
import json
from pathlib import Path

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)

ROOT = 'UICamera/Canvas/UIMain/CombatLoadUI(Clone)/loading/loading_label'


@pytest.mark.parametrize('resource', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
def test_native_combat_loader_owns_only_passive_reward_absence(resource):
    backend = FakeBackend([])
    backend.ui = make_ui([make_text('NOW LOADING...', ROOT), make_text('33.82%', ROOT+'/percent')])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert adapter.appear(resource) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(resource)
    assert not backend.taps


@pytest.mark.parametrize('fault', ['unknown', 'missing', 'popup', 'stale'])
def test_unproven_loading_remains_closed(fault):
    backend = FakeBackend([])
    backend.ui = make_ui([make_text('NOW LOADING...', ROOT), make_text('33.82%', ROOT+'/percent')])
    if fault == 'unknown':
        backend.ui['texts'][0]['path'] = 'UnknownUI/loading'
    elif fault == 'missing':
        backend.ui['texts'].pop()
        backend.ui['text_count'] = 1
    elif fault == 'popup':
        backend.buttons['buttons'] = [make_button('confirm', 'UnknownModal/confirm')]
        backend.buttons['button_count'] = 1
    else:
        backend.ui['generation'] = 13
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.appear('GET_ITEMS_1')
    assert not backend.taps


def test_retained_abyssal_loader_without_buttons():
    retained = Path(__file__).resolve().parents[1] / (
        'artifacts/continuity-20261004/goal-r67-abyssal-native-continuation-r1.json')
    if not retained.exists():
        pytest.skip('retained abyssal loader unavailable')
    data = json.loads(retained.read_text(encoding='utf8'))
    assert not data['failed_state']['buttons']
    backend = FakeBackend([])
    backend.ui = make_ui(data['failed_ui']['snapshot']['texts'])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter.appear('GET_ITEMS_1') is False
    assert not backend.taps


@pytest.mark.parametrize('resource', ['GET_ADAPTABILITY', 'GET_MEOWFFICER_ITEMS_1', 'GET_ITEMS_1', 'OS_CHECK'])
def test_session_exact_loader_owns_native_passive_probes_and_loading_state(resource):
    backend = FakeBackend([])
    backend.ui = make_ui([make_text('NOW LOADING...', ROOT), make_text('44.28%', ROOT+'/percent')])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    session = AlasSemanticSession('replay', adapter.oracle.fingerprint.driver_revision)
    session.adapter = adapter
    assert session.appear(resource) is False
    assert session.combat_is_loading() is True
    assert not backend.taps


def test_session_loader_with_unknown_popup_remains_closed():
    backend = FakeBackend([make_button('confirm', 'UnknownModal/confirm')])
    backend.ui = make_ui([make_text('NOW LOADING...', ROOT), make_text('44.28%', ROOT+'/percent')])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    session = AlasSemanticSession('replay', adapter.oracle.fingerprint.driver_revision)
    session.adapter = adapter
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        session.appear('GET_ADAPTABILITY')
    assert not backend.taps


@pytest.mark.parametrize('result_accepted', [False, True])
def test_combat_owner_is_not_retired_by_the_departing_map_before_result_input(result_accepted):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._operation_siren_combat_active = True
    oracle.enabled_values['reward/award-info/close'] = False
    adapter.complete_operation_siren_combat_if_map_restored = Mock(return_value=False)
    session = AlasSemanticSession('replay', '506b76f698b5089aaa29c4e7908b48edb8532a44')
    session.adapter = adapter
    session._live_combat_visible = lambda: ()
    session._combat_last_result_receipt = SimpleNamespace(generation=9) if result_accepted else None
    assert session.appear('BATTLE_PREPARATION') is False
    assert adapter.complete_operation_siren_combat_if_map_restored.call_count == int(result_accepted)
    assert adapter._operation_siren_combat_active


def test_new_boss_clears_only_previous_result_correlation_after_owner_proof():
    from unittest.mock import Mock
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, _, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_operation_siren_boss_combat = Mock()
    session = AlasSemanticSession('replay', '506b76f698b5089aaa29c4e7908b48edb8532a44')
    session.adapter = adapter
    session._combat_last_result_receipt = object()
    session._combat_result_observation = ('BATTLE_STATUS_S', 100)
    session._combat_result_transition_until = 110
    session.begin_operation_siren_boss_combat()
    adapter.begin_operation_siren_boss_combat.assert_called_once()
    assert session._combat_last_result_receipt is None
    assert session._combat_result_observation is None
    assert session._combat_result_transition_until == 0
