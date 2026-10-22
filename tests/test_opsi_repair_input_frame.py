"""Port repair consumes one coherent screenshot frame, including modal text."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle, semantic_runtime_fingerprint_sha256
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.semantic_support.observer_fixtures import FakeBackend


def host(fixture='opsi-port-repair-modal-r799.json'):
    raw = json.loads((Path(__file__).parent / 'fixtures' / fixture).read_text(encoding='utf-8'))['frame']['projections']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (
        copy.deepcopy(raw[key]) for key in ('snapshot', 'buttons', 'ui'))
    bridge = AdbObserverBridge('offline-repair-frame', backend.snapshot['package'])
    bridge.pid = backend.snapshot['pid']
    bridge.request = backend.request
    bridge.foreground_component = Mock(side_effect=backend.foreground_component)
    bridge.tap, bridge.swipe = backend.tap, backend.swipe
    bridge.package_pid = Mock(return_value=bridge.pid)
    revision = backend.snapshot['driver_revision']
    fingerprint = semantic_runtime_fingerprint_sha256(package=backend.snapshot['package'],
        component=backend.foreground, driver_revision=revision, required_primary_abi='x86_64')
    session = AlasSemanticSession(driver_revision=revision,
        runtime_handle=AdbRuntimeHandle(bridge, fingerprint_sha256=fingerprint),
        policy_grants={'operation_siren.port_repair': 1, 'shop.purchase': 0})
    session.refresh_frame()
    return backend, session


def test_cost_observation_uses_original_screenshot_without_live_sandwich():
    backend, session = host()
    session.open().oracle.operation_siren_port_repair_cost = Mock(
        side_effect=AssertionError('split live modal read'))
    assert session.operation_siren_port_repair_cost() == 1250
    assert not backend.taps


@pytest.mark.parametrize('confirm', [True, False])
def test_input_refreshes_frame_and_dispatches_once_without_split_live_reads(confirm):
    backend, session = host()
    live = session.open().oracle
    live.click_operation_siren_port_repair = Mock(
        side_effect=SemanticGateClosed('operation siren repair prompt snapshots are not coherent'))
    receipt = session.click_operation_siren_port_repair(confirm)
    assert receipt.semantic_id.endswith('repair-confirm' if confirm else 'repair-cancel')
    assert len(backend.taps) == 1
    assert session.action_ledger.remaining('operation_siren.port_repair') == (0 if confirm else 1)
    live.click_operation_siren_port_repair.assert_not_called()
    # A tap invalidates the refreshed lease; acquisition still advanced its ordinal.
    assert session._frame_clock._ordinal >= 2


@pytest.mark.parametrize('case', ['foreign', 'covered', 'duplicate', 'unknown-text', 'incoherent'])
def test_changed_modal_or_identity_refuses_before_input_without_burning_grant(case):
    backend, session = host()
    if case == 'foreign':
        backend.foreground = 'other.package/.Activity'
    elif case == 'covered':
        for button in backend.buttons['buttons']:
            if button['name'] == 'custom_button_1(Clone)':
                button['raycast_top'] = False
    elif case == 'duplicate':
        button = next(b for b in backend.buttons['buttons'] if b['name'] == 'custom_button_1(Clone)')
        backend.buttons['buttons'].append(copy.deepcopy(button))
        backend.buttons['button_count'] += 1
    elif case == 'unknown-text':
        for text in backend.ui['texts']:
            if text['path'].endswith('/msg_panel/content'):
                text['text'] = '购买商品需要1250'
    else:
        backend.ui['generation'] = backend.snapshot['generation'] + 100
    # Offline immutable fixtures cannot settle; skip only their real-time waits.
    from unittest.mock import patch
    with patch('alas_headless.adapter.frame.time.sleep', lambda _: None):
        with pytest.raises(SemanticGateClosed):
            session.click_operation_siren_port_repair(True)
    assert not backend.taps
    assert session.action_ledger.remaining('operation_siren.port_repair') == 1
