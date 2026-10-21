"""Commission oil precheck shares the prepared immutable input frame."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle, semantic_runtime_fingerprint_sha256
from alas_headless.adapter.errors import StaleFrameError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.test_commission_oil_maxed_native_observation import retained


def host(drift=False):
    name = 'commission-reward-frame-r1146.json'
    data = json.loads((Path(__file__).parent / 'fixtures' / name).read_text(encoding='utf8'))
    raw = data['frame']['projections'] if 'frame' in data else data
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (
        copy.deepcopy(raw[key]) for key in ('snapshot', 'buttons', 'ui'))
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['compatible_extra_field'] = True
    bridge = AdbObserverBridge('offline-commission-frame', backend.snapshot['package'])
    bridge.pid = backend.snapshot['pid']
    bridge.request = backend.request
    bridge.foreground_component = Mock(side_effect=backend.foreground_component)
    bridge.package_pid = Mock(return_value=bridge.pid)
    bridge.tap, bridge.swipe = backend.tap, backend.swipe
    revision = backend.snapshot['driver_revision']
    fingerprint = semantic_runtime_fingerprint_sha256(package=backend.snapshot['package'],
        component=backend.foreground, driver_revision=revision, required_primary_abi='x86_64')
    session = AlasSemanticSession(driver_revision=revision,
        runtime_handle=AdbRuntimeHandle(bridge, fingerprint_sha256=fingerprint),
        policy_grants={'commission.reward': 2, 'shop.purchase': 0})
    session.refresh_frame()
    session.begin_commission()
    return backend, session, session.open()


@pytest.mark.parametrize('drift', [False, True])
def test_actual_reward_frame_does_not_reopen_split_live_oil_reads(drift):
    backend, session, adapter = host(drift=drift)
    adapter.oracle.commission_reward_oil_maxed = Mock(
        side_effect=SemanticGateClosed('commission oil rejection snapshots are incoherent'))
    receipt = session.click('REWARD_1')
    assert receipt.semantic_id == 'reward/commission/finish'
    assert len(backend.taps) == 1
    assert session.action_ledger.remaining('commission.reward') == 1
    adapter.oracle.commission_reward_oil_maxed.assert_not_called()


@pytest.mark.parametrize('drift', [False, True])
def test_real_oil_rejection_keeps_native_recovery_and_does_not_spend_grant(drift):
    # The historical oil tip is a sequential diagnostic pair, not a captured
    # immutable frame. Reuse its existing oracle-only replay without rewriting
    # generations or claiming it passed full session-frame acquisition.
    backend, oracle, adapter = retained(drift)
    prepared = copy.copy(oracle)
    adapter._frame_observation_oracle = lambda: prepared
    adapter.oracle.commission_reward_oil_maxed = Mock(side_effect=AssertionError('split live read'))
    assert adapter.appear('OIL_MAXED') is True
    before = adapter._action_ledger.remaining('commission.reward')
    with adapter.prepared_input_frame(lambda: prepared):
        with pytest.raises(AlasSemanticActionDeferred, match='client oil capacity'):
            adapter.click('REWARD_1')
    assert adapter._action_ledger.remaining('commission.reward') == before
    assert not backend.taps
    adapter.oracle.commission_reward_oil_maxed.assert_not_called()


@pytest.mark.parametrize('change', ['foreign', 'stale', 'incoherent', 'duplicate', 'covered'])
def test_changed_reward_surface_refuses_without_input_or_grant(change):
    backend, session, _ = host()
    if change == 'foreign':
        backend.foreground = 'other.package/.Activity'
    elif change == 'stale':
        session.refresh_frame = Mock(side_effect=StaleFrameError())
    elif change == 'incoherent':
        backend.ui['generation'] += 100
    else:
        owner = next(b for b in backend.buttons['buttons']
                     if b['path'].endswith('/event/frame/finish_btn'))
        if change == 'duplicate':
            backend.buttons['buttons'].append(copy.deepcopy(owner))
            backend.buttons['button_count'] += 1
        else:
            owner['raycast_top'] = False
    with patch('alas_headless.adapter.frame.time.sleep', lambda _: None):
        with pytest.raises(SemanticGateClosed):
            session.click('REWARD_1')
    assert session.action_ledger.remaining('commission.reward') == 2
    assert not backend.taps
