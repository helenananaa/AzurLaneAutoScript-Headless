import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend, make_button


def retained_map(case='ready'):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-r31-story-reward-close-failed-frame-r1.json'
    if not path.exists():
        pytest.skip('retained r31 story-reward map unavailable; direct close-owner cases still run')
    evidence = json.loads(path.read_text(encoding='utf-8'))
    frame = evidence['failure_observation']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons_snapshot']
    backend.ui = frame['ui']['snapshot']
    generation = max(x['generation'] for x in (backend.snapshot, backend.buttons, backend.ui))
    for snapshot in (backend.snapshot, backend.buttons, backend.ui):
        snapshot['generation'] = generation
    if case == 'blocked':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'not_map':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'fleet_bar']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif case == 'metadata':
        backend.snapshot['future_optional_field'] = {'version': 2}
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    adapter = AlasSemanticAdapter(oracle, package_gate=Mock())
    receipt = SimpleNamespace(**evidence['accepted_close'])
    if case == 'old_generation':
        receipt.generation = generation
    adapter._operation_siren_reward_close_receipt = None if case == 'no_receipt' else receipt
    session = AlasSemanticSession('replay', backend.snapshot['driver_revision'])
    session.adapter = adapter
    adapter._frame_observation_oracle = lambda: oracle
    session.refresh_frame = Mock()
    if case == 'foreign_pid':
        backend.snapshot['pid'] += 1
    return backend, adapter, session, receipt


@pytest.mark.parametrize('case', ['ready', 'metadata'])
def test_native_duplicate_safe_area_reuses_only_accepted_close_without_input(case):
    backend, adapter, session, receipt = retained_map(case)
    assert session.click(NamedButton('CLICK_SAFE_AREA')) is receipt
    assert adapter._operation_siren_reward_close_receipt is None
    adapter._package_gate.assert_called()
    with pytest.raises(SemanticGateClosed):
        session.click(NamedButton('CLICK_SAFE_AREA'))
    assert backend.taps == []


@pytest.mark.parametrize('case', ['no_receipt', 'old_generation', 'blocked', 'not_map', 'foreign_pid'])
def test_missing_or_unproven_reward_return_keeps_input_closed(case):
    backend, adapter, session, receipt = retained_map(case)
    with pytest.raises(SemanticGateClosed):
        session.click(NamedButton('CLICK_SAFE_AREA'))
    assert backend.taps == []


@pytest.mark.parametrize('owner', ['map', 'assist', 'beacon'])
def test_exact_close_records_receipt_for_its_existing_owner(owner):
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._operation_siren_combat_active = True
    if owner == 'assist':
        adapter.begin_meta_assist()
    elif owner == 'beacon':
        adapter.begin_meta_beacon()
    oracle.award_info_page_visible = Mock(return_value=True)
    oracle.enabled_values = {'reward/award-info/close': True, 'reward/award-info1/close': False}
    receipt = adapter.click_operation_siren_reward_close()
    assert adapter._operation_siren_reward_close_receipt is (receipt if owner == 'map' else None)
    assert adapter._meta_reward_close_receipt is (None if owner == 'map' else receipt)
    assert oracle.click_calls == ['reward/award-info/close']


def test_present_reward_is_never_acknowledged_as_a_completed_return():
    backend, adapter, session, receipt = retained_map()
    backend.buttons['buttons'].append(make_button('close',
        'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close'))
    backend.buttons['button_count'] += 1
    assert adapter._operation_siren_reward_return_completed(adapter.oracle) is None
    assert adapter._operation_siren_reward_close_receipt is receipt
    assert backend.taps == []
