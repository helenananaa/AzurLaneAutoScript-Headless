"""An accepted sidebar entry must stay in native navigation during mounting."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt, Bounds, OracleFingerprint, Point, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button


def pending_entry(drift=False):
    data = json.loads((Path(__file__).parent / 'fixtures/reward-sidebar-pending-r619.json')
                      .read_text(encoding='utf-8'))
    backend = FakeBackend([])
    backend.snapshot = deepcopy(data['source']['snapshot'])
    backend.buttons = deepcopy(data['source']['buttons'])
    backend.ui = deepcopy(data['source']['ui'])
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['optional_metadata'] = {'additive': True}
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'],
            expected_pid=backend.snapshot['pid'], max_age_ms=10000))
    raw = data['prior_receipt']
    receipt = ActionReceipt(**(raw | {'point': Point(**raw['point']),
                                    'bounds': Bounds(**raw['bounds'])}))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_mission_reward(daily=True, weekly=True)
    adapter._mission_context.summary_entry_receipt = receipt
    adapter._main_more_entry_receipt = receipt
    adapter._commission_navigation_handoff = receipt, oracle.input_dispatch_count, 12.0
    return backend, oracle, adapter, receipt, data


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('alias', ['MAIN_GOTO_REWARD', 'MAIN_GOTO_REWARD_WHITE'])
def test_actual_pending_main_returns_accepted_receipt_to_native_loop(alias, drift):
    backend, oracle, adapter, prior, data = pending_entry(drift)
    clock = [0.0]
    with patch('alas_headless.adapter.semantic.dispatch.time.monotonic', lambda: clock[0]), \
         patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep',
               lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
        assert adapter.click(alias) is prior
    assert clock[0] == 0.0
    assert not backend.taps
    assert not oracle.reward_sidebar_entry_ready(oracle.read_state())
    # Native polling can then observe the later retained destination. This is
    # not a claim that the entry was already complete in source generation75314.
    backend.snapshot = deepcopy(data['after_error']['snapshot'])
    backend.buttons = deepcopy(data['after_error']['buttons_snapshot'])
    assert oracle.reward_sidebar_entry_ready(oracle.read_state())


@pytest.mark.parametrize('damage', ['stale', 'foreign-foreground', 'foreign-modal'])
def test_pending_sidebar_handoff_keeps_current_state_refusals(damage):
    backend, _, adapter, _, _ = pending_entry()
    if damage == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif damage == 'foreign-foreground':
        backend.foreground = 'other.package/.Main'
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with patch('alas_headless.adapter.semantic.dispatch.time.monotonic', lambda: 0.0):
        with pytest.raises(SemanticGateClosed):
            adapter.click('MAIN_GOTO_REWARD_WHITE')
    assert not backend.taps
