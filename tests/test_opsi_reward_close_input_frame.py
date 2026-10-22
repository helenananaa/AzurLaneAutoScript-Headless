"""Native reward polling shares one fresh proof and never retries a tap."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter.errors import StaleFrameError
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('case', ['ready', 'gone', 'covered', 'mounting', 'foreign_pid', 'expired', 'uncertain'])
def test_reward_close_uses_only_one_fresh_frame_and_sends_at_most_one_input(case):
    button = make_button('close', 'root/AwardInfoUI(Clone)/items/close', x=351, y=407)
    backend = FakeBackend([button])
    live = make_oracle(backend)
    for method in ('award_info_page_visible', 'enabled', 'click'):
        setattr(live, method, Mock(side_effect=AssertionError('extra live action proof')))
    fixed = [None]
    refreshed = []
    def guard():
        if case == 'expired':
            raise StaleFrameError()
    def refresh():
        refreshed.append(True)
        if case == 'gone':
            backend.buttons['buttons'] = []
        elif case == 'covered':
            backend.buttons['buttons'][0]['raycast_top'] = False
        elif case == 'mounting':
            backend.buttons['buttons'][0]['path'] = 'root/AwardInfoUI(Clone)/items/pending'
        elif case == 'foreign_pid':
            backend.snapshot['pid'] += 1
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
        responses = {
            'GET /v1/state\n': {'protocol_schema': backend.snapshot['protocol_schema'],
                               'status': 'ok', 'snapshot': copy.deepcopy(backend.snapshot),
                               'buttons': copy.deepcopy(backend.buttons)},
            'GET /v1/buttons\n': copy.deepcopy(backend.buttons),
            'GET /v1/ui\n': copy.deepcopy(backend.ui),
        }
        def tap(x, y):
            guard()
            backend.tap(x, y)
            if case == 'uncertain':
                raise RuntimeError('accepted tap acknowledgement lost')
        fixed[0] = _FrameBoundSemanticOracle(lambda q: responses[q], backend.foreground_component,
                    tap, live.fingerprint, frame_guard=guard)
    adapter = AlasSemanticAdapter(live, package_gate=lambda: None,
        input_frame_refresher=refresh, frame_observation_oracle=lambda: fixed[0])
    adapter._operation_siren_combat_active = True
    session = AlasSemanticSession('replay', live.fingerprint.driver_revision)
    session.adapter = adapter
    session.refresh_frame = refresh
    if case in ('foreign_pid', 'expired', 'uncertain'):
        with pytest.raises((SemanticGateClosed, StaleFrameError, RuntimeError)):
            session.try_click_operation_siren_reward_close()
    else:
        receipt = session.try_click_operation_siren_reward_close()
        if case == 'ready':
            assert receipt.semantic_id == 'os/combat/reward/close'
            assert receipt.point.x == 351 and receipt.point.y == 407
        else:
            assert receipt is None
            assert adapter._operation_siren_reward_close_receipt is None
    assert refreshed == [True]
    assert len(backend.taps) == (1 if case in ('ready', 'uncertain') else 0)


def test_duplicate_actionable_close_and_absent_owner_still_fail_closed():
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._operation_siren_combat_active = True
    oracle.award_info_page_visible = Mock(return_value=True)
    oracle.enabled_values = {'reward/award-info/close': True, 'reward/award-info1/close': True}
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        adapter.try_click_operation_siren_reward_close()
    adapter._operation_siren_combat_active = False
    with pytest.raises(SemanticGateClosed, match='owner'):
        adapter.try_click_operation_siren_reward_close()
    assert not oracle.click_calls


def test_actual_r112_failed_frame_passively_returns_without_reward_input():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-r112-abyssal-reward-failure-r1.json'
    if not path.exists():
        pytest.skip('local frozen failure unavailable; synthetic contract cases remain active')
    row = json.loads(path.read_text(encoding='utf8'))['native_row']
    projections = row['failed_presence']['retained_screenshot_before_diagnostic_reads']['frame']['projections']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (projections[k] for k in ('snapshot', 'buttons', 'ui'))
    fingerprint = OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
        driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid'])
    oracle = _FrameBoundSemanticOracle(backend.request, backend.foreground_component, backend.tap,
                                     fingerprint, frame_guard=lambda: None)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._operation_siren_combat_active = True
    assert oracle.operation_siren_local_map_visible()
    assert adapter.try_click_operation_siren_reward_close() is None
    assert adapter._operation_siren_reward_close_receipt is None
    assert not backend.taps


def test_actual_r113_item_description_keeps_covered_award_closed_and_routes_its_owner():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-r113-retained-award-item-info-failure-r1.json'
    if not path.exists():
        pytest.skip('local retained item-info unavailable; synthetic cases remain active')
    row = json.loads(path.read_text(encoding='utf8'))['native_row']
    # Later diagnostic projections retain their exact raw generations; these
    # are not mislabeled as the action-time frozen frame.
    observed = row['failure_observation']
    backend = FakeBackend([])
    backend.snapshot = observed['state']['snapshot']
    backend.buttons = observed['state']['buttons_snapshot']
    backend.ui = observed['ui']['snapshot']
    fingerprint = OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
        driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid'])
    fixed = _FrameBoundSemanticOracle(backend.request, backend.foreground_component, backend.tap,
                                     fingerprint, frame_guard=lambda: None)
    assert fixed.reward_item_info_visible()
    assert not fixed.enabled('reward/award-info/close')
    live = Mock()
    item_receipt = object()
    live.click.return_value = item_receipt
    adapter = AlasSemanticAdapter(live, package_gate=lambda: None)
    adapter._operation_siren_combat_active = True
    adapter._fresh_input_oracle = lambda: fixed
    assert adapter.try_click_operation_siren_reward_close() is item_receipt
    live.click.assert_called_once_with('reward/item-info/close')
    assert adapter._operation_siren_reward_close_receipt is None
    assert not backend.taps


@pytest.mark.parametrize('case', ['ready', 'drift', 'covered', 'foreign-blocker', 'pid', 'unrelated'])
def test_complete_item_description_above_map_retains_original_input_guards(case):
    from tests.test_commission_item_info_close import retained
    backend, oracle = retained(case)
    backend.buttons['buttons'].append(make_button('res',
        'root/top/adapt/top_stage/resources/WorldResPanel(Clone)/res'))
    backend.buttons['button_count'] += 1
    if case in ('ready', 'drift'):
        receipt = oracle.click('reward/item-info/close')
        assert receipt.semantic_id == 'reward/item-info/close'
        assert backend.taps == [(894, 196)]
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.click('reward/item-info/close')
        assert not backend.taps
